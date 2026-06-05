"""REST entry endpoints enforce Bearer auth (M7 deliverable 4).

Without a credential they 401; with the seeded API key (conftest) they authenticate and
route to that user's DB. Proves the dev stub is gone and the real dependency is applied.
"""

import os

import pytest
from fastapi.testclient import TestClient

from brain2.main import create_app


@pytest.fixture
def no_auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from brain2.config import get_settings

    get_settings.cache_clear()
    return TestClient(create_app(enable_worker=False))


def test_entries_require_auth(no_auth_client):
    assert no_auth_client.post("/entries", json={"type": "note", "captured_text": "x"}).status_code == 401
    assert no_auth_client.get("/entries/failed").status_code == 401


def test_entries_accept_valid_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from brain2.config import get_settings

    get_settings.cache_clear()
    client = TestClient(create_app(enable_worker=False))
    client.headers.update({"Authorization": f"Bearer {os.environ['AUTH_API_KEY']}"})
    r = client.post("/entries", json={"type": "note", "captured_text": "authed note"})
    assert r.status_code == 201
    assert r.json()["status"] == "saved"


def test_entries_reject_garbage_bearer(no_auth_client):
    no_auth_client.headers.update({"Authorization": "Bearer not-a-real-token"})
    assert no_auth_client.post(
        "/entries", json={"type": "note", "captured_text": "x"}
    ).status_code == 401
