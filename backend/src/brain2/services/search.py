"""Keyword retrieval over ``entries_fts`` using FTS5 BM25 (spec §11 BM25 half).

This is the keyword half of the hybrid search; vector + RRF arrive in M4. It is
decoupled from transport so both REST (future) and MCP call the same function.

Ranking: ``bm25(entries_fts)`` over title + tags_text + content. SQLite returns a
lower (more negative) bm25 score for a better match, so results are ordered ascending
and the score is negated into an intuitive "higher is better" value for the agent.
"""

import re
import sqlite3

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


def _matching_entry_ids_by_tags(conn: sqlite3.Connection, tags: list[str]) -> set[str]:
    """Entry ids that carry ALL of the given tags (conjunctive pre-filter)."""
    placeholders = ",".join("?" for _ in tags)
    rows = conn.execute(
        f"""
        SELECT entry_id FROM entry_tags
         WHERE tag IN ({placeholders})
         GROUP BY entry_id
        HAVING COUNT(DISTINCT tag) = ?
        """,
        (*tags, len(tags)),
    ).fetchall()
    return {row[0] for row in rows}


def _tags_for(conn: sqlite3.Connection, entry_id: str) -> list[str]:
    """Tags attached to an entry, for the compact result shape."""
    rows = conn.execute(
        "SELECT tag FROM entry_tags WHERE entry_id = ? ORDER BY tag", (entry_id,)
    ).fetchall()
    return [row[0] for row in rows]


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
    tokens = _TOKEN_RE.findall(query)
    if not tokens:
        return []
    fts_tokens = [t for t in tokens if len(t) >= _TRIGRAM_MIN_CHARS]
    short_tokens = [t for t in tokens if len(t) < _TRIGRAM_MIN_CHARS]

    # Tag pre-filter: resolve the allowed id set first; an empty set means no match.
    allowed_ids: set[str] | None = None
    if tags:
        allowed_ids = _matching_entry_ids_by_tags(conn, tags)
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

    return [
        {
            "id": row["id"],
            "url": row["url"],
            "title": row["title"],
            "tags": _tags_for(conn, row["id"]),
            "note": row["note"],
            # Pre-enrichment (M2) the note is NULL until summarization; surface the
            # stored body so the agent can read what BM25 matched on (spec §10, §15).
            "content": row["content"],
            "type": row["type"],
            "saved_at": row["saved_at"],
            # bm25() is negative-better; negate so higher == more relevant.
            "score": -float(row["rank"]),
        }
        for row in rows
    ]
