"""Dynamic Client Registration (RFC 7591) — public OAuth clients only (spec §12).

MCP clients that implement the MCP authorization flow (e.g. Claude web custom
connectors) discover ``registration_endpoint`` in the AS metadata, POST their metadata
to ``/oauth/register``, and receive a ``client_id``. Only PUBLIC clients are supported:
``token_endpoint_auth_method`` is always ``none`` and no secret is ever issued —
possession is proven by PKCE (S256), exactly as for the extension.

Registered ``redirect_uris`` are stored verbatim and matched EXACTLY at
``/oauth/authorize`` (no substring or prefix matching), preserving the open-redirect
posture of the static allowlist.
"""

import json
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlsplit

from nanoid import generate as nanoid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_acceptable_redirect_uri(uri: str) -> bool:
    """True for an absolute https URI, or http on a loopback host (native-client dev).

    RFC 8252 §7.3 permits plain http only for loopback redirects; everything else must
    be https so an authorization code can never transit cleartext.
    """
    parts = urlsplit(uri)
    if not parts.netloc:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")


def register_client(
    conn: sqlite3.Connection,
    *,
    redirect_uris: list[str],
    client_name: str | None = None,
) -> dict:
    """Register a public client and return its RFC 7591 client-information response.

    The caller validates ``redirect_uris`` (non-empty, each acceptable) before calling;
    this function only persists and shapes the response.
    """
    client_id = nanoid()
    created_at = _now()
    conn.execute(
        "INSERT INTO oauth_clients (client_id, client_name, redirect_uris, created_at) "
        "VALUES (?,?,?,?)",
        (client_id, client_name, json.dumps(redirect_uris), created_at),
    )
    conn.commit()
    return {
        "client_id": client_id,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }


def get_client(conn: sqlite3.Connection, client_id: str | None) -> dict | None:
    """Return a registered client (``client_id``, ``client_name``, ``redirect_uris``),
    or None if ``client_id`` is not a dynamically registered client."""
    if not client_id:
        return None
    row = conn.execute(
        "SELECT client_id, client_name, redirect_uris FROM oauth_clients WHERE client_id=?",
        (client_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "client_id": row["client_id"],
        "client_name": row["client_name"],
        "redirect_uris": json.loads(row["redirect_uris"]),
    }
