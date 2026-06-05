"""Shared tag/type pre-filter helpers for retrieval (spec §10, §11).

Both the BM25 (``search``) and vector (``vector``) legs apply the *same* tag/type
pre-filters before ranking, so filtered entries never appear in either leg or in the
fused result. Centralizing the SQL here keeps the two legs in lockstep (DRY).
"""

import sqlite3


def entry_ids_with_all_tags(conn: sqlite3.Connection, tags: list[str]) -> set[str]:
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


def entry_ids_of_type(conn: sqlite3.Connection, type: str) -> set[str]:
    """Entry ids of a given type (the type pre-filter as an id set)."""
    rows = conn.execute("SELECT id FROM entries WHERE type = ?", (type,)).fetchall()
    return {row[0] for row in rows}
