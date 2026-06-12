"""Auth-layer FastAPI dependencies (spec §12).

- ``get_auth_db`` yields a connection to the central auth.db for a request.
- ``get_session_user`` authenticates the dashboard/session endpoints: it accepts the
  Brain2 session JWT from the httpOnly cookie OR a Bearer credential, resolving either to
  a ``user_id`` (so the same endpoints work from the browser session and from a token).
"""

import sqlite3
from collections.abc import Iterator
from urllib.parse import urlsplit

from fastapi import Cookie, Depends, Header, HTTPException, status

from brain2.auth import bearer, jwt_service
from brain2.auth.store import open_auth_db
from brain2.config import Settings, get_settings

# Name of the dashboard session cookie carrying the Brain2 session JWT.
SESSION_COOKIE = "brain2_session"

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required.",
    headers={"WWW-Authenticate": "Bearer"},
)

_CROSS_ORIGIN_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Cross-origin request rejected."
)


def _origin_of(url: str) -> str | None:
    """Return the ``scheme://host[:port]`` origin of ``url``, or None if it has no host."""
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def _allowed_origins(settings: Settings) -> set[str]:
    """Origins permitted to make cookie-authed state-changing requests (spec §12).

    The dashboard origin (where the session cookie lives) plus the origins of any
    configured OAuth redirect URIs (the same first-party surfaces) — derived, not a new
    config knob (YAGNI).
    """
    origins: set[str] = set()
    dashboard = _origin_of(settings.dashboard_url)
    if dashboard:
        origins.add(dashboard)
    for uri in settings.oauth_redirect_uris:
        origin = _origin_of(uri)
        if origin:
            origins.add(origin)
    return origins


def get_auth_db() -> Iterator[sqlite3.Connection]:
    """Yield a connection to the central auth.db for the request."""
    with open_auth_db(get_settings().auth_db_path) as conn:
        yield conn


def get_session_user(
    brain2_session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> str:
    """Resolve the dashboard user from the session cookie or a Bearer credential, or 401.

    The session cookie holds a Brain2 JWT; a Bearer header (API key or JWT) is also
    accepted so the token-management endpoints work from both the browser and a CLI.
    """
    settings = get_settings()
    if brain2_session:
        user_id = jwt_service.verify_token(
            brain2_session, secret=settings.jwt_secret, expected_typ="session"
        )
        if user_id is not None:
            # Verify the user actually exists in the central users table
            row = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row is not None:
                return user_id
    user_id = bearer.resolve_bearer(authorization, conn=conn, secret=settings.jwt_secret)
    if user_id is None:
        raise _UNAUTHENTICATED
    return user_id


def require_same_origin(
    brain2_session: str | None = Cookie(default=None),
    origin: str | None = Header(default=None),
    referer: str | None = Header(default=None),
) -> None:
    """CSRF defense-in-depth for COOKIE-authed mutating endpoints (spec §12).

    The session cookie is SameSite=Lax, which already blocks cross-site no-header
    navigations; this is a second layer for the state-changing token endpoints. We only
    enforce it when the request carries the ambient session cookie — a Bearer credential
    cannot be set cross-site by an attacker, so Bearer-authed CLIs/extensions are exempt.

    Decision: allow when BOTH ``Origin`` and ``Referer`` are absent (same-origin browsers
    legitimately omit them, and SameSite=Lax covers the cross-site no-header case). When an
    ``Origin`` is present it must match an allowed origin; otherwise fall back to the
    ``Referer``'s origin. A mismatch is rejected with 403.
    """
    # No session cookie => Bearer (or unauthenticated). Not CSRF-able; skip the check.
    if not brain2_session:
        return
    # Same-origin browsers may omit both headers; SameSite=Lax already covers cross-site.
    if not origin and not referer:
        return
    request_origin = origin or (_origin_of(referer) if referer else None)
    if request_origin in _allowed_origins(get_settings()):
        return
    raise _CROSS_ORIGIN_FORBIDDEN
