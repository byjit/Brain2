"""FastAPI application factory for the Brain2 backend.

Wires the API routers. Auth, the async worker, and MCP transport arrive in later
milestones (see backend/ARCHITECTURE.md). Run with:

    uv run uvicorn brain2.main:app --reload
"""

from fastapi import FastAPI

from brain2.api import entries


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Brain2 Backend",
        version="0.1.0",
        description="Per-user SQLite memory store. Save once, recall anywhere over MCP.",
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok"}

    app.include_router(entries.router)
    return app


# Module-level app for `uvicorn brain2.main:app`.
app = create_app()
