"""Transport-free implementations of the MCP ``save`` and ``retrieve`` tools.

These functions hold the tool logic and are unit-testable without an MCP client: they
resolve the current user (set by the transport auth layer), open that user's DB, and
delegate to the shared entries/search services so REST and MCP share one implementation.
``brain2.mcp.server`` wraps them with typed FastMCP tool definitions.
"""

import re
from datetime import datetime, timedelta, timezone

from brain2.config import get_settings
from brain2.db.connection import open_user_db
from brain2.mcp import auth
from brain2.models.entries import CreateEntryRequest
from brain2.services.entries import delete_entry, list_entries, save_entry
from brain2.services.providers.factory import build_providers
from brain2.services.search import hybrid_search
from brain2.services.tagging import apply_agent_tags
from brain2.services.tags_service import list_tags


def _open_current_user_db():
    """Open the per-user DB for the authenticated MCP request."""
    user_id = auth.current_user_id()
    return open_user_db(user_id, data_dir=get_settings().data_dir)


# Compact, agent-friendly relative-window grammar: "<amount><unit>", e.g. "30m", "24h",
# "3d", "2w". Maps each unit letter to its timedelta keyword.
_WINDOW_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
_WINDOW_PATTERN = re.compile(r"^\s*(\d+)\s*([mhdw])\s*$", re.IGNORECASE)


def _window_to_saved_after(window: str, *, now: datetime | None = None) -> str:
    """Translate a relative time window into an inclusive ``saved_after`` lower bound.

    Accepts a compact ``<amount><unit>`` string — ``m`` (minutes), ``h`` (hours), ``d``
    (days) or ``w`` (weeks), e.g. ``"24h"`` (last 24 hours) or ``"3d"`` (last 3 days) — and
    returns the ISO-8601 UTC cutoff ``now - window``. The cutoff is formatted with
    ``isoformat()`` so it matches the stored ``saved_at`` column exactly, keeping the
    downstream lexical range compare in ``list_entries`` sound. ``now`` is injectable for
    deterministic tests.
    """
    match = _WINDOW_PATTERN.match(window)
    if not match:
        raise ValueError(
            "window must be a positive integer followed by a unit — m (minutes), "
            "h (hours), d (days), or w (weeks), e.g. '24h' or '3d'"
        )
    amount = int(match.group(1))
    unit = _WINDOW_UNITS[match.group(2).lower()]
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(**{unit: amount})).isoformat()


def save_tool(
    *,
    type: str,
    url: str | None = None,
    title: str | None = None,
    note: str | None = None,
    tags: list[str] | None = None,
    source_url: str | None = None,
) -> dict:
    """Upsert an entry for the current user; returns ``{id, status}`` (spec §10 save).

    Reuses the M1 ``save_entry`` service (the same path as POST /entries). Per spec §10
    the MCP ``note`` field is the authored text: for ``type=note`` it is the user's note
    (its only persisted copy, so it flows to captured_text); for URL-backed types it is
    the note override that skips LLM summarization (it flows to the note column and is
    reflected back in retrieve).

    Optional ``tags`` are agent-supplied (spec §10): they skip the LLM proposal step but
    are still normalized + canonicalized (snap-to-near-duplicate or create) and merged
    ADDITIVELY into the entry's tags, so an agent cannot fragment the vocabulary. Automatic
    background tagging (the worker) still runs for the rest.
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
    # Supply the embedder so a re-save of an existing URL with a changed note override
    # refreshes the note vector in lockstep with FTS (spec §7.1). Wired from config
    # (real Gemini when keyed, else the offline fake).
    settings = get_settings()
    _, _, embedder = build_providers(settings)
    with _open_current_user_db() as conn:
        result = save_entry(conn, req, embedder=embedder)
        if tags:
            # Canonicalize-on-write so agent tags cannot fragment the vocabulary (spec §10).
            apply_agent_tags(
                conn,
                result.id,
                tags,
                embedder=embedder,
                threshold=settings.canonicalize_threshold,
                max_tags=settings.tags_per_entry_max,
            )
            conn.commit()
    return {"id": result.id, "status": result.status.value}


def retrieve_tool(
    *,
    query: str,
    tags: list[str] | None = None,
    type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Hybrid search for the current user (spec §10 retrieve, §11 BM25 + vector + RRF).

    Fuses BM25 (set A) and vector KNN over the note embedding (set B) with RRF (k=60).
    Returns the compact result shape (``id, url, title, tags, note, content, type,
    saved_at, score``) ordered best-first. ``tags``/``type`` are applied as pre-filters
    to both legs. The embedder is wired from config (real Gemini when keyed, else fake).
    """
    # Validate at the boundary: a negative limit otherwise hits vec0 KNN as an opaque
    # DB error on one leg and becomes an unbounded SQLite 'LIMIT -1' on the other.
    if limit < 0:
        raise ValueError("limit must be >= 0")
    _, _, embedder = build_providers(get_settings())
    with _open_current_user_db() as conn:
        return hybrid_search(conn, query, embedder=embedder, tags=tags, type=type, limit=limit)


def list_tool(
    *,
    tags: list[str] | None = None,
    window: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """Deterministic entry listing for the current user (spec §10 list).

    The browse/filter complement to ``retrieve``: filter by ``tags`` (ANY match) and/or a
    relative ``window`` (e.g. ``"24h"`` for the last 24 hours, ``"3d"`` for the last three
    days), ordered newest-first, paged via ``limit``/``offset``. Returns only active
    entries in the compact result shape (no relevance ``score``). The window is resolved to
    a ``saved_after`` cutoff before hitting the ``list_entries`` primitive.
    """
    # Validate at the boundary so a direct/REST caller gets a clear error, not a raw
    # SQLite failure (the MCP layer additionally constrains these via Field bounds).
    if limit < 0:
        raise ValueError("limit must be >= 0")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    saved_after = _window_to_saved_after(window) if window else None
    with _open_current_user_db() as conn:
        return list_entries(
            conn,
            tags=tags,
            saved_after=saved_after,
            limit=limit,
            offset=offset,
        )


def delete_tool(*, id: str) -> dict:
    """Delete an entry + all its derived data for the current user (spec §10 delete).

    Removes the entry, its FTS row, its note vector and its tag edges, and symmetrically
    decrements tag counts + co-occurrence. Returns ``{deleted: true}`` when a row was
    removed, ``{deleted: false}`` when the id was absent (idempotent).
    """
    with _open_current_user_db() as conn:
        return {"deleted": delete_entry(conn, id)}


def get_tags_tool(*, limit: int = 50, sort: str = "count") -> list[dict]:
    """List the user's tags with counts, descriptions, and co-occurrence (spec §10 get_tags).

    Paged: ``limit`` (default 50) and ``sort`` ('count' default desc, or 'name' asc).
    Returns ``{tag, description, count, co_occurs_with}`` items in the §10 shape.
    """
    with _open_current_user_db() as conn:
        return list_tags(conn, limit=limit, sort=sort)
