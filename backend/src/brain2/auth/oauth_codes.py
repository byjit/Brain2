"""OAuth 2.1 authorization-code store with PKCE S256 (spec §12).

Codes are single-use, short-lived, and bound to the S256 ``code_challenge`` + the client
``redirect_uri``. ``/oauth/token`` consumes a code by verifying the presented
``code_verifier`` against the stored challenge (constant-time) and matching the redirect
URI. Reuse is rejected by marking the row consumed atomically. Only S256 is supported
('plain' is never accepted, per the security constraints).
"""

import base64
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

_S256 = "S256"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def verify_pkce_s256(code_verifier: str, code_challenge: str) -> bool:
    """Return True iff BASE64URL(SHA256(code_verifier)) == code_challenge (constant-time)."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(expected, code_challenge)


def issue_code(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    code_challenge: str,
    redirect_uri: str,
    ttl: int,
    client_id: str | None = None,
) -> str:
    """Issue a single-use authorization code bound to the S256 challenge + redirect_uri.

    ``client_id`` records which OAuth client the code was issued to, so the token
    endpoint can reject a redemption attempted under a different client identity.
    """
    # Opportunistically purge spent/expired rows so this shared table stays bounded.
    conn.execute(
        "DELETE FROM oauth_codes WHERE consumed_at IS NOT NULL OR expires_at < ?",
        (_now().isoformat(),),
    )
    code = secrets.token_urlsafe(32)
    expires_at = (_now() + timedelta(seconds=ttl)).isoformat()
    conn.execute(
        "INSERT INTO oauth_codes "
        "(code, user_id, code_challenge, code_challenge_method, redirect_uri, client_id, "
        "expires_at) VALUES (?,?,?,?,?,?,?)",
        (code, user_id, code_challenge, _S256, redirect_uri, client_id, expires_at),
    )
    conn.commit()
    return code


def consume_code(
    conn: sqlite3.Connection,
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str | None = None,
) -> str | None:
    """Verify + consume a code, returning its ``user_id`` or None if invalid.

    Rejects: unknown/already-consumed codes, expired codes, a redirect_uri mismatch, a
    client_id that does not match the one the code was issued to (STRICT: a bound code
    cannot be redeemed by omitting client_id; only legacy NULL rows skip the check), and
    a code_verifier that does not match the stored S256 challenge. Consumption is atomic
    (single-use): the row is marked consumed before returning success, so a replay fails.
    """
    row = conn.execute(
        "SELECT user_id, code_challenge, redirect_uri, client_id, expires_at, consumed_at "
        "FROM oauth_codes WHERE code=?",
        (code,),
    ).fetchone()
    if row is None or row["consumed_at"] is not None:
        return None
    if row["redirect_uri"] != redirect_uri:
        return None
    if row["client_id"] is not None and client_id != row["client_id"]:
        return None
    if datetime.fromisoformat(row["expires_at"]) < _now():
        return None
    if not verify_pkce_s256(code_verifier, row["code_challenge"]):
        return None
    # Atomically mark consumed; guard on consumed_at IS NULL so a concurrent replay loses.
    cur = conn.execute(
        "UPDATE oauth_codes SET consumed_at=? WHERE code=? AND consumed_at IS NULL",
        (_now().isoformat(), code),
    )
    conn.commit()
    if cur.rowcount == 0:
        return None
    return row["user_id"]
