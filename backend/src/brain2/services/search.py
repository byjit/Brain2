"""Hybrid retrieval over a user's DB (spec §10 retrieve, §11 search strategy).

Two legs, fused with Reciprocal Rank Fusion (RRF):
- **BM25** (set A): ``bm25(entries_fts)`` over title + tags_text + content. SQLite returns
  a lower (more negative) score for a better match, so rows are ordered ascending and the
  score is negated into a "higher is better" value.
- **Vector** (set B): sqlite-vec KNN over the note embedding (``services.vector``).

``hybrid_search`` is the public retrieve path (MCP uses it); ``search_entries`` is the
BM25-only path kept internally usable. Tag/type pre-filters are applied to BOTH legs (via
the shared ``prefilter`` helpers) so a filtered entry never appears in either leg or the
fused result. Decoupled from transport so REST (future) and MCP share one implementation.
"""

import re
import sqlite3

from brain2.services.prefilter import entry_ids_with_all_tags
from brain2.services.projection import compact_entry
from brain2.services.providers.embedder import Embedder
from brain2.services.vector import vector_search

# Reciprocal Rank Fusion constant (spec §11: RRF score = Σ 1/(k + rank), k=60).
_RRF_K = 60

# Default page size for retrieve (spec §10).
_DEFAULT_LIMIT = 10

# FTS5 query syntax is fragile: bare quotes, NEAR, AND/OR, ``*``, ``:`` and parens
# are operators. Rather than escape each operator, extract plain word tokens and
# re-quote them as FTS5 string literals so every token matches literally.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# The trigram tokenizer cannot index/match tokens shorter than 3 chars (incl. 1-2 char
# CJK), so such tokens silently return nothing through MATCH. They fall back to a LIKE
# substring scan over the indexed columns instead (spec §15 CJK recall).
_TRIGRAM_MIN_CHARS = 3


def _to_match_query(tokens: list[str]) -> str | None:
    """Turn FTS-capable tokens into a safe FTS5 MATCH expression.

    Quotes each token as a literal phrase, then joins with spaces (implicit AND). Returns
    None when there are no FTS-capable tokens so the caller can use the LIKE-only path.
    """
    if not tokens:
        return None
    return " ".join(f'"{token}"' for token in tokens)


def _like_clause(token: str) -> tuple[str, list[str]]:
    """A clause matching ``token`` as a substring of any indexed FTS column.

    Used for tokens too short for the trigram tokenizer. ``%`` / ``_`` are escaped so a
    user token is treated literally, not as a LIKE wildcard.
    """
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    cols = ("entries_fts.title", "entries_fts.tags_text", "entries_fts.content")
    clause = "(" + " OR ".join(f"{c} LIKE ? ESCAPE '\\'" for c in cols) + ")"
    return clause, [pattern] * len(cols)


def search_entries(
    conn: sqlite3.Connection,
    query: str,
    *,
    tags: list[str] | None = None,
    type: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict]:
    """BM25 keyword search with optional tag/type pre-filters (spec §10 retrieve).

    Args:
        query: Free-text query; FTS5 special characters are neutralized.
        tags: If given, only entries carrying ALL of these tags are considered.
        type: If given, restrict to this entry type.
        limit: Maximum results (default 10).

    Returns:
        A list of compact result dicts (spec §10): ``id, url, title, tags, note,
        content, type, saved_at, score``, ordered best-first.
    """
    # Defensive guard: a negative limit becomes SQLite 'LIMIT -1' (unbounded).
    if limit < 0:
        raise ValueError("limit must be >= 0")
    tokens = _TOKEN_RE.findall(query)
    if not tokens:
        return []
    fts_tokens = [t for t in tokens if len(t) >= _TRIGRAM_MIN_CHARS]
    short_tokens = [t for t in tokens if len(t) < _TRIGRAM_MIN_CHARS]

    # Tag pre-filter: resolve the allowed id set first; an empty set means no match.
    allowed_ids: set[str] | None = None
    if tags:
        allowed_ids = entry_ids_with_all_tags(conn, tags)
        if not allowed_ids:
            return []

    where: list[str] = []
    params: list = []
    # FTS-capable tokens drive bm25 ranking; short tokens (trigram can't match them) add
    # a LIKE substring filter so they don't silently zero out the result (spec §15).
    match_query = _to_match_query(fts_tokens)
    rank_expr = "0.0"
    if match_query is not None:
        where.append("entries_fts MATCH ?")
        params.append(match_query)
        rank_expr = "bm25(entries_fts)"
    for token in short_tokens:
        clause, clause_params = _like_clause(token)
        where.append(clause)
        params.extend(clause_params)
    if type is not None:
        where.append("e.type = ?")
        params.append(type)
    if allowed_ids is not None:
        placeholders = ",".join("?" for _ in allowed_ids)
        where.append(f"e.id IN ({placeholders})")
        params.extend(allowed_ids)

    sql = f"""
        SELECT e.id, e.url, e.title, e.note, e.content, e.type, e.saved_at,
               {rank_expr} AS rank
          FROM entries_fts
          JOIN entries e ON e.id = entries_fts.id
         WHERE {" AND ".join(where)}
         ORDER BY rank ASC
         LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()

    # bm25() is negative-better; negate so higher == more relevant. Pre-enrichment (M2)
    # the note is NULL until summarization, but compact_entry still surfaces the stored
    # body so the agent can read what BM25 matched on (spec §10, §15).
    return [compact_entry(conn, row, score=-float(row["rank"])) for row in rows]


# Candidate pool per leg before fusion. We over-fetch beyond the final ``limit`` so an
# entry ranked modestly in one leg can still surface via the other under RRF.
_CANDIDATE_POOL = 50


def _rrf_scores(ranked_ids: list[str]) -> dict[str, float]:
    """RRF contribution of one ranked leg: 1/(k + rank), rank starting at 1 (spec §11)."""
    return {entry_id: 1.0 / (_RRF_K + rank) for rank, entry_id in enumerate(ranked_ids, start=1)}


def _project_entry(conn: sqlite3.Connection, entry_id: str, score: float) -> dict:
    """Build the compact spec §10 result row for an entry id."""
    row = conn.execute(
        "SELECT id, url, title, note, content, type, saved_at FROM entries WHERE id = ?",
        (entry_id,),
    ).fetchone()
    return compact_entry(conn, row, score=score)


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    embedder: Embedder,
    tags: list[str] | None = None,
    type: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict]:
    """Hybrid BM25 + vector retrieval fused with RRF (spec §10 retrieve, §11).

    Set A (BM25) and set B (vector KNN over the note embedding) are each ranked under the
    SAME tag/type pre-filters, then fused: ``score = Σ 1/(k + rank_i)`` with ``k=60``.
    Returns the compact §10 result shape ordered by fused score (default limit 10). An
    empty/whitespace query (no searchable tokens) returns ``[]``.
    """
    # Defensive guard: a negative limit would slice the fused list oddly (ordered[:-n]).
    if limit < 0:
        raise ValueError("limit must be >= 0")
    # No searchable tokens -> nothing to rank lexically or to embed meaningfully.
    if not _TOKEN_RE.findall(query):
        return []

    # Set A: BM25 ranked ids (over-fetched). search_entries already applies the same
    # tag/type pre-filters, so we reuse it rather than duplicating the BM25 path (DRY).
    bm25_ids = [
        r["id"]
        for r in search_entries(conn, query, tags=tags, type=type, limit=_CANDIDATE_POOL)
    ]
    # Set B: vector ranked ids under the identical pre-filters.
    vector_ids = vector_search(
        conn, embedder.embed(query), tags=tags, type=type, limit=_CANDIDATE_POOL
    )

    # Fuse: sum each leg's RRF contribution per id.
    fused: dict[str, float] = {}
    for leg in (_rrf_scores(bm25_ids), _rrf_scores(vector_ids)):
        for entry_id, score in leg.items():
            fused[entry_id] = fused.get(entry_id, 0.0) + score

    # Order by fused score (desc); ties broken by id for deterministic output.
    ordered = sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))
    return [_project_entry(conn, entry_id, score) for entry_id, score in ordered[:limit]]
