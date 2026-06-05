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
    conn.commit()
