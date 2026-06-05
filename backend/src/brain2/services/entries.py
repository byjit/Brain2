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
        # Non-destructive update (spec §10): omitted optional fields keep their
        # stored value (COALESCE), and a content-less save (e.g. a page) never
        # nulls content that already holds the only copy of a clip/note.
        conn.execute(
            """
            UPDATE entries
               SET original_url = COALESCE(?, original_url),
                   title        = COALESCE(?, title),
                   content      = COALESCE(?, content),
                   type         = ?,
                   source_url   = COALESCE(?, source_url),
                   updated_at   = ?
             WHERE id = ?
            """,
            (req.url, req.title, content, req.type.value, req.source_url, now, existing_id),
        )
        conn.commit()
        return SaveEntryResponse(id=existing_id, status=SaveStatus.UPDATED)

    entry_id = generate()
    note_source = _NOTE_TYPE_SOURCE if req.type == EntryType.NOTE else _DEFAULT_NOTE_SOURCE
    note = req.captured_text if req.type == EntryType.NOTE else None
    # Notes never carry a dedup key: store url=None so they can never collide with a
    # URL-backed entry (provenance is kept in original_url). Read-side dedup is also skipped.
    stored_url = None if req.type == EntryType.NOTE else normalized
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
    conn.commit()
    return SaveEntryResponse(id=entry_id, status=SaveStatus.SAVED)
