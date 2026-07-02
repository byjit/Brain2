"""Schema migration runner.

The v1 schema is a single idempotent ``schema.sql`` (every statement uses
``IF NOT EXISTS``), so applying it is safe. Additive column migrations for DBs created
before a column existed live in ``_apply_additive_migrations``.

To avoid re-parsing the DDL and re-running the ``PRAGMA table_info`` checks on every
per-request connection open (spec §12 opens one connection per request), the whole
apply step is gated on ``PRAGMA user_version``: when the stored version already matches
``SCHEMA_VERSION`` the connection skips both the ``executescript`` and the additive
checks; otherwise it applies them and stamps the current version. Bump ``SCHEMA_VERSION``
whenever ``schema.sql`` changes or an additive migration is added so existing DBs pick
the change up on their next open.
"""

import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Bump on any change to schema.sql or the additive migrations below so existing user DBs
# re-apply on their next open. v1 was the implicit unversioned schema; v2 adds the
# idx_entry_tags_tag / idx_entries_type / idx_tag_cooccurrence_tag_b indexes and the
# entries.last_accessed_at column.
SCHEMA_VERSION = 2


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply the canonical schema to ``conn`` idempotently, gated on ``user_version``.

    When the DB's ``user_version`` already equals ``SCHEMA_VERSION`` the DDL is skipped
    entirely (it is idempotent, so this is purely a per-request performance gate); when it
    differs, the full schema + additive migrations run and the version is stamped.
    """
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current == SCHEMA_VERSION:
        return
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    _apply_additive_migrations(conn)
    # PRAGMA does not accept a bound parameter, so interpolate the trusted int constant.
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def _apply_additive_migrations(conn: sqlite3.Connection) -> None:
    """Additive column migrations for DBs created before a column existed.

    ``CREATE TABLE IF NOT EXISTS`` does not add columns to an already-created table, so
    new columns are added here guarded by a presence check (idempotent on every open).
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(entries)")}
    if "next_retry_at" not in columns:
        conn.execute("ALTER TABLE entries ADD COLUMN next_retry_at TEXT")
    if "last_accessed_at" not in columns:
        conn.execute("ALTER TABLE entries ADD COLUMN last_accessed_at TEXT")
