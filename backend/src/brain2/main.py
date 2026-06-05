"""FastAPI application factory for the Brain2 backend.

Wires the REST routers and mounts the MCP server (streamable HTTP transport) so AI
agents can call the ``save``/``retrieve`` tools. Real auth and the async worker arrive
in later milestones (see backend/ARCHITECTURE.md). Run with:

    uv run uvicorn brain2.main:app --reload
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from brain2.api import auth as auth_api
from brain2.api import entries, settings_tokens
from brain2.mcp.server import build_mcp_server
from brain2.services.worker import run_worker_loop

# Path under which the MCP transport is mounted; the SDK serves the endpoint at
# ``{MCP_MOUNT}/mcp`` (streamable HTTP). Documented in ARCHITECTURE.md.
MCP_MOUNT = "/mcp"


def create_app(
    mcp_transport_security: TransportSecuritySettings | None = None,
    *,
    enable_worker: bool = True,
) -> FastAPI:
    """Build and configure the FastAPI application.

    ``mcp_transport_security`` is forwarded to the MCP server for tests that need a
    permissive DNS-rebinding allow-list; production uses the SDK's secure default.
    ``enable_worker`` runs the background enrichment drain loop in the lifespan; tests
    that don't need it can disable it to keep the event loop quiet.
    """
    mcp = build_mcp_server(transport_security=mcp_transport_security)
    mcp_app = mcp.streamable_http_app()

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # The streamable-HTTP session manager must run for the app's lifetime.
        async with mcp.session_manager.run():
            worker_task = (
                asyncio.create_task(run_worker_loop()) if enable_worker else None
            )
            try:
                yield
            finally:
                if worker_task is not None:
                    worker_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await worker_task

    app = FastAPI(
        title="Brain2 Backend",
        version="0.1.0",
        description="Per-user SQLite memory store. Save once, recall anywhere over MCP.",
        lifespan=lifespan,
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    app.include_router(entries.router)
    app.include_router(auth_api.router)
    app.include_router(settings_tokens.router)
    # Mount the MCP ASGI app; tools live at ``{MCP_MOUNT}/mcp``.
    app.mount(MCP_MOUNT, mcp_app)
    return app


# Module-level app for `uvicorn brain2.main:app`.
app = create_app()
