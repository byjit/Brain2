"""Transport-free implementations of the MCP ``save`` and ``retrieve`` tools.

These functions hold the tool logic and are unit-testable without an MCP client: they
resolve the current user (set by the transport auth layer), open that user's DB, and
delegate to the shared entries/search services so REST and MCP share one implementation.
``brain2.mcp.server`` wraps them with typed FastMCP tool definitions.
"""

from brain2.config import get_settings
from brain2.db.connection import open_user_db
from brain2.mcp import auth
from brain2.models.entries import CreateEntryRequest
from brain2.services.entries import save_entry
from brain2.services.search import search_entries


def _open_current_user_db():
    """Open the per-user DB for the authenticated MCP request."""
    user_id = auth.current_user_id()
    return open_user_db(user_id, data_dir=get_settings().data_dir)


def save_tool(
    *,
    type: str,
    url: str | None = None,
    title: str | None = None,
    note: str | None = None,
    source_url: str | None = None,
) -> dict:
    """Upsert an entry for the current user; returns ``{id, status}`` (spec §10 save).

    Reuses the M1 ``save_entry`` service (the same path as POST /entries). Per spec §10
    the MCP ``note`` field is the authored text: for ``type=note`` it is the user's note
    (its only persisted copy, so it flows to captured_text); for URL-backed types it is
    the note override that skips LLM summarization (it flows to the note column and is
    reflected back in retrieve). Agent-supplied tags are deferred to M5.
    """
    is_note_type = type == "note"
    req = CreateEntryRequest(
        type=type,
        url=url,
        title=title,
        captured_text=note if is_note_type else None,
        note=None if is_note_type else note,
        source_url=source_url,
    )
    with _open_current_user_db() as conn:
        result = save_entry(conn, req)
    return {"id": result.id, "status": result.status.value}


def retrieve_tool(
    *,
    query: str,
    tags: list[str] | None = None,
    type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """BM25 keyword search for the current user (spec §10 retrieve, §11 BM25 half).

    Returns the compact result shape (``id, url, title, tags, note, content, type,
    saved_at, score``) ordered best-first. ``tags``/``type`` are applied as pre-filters.
    """
    with _open_current_user_db() as conn:
        return search_entries(conn, query, tags=tags, type=type, limit=limit)
