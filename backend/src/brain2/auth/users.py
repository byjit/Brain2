"""User identity store + implicit first-time signup (spec §12).

The first successful authentication creates a ``users`` row AND the user's isolated
``{user_id}.db`` (running the per-user schema). A returning ``google_sub`` resolves to
the same ``user_id``. The ``user_id`` is a server-generated nanoid — never derived from
client input — so it is inherently path-safe for ``{user_id}.db`` routing (spec §12).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from nanoid import generate as nanoid

from brain2.db.connection import open_user_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_user_db(user_id: str, data_dir: Path) -> None:
    """Create the user's per-user DB and apply the schema (idempotent)."""
    # open_user_db applies the schema on open; opening then closing materializes the file.
    with open_user_db(user_id, data_dir=data_dir):
        pass


def upsert_by_google_sub(
    conn: sqlite3.Connection,
    *,
    google_sub: str,
    email: str | None,
    data_dir: Path,
) -> str:
    """Resolve a Google identity to a ``user_id``, creating the user on first sight.

    Implicit signup (spec §12): a new ``google_sub`` inserts a ``users`` row with a fresh
    nanoid ``user_id`` and creates ``{user_id}.db``. A known ``google_sub`` returns its
    existing ``user_id`` unchanged.
    """
    existing = conn.execute(
        "SELECT user_id FROM users WHERE google_sub=?", (google_sub,)
    ).fetchone()
    if existing is not None:
        return existing["user_id"]

    user_id = nanoid()
    conn.execute(
        "INSERT INTO users (user_id, google_sub, email, created_at) VALUES (?,?,?,?)",
        (user_id, google_sub, email, _now()),
    )
    conn.commit()
    _ensure_user_db(user_id, data_dir)
    return user_id


def get_user(conn: sqlite3.Connection, user_id: str) -> dict | None:
    """Return a user's public profile (``user_id``, ``email``, ``created_at``) or None."""
    row = conn.execute(
        "SELECT user_id, email, created_at FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    return dict(row) if row is not None else None
