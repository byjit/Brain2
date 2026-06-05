"""Canonicalize-on-write for tags (spec §7.2 mechanism 3).

Two responsibilities, kept pure and DB-free where possible so they unit-test offline:

1. ``normalize_tag`` — CONSERVATIVE surface normalization: lowercase, trim, strip
   surrounding punctuation, and collapse plurals ONLY via a safe rule guarded by a
   tech-term stoplist. We never blind-stem, or ``redis`` becomes ``redi`` and
   ``kubernetes`` becomes ``kubernete`` (spec §7.2). When in doubt, leave the token alone
   and let embedding-based snapping catch the duplicate.

2. ``canonicalize_candidates`` — embed each candidate's concept DESCRIPTION and snap it to
   the nearest existing tag when cosine >= the threshold (default 0.90); otherwise mint a
   new tag with its stable description and persist that description's embedding into
   ``tags_vec``. The LLM never writes the tag table directly — only this does. Reuse is
   biased over invention by the high threshold (spec §7.2 mechanism 4).
"""

import re
import sqlite3
from dataclasses import dataclass

from brain2.services.providers.embedder import Embedder
from brain2.services.tags_vector import index_tag_vector, nearest_tag

# Surrounding punctuation to strip (anything that is not a word char, space, +, # or .).
# We strip only the EDGES so intra-token punctuation (c++, asp.net, c#) survives.
_EDGE_PUNCT = re.compile(r"^[^\w]+|[^\w]+$")

# Tokens that look plural but must NEVER lose a trailing 's' (spec §7.2). Lowercased.
_PLURAL_STOPLIST = frozenset(
    {
        "redis", "kubernetes", "kafka", "nginx", "css", "ios", "js", "aws", "https",
        "rss", "cors", "dns", "tls", "sass", "less", "graphics", "physics", "news",
        "series", "analysis", "devops", "ops", "os", "https", "rust", "elasticsearch",
    }
)

# Below this length a trailing 's' is too likely to be part of the word to strip safely.
_MIN_STEM_LEN = 4


def normalize_tag(raw: str) -> str:
    """Conservatively normalize a tag surface form (spec §7.2).

    Lowercase, trim, strip surrounding punctuation, and collapse a SAFE plural. Returns
    an empty string for blank input so the caller can drop it.
    """
    token = _EDGE_PUNCT.sub("", raw.strip().lower())
    if not token:
        return ""
    return _depluralize(token)


def _depluralize(token: str) -> str:
    """Collapse a safe plural only; never blind-stem (spec §7.2 'redis' guard)."""
    if token in _PLURAL_STOPLIST or " " in token:
        # A stoplisted term or a multi-word phrase: leave it alone (only the phrase's last
        # word could be plural, and phrase tags are rare enough to not risk mangling).
        return token
    # 'libraries' -> 'library' (consonant + 'ies' -> 'y').
    if token.endswith("ies") and len(token) > 4 and token[-4] not in "aeiou":
        return token[:-3] + "y"
    # Plain '...s' -> '...': only when long enough and not a double 's' (e.g. 'css').
    if (
        token.endswith("s")
        and not token.endswith("ss")
        and not token.endswith("us")  # 'status', 'bonus'
        and len(token) > _MIN_STEM_LEN
    ):
        return token[:-1]
    return token


@dataclass(frozen=True)
class TagCandidate:
    """A proposed tag: its (already-normalized) name and a concept-level description.

    For a candidate that matches an existing tag the LLM need not supply a description;
    snapping uses the existing tag's stored embedding, so ``description`` may be empty.
    """

    name: str
    description: str


def canonicalize_candidates(
    conn: sqlite3.Connection,
    candidates: list[TagCandidate],
    *,
    embedder: Embedder,
    threshold: float,
    max_tags: int,
) -> list[str]:
    """Resolve candidates to final tag names, creating tags as needed. Caller commits.

    For each candidate (in order, biased to reuse): normalize, then either snap to the
    nearest existing tag at cosine >= ``threshold`` or mint a new tag — embedding its
    description into ``tags_vec`` and inserting a ``tags`` row with that stable
    description (generated ONCE at creation, never regenerated on reuse, spec §9.3).
    The result is de-duplicated and capped to ``max_tags``.
    """
    final: list[str] = []
    for cand in candidates:
        if len(final) >= max_tags:
            break
        name = normalize_tag(cand.name)
        if not name:
            continue

        resolved = _resolve_one(conn, name, cand.description, embedder, threshold)
        if resolved and resolved not in final:
            final.append(resolved)
    return final


def _resolve_one(
    conn: sqlite3.Connection,
    name: str,
    description: str,
    embedder: Embedder,
    threshold: float,
) -> str | None:
    """Snap one normalized candidate to an existing tag, or create it. Caller commits."""
    # Exact-name reuse is the cheapest possible canonicalization: if the normalized name
    # already exists, reuse it directly (no new vector, no description change — stable).
    if _tag_exists(conn, name):
        return name

    # Embed the candidate's concept DESCRIPTION (never the bare name) and snap to the
    # nearest existing tag whose description is close enough (spec §7.2 / §9.3).
    if not description.strip():
        # No description to embed and no exact match: fall back to the name as its own
        # minimal description so a tag still gets created rather than silently dropped.
        description = name
    embedding = embedder.embed(description)
    match = nearest_tag(conn, embedding)
    if match is not None and match[1] >= threshold:
        return match[0]  # snap to the existing tag (reuse over invention)

    # Genuinely new concept: create the tag with its stable description and persist the
    # description's embedding so future candidates can snap to it.
    _create_tag(conn, name, description, embedding)
    return name


def _tag_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM tags WHERE name = ?", (name,)).fetchone() is not None


def _create_tag(
    conn: sqlite3.Connection, name: str, description: str, embedding: list[float]
) -> None:
    """Insert the tag row (count starts at 0; the caller's edge write increments it) and
    its description embedding into ``tags_vec``. Caller commits."""
    conn.execute(
        "INSERT INTO tags (name, description, count) VALUES (?, ?, 0)",
        (name, description),
    )
    index_tag_vector(conn, name, embedding)
