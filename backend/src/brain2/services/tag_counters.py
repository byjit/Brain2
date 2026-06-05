"""Symmetric tag counter maintenance (spec §9.2) — the single owner of count math.

Inserting an ``entry_tags`` edge increments ``tags.count`` and, for every unordered
tag-pair, ``tag_cooccurrence.count``; ``delete`` decrements both. Keeping the increment
and its EXACT inverse decrement in one place guarantees they use the same canonical pair
ordering (``tag_a < tag_b``, so (a,b)/(b,a) never split) and that delete is a true mirror
of M5's write (spec §9.2). Counts floor at 0; a tag whose count reaches 0 is LEFT in place
(its description + ``tags_vec`` embedding stay useful for canonicalization, spec §9.2), so
this module never deletes a ``tags`` row.
"""

import sqlite3
from itertools import combinations


def _pairs(tags: list[str]):
    """Yield every unordered tag-pair in canonical (``tag_a < tag_b``) order."""
    return combinations(sorted(tags), 2)


def _bump_count(conn: sqlite3.Connection, tag: str, delta: int) -> None:
    conn.execute("UPDATE tags SET count = MAX(count + ?, 0) WHERE name = ?", (delta, tag))


def _bump_pair(conn: sqlite3.Connection, tag_a: str, tag_b: str, delta: int) -> None:
    """Apply ``delta`` to a canonical pair's co-occurrence count, flooring at 0 / upserting."""
    if delta > 0:
        conn.execute(
            """
            INSERT INTO tag_cooccurrence (tag_a, tag_b, count) VALUES (?, ?, ?)
            ON CONFLICT(tag_a, tag_b) DO UPDATE SET count = count + ?
            """,
            (tag_a, tag_b, delta, delta),
        )
    else:
        conn.execute(
            "UPDATE tag_cooccurrence SET count = MAX(count + ?, 0) WHERE tag_a = ? AND tag_b = ?",
            (delta, tag_a, tag_b),
        )


def apply_edge_diff(
    conn: sqlite3.Connection, added: list[str], removed: list[str], kept: list[str]
) -> None:
    """Apply the exact counter delta for a partial re-tag (spec §7.4, §9.2). Caller commits.

    Given an entry whose edges change, with ``added`` new tags, ``removed`` dropped tags,
    and ``kept`` tags present both before and after:
      - ``tags.count`` rises by 1 per added tag and falls by 1 per removed tag.
      - ``tag_cooccurrence`` rises for every pair newly co-present (added×added internal +
        added×kept cross pairs) and falls for every pair no longer co-present
        (removed×removed internal + removed×kept cross pairs).
    This is what makes counters always equal the live edge set across partial overlaps.
    """
    for tag in added:
        _bump_count(conn, tag, +1)
    for tag in removed:
        _bump_count(conn, tag, -1)

    for pair in _added_pairs(added, kept):
        _bump_pair(conn, pair[0], pair[1], +1)
    for pair in _removed_pairs(removed, kept):
        _bump_pair(conn, pair[0], pair[1], -1)


def _canon(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _added_pairs(added: list[str], kept: list[str]) -> set[tuple[str, str]]:
    """Pairs that become co-present: added×added (internal) + added×kept (cross)."""
    pairs = set(_pairs(added))
    pairs.update(_canon(a, k) for a in added for k in kept)
    return pairs


def _removed_pairs(removed: list[str], kept: list[str]) -> set[tuple[str, str]]:
    """Pairs that stop being co-present: removed×removed + removed×kept."""
    pairs = set(_pairs(removed))
    pairs.update(_canon(r, k) for r in removed for k in kept)
    return pairs


def decrement_for_tags(conn: sqlite3.Connection, tags: list[str]) -> None:
    """Remove a WHOLE edge set's counters — the symmetric inverse of a full add (spec §9.2 delete).

    Decrements ``tags.count`` per tag and ``tag_cooccurrence.count`` per pair, flooring at 0
    so a counter never goes negative. The ``tags`` row is never deleted even at count 0 — its
    stable description + ``tags_vec`` embedding stay useful for future canonicalization
    (spec §9.2). A thin wrapper over :func:`apply_edge_diff` (added=[], kept=[]), so the
    delete-side decrement uses the exact same canonical pair ordering as the write-side add.
    Caller commits.
    """
    apply_edge_diff(conn, added=[], removed=tags, kept=[])
