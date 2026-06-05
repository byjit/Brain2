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


def _to_match_query(query: str) -> str | None:
    """Turn arbitrary user text into a safe FTS5 MATCH expression.

    Extracts word tokens and quotes each as a literal phrase (doubling any embedded
    quote), then joins with spaces (implicit AND). Returns None when there is nothing
    searchable so the caller can short-circuit to an empty result.
    """
    tokens = _TOKEN_RE.findall(query)
    if not tokens:
        return None
    return " ".join(f'"{token}"' for token in tokens)


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
    match_query = _to_match_query(query)
    if match_query is None:
        return []

    # Tag pre-filter: resolve the allowed id set first; an empty set means no match.
    allowed_ids: set[str] | None = None
    if tags:
        allowed_ids = _matching_entry_ids_by_tags(conn, tags)
        if not allowed_ids:
            return []

    where = ["entries_fts MATCH ?"]
    params: list = [match_query]
    if type is not None:
        where.append("e.type = ?")
        params.append(type)
    if allowed_ids is not None:
        placeholders = ",".join("?" for _ in allowed_ids)
        where.append(f"e.id IN ({placeholders})")
        params.extend(allowed_ids)

    sql = f"""
        SELECT e.id, e.url, e.title, e.note, e.content, e.type, e.saved_at,
               bm25(entries_fts) AS rank
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
