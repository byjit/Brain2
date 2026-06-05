"""get_tags read model: the paged tag landscape (spec §10 get_tags).

Lists tags with ``name``, ``description``, ``count`` and ``co_occurs_with`` (the top
co-occurring tag names from ``tag_cooccurrence``) so an agent can understand the vocabulary
and pick tags to filter on in ``retrieve``. Paged because a heavy user has hundreds of tags
(spec §10): ``limit`` (default 50) + ``sort`` ('count' default desc, or 'name' asc). No
other knobs (YAGNI). Read-only; the caller owns the connection.
"""

import sqlite3

# Default page size (spec §10 "top 50 by count").
_DEFAULT_LIMIT = 50

# How many co-occurring partners to surface per tag. The §10 example lists a handful; a
# small fixed cap keeps the response compact at hundreds of tags.
_COOCCUR_LIMIT = 5

_SORTS = {
    "count": "count DESC, name ASC",  # heaviest first; name breaks ties deterministically
    "name": "name ASC",
}


def list_tags(
    conn: sqlite3.Connection, *, limit: int = _DEFAULT_LIMIT, sort: str = "count"
) -> list[dict]:
    """Return the paged tag list in the exact spec §10 shape. Read-only.

    Each item is ``{tag, description, count, co_occurs_with}`` where ``co_occurs_with`` is
    the top co-occurring tag names ordered by co-occurrence count (desc). ``sort`` is
    'count' (default, desc) or 'name' (asc); an unknown sort raises ``ValueError``.
    """
    if sort not in _SORTS:
        raise ValueError(f"sort must be one of {sorted(_SORTS)}")
    if limit < 0:
        raise ValueError("limit must be >= 0")

    rows = conn.execute(
        f"SELECT name, description, count FROM tags ORDER BY {_SORTS[sort]} LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "tag": row["name"],
            "description": row["description"],
            "count": row["count"],
            "co_occurs_with": _co_occurs_with(conn, row["name"]),
        }
        for row in rows
    ]


def _co_occurs_with(conn: sqlite3.Connection, name: str) -> list[str]:
    """Top co-occurring tag names for ``name``, ordered by co-occurrence count (desc).

    Pairs are stored once in canonical order (``tag_a < tag_b``), so a tag can appear as
    either side; this unions both directions so the lookup is symmetric. Zero-count pairs
    (decremented away on delete, spec §9.2) are excluded so they don't surface as relations.
    """
    rows = conn.execute(
        """
        SELECT partner, count FROM (
            SELECT tag_b AS partner, count FROM tag_cooccurrence
             WHERE tag_a = ? AND count > 0
            UNION ALL
            SELECT tag_a AS partner, count FROM tag_cooccurrence
             WHERE tag_b = ? AND count > 0
        )
        ORDER BY count DESC, partner ASC
        LIMIT ?
        """,
        (name, name, _COOCCUR_LIMIT),
    ).fetchall()
    return [row["partner"] for row in rows]
