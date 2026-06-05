"""MCP request authentication and per-request user routing (spec §12).

A Bearer token on the MCP HTTP request is resolved to a ``user_id`` and held in a
``ContextVar`` for the duration of the request, so tool functions can open the right
per-user DB without threading the user through every call. Resolution routes an API key
or a Brain2 access token through the central ``auth.db`` (M7), replacing the M2 dev stub.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from brain2.auth import bearer
from brain2.auth.store import open_auth_db
from brain2.config import get_settings

# The resolved user id for the in-flight MCP request (None outside a request).
_current_user: ContextVar[str | None] = ContextVar("mcp_current_user", default=None)


def resolve_token_to_user_id(authorization_header: str | None) -> str | None:
    """Resolve an ``Authorization`` header to a user id, or None if invalid (spec §12).

    Routes an API key (``br2_live_`` prefix) or a Brain2 access token through auth.db. All
    four MCP tools require a valid Bearer credential (spec §10).
    """
    settings = get_settings()
    with open_auth_db(settings.auth_db_path) as conn:
        return bearer.resolve_bearer(
            authorization_header, conn=conn, secret=settings.jwt_secret
        )


@contextmanager
def user_scope(user_id: str) -> Iterator[None]:
    """Bind ``user_id`` as the current MCP user for the duration of the block."""
    token = _current_user.set(user_id)
    try:
        yield
    finally:
        _current_user.reset(token)


def current_user_id() -> str:
    """Return the current MCP user id, raising if no authenticated request is bound."""
    user_id = _current_user.get()
    if user_id is None:
        raise PermissionError("Unauthenticated: a valid Bearer token is required.")
    return user_id
