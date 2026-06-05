"""API key management endpoint tests (M7 deliverable 7).

POST creates a key (shown once); GET lists without the secret; DELETE revokes. All require
auth. Uses the session-cookie/JWT seam: the conftest seeds a user; here we authenticate
with the seeded API key as the Bearer credential (resolves the same user via auth.db).
"""

import os

import pytest
from fastapi.testclient import TestClient

from brain2.main import create_app


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """A TestClient hitting the real auth dependency (no override), authed via Bearer."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from brain2.config import get_settings

    get_settings.cache_clear()
    app = create_app(enable_worker=False)
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {os.environ['AUTH_API_KEY']}"})
    return client


@pytest.fixture
def cookie_client(tmp_path, monkeypatch):
    """A TestClient authed via the dashboard session COOKIE (the CSRF-exposed seam)."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from brain2.auth import jwt_service
    from brain2.auth.deps import SESSION_COOKIE
    from brain2.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    app = create_app(enable_worker=False)
    client = TestClient(app)
    # Seed a real session JWT for the seeded test user (resolves via the session cookie).
    token = jwt_service.issue_token(
        "test-user", secret=settings.jwt_secret, ttl=settings.session_ttl, typ="session"
    )
    client.cookies.set(SESSION_COOKIE, token)
    return client


def test_create_token_returns_secret_once(auth_client):
    r = auth_client.post("/settings/tokens", json={"name": "my-cli"})
    assert r.status_code == 201
    body = r.json()
    assert body["api_key"].startswith("br2_live_")
    assert body["prefix"]
    assert body["id"]


def test_list_tokens_never_returns_secret(auth_client):
    created = auth_client.post("/settings/tokens", json={"name": "listed"}).json()
    r = auth_client.get("/settings/tokens")
    assert r.status_code == 200
    items = r.json()
    assert any(i["id"] == created["id"] for i in items)
    for item in items:
        assert "api_key" not in item
        assert "token_hash" not in item
        assert created["api_key"] not in item.values()
        assert set(item) >= {"id", "prefix", "name", "created_at", "revoked"}


def test_delete_token_revokes_it(auth_client):
    created = auth_client.post("/settings/tokens", json={"name": "to-revoke"}).json()
    r = auth_client.delete(f"/settings/tokens/{created['id']}")
    assert r.status_code == 200
    assert r.json()["revoked"] is True
    # The revoked key is listed as revoked.
    items = auth_client.get("/settings/tokens").json()
    assert next(i for i in items if i["id"] == created["id"])["revoked"] is True


def test_endpoints_require_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from brain2.config import get_settings

    get_settings.cache_clear()
    client = TestClient(create_app(enable_worker=False))
    assert client.get("/settings/tokens").status_code == 401
    assert client.post("/settings/tokens", json={"name": "x"}).status_code == 401
    assert client.delete("/settings/tokens/abc").status_code == 401


# --- CSRF defense-in-depth (same-origin check on cookie-authed mutations) ---------------

# Default DASHBOARD_URL (config.py) when none is configured in tests.
_DASHBOARD_ORIGIN = "http://localhost:5173"


def test_cookie_post_with_foreign_origin_is_rejected(cookie_client):
    r = cookie_client.post(
        "/settings/tokens",
        json={"name": "x"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert r.status_code == 403


def test_cookie_delete_with_foreign_origin_is_rejected(cookie_client):
    r = cookie_client.delete(
        "/settings/tokens/some-id", headers={"Origin": "https://evil.example.com"}
    )
    assert r.status_code == 403


def test_cookie_post_with_dashboard_origin_succeeds(cookie_client):
    r = cookie_client.post(
        "/settings/tokens", json={"name": "ok"}, headers={"Origin": _DASHBOARD_ORIGIN}
    )
    assert r.status_code == 201


def test_cookie_post_with_dashboard_referer_succeeds(cookie_client):
    """A request with only a Referer (no Origin) is allowed when the referer origin matches."""
    r = cookie_client.post(
        "/settings/tokens",
        json={"name": "ok2"},
        headers={"Referer": f"{_DASHBOARD_ORIGIN}/settings"},
    )
    assert r.status_code == 201


def test_cookie_post_with_no_origin_or_referer_is_allowed(cookie_client):
    """Same-origin browsers may omit Origin/Referer; SameSite=Lax already covers cross-site
    no-header navigations, so we allow the request when BOTH headers are absent."""
    r = cookie_client.post("/settings/tokens", json={"name": "ok3"})
    assert r.status_code == 201


def test_cookie_referer_foreign_origin_is_rejected(cookie_client):
    r = cookie_client.post(
        "/settings/tokens",
        json={"name": "x"},
        headers={"Referer": "https://evil.example.com/page"},
    )
    assert r.status_code == 403


def test_bearer_request_skips_same_origin_check(auth_client):
    """Bearer-authed requests carry no ambient cookie, so they aren't CSRF-able; a foreign
    Origin must NOT block them (CLIs/extensions legitimately send arbitrary/no Origin)."""
    r = auth_client.post(
        "/settings/tokens",
        json={"name": "cli"},
        headers={"Origin": "https://some-cli-origin.example"},
    )
    assert r.status_code == 201
