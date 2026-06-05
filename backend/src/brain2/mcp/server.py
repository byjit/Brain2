"""FastMCP server exposing Brain2's ``save`` and ``retrieve`` tools.

Transport: streamable HTTP (the SDK's current recommendation), run statelessly with
JSON responses so it scales horizontally. The spec (§6) names SSE; we diverge to the
SDK-recommended streamable HTTP and note this in ARCHITECTURE.md.

Auth: each tool reads the request's ``Authorization`` Bearer header, resolves it to a
user id (M2 stub, M7 real), and runs the shared service inside that user's scope so the
per-user DB routing flows through MCP exactly as it does over REST.

Tool parameters are declared individually (not wrapped in one model) so FastMCP emits a
flat, agent-friendly ``inputSchema`` matching the spec §10 contract; outputs are typed
Pydantic/list returns so FastMCP emits structured output.
"""

from typing import Annotated, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

from brain2.mcp import auth, tools
from brain2.models.entries import EntryType

SERVER_NAME = "brain2_mcp"


class SaveOutput(BaseModel):
    """Result of an upsert (spec §10 save)."""

    id: str = Field(description="Entry id")
    status: str = Field(description="'saved' for a new entry, 'updated' for an existing URL")


class RetrieveResult(BaseModel):
    """One compact search hit (spec §10 result shape)."""

    id: str
    url: str | None
    title: str | None
    tags: list[str]
    note: str | None
    content: str | None
    type: str
    saved_at: str
    score: float


class DeleteOutput(BaseModel):
    """Result of a delete (spec §10 delete)."""

    deleted: bool = Field(description="True if the entry existed and was removed, else False")


class TagInfo(BaseModel):
    """One tag in the landscape (spec §10 get_tags result shape)."""

    tag: str
    description: str
    count: int
    co_occurs_with: list[str] = Field(
        description="Top co-occurring tag names, ordered by co-occurrence count"
    )


def _resolve_user(ctx: Context) -> str:
    """Resolve the request's Bearer token to a user id, or raise PermissionError."""
    request = ctx.request_context.request
    header = request.headers.get("authorization") if request is not None else None
    user_id = auth.resolve_token_to_user_id(header)
    if user_id is None:
        raise PermissionError("Unauthenticated: a valid Bearer token is required.")
    return user_id


def build_mcp_server(transport_security: TransportSecuritySettings | None = None) -> FastMCP:
    """Construct the FastMCP server with the save and retrieve tools registered.

    ``transport_security`` overrides the SDK's default DNS-rebinding allow-list (kept
    on for production); tests pass a permissive setting for in-process ASGI clients.
    """
    mcp = FastMCP(
        SERVER_NAME,
        stateless_http=True,
        json_response=True,
        transport_security=transport_security,
    )

    @mcp.tool(
        name="save",
        annotations={
            "title": "Save to Brain2",
            "readOnlyHint": False,
            "destructiveHint": True,  # upsert can overwrite fields of an existing URL
            "idempotentHint": True,   # re-saving the same URL converges on the same row
            "openWorldHint": True,    # persists to the user's external memory store
        },
    )
    def save(
        ctx: Context,
        type: Annotated[EntryType, Field(description="Capture type: page, clip, conversation, or note")],
        url: Annotated[str | None, Field(description="Source URL; required for non-note types, normalized for dedup")] = None,
        title: Annotated[str | None, Field(description="Title; auto-fetched later if omitted")] = None,
        note: Annotated[
            str | None,
            Field(description="For type=note this is the user's note text (required); for URL-backed types, an optional captured body"),
        ] = None,
        tags: Annotated[
            list[str] | None,
            Field(description="Optional tags; normalized + canonicalized and merged additively (auto-tagging still runs)"),
        ] = None,
        source_url: Annotated[str | None, Field(description="For clips: the page the selection came from")] = None,
    ) -> SaveOutput:
        """Save (upsert) a memory into the user's Brain2 store.

        Deduplicates URL-backed entries by normalized URL: a new URL inserts a pending
        entry; a known URL updates it (omitted fields are preserved). type=note has no
        URL and never dedups; its ``note`` is the text the user wrote. Optional ``tags``
        are canonicalized before write and merged additively, so they cannot fragment the
        tag vocabulary.

        Returns:
            SaveOutput: {id, status} where status is "saved" or "updated".
        """
        user_id = _resolve_user(ctx)
        with auth.user_scope(user_id):
            result = tools.save_tool(
                type=type.value,
                url=url,
                title=title,
                note=note,
                tags=tags,
                source_url=source_url,
            )
        return SaveOutput(**result)

    @mcp.tool(
        name="retrieve",
        annotations={
            "title": "Search Brain2",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    def retrieve(
        ctx: Context,
        query: Annotated[str, Field(description="Free-text keyword query; FTS5 special characters are handled safely")],
        tags: Annotated[list[str] | None, Field(description="Pre-filter: entry must carry ALL of these tags")] = None,
        type: Annotated[EntryType | None, Field(description="Pre-filter by entry type")] = None,
        limit: Annotated[int, Field(ge=1, le=100, description="Maximum results (default 10)")] = 10,
    ) -> list[RetrieveResult]:
        """Search the user's Brain2 memories by keyword (BM25 over title, tags, content).

        Optional ``tags`` (must match ALL) and ``type`` are applied as pre-filters before
        ranking. Returns compact hits ordered best-first; higher ``score`` is more relevant.

        Returns:
            list[RetrieveResult]: id, url, title, tags, note, content, type, saved_at, score.
        """
        user_id = _resolve_user(ctx)
        with auth.user_scope(user_id):
            hits = tools.retrieve_tool(
                query=query,
                tags=tags,
                type=type.value if type is not None else None,
                limit=limit,
            )
        return [RetrieveResult(**hit) for hit in hits]

    @mcp.tool(
        name="delete",
        annotations={
            "title": "Delete from Brain2",
            "readOnlyHint": False,
            "destructiveHint": True,   # removes the entry and all its derived data
            "idempotentHint": True,    # deleting an absent id is a safe no-op
            "openWorldHint": True,
        },
    )
    def delete(
        ctx: Context,
        id: Annotated[str, Field(description="Id of the entry to delete")],
    ) -> DeleteOutput:
        """Delete an entry and all its derived data from the user's Brain2 store.

        Removes the entry, its search index, its note vector and its tag edges, and
        decrements tag counts + co-occurrence. Idempotent: deleting an unknown id returns
        ``deleted: false`` rather than erroring.

        Returns:
            DeleteOutput: {deleted} — true if removed, false if the id was absent.
        """
        user_id = _resolve_user(ctx)
        with auth.user_scope(user_id):
            result = tools.delete_tool(id=id)
        return DeleteOutput(**result)

    @mcp.tool(
        name="get_tags",
        annotations={
            "title": "List Brain2 tags",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    def get_tags(
        ctx: Context,
        limit: Annotated[int, Field(ge=1, le=500, description="Maximum tags to return (default 50)")] = 50,
        sort: Annotated[
            Literal["count", "name"],
            Field(description="'count' (default, descending) or 'name' (ascending)"),
        ] = "count",
    ) -> list[TagInfo]:
        """List the user's tags with counts, descriptions, and co-occurrence (spec §10).

        Lets an agent understand the tag landscape and pick tags to pre-filter ``retrieve``.
        Paged by ``limit``; ``sort`` is 'count' (default, heaviest first) or 'name'.

        Returns:
            list[TagInfo]: {tag, description, count, co_occurs_with}.
        """
        user_id = _resolve_user(ctx)
        with auth.user_scope(user_id):
            rows = tools.get_tags_tool(limit=limit, sort=sort)
        return [TagInfo(**row) for row in rows]

    return mcp
