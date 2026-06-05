"""MCP request authentication and per-request user routing.

A Bearer token on the MCP HTTP request is resolved to a ``user_id`` and held in a
``ContextVar`` for the duration of the request, so tool functions can open the right
per-user DB without threading the user through every call. Token validation is a stub
that reuses ``get_current_user``'s dev user (real OAuth/API-key validation is M7).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from brain2.config import get_settings

# The resolved user id for the in-flight MCP request (None outside a request).
_current_user: ContextVar[str | None] = ContextVar("mcp_current_user", default=None)

_BEARER_PREFIX = "bearer "


def resolve_token_to_user_id(authorization_header: str | None) -> str | None:
    """Resolve an ``Authorization`` header value to a user id, or None if invalid.

    M2 stub: any well-formed ``Bearer <token>`` maps to the dev user so per-user DB
    routing already flows through MCP. M7 replaces this with real API-key/JWT lookup.
    """
    if not authorization_header:
        return None
    if not authorization_header.lower().startswith(_BEARER_PREFIX):
        return None
    token = authorization_header[len(_BEARER_PREFIX):].strip()
    if not token:
        return None
    return get_settings().dev_user_id


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
