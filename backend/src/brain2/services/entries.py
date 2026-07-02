"""Entry save service: the synchronous portion of the save pipeline (spec §7.1).

Normalizes the URL, applies conditional content persistence, and upserts by
normalized URL. Async enrichment (note, tags, vectors) is added in later milestones;
new entries land with ``status='pending'`` for the future worker to pick up.
"""

import sqlite3
from datetime import datetime, timezone

from nanoid import generate

from brain2.models.entries import CreateEntryRequest, EntryType, SaveEntryResponse, SaveStatus
from brain2.services.content import persisted_content
from brain2.services.fts import index_entry, remove_entry
from brain2.services.projection import compact_entry
from brain2.services.providers.embedder import Embedder
from brain2.services.tag_counters import decrement_for_tags
from brain2.services.url_normalize import normalize_url
from brain2.services.vector import index_entry_vector, remove_entry_vector

# note_source provenance (spec §7.3): a user-typed note is authored; everything else
# starts from the page body until the async ladder resolves a better source.
_DEFAULT_NOTE_SOURCE = "body"
_NOTE_TYPE_SOURCE = "user"


def _now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _find_by_normalized_url(conn: sqlite3.Connection, url: str) -> str | None:
    """Return the id of an existing entry with this normalized URL, if any."""
    row = conn.execute("select id from entries where url = ?", (url,)).fetchone()
    return row[0] if row else None


def save_entry(
    conn: sqlite3.Connection,
    req: CreateEntryRequest,
    *,
    embedder: Embedder | None = None,
) -> SaveEntryResponse:
    """Upsert an entry and return its id and save status.

    - type=note: never dedups (no URL); its text is the note authored by the user.
    - other types: dedup by normalized URL — update if present, else insert pending.

    When ``embedder`` is supplied and an existing URL is re-saved WITH a changed note
    override, the note vector is refreshed in lockstep with FTS so the two retrieval legs
    never diverge (spec §7.1 clear/replace invariant). It is optional so the insert path
    and override-free updates need no provider wiring.
    """
    normalized = normalize_url(req.url)
    content = persisted_content(req.type.value, req.captured_text)
    now = _now_iso()

    # Notes are never deduped; URL-backed types dedup by normalized URL.
    existing_id = (
        _find_by_normalized_url(conn, normalized)
        if req.type != EntryType.NOTE and normalized
        else None
    )

    if existing_id:
        return _update_existing(conn, existing_id, req, content, now, embedder=embedder)

    entry_id = generate()
    note, note_source = _note_for_insert(req)
    # Notes never carry a dedup key: store url=None so they can never collide with a
    # URL-backed entry (provenance is kept in original_url). Read-side dedup is also skipped.
    stored_url = None if req.type == EntryType.NOTE else normalized
    try:
        conn.execute(
            """
            INSERT INTO entries
                (id, url, original_url, title, note, note_source, content, type,
                 source_url, saved_at, updated_at, status, attempts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0)
            """,
            (
                entry_id,
                stored_url,
                req.url,
                req.title,
                note,
                note_source,
                content,
                req.type.value,
                req.source_url,
                now,
                now,
            ),
        )
    except sqlite3.IntegrityError:
        # TOCTOU race: another writer committed this URL between our lookup and INSERT
        # (the partial unique index on url rejects the duplicate). Converge on the
        # now-committed row instead of surfacing a 500, preserving idempotent re-save
        # semantics (spec §10).
        conn.rollback()
        raced_id = _find_by_normalized_url(conn, normalized)
        if raced_id is None:
            raise  # not the URL-dedup conflict we expected; do not mask it
        return _update_existing(conn, raced_id, req, content, now, embedder=embedder)

    # For page type, do not index the body content in FTS, since it is not permanently persisted.
    fts_content = None if req.type == EntryType.PAGE else content
    index_entry(conn, entry_id, req.title, fts_content)
    conn.commit()
    return SaveEntryResponse(id=entry_id, status=SaveStatus.SAVED)


def _note_for_insert(req: CreateEntryRequest) -> tuple[str | None, str]:
    """Resolve the (note, note_source) to persist on a fresh insert.

    - type=note: the user's typed text is the authored note (its only copy).
    - any type with an explicit ``note`` override (spec §10): authored, skips later
      summarization, recorded with note_source='user'.
    - otherwise: no note yet; note_source='body' until the async ladder resolves one.
    """
    if req.type == EntryType.NOTE:
        return req.captured_text, _NOTE_TYPE_SOURCE
    if req.note is not None:
        return req.note, _NOTE_TYPE_SOURCE
    return None, _DEFAULT_NOTE_SOURCE


def _update_existing(
    conn: sqlite3.Connection,
    existing_id: str,
    req: CreateEntryRequest,
    content: str | None,
    now: str,
    *,
    embedder: Embedder | None = None,
) -> SaveEntryResponse:
    """Non-destructive update of an existing URL-backed entry (spec §10).

    Omitted optional fields keep their stored value (COALESCE), and a content-less
    save (e.g. a page) never nulls content that already holds the only copy of a
    clip/note. An explicit ``note`` override (spec §10) is written through with
    note_source='user' so it survives and is reflected back in retrieve.

    When the request carries a note override and an ``embedder`` is supplied, the note
    vector is re-indexed alongside FTS so both retrieval legs reflect the new note (spec
    §7.1 clear/replace invariant); otherwise the vector is left untouched.
    """
    existing = conn.execute(
        "select status from entries where id = ?", (existing_id,)
    ).fetchone()
    existing_status = existing["status"] if existing else "pending"

    # For page type, if it's already active, do not overwrite the discarded content
    # with the newly scraped text.
    if req.type == EntryType.PAGE and existing_status == "active":
        content = None

    conn.execute(
        """
        UPDATE entries
           SET original_url = COALESCE(?, original_url),
               title        = COALESCE(?, title),
               note         = COALESCE(?, note),
               note_source  = CASE WHEN ? IS NOT NULL THEN ? ELSE note_source END,
               content      = COALESCE(?, content),
               type         = ?,
               source_url   = COALESCE(?, source_url),
               updated_at   = ?
         WHERE id = ?
        """,
        (
            req.url,
            req.title,
            req.note,
            req.note,
            _NOTE_TYPE_SOURCE,
            content,
            req.type.value,
            req.source_url,
            now,
            existing_id,
        ),
    )
    # Re-index from the effective (post-COALESCE) row so the FTS index reflects
    # what is actually stored, not just the fields this request supplied.
    effective = conn.execute(
        "select title, content, type, note from entries where id = ?", (existing_id,)
    ).fetchone()
    # For page type, do not index the body content in FTS.
    fts_content = None if effective["type"] == "page" else effective["content"]
    index_entry(conn, existing_id, effective["title"], fts_content)
    # A note override changes the vectorized field, so re-embed in lockstep with FTS to
    # keep the two legs consistent (spec §7.1). Scoped to the override case so an
    # override-free re-save of an active entry does not blindly re-embed (spec §10).
    if req.note is not None and embedder is not None:
        index_entry_vector(conn, existing_id, embedder.embed(effective["note"]))
    conn.commit()
    return SaveEntryResponse(id=existing_id, status=SaveStatus.UPDATED)


def failed_entries(
    conn: sqlite3.Connection, *, limit: int = 50, offset: int = 0
) -> list[sqlite3.Row]:
    """Return a page of the user's failed entries for the 'needs attention' surface (§7.4).

    Read-only. Scoped to the current user's DB (the caller opens it). Newest first so the
    dashboard/badge shows the most recent failures at the top. Paged with ``limit``/
    ``offset`` so a user with many failures never fetches an unbounded set; the caller pairs
    this with ``failed_entries_total`` for the full count. Only the §7.4 repair fields are
    needed downstream, but returning the rows keeps the model mapping in one place.
    """
    if limit < 0:
        raise ValueError("limit must be >= 0")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    return conn.execute(
        """
        SELECT id, url, title, note, error_message, updated_at
          FROM entries WHERE status = 'failed'
         ORDER BY updated_at DESC
         LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()


def failed_entries_total(conn: sqlite3.Connection) -> int:
    """Total count of the user's failed entries (the badge count, independent of paging)."""
    return conn.execute(
        "SELECT count(*) FROM entries WHERE status = 'failed'"
    ).fetchone()[0]


def list_entries(
    conn: sqlite3.Connection,
    *,
    tags: list[str] | None = None,
    saved_after: str | None = None,
    saved_before: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Deterministic, newest-first listing of a user's entries (spec §10 list).

    The browse/filter complement to ``retrieve``: no search query, no relevance ranking.
    Filters are optional and ANDed together, then results are ordered by ``saved_at``
    descending and paged with ``limit``/``offset``. With no filters it returns the most
    recent saves.

    Args:
        tags: If given, keep entries carrying ANY of these tags (union) — unlike
            ``retrieve``'s conjunctive pre-filter, ``list`` browses by topic.
        saved_after: Inclusive lower bound on ``saved_at`` (ISO-8601 UTC). ISO-8601 UTC
            sorts lexically as it does chronologically, so this is a plain string compare.
        saved_before: Inclusive upper bound on ``saved_at`` (ISO-8601 UTC).
        limit: Maximum entries (default 20).
        offset: Entries to skip, for paging (default 0).

    Returns:
        Compact result dicts (``id, url, title, tags, note, note_source, content, type,
        saved_at``), newest first. Only ``active`` entries are returned — pending/failed rows aren't
        ready to surface (failures live in the §7.4 repair surface instead).
    """
    # Boundary guards: a negative limit becomes SQLite 'LIMIT -1' (unbounded) and a
    # negative offset is a silent SQL error; reject both with a clear message.
    if limit < 0:
        raise ValueError("limit must be >= 0")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    where = ["status = 'active'"]
    params: list = []
    if tags:
        placeholders = ",".join("?" for _ in tags)
        # ANY-tag (union): no GROUP BY/HAVING, so an entry matches if it carries any tag.
        where.append(f"id IN (SELECT entry_id FROM entry_tags WHERE tag IN ({placeholders}))")
        params.extend(tags)
    if saved_after is not None:
        where.append("saved_at >= ?")
        params.append(saved_after)
    if saved_before is not None:
        where.append("saved_at <= ?")
        params.append(saved_before)

    # Tie-break by id so entries sharing a saved_at paginate in a stable order.
    sql = f"""
        SELECT id, url, title, note, note_source, content, type, saved_at
          FROM entries
         WHERE {" AND ".join(where)}
         ORDER BY saved_at DESC, id DESC
         LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    return [compact_entry(conn, row) for row in rows]


def touch_last_accessed(conn: sqlite3.Connection, entry_ids: list[str]) -> None:
    """Stamp ``last_accessed_at`` = now (ISO-8601 UTC) for the given entries. Caller commits.

    Called with the MCP ``retrieve`` tool's final hit set so the store can surface
    recently-used memories (spec browse/relevance signal). One batched UPDATE regardless of
    the hit count. NOT called by ``list`` (deterministic browse) or on save, and the column
    is never returned in the compact projection sent to agents.
    """
    if not entry_ids:
        return
    now = _now_iso()
    placeholders = ",".join("?" for _ in entry_ids)
    conn.execute(
        f"UPDATE entries SET last_accessed_at = ? WHERE id IN ({placeholders})",
        (now, *entry_ids),
    )


def delete_entry(conn: sqlite3.Connection, entry_id: str) -> bool:
    """Delete an entry and ALL its derived data (spec §10 delete, §9.2 counters).

    Removes the entry (cascading its ``entry_tags`` edges), its ``entries_fts`` row, and
    its ``entries_vec`` note vector, then SYMMETRICALLY decrements ``tags.count`` and
    ``tag_cooccurrence.count`` for the removed edge set — the exact inverse of M5's write
    (canonical pair order, floor at 0). A tag whose count hits 0 is LEFT in place: its
    description + ``tags_vec`` embedding stay useful for canonicalization (spec §9.2).
    Returns True if a row was removed, False when the id is absent (so the tool can return
    ``deleted: false`` idempotently).
    """
    # Snapshot the edge set BEFORE the cascade so we know exactly which counters to undo.
    tags = [
        r[0]
        for r in conn.execute(
            "SELECT tag FROM entry_tags WHERE entry_id = ?", (entry_id,)
        )
    ]
    cursor = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    if cursor.rowcount == 0:
        conn.rollback()  # nothing existed; release the implicit transaction
        return False
    decrement_for_tags(conn, tags)  # the edges themselves cascaded via the FK
    remove_entry(conn, entry_id)
    remove_entry_vector(conn, entry_id)
    conn.commit()
    return True
