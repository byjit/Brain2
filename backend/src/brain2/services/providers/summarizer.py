"""Summarizer provider interface + implementations (spec §7.1 step, §7.3).

The async worker depends on the ``Summarizer`` abstraction (dependency inversion),
never on Gemini directly, so the pipeline is unit-testable offline with ``FakeSummarizer``.
The real ``GeminiSummarizer`` uses the google-genai SDK + Gemini Flash.
"""

from typing import Protocol, runtime_checkable

# Upper bound on source characters fed to the note-writer (this summarizer and the M5
# tagger's combined call). The note is a routing card, not a faithful compression of the
# source (spec §7.3): an agent reads the note to decide whether to open the URL / re-fetch
# the body, so a generous PREFIX is sufficient — an article's thesis, scope, and key
# specifics live up front. This is deliberately larger than EMBED_INPUT_MAX_CHARS (the
# embedder's hard ~2k-token budget): the LLM can read far more than the embedder, and 8k
# would cut a long article short and starve the summary. Bounding it still caps LLM
# cost/latency and decouples note quality from article length. The full source is never
# lost — re-fetchable for `page`, FTS-indexed for clip/conversation/note (spec §11).
SUMMARY_INPUT_MAX_CHARS = 16_000

# The note is the vectorized field (spec §5) and a routing card (spec §7.3): it must let a
# reader judge, from the note alone, whether to open the source. So we ask for what the
# source is ABOUT and what a reader would FIND in it — not a verbatim recap.
_SUMMARY_INSTRUCTION = (
    "Write a neutral 2-3 sentence note describing what this source is about and what a "
    "reader would find in it, so someone can judge from the note alone whether to open the "
    "source for the full content. Output only the note, no preamble.\n\nContent:\n"
)


@runtime_checkable
class Summarizer(Protocol):
    """Turns source text into a concise 2-3 sentence note."""

    def summarize(self, text: str) -> str:
        """Return a 2-3 sentence note for ``text``."""
        ...


class FakeSummarizer:
    """Deterministic offline summarizer for tests.

    Records every call so tests can assert the worker did (or did not) summarize, and
    can be primed to raise to exercise the worker's retry/failure path.
    """

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.calls: list[str] = []

    def summarize(self, text: str) -> str:
        self.calls.append(text)
        if self._raises is not None:
            raise self._raises
        # Deterministic, content-derived so assertions are stable.
        head = " ".join(text.split()[:8])
        return f"Summary: {head}"


# Request timeout (ms) for a single summarization call. A stalled call must fail fast
# rather than wedge the shared worker drain thread for all users (spec §7.4).
_REQUEST_TIMEOUT_MS = 30_000


class GeminiSummarizer:
    """Real summarizer backed by the google-genai SDK + Gemini Flash."""

    def __init__(self, api_key: str, model: str) -> None:
        # Import lazily so the SDK is only required when the real provider is used.
        from google import genai
        from google.genai import types

        # An explicit request timeout bounds every call so a network stall fails fast
        # and routes through the worker's retry/fail path.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
        )
        self._model = model

    def summarize(self, text: str) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=_SUMMARY_INSTRUCTION + text,
        )
        return (response.text or "").strip()
