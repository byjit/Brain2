"""Vector index + KNN over ``tags_vec`` — the tag embedding layer (spec §9.2, §9.3).

``tags_vec`` embeds each tag's stable concept DESCRIPTION (never the bare name, spec §9.3),
so it powers both anti-fragmentation levers: fetching the nearest EXISTING tags to ground
the LLM proposal (``nearest_tags``), and snapping a candidate description to an existing
tag at write time (``nearest_tag`` for canonicalization). Mirrors ``vector.py`` for
``entries_vec``: delete-then-insert (vec0 has no UPSERT) and the same serialization.
"""

import sqlite3

import sqlite_vec

# Default neighbors to fetch for the RAG-grounding prompt (capped so it stays small at
# hundreds of tags, spec §7.2). Overridable by the caller.
_DEFAULT_K = 10


def index_tag_vector(
    conn: sqlite3.Connection, name: str, embedding: list[float]
) -> None:
    """Insert or replace a tag's description vector. Caller commits.

    A description is generated once at creation and kept stable (spec §9.3), so in normal
    operation this is written exactly once per tag; delete-then-insert only guards against
    an accidental re-create and keeps one row per tag.
    """
    conn.execute("DELETE FROM tags_vec WHERE name = ?", (name,))
    conn.execute(
        "INSERT INTO tags_vec (name, embedding) VALUES (?, ?)",
        (name, sqlite_vec.serialize_float32(embedding)),
    )


def nearest_tags(
    conn: sqlite3.Connection, query_embedding: list[float], *, limit: int = _DEFAULT_K
) -> list[tuple[str, float]]:
    """Return the nearest existing tags as ``(name, cosine_similarity)``, nearest first.

    The note basis embedding is the query (spec §7.2 mechanism 2). ``tags_vec`` uses
    cosine distance, so similarity is ``1 - distance``. An empty index yields ``[]``.

    A zero-magnitude query (e.g. an empty basis that tokenizes to nothing) has no cosine
    direction, so sqlite-vec returns a NULL distance for it; such rows are skipped (no
    match) rather than crashing on ``1 - None`` — keeping an empty-basis entry on the
    worker's blank-note failure path with an actionable message (spec §7.4).
    """
    if limit <= 0:
        return []
    rows = conn.execute(
        """
        SELECT name, distance FROM tags_vec
         WHERE embedding MATCH ? AND k = ?
         ORDER BY distance
        """,
        (sqlite_vec.serialize_float32(query_embedding), limit),
    ).fetchall()
    return [(row[0], 1.0 - row[1]) for row in rows if row[1] is not None]


def nearest_tag(
    conn: sqlite3.Connection, query_embedding: list[float]
) -> tuple[str, float] | None:
    """Return the single nearest existing tag as ``(name, cosine_similarity)``, or None.

    Used by canonicalization to decide whether a candidate snaps to an existing tag.
    """
    result = nearest_tags(conn, query_embedding, limit=1)
    return result[0] if result else None
