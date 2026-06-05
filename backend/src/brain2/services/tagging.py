"""Auto-tagging orchestration (spec §7.1 steps 4-9, §7.2) — the core of v1.

``apply_tags`` runs the full anti-fragmentation pipeline for one entry, against a live DB
connection, with all external services injected as abstractions so it unit-tests offline:

  1. Structured-source priors (GitHub topics/language, OG keywords) seed the candidate set.
  2. Embed the basis text and KNN over ``tags_vec`` for the nearest EXISTING tags (the
     biggest anti-fragmentation lever; ``tags_vec`` embeds DESCRIPTIONS, not names).
  3. ONE Gemini call (the ``Tagger``) returns the note (when needed) + candidate tags +
     a concept description per NEW candidate. Exactly one LLM call per entry.
  4. Canonicalize-on-write: normalize each candidate, snap to the nearest existing tag at
     cosine >= threshold, else create it with its stable description embedded into
     ``tags_vec``. Capped to ``max_tags`` and biased to reuse.
  5. Persist ``entry_tags`` edges, increment ``tags.count`` and ``tag_cooccurrence`` for
     every unordered tag-pair (stored in canonical order), and denormalize the final tags
     into ``entries_fts.tags_text`` so BM25 matches tags.

Returns the resolved note (the LLM summary when ``needs_summary`` else ``""``) so the
worker can persist it. The basis-text embedding is computed here (reusing the M4 embedder)
and not duplicated elsewhere (DRY).
"""

import sqlite3
from itertools import combinations

from brain2.services.canonicalize import TagCandidate, canonicalize_candidates
from brain2.services.fts import index_entry
from brain2.services.providers.embedder import Embedder
from brain2.services.providers.page_fetcher import PageContent
from brain2.services.providers.tagger import Tagger, TagRequest
from brain2.services.structured_tags import StructuredTagSource
from brain2.services.tags_vector import nearest_tags

# Bound on basis text sent to the embedder/tagger, mirroring the worker's embed cap so an
# oversized basis cannot fail every attempt (the model has an input token budget).
_BASIS_MAX_CHARS = 8_000


def apply_tags(
    conn: sqlite3.Connection,
    entry_id: str,
    *,
    basis_text: str,
    needs_summary: bool,
    source: StructuredTagSource,
    tagger: Tagger,
    embedder: Embedder,
    threshold: float,
    max_tags: int,
    nearest_limit: int,
    url: str | None = None,
    page: PageContent = PageContent(),
) -> str:
    """Run the auto-tagging pipeline for one entry. Returns the resolved note. Caller commits.

    ``basis_text`` is the already-resolved note basis (verbatim text or page body). When
    ``needs_summary`` the single tagger call also produces the summary note; otherwise the
    note is already set and the call returns tags only.
    """
    basis = basis_text[:_BASIS_MAX_CHARS]

    # 1. Structured-source priors (high-confidence metadata; never raise). The page's
    # OG/meta keywords + a GitHub repo's topics/language seed the candidate set (spec §7.2).
    structured = source.priors(url=url, page=page)

    # 2. Nearest EXISTING tags via the basis embedding (RAG grounding, spec §7.2).
    basis_embedding = embedder.embed(basis)
    nearest = [name for name, _sim in nearest_tags(conn, basis_embedding, limit=nearest_limit)]

    # 3. The SINGLE combined LLM call (exactly one per entry).
    proposal = tagger.propose(
        TagRequest(
            basis_text=basis,
            structured_tags=structured,
            nearest_existing_tags=nearest,
            needs_summary=needs_summary,
        )
    )

    # 4. Canonicalize-on-write: snap or create, capped + biased to reuse.
    candidates = [
        TagCandidate(name=name, description=proposal.new_tag_descriptions.get(name, ""))
        for name in proposal.tags
    ]
    final_tags = canonicalize_candidates(
        conn, candidates, embedder=embedder, threshold=threshold, max_tags=max_tags
    )

    # 5. Persist edges + counters + denormalized tags_text.
    _persist_tags(conn, entry_id, final_tags)

    return proposal.note if needs_summary else ""


def _persist_tags(conn: sqlite3.Connection, entry_id: str, tags: list[str]) -> None:
    """Write edges, bump counts + co-occurrence, and refresh tags_text (spec §7.1 step 9).

    Counters are structured so a symmetric DECREMENT (M6 delete) is trivial: each edge
    bumps ``tags.count`` by 1, and each unordered tag-pair (stored ``tag_a < tag_b`` so
    (a,b) and (b,a) never split) bumps ``tag_cooccurrence.count`` by 1. Counters are only
    bumped for NEWLY-inserted edges, so re-processing an already-tagged entry (spec §7.4
    repair) cannot inflate counts above the live edge count and they stay safe to decrement.
    """
    new_tags = [
        tag
        for tag in tags
        if conn.execute(
            "INSERT OR IGNORE INTO entry_tags (entry_id, tag) VALUES (?, ?)", (entry_id, tag)
        ).rowcount
        > 0
    ]
    for tag in new_tags:
        conn.execute("UPDATE tags SET count = count + 1 WHERE name = ?", (tag,))

    for tag_a, tag_b in combinations(sorted(new_tags), 2):  # canonical order, no (b,a) dup
        conn.execute(
            """
            INSERT INTO tag_cooccurrence (tag_a, tag_b, count) VALUES (?, ?, 1)
            ON CONFLICT(tag_a, tag_b) DO UPDATE SET count = count + 1
            """,
            (tag_a, tag_b),
        )

    # Denormalize the final tags into entries_fts so a tag keyword matches via BM25.
    row = conn.execute(
        "SELECT title, content FROM entries WHERE id = ?", (entry_id,)
    ).fetchone()
    index_entry(conn, entry_id, row["title"], row["content"])
