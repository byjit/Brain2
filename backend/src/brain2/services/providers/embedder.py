"""Embedder provider interface + implementations (spec §7.1 step 8, §11 vector half).

The worker and search depend on the ``Embedder`` abstraction (dependency inversion),
never on Gemini directly, so the vector half of retrieval is unit-testable offline with
``FakeEmbedder``. The real ``GeminiEmbedder`` uses the google-genai SDK ``embed_content``
with the configured embedding model at 768-dim.

``FakeEmbedder`` is deterministic AND similarity-meaningful: it builds a hashed
bag-of-words over the text's tokens and unit-normalizes it, so token overlap raises the
cosine similarity. That makes KNN ordering and RRF assertions test real ranking, not just
plumbing.
"""

import math
import re
from typing import Protocol, runtime_checkable

# 768-dim for both note and tag-description embeddings (spec §9.2 vec0 FLOAT[768]).
EMBEDDING_DIM = 768

# Upper bound on characters sent to the embedder. The embedding API has an input token
# budget, so an oversized text (tens of KB) would fail to embed on every attempt and turn
# an otherwise-valid entry into a permanent failure. Callers embed a bounded prefix instead
# so the entry still gets a representative vector and stays activatable; ~8k chars stays
# comfortably under the model's token budget while capturing the text's gist. Single source
# of truth shared by the worker, the tagging basis, and repair (DRY).
EMBED_INPUT_MAX_CHARS = 8_000

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@runtime_checkable
class Embedder(Protocol):
    """Turns text into a fixed-dimension embedding vector."""

    @property
    def dimension(self) -> int:
        """The dimensionality of the produced vectors."""
        ...

    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for ``text``."""
        ...


class FakeEmbedder:
    """Deterministic, similarity-meaningful offline embedder for tests.

    Each token is hashed to a bucket; bucket weights form a bag-of-words vector that is
    then unit-normalized. Shared tokens land in shared buckets, so texts that overlap
    lexically (or share fake-embedding tokens) score a higher cosine similarity than
    unrelated texts — enough for KNN/RRF ordering to be genuinely asserted offline.
    """

    def __init__(self, *, dimension: int = EMBEDDING_DIM) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        for token in _TOKEN_RE.findall(text.lower()):
            # Stable per-token bucket via a deterministic hash (md5, not Python's salted
            # hash()), so the same token maps to the same dimension across processes.
            bucket = _stable_bucket(token, self._dimension)
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            # No tokens: a well-defined zero vector rather than a divide-by-zero NaN.
            return vec
        return [v / norm for v in vec]


def _stable_bucket(token: str, dimension: int) -> int:
    """Map a token to a stable bucket in ``[0, dimension)`` independent of PYTHONHASHSEED."""
    import hashlib

    digest = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % dimension


def l2_normalize(vec: list[float]) -> list[float]:
    """Return ``vec`` scaled to unit length (L2 norm 1), or unchanged if it is the zero
    vector.

    gemini-embedding-2 only returns unit-normalized vectors at its native dims;
    at a reduced ``output_dimensionality`` (768) the result is NOT re-normalized, so its
    magnitude varies. Re-normalizing makes the entries_vec L2 KNN monotonic with cosine,
    so retrieval ranks by semantic direction rather than magnitude (spec §11). Guards the
    zero vector so an all-zero embedding never produces NaN from a divide-by-zero.
    """
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


# Request timeout (ms) for a single embedding call — fail fast rather than wedge the
# shared worker drain thread for all users (mirrors the summarizer; spec §7.4).
_REQUEST_TIMEOUT_MS = 30_000


class GeminiEmbedder:
    """Real embedder backed by the google-genai SDK ``embed_content``."""

    def __init__(self, api_key: str, model: str, *, dimension: int = EMBEDDING_DIM) -> None:
        # Import lazily so the SDK is only required when the real provider is used.
        from google import genai
        from google.genai import types

        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
        )
        self._types = types
        self._model = model
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        response = self._client.models.embed_content(
            model=self._model,
            contents=text,
            config=self._types.EmbedContentConfig(output_dimensionality=self._dimension),
        )
        values = list(response.embeddings[0].values)
        if len(values) != self._dimension:
            raise ValueError(
                f"Embedding model returned {len(values)} dims, expected {self._dimension}"
            )
        # Reduced-dimension Gemini vectors are not unit-normalized; re-normalize so the
        # vec0 L2 KNN ranks by cosine direction, not magnitude (spec §11). See l2_normalize.
        return l2_normalize(values)
