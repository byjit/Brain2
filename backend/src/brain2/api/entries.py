"""Entries REST API (spec §6, §7.1, §7.4)."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from brain2.config import get_settings
from brain2.deps import get_db
from brain2.models.entries import (
    CreateEntryRequest,
    EntryResponse,
    FailedEntriesResponse,
    FailedEntry,
    RepairEntryRequest,
    SaveEntryResponse,
    DeleteEntryResponse,
)
from brain2.services.entries import failed_entries, failed_entries_total, save_entry
from brain2.services.providers.factory import build_providers, build_tagging_providers
from brain2.services.repair import repair_entry

router = APIRouter(prefix="/entries", tags=["entries"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SaveEntryResponse)
def create_entry(
    req: CreateEntryRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> SaveEntryResponse:
    """Save (upsert) an entry and return immediately.

    Normalizes the URL, applies conditional content persistence, and upserts by
    normalized URL. All enrichment (note, tags, indexing) runs async later; this
    endpoint is pure synchronous DB work and returns well under 2s (spec §7.1).
    """
    return save_entry(conn, req)


# Registered BEFORE the parameterized /{id} route so the literal "failed" path is not
# captured as an entry id.
@router.get("/failed", response_model=FailedEntriesResponse)
def list_failed_entries(
    conn: sqlite3.Connection = Depends(get_db),
    limit: int = Query(default=50, ge=0, le=200),
    offset: int = Query(default=0, ge=0),
) -> FailedEntriesResponse:
    """List the current user's failed entries for the 'needs attention' surface (spec §7.4).

    Returns a page of failed rows (``limit`` default 50, max 200; ``offset`` for paging)
    plus ``total`` — the full failed count for the extension badge / web dashboard, so the
    response shape stays ``{total, entries}`` while the row set is now bounded. Scoped to
    the current user's DB.
    """
    rows = failed_entries(conn, limit=limit, offset=offset)
    return FailedEntriesResponse(
        total=failed_entries_total(conn),
        entries=[FailedEntry(**dict(r)) for r in rows],
    )


@router.patch("/{entry_id}", response_model=EntryResponse)
def repair_entry_endpoint(
    entry_id: str,
    req: RepairEntryRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> EntryResponse:
    """Repair an entry from a user-supplied note (spec §7.4 PATCH /entries/{id}).

    Sets note = user text (note_source='user'), clears the error, resets retries, and
    re-enters processing using the note as the basis (embed -> auto-tag -> index -> active).
    A failed (or active) entry is always recoverable this way. Providers are wired from
    config (real Gemini when keyed, else offline fakes).
    """
    settings = get_settings()
    _, _, embedder = build_providers(settings)
    tagger, structured_source = build_tagging_providers(settings)
    row = repair_entry(
        conn,
        entry_id,
        note=req.note,
        tags=req.tags,
        embedder=embedder,
        tagger=tagger,
        structured_source=structured_source,
        threshold=settings.canonicalize_threshold,
        max_tags=settings.tags_per_entry_max,
        nearest_limit=settings.nearest_tags_limit,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entry not found")
    return EntryResponse(**dict(row))


@router.delete("/{entry_id}", response_model=DeleteEntryResponse)
def delete_entry_endpoint(
    entry_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> DeleteEntryResponse:
    """Delete an entry and all its derived data (spec §10 delete)."""
    from brain2.services.entries import delete_entry
    existed = delete_entry(conn, entry_id)
    return DeleteEntryResponse(deleted=existed)
