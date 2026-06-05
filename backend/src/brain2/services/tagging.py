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

from brain2.services.canonicalize import TagCandidate, canonicalize_candidates
from brain2.services.fts import index_entry
from brain2.services.providers.embedder import EMBED_INPUT_MAX_CHARS, Embedder
from brain2.services.providers.page_fetcher import PageContent
from brain2.services.providers.tagger import Tagger, TagRequest
from brain2.services.structured_tags import StructuredTagSource
from brain2.services.tag_counters import apply_edge_diff
from brain2.services.tags_vector import nearest_tags

# Bound on basis text sent to the embedder/tagger: the shared embedder input cap, so an
# oversized basis cannot fail every attempt (the model has an input token budget).
_BASIS_MAX_CHARS = EMBED_INPUT_MAX_CHARS


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


def apply_agent_tags(
    conn: sqlite3.Connection,
    entry_id: str,
    raw_tags: list[str],
    *,
    embedder: Embedder,
    threshold: float,
    max_tags: int,
    descriptions: dict[str, str] | None = None,
) -> None:
    """Canonicalize agent-supplied tags and merge them ADDITIVELY (spec §10 save). Caller commits.

    Agent tags skip the LLM proposal step (§7.2 mechanism 2) but still go through
    canonicalize-on-write (mechanism 3) so they cannot fragment the vocabulary: each raw
    name is normalized, then snapped to a near-duplicate existing tag (cosine >= threshold)
    or created with a stable description. The result is UNIONed with the entry's current
    edges (never replacing them, spec §10 "tag merges are additive") and reconciled, so
    counters/co-occurrence/tags_text update for exactly the newly-added edges. ``descriptions``
    optionally supplies a concept description per raw name; otherwise canonicalize falls back
    to the name as its own minimal description.
    """
    descriptions = descriptions or {}
    candidates = [
        TagCandidate(name=name, description=descriptions.get(name, ""))
        for name in raw_tags
    ]
    canonical = canonicalize_candidates(
        conn, candidates, embedder=embedder, threshold=threshold, max_tags=max_tags
    )
    current = [
        r[0]
        for r in conn.execute("SELECT tag FROM entry_tags WHERE entry_id = ?", (entry_id,))
    ]
    # Additive merge: keep all existing edges, add the canonicalized agent tags.
    reconcile_tags(conn, entry_id, current + canonical)


def reconcile_tags(conn: sqlite3.Connection, entry_id: str, final_tags: list[str]) -> None:
    """Reconcile an entry's edges to exactly ``final_tags`` (spec §7.4 re-tag, §9.2).

    The single owner of edge writes shared by first-tag and re-tag (worker reprocess /
    repair). It diffs the entry's CURRENT edges against ``final_tags`` and:
      - REMOVES dropped edges, decrementing ``tags.count`` + ``tag_cooccurrence`` for them;
      - ADDS new edges, incrementing the same counters.
    Counters therefore always equal the live edge set, so they stay safe to decrement and
    a partial-overlap re-tag (the case M5 deferred) is handled correctly. The increment and
    decrement use the symmetric helpers (canonical pair order, floor at 0) so the math is a
    true mirror. Re-tagging with the SAME set is a no-op for counters (no double-bump).
    Finally refreshes the denormalized ``entries_fts.tags_text`` so BM25 matches tags.
    Caller commits.
    """
    current = {
        r[0] for r in conn.execute(
            "SELECT tag FROM entry_tags WHERE entry_id = ?", (entry_id,)
        )
    }
    desired = list(dict.fromkeys(final_tags))  # de-dup, preserve order
    desired_set = set(desired)

    removed = sorted(current - desired_set)
    added = [t for t in desired if t not in current]
    kept = sorted(current & desired_set)

    for tag in removed:
        conn.execute("DELETE FROM entry_tags WHERE entry_id = ? AND tag = ?", (entry_id, tag))
    for tag in added:
        conn.execute("INSERT INTO entry_tags (entry_id, tag) VALUES (?, ?)", (entry_id, tag))
    # Counter delta over the partial overlap: added×{added,kept} pairs rise, removed×
    # {removed,kept} pairs fall — so counters always equal the live edge set (spec §7.4/§9.2).
    apply_edge_diff(conn, added=added, removed=removed, kept=kept)

    # Denormalize the final tags into entries_fts so a tag keyword matches via BM25.
    row = conn.execute(
        "SELECT title, content FROM entries WHERE id = ?", (entry_id,)
    ).fetchone()
    index_entry(conn, entry_id, row["title"], row["content"])


def _persist_tags(conn: sqlite3.Connection, entry_id: str, tags: list[str]) -> None:
    """Persist the entry's final tag set via :func:`reconcile_tags` (spec §7.1 step 9)."""
    reconcile_tags(conn, entry_id, tags)
