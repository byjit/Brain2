"""Shared pytest fixtures.

A TestClient wired to a temp DATA_DIR so tests never touch the real ./data.
The get_db dependency is overridden to open a per-test user DB under tmp_path.
"""

import pytest
from fastapi.testclient import TestClient

from brain2.db.connection import open_user_db
from brain2.deps import get_current_user, get_db
from brain2.main import create_app

_DEV_USER = "test-user"


@pytest.fixture
def client(tmp_path):
    app = create_app()

    def _override_get_db():
        with open_user_db(_DEV_USER, data_dir=tmp_path) as conn:
            yield conn

    app.dependency_overrides[get_current_user] = lambda: _DEV_USER
    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as c:
        yield c
