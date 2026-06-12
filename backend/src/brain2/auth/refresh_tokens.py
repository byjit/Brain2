"""OAuth refresh tokens — long-lived, hashed at rest, rotated on every use (spec §12).

Brain2 access tokens live ~1h; MCP clients (Claude web custom connectors) hold a
connection far longer. A refresh token lets the client mint a new access token without
interactive re-auth. The security model mirrors API keys:

- The raw token is returned to the client EXACTLY ONCE; only its SHA-256 hash is stored.
- Consuming a token ROTATES it: the old row is marked ``rotated_at`` and a replacement
  is issued, so a replayed (leaked) refresh token is rejected rather than honored.
- Tokens carry the ``client_id`` they were issued to; a presented client_id that
  contradicts the stored one is rejected.
"""

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from nanoid import generate as nanoid

# Distinguishes a refresh token from an access JWT / API key at a glance in logs and
# client configs; carries no routing meaning (refresh tokens are only valid at /oauth/token).
_TOKEN_PREFIX = "br2_rt_"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(raw_token: str) -> str:
    """SHA-256 hex digest of a raw refresh token (the only form ever stored)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    client_id: str | None,
    ttl: int,
) -> str:
    """Issue a refresh token for ``user_id``; store only its hash, return the raw once."""
    raw_token = _TOKEN_PREFIX + secrets.token_urlsafe(32)
    expires_at = (_now() + timedelta(seconds=ttl)).isoformat()
    conn.execute(
        "INSERT INTO oauth_refresh_tokens "
        "(id, user_id, client_id, token_hash, expires_at, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (nanoid(), user_id, client_id, _hash(raw_token), expires_at, _now().isoformat()),
    )
    conn.commit()
    return raw_token


def consume(
    conn: sqlite3.Connection,
    *,
    raw_token: str,
    client_id: str | None,
    ttl: int,
) -> tuple[str, str] | None:
    """Rotate a refresh token: verify, retire it, and issue a replacement.

    Returns ``(user_id, new_raw_token)`` or None for an unknown, already-rotated
    (replay), expired, or client-mismatched token. Rotation is atomic — the UPDATE
    guards on ``rotated_at IS NULL`` so a concurrent replay loses the race.
    """
    if not raw_token:
        return None
    presented_hash = _hash(raw_token)
    row = conn.execute(
        "SELECT id, user_id, client_id, token_hash, expires_at, rotated_at "
        "FROM oauth_refresh_tokens WHERE token_hash=?",
        (presented_hash,),
    ).fetchone()
    if row is None or row["rotated_at"] is not None:
        return None
    # Constant-time comparison (the SELECT already matched; never short-circuit here).
    if not hmac.compare_digest(row["token_hash"], presented_hash):
        return None
    if datetime.fromisoformat(row["expires_at"]) < _now():
        return None
    # STRICT client binding: a token issued to a client can only be rotated by that
    # client naming itself — omitting client_id does not bypass the check. Only legacy
    # NULL rows (issued before binding existed) skip it.
    if row["client_id"] is not None and client_id != row["client_id"]:
        return None
    cur = conn.execute(
        "UPDATE oauth_refresh_tokens SET rotated_at=? WHERE id=? AND rotated_at IS NULL",
        (_now().isoformat(), row["id"]),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    new_raw = issue(conn, user_id=row["user_id"], client_id=row["client_id"], ttl=ttl)
    return row["user_id"], new_raw
