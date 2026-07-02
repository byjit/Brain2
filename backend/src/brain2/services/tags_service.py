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
    names = [row["name"] for row in rows]
    cooccur = _co_occurs_for(conn, names)
    return [
        {
            "tag": row["name"],
            "description": row["description"],
            "count": row["count"],
            "co_occurs_with": cooccur.get(row["name"], []),
        }
        for row in rows
    ]


def _co_occurs_for(
    conn: sqlite3.Connection, names: list[str]
) -> dict[str, list[str]]:
    """Top co-occurring tag names for a whole page of tags, in ONE batched query.

    Avoids the N+1 that a per-tag query caused (N tags -> N co-occurrence scans). Pairs are
    stored once in canonical order (``tag_a < tag_b``), so a page tag can appear as either
    side; both directions are unioned so the lookup is symmetric. Zero-count pairs
    (decremented away on delete, spec §9.2) are excluded so they don't surface as relations.

    Returns ``{tag_name: [partner, ...]}`` where each partner list preserves the exact
    per-tag ordering the previous per-tag query produced (co-occurrence count desc, partner
    name asc) and is capped at ``_COOCCUR_LIMIT``.
    """
    if not names:
        return {}
    placeholders = ",".join("?" for _ in names)
    # Fetch every co-occurrence edge that touches ANY page tag, from both directions, in
    # one pass. ``anchor`` is the page-tag side and ``partner`` is the co-occurring tag.
    rows = conn.execute(
        f"""
        SELECT tag_a AS anchor, tag_b AS partner, count FROM tag_cooccurrence
         WHERE count > 0 AND tag_a IN ({placeholders})
        UNION ALL
        SELECT tag_b AS anchor, tag_a AS partner, count FROM tag_cooccurrence
         WHERE count > 0 AND tag_b IN ({placeholders})
        """,
        (*names, *names),
    ).fetchall()

    # Group partners per anchor, then order + cap in Python to match the previous
    # per-tag ``ORDER BY count DESC, partner ASC LIMIT _COOCCUR_LIMIT`` exactly.
    grouped: dict[str, list[tuple[int, str]]] = {}
    for row in rows:
        grouped.setdefault(row["anchor"], []).append((row["count"], row["partner"]))
    return {
        anchor: [
            partner
            for _, partner in sorted(partners, key=lambda cp: (-cp[0], cp[1]))[:_COOCCUR_LIMIT]
        ]
        for anchor, partners in grouped.items()
    }
