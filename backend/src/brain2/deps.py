"""FastAPI dependencies: Bearer authentication, current user, and per-user DB (spec §12).

Every REST entry endpoint authenticates a ``Authorization: Bearer`` credential (an API
key or a Brain2 JWT/session token), resolves it to a ``user_id`` against the central
``auth.db``, and opens that user's isolated ``{user_id}.db``. Missing/invalid/expired/
revoked credentials yield a 401. Tests override ``get_current_user`` with a known user via
the dependency-override seam, so the suite stays offline.
"""

import sqlite3
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, status

from brain2.auth import bearer
from brain2.auth.store import open_auth_db
from brain2.config import get_settings
from brain2.db.connection import open_user_db

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="A valid Bearer credential (API key or access token) is required.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(authorization: str | None = Header(default=None)) -> str:
    """Resolve the request's Bearer credential to a ``user_id`` (spec §12), or 401.

    Routes an API key (``br2_live_`` prefix) or a Brain2 JWT to its owner via the central
    auth.db. Tests override this dependency to inject a known user without touching auth.db.
    """
    settings = get_settings()
    with open_auth_db(settings.auth_db_path) as auth_conn:
        user_id = bearer.resolve_bearer(
            authorization, conn=auth_conn, secret=settings.jwt_secret
        )
    if user_id is None:
        raise _UNAUTHENTICATED
    return user_id


def get_db(user_id: str = Depends(get_current_user)) -> Iterator[sqlite3.Connection]:
    """Yield a connection to the current user's isolated DB for this request."""
    with open_user_db(user_id, data_dir=get_settings().data_dir) as conn:
        yield conn
