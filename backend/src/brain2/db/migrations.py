"""Schema migration runner.

The v1 schema is a single idempotent ``schema.sql`` (every statement uses
``IF NOT EXISTS``), so applying it on every open is safe and cheap. When the schema
evolves, additive migration files can be added and applied in order here.
"""

import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply the canonical schema to ``conn`` idempotently."""
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    _apply_additive_migrations(conn)
    conn.commit()


def _apply_additive_migrations(conn: sqlite3.Connection) -> None:
    """Additive column migrations for DBs created before a column existed.

    ``CREATE TABLE IF NOT EXISTS`` does not add columns to an already-created table, so
    new columns are added here guarded by a presence check (idempotent on every open).
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(entries)")}
    if "next_retry_at" not in columns:
        conn.execute("ALTER TABLE entries ADD COLUMN next_retry_at TEXT")
