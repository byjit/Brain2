"""Per-user SQLite connection layer (spec §12).

Each user gets an isolated ``{DATA_DIR}/{user_id}.db``. Every connection:
- enforces WAL mode for concurrent reads during writes,
- loads the sqlite-vec extension so ``vec0`` tables work,
- applies the schema idempotently on open.

``get_db`` is the FastAPI dependency; ``open_user_db`` is the standalone helper used
by it and by tests (with a temp ``data_dir``).
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import sqlite_vec

from brain2.config import get_settings
from brain2.db.migrations import apply_schema


def user_db_path(user_id: str, data_dir: Path) -> Path:
    """Path to a user's isolated SQLite file."""
    return data_dir / f"{user_id}.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with WAL, foreign keys, sqlite-vec, and schema applied."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Load the sqlite-vec extension (required for the vec0 tables).
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # WAL serializes writers; wait up to 5s for a busy writer instead of surfacing
    # a raw "database is locked" error (do not rely on the driver default).
    conn.execute("PRAGMA busy_timeout=5000")

    apply_schema(conn)
    return conn


@contextmanager
def open_user_db(user_id: str, data_dir: Path) -> Iterator[sqlite3.Connection]:
    """Context-managed connection to a user's DB; closes on exit."""
    conn = _connect(user_db_path(user_id, data_dir))
    try:
        yield conn
    finally:
        conn.close()
