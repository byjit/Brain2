"""Personal Access Tokens — API keys for CLI/Desktop MCP clients (spec §12).

Security model (the point of M7):
- The raw key is shown to the user EXACTLY ONCE at creation; only its SHA-256 hash is
  persisted, plus a short non-secret ``prefix`` for the dashboard listing.
- Keys are generated with ``secrets.token_urlsafe`` (high entropy).
- Verification hashes the presented key and compares with ``hmac.compare_digest``
  (constant-time) — and rejects revoked keys.
"""

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from nanoid import generate as nanoid

# Distinguishes an API key from a Brain2 JWT in the Bearer header (spec §12 routing).
KEY_PREFIX = "br2_live_"
# Length of the leading display fragment stored for the dashboard (non-secret).
_DISPLAY_PREFIX_LEN = len(KEY_PREFIX) + 6


@dataclass(frozen=True)
class CreatedKey:
    """The one-time result of creating a key. ``api_key`` is never persisted or re-shown."""

    id: str
    api_key: str
    prefix: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(raw_key: str) -> str:
    """SHA-256 hex digest of a raw key (the only form ever stored)."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def has_api_key_prefix(token: str) -> bool:
    """True if ``token`` is an API key (vs a Brain2 JWT) by its ``br2_live_`` prefix."""
    return token.startswith(KEY_PREFIX)


def create_key(conn: sqlite3.Connection, *, user_id: str, name: str | None = None) -> CreatedKey:
    """Generate a new API key for ``user_id``; store only its hash, return the raw key once."""
    raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
    key_id = nanoid()
    prefix = raw_key[:_DISPLAY_PREFIX_LEN]
    conn.execute(
        "INSERT INTO api_keys (id, user_id, token_hash, prefix, name, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (key_id, user_id, _hash(raw_key), prefix, name, _now()),
    )
    conn.commit()
    return CreatedKey(id=key_id, api_key=raw_key, prefix=prefix)


def verify_key(conn: sqlite3.Connection, raw_key: str) -> str | None:
    """Resolve a presented raw key to its ``user_id``, or None if invalid/revoked.

    Looks up by hash, then constant-time-compares the stored hash to defend against any
    timing leak, and bumps ``last_used_at`` on success.
    """
    if not raw_key or not has_api_key_prefix(raw_key):
        return None
    presented_hash = _hash(raw_key)
    row = conn.execute(
        "SELECT id, user_id, token_hash, revoked_at FROM api_keys WHERE token_hash=?",
        (presented_hash,),
    ).fetchone()
    if row is None:
        return None
    # Constant-time comparison (the SELECT already matched, but compare explicitly so the
    # verification path never short-circuits on a byte-by-byte string compare).
    if not hmac.compare_digest(row["token_hash"], presented_hash):
        return None
    if row["revoked_at"] is not None:
        return None
    conn.execute("UPDATE api_keys SET last_used_at=? WHERE id=?", (_now(), row["id"]))
    conn.commit()
    return row["user_id"]


def revoke_key(conn: sqlite3.Connection, user_id: str, key_id: str) -> bool:
    """Revoke a key owned by ``user_id``. Returns True if a live key was revoked."""
    cur = conn.execute(
        "UPDATE api_keys SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL",
        (_now(), key_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def list_keys(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    """List a user's keys for the dashboard — WITHOUT the secret or its hash."""
    rows = conn.execute(
        "SELECT id, prefix, name, created_at, last_used_at, revoked_at "
        "FROM api_keys WHERE user_id=? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "prefix": r["prefix"],
            "name": r["name"],
            "created_at": r["created_at"],
            "last_used_at": r["last_used_at"],
            "revoked": r["revoked_at"] is not None,
        }
        for r in rows
    ]
