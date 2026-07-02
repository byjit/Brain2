"""Vector index + KNN search over ``entries_vec`` (spec §9.2, §11 vector half).

This is the semantic leg of hybrid retrieval. The worker embeds each entry's note and
upserts the 768-dim vector here; ``vector_search`` runs a sqlite-vec ``vec0`` KNN over
those vectors and returns ranked entry ids (set B for the RRF merge in ``search``).

Tag/type pre-filters are applied around the KNN (same filters as the BM25 leg) so a
filtered-out entry never appears.

Filter strategy (sqlite-vec 0.1.9). vec0's ``id IN (...)`` clause on a TEXT-PK table is a
*post*-filter over the k nearest neighbours, not a pushdown into the distance computation:
a filtered match that sits outside the top-k by raw distance is silently dropped even
though it is a true nearest neighbour among the filtered set (verified empirically — see
``tests/test_vector.py::test_filter_recall_beyond_overfetch``). Only true scalar metadata
columns are pushed down, and tags are many-to-many so cannot be metadata columns. To fix
the silent recall loss we ESCALATE ``k``: start at ``limit * overfetch`` and, whenever the
filtered survivor count is short of ``limit`` while unfetched rows remain, retry with a
larger ``k`` up to the full table size. This guarantees up to ``limit`` true nearest
matches among the filtered set (correctness). The common (non-escalating) case is
unchanged — a single KNN at ``limit * overfetch``; only the escalation path costs
additional full scans (O(n) per iteration, up to ~log2 iterations), accepted to guarantee
recall.
"""

import sqlite3

import sqlite_vec

from brain2.services.prefilter import entry_ids_of_type, entry_ids_with_all_tags

# Default neighbors to fetch (spec §10 retrieve default limit). The RRF merge re-ranks,
# so a modest candidate pool per leg is sufficient.
_DEFAULT_K = 10

# When pre-filters are active we start by over-fetching, because many top neighbors may be
# filtered out before we have ``k`` survivors. A generous multiple keeps the common case
# to a single query; the escalation below guarantees correctness beyond it.
_PREFILTER_OVERFETCH = 10


def _require_dimension(conn: sqlite3.Connection, embedding: list[float]) -> None:
    """Raise a clear error if the vector's length does not match the vec0 column.

    sqlite-vec also rejects mismatches on insert, but failing here gives a typed
    ``ValueError`` with the expected/received dims instead of a raw OperationalError,
    so a misconfigured embedder never silently corrupts the index.
    """
    expected = conn.execute(
        "SELECT vec_length(embedding) FROM entries_vec LIMIT 1"
    ).fetchone()
    # ``vec_length`` only returns a row once the table has data; fall back to the schema
    # dimension (768) when empty so the very first insert is still validated.
    expected_dim = expected[0] if expected else 768
    if len(embedding) != expected_dim:
        raise ValueError(
            f"Embedding has {len(embedding)} dims, expected {expected_dim} for entries_vec"
        )


def index_entry_vector(
    conn: sqlite3.Connection, entry_id: str, embedding: list[float]
) -> None:
    """Insert or replace the entry's note vector. Caller commits.

    vec0 has no UPSERT, so we delete-then-insert to keep exactly one vector per entry on
    both first enrichment and re-enrichment (spec §7.1: clear/replace on re-enrichment).
    """
    _require_dimension(conn, embedding)
    conn.execute("DELETE FROM entries_vec WHERE id = ?", (entry_id,))
    conn.execute(
        "INSERT INTO entries_vec (id, embedding) VALUES (?, ?)",
        (entry_id, sqlite_vec.serialize_float32(embedding)),
    )


def remove_entry_vector(conn: sqlite3.Connection, entry_id: str) -> None:
    """Remove the entry's note vector. Caller commits."""
    conn.execute("DELETE FROM entries_vec WHERE id = ?", (entry_id,))


def vector_search(
    conn: sqlite3.Connection,
    query_embedding: list[float],
    *,
    tags: list[str] | None = None,
    type: str | None = None,
    limit: int = _DEFAULT_K,
) -> list[str]:
    """KNN over note vectors with tag/type pre-filters; returns ranked entry ids.

    Args:
        query_embedding: The embedded query vector (set B's query, spec §11).
        tags: If given, only entries carrying ALL of these tags survive.
        type: If given, restrict to this entry type.
        limit: Maximum ids to return (default 10).

    Returns ids ordered by ascending distance (nearest first).
    """
    # Defensive guard: a negative k makes vec0 raise an opaque OperationalError.
    if limit < 0:
        raise ValueError("limit must be >= 0")
    # Resolve the allowed id set from the pre-filters (same filters as the BM25 leg). An
    # empty allowed set means nothing can match, so we skip the KNN entirely.
    allowed: set[str] | None = None
    if tags:
        allowed = entry_ids_with_all_tags(conn, tags)
    if type is not None:
        type_ids = entry_ids_of_type(conn, type)
        allowed = type_ids if allowed is None else (allowed & type_ids)
    if allowed is not None and not allowed:
        return []

    query_vec = sqlite_vec.serialize_float32(query_embedding)

    # Unfiltered: a single KNN at ``limit`` is exact.
    if allowed is None:
        rows = conn.execute(
            "SELECT id FROM entries_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (query_vec, limit),
        ).fetchall()
        return [row[0] for row in rows[:limit]]

    # Filtered: vec0's post-filter drops filtered matches that fall outside the current
    # top-k, so escalate ``k`` until we have ``limit`` survivors or have scanned the whole
    # table. This is the correctness fix for the silent recall loss (see module docstring).
    total = conn.execute("SELECT count(*) FROM entries_vec").fetchone()[0]
    if total == 0:
        return []
    k = min(max(limit * _PREFILTER_OVERFETCH, limit), total)
    while True:
        rows = conn.execute(
            "SELECT id FROM entries_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (query_vec, k),
        ).fetchall()
        survivors = [row[0] for row in rows if row[0] in allowed]
        # Enough survivors, or we've already considered every vector in the table.
        if len(survivors) >= limit or k >= total:
            return survivors[:limit]
        k = min(k * 2, total)
