"""FastAPI application factory for the Brain2 backend.

Wires the REST routers and mounts the MCP server (streamable HTTP transport) so AI
agents can call the ``save``/``retrieve`` tools. Real auth and the async worker arrive
in later milestones (see backend/ARCHITECTURE.md). Run with:

    uv run uvicorn brain2.main:app --reload
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.transport_security import TransportSecuritySettings

from brain2.api import auth as auth_api
from brain2.api import entries, settings_tokens
from brain2.mcp import auth as mcp_auth
from brain2.mcp.server import build_mcp_server
from brain2.services.worker import run_worker_loop

# Path under which the MCP transport is mounted; the SDK serves the endpoint at
# ``{MCP_MOUNT}/mcp`` (streamable HTTP). Documented in ARCHITECTURE.md.
MCP_MOUNT = "/connect"


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

    # Configure CORS to allow access from Claude Web and other clients, exposing headers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://claude.ai",
            "https://chat.openai.com",
            "http://localhost:3000",
            "http://localhost:5173",
        ],
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["WWW-Authenticate"],
    )

    @app.middleware("http")
    async def mcp_auth_challenge_middleware(request: Request, call_next):
        """MCP connection-level authorization challenge middleware (spec §12).

        Bypasses CORS OPTIONS requests. Challenges a missing Authorization header AND an
        invalid/expired credential with HTTP 401 + ``WWW-Authenticate`` pointing at the
        Protected Resource Metadata — the signal MCP clients (Claude web) need to start
        or refresh their OAuth flow. Without this, an expired token would surface as a
        tool-level error inside a 200 response and the client would never re-authorize.
        """
        path = request.url.path
        if (path == f"{MCP_MOUNT}/mcp" or path.startswith(f"{MCP_MOUNT}/mcp/")) and request.method != "OPTIONS":
            base_url = str(request.base_url).rstrip("/")
            # RFC 9728 path-suffix metadata URL for the MCP resource.
            metadata_url = f"{base_url}/.well-known/oauth-protected-resource{MCP_MOUNT}/mcp"
            auth_header = request.headers.get("authorization")
            if not auth_header:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized"},
                    headers={"WWW-Authenticate": f'Bearer resource_metadata="{metadata_url}"'},
                )
            if mcp_auth.resolve_token_to_user_id(auth_header) is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or expired token"},
                    headers={
                        "WWW-Authenticate": (
                            f'Bearer error="invalid_token", resource_metadata="{metadata_url}"'
                        )
                    },
                )
        return await call_next(request)

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
