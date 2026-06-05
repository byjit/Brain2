"""FastAPI dependencies: current user and per-user DB connection.

Auth is deferred to M7. ``get_current_user`` is a stub that yields a fixed dev
user id from settings, so DB routing is already wired. ``get_db`` opens that
user's isolated SQLite connection for the request and closes it afterward.
"""

import sqlite3
from collections.abc import Iterator

from fastapi import Depends

from brain2.config import get_settings
from brain2.db.connection import open_user_db


def get_current_user() -> str:
    """Resolve the request's user id. Stubbed to the dev user until M7 auth lands."""
    return get_settings().dev_user_id


def get_db(user_id: str = Depends(get_current_user)) -> Iterator[sqlite3.Connection]:
    """Yield a connection to the current user's isolated DB for this request."""
    with open_user_db(user_id, data_dir=get_settings().data_dir) as conn:
        yield conn
