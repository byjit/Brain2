"""Bearer credential resolution — the single credential->user_id router (spec §12).

Parses an ``Authorization: Bearer <token>`` header. If the token carries the API-key
prefix it is validated against ``api_keys`` (hash lookup); otherwise it is validated as a
Brain2 JWT. Both resolve to a ``user_id`` (which the caller uses to open ``{user_id}.db``)
or None for missing/invalid/expired/revoked credentials.
"""

import sqlite3

from brain2.auth import api_keys, jwt_service

_BEARER_PREFIX = "bearer "


def parse_bearer(authorization_header: str | None) -> str | None:
    """Extract the raw token from an ``Authorization`` header value, or None."""
    if not authorization_header:
        return None
    if not authorization_header.lower().startswith(_BEARER_PREFIX):
        return None
    token = authorization_header[len(_BEARER_PREFIX):].strip()
    return token or None


def resolve_bearer(
    authorization_header: str | None,
    *,
    conn: sqlite3.Connection,
    secret: str,
) -> str | None:
    """Resolve a Bearer header to a ``user_id``, or None if the credential is invalid.

    API keys (``br2_live_`` prefix) are validated against ``api_keys``; everything else is
    validated as a Brain2 JWT. This is the one place the two credential types converge.
    """
    token = parse_bearer(authorization_header)
    if token is None:
        return None
    if api_keys.has_api_key_prefix(token):
        user_id = api_keys.verify_key(conn, token)
    else:
        user_id = jwt_service.verify_token(token, secret=secret)

    if user_id is None:
        return None

    # Verify that the user exists in the central users table
    row = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return user_id

