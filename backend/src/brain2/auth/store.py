"""Central auth store connection layer (spec §12).

A single ``auth.db`` holds identities, API-key hashes, and OAuth codes — separate from
the per-user ``{user_id}.db`` files, because a credential must resolve to a ``user_id``
*before* any per-user DB can be opened. Connections mirror the per-user db module: WAL,
foreign keys, and a busy timeout on every open. The (idempotent) schema script is applied
exactly ONCE per db path — guarded by a process-level set — so authenticated requests,
which open a fresh connection each time, never re-run the full schema (load amplification).
"""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from brain2.config import get_settings

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Paths whose schema has already been applied in THIS process. Guards against re-running
# the schema script on every connection. The lock makes first-use initialization
# thread-safe (concurrent requests may race to open the same db).
_initialized_paths: set[Path] = set()
_init_lock = threading.Lock()


def reset_initialized_paths() -> None:
    """Forget which paths have been initialized (test hook for tmp auth.db reuse)."""
    with _init_lock:
        _initialized_paths.clear()


def _ensure_schema(conn: sqlite3.Connection, db_path: Path) -> None:
    """Apply the schema script once per ``db_path`` (idempotent, thread-safe)."""
    resolved = db_path.resolve()
    if resolved in _initialized_paths:
        return
    with _init_lock:
        # Re-check under the lock: another thread may have initialized while we waited.
        if resolved in _initialized_paths:
            return
        conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
        _initialized_paths.add(resolved)


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open the auth DB with WAL, foreign keys, and schema applied once per path."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    _ensure_schema(conn, db_path)
    return conn


@contextmanager
def open_auth_db(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context-managed connection to the central auth DB; closes on exit.

    ``db_path`` defaults to the configured ``auth_db_path`` (tests pass a tmp path).
    """
    path = db_path if db_path is not None else get_settings().auth_db_path
    conn = _connect(Path(path))
    try:
        yield conn
    finally:
        conn.close()
