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
from brain2.services.url_normalize import normalize_url

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


def save_entry(conn: sqlite3.Connection, req: CreateEntryRequest) -> SaveEntryResponse:
    """Upsert an entry and return its id and save status.

    - type=note: never dedups (no URL); its text is the note authored by the user.
    - other types: dedup by normalized URL — update if present, else insert pending.
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
        return _update_existing(conn, existing_id, req, content, now)

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
        return _update_existing(conn, raced_id, req, content, now)

    index_entry(conn, entry_id, req.title, content)
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
) -> SaveEntryResponse:
    """Non-destructive update of an existing URL-backed entry (spec §10).

    Omitted optional fields keep their stored value (COALESCE), and a content-less
    save (e.g. a page) never nulls content that already holds the only copy of a
    clip/note. An explicit ``note`` override (spec §10) is written through with
    note_source='user' so it survives and is reflected back in retrieve.
    """
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
        "select title, content from entries where id = ?", (existing_id,)
    ).fetchone()
    index_entry(conn, existing_id, effective["title"], effective["content"])
    conn.commit()
    return SaveEntryResponse(id=existing_id, status=SaveStatus.UPDATED)


def delete_entry(conn: sqlite3.Connection, entry_id: str) -> bool:
    """Delete an entry and its derived FTS row (spec §10 delete).

    Returns True if a row was removed. ``entry_tags`` rows cascade via the schema
    FK; tag-count/vector cleanup arrives with those features in later milestones.
    """
    cursor = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    if cursor.rowcount == 0:
        return False
    remove_entry(conn, entry_id)
    conn.commit()
    return True
