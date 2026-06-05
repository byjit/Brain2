"""Entries REST API (spec §6, §7.1)."""

import sqlite3

from fastapi import APIRouter, Depends, status

from brain2.deps import get_db
from brain2.models.entries import CreateEntryRequest, SaveEntryResponse
from brain2.services.entries import save_entry

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
