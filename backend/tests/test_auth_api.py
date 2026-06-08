"""Google Sign-In + OAuth 2.1 + PKCE endpoint tests (M7 deliverables 5 & 6).

All offline via FakeIdentityProvider (no network, no real Google). Covers: login redirect
with CSRF state; callback implicit-signup creating the user + their {user_id}.db; returning
sub maps to same user; /auth/me + logout; OAuth authorize+token PKCE happy path; reused
code, wrong verifier, non-allowlisted redirect_uri, and missing state/challenge rejected.
"""

import base64
import hashlib

import pytest
from fastapi.testclient import TestClient

from brain2.auth.deps import SESSION_COOKIE
from brain2.db.connection import user_db_path
from brain2.main import create_app

_REDIRECT = "https://app.example.com/callback"


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """A TestClient with an offline FakeIdentityProvider and a tmp data dir + allowlist."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "users"))
    monkeypatch.setenv("OAUTH_REDIRECT_URIS", f'["{_REDIRECT}"]')
    monkeypatch.setenv("COOKIE_SECURE", "false")
    from brain2.config import get_settings

    get_settings.cache_clear()
    app = create_app(enable_worker=False)
    # Redirects are not auto-followed so we can assert on the 3xx Location.
    return TestClient(app, follow_redirects=False)


def _data_dir(tmp_path):
    return tmp_path / "users"


# --- Google Sign-In (deliverable 5) ---------------------------------------------------


def test_login_redirects_to_google_with_state(app_client):
    r = app_client.get("/auth/login")
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    assert "accounts.google.com" in loc
    assert "state=" in loc  # CSRF state present


def test_callback_implicit_signup_creates_user_and_db(app_client, tmp_path):
    # Begin login to obtain the signed state, then complete the callback.
    login = app_client.get("/auth/login")
    state = _extract_state(login.headers["location"])

    r = app_client.get("/api/auth/callback/google", params={"code": "code-1", "state": state})
    assert r.status_code in (302, 307)
    # A session cookie was set.
    assert SESSION_COOKIE in r.cookies or any(
        SESSION_COOKIE in c for c in r.headers.get_list("set-cookie")
    )
    # /auth/me now returns the user.
    me = app_client.get("/auth/me")
    assert me.status_code == 200
    user_id = me.json()["user_id"]
    assert user_db_path(user_id, _data_dir(tmp_path)).exists()


def test_callback_rejects_bad_state(app_client):
    r = app_client.get("/api/auth/callback/google", params={"code": "code-1", "state": "forged"})
    assert r.status_code == 400


def test_callback_rejects_state_not_bound_to_browser(app_client):
    """A signed state from a DIFFERENT browser (no matching nonce cookie) is rejected.

    Login CSRF defense: the state nonce must match the httpOnly cookie set at /auth/login.
    Here we replay a valid state without the cookie the server set for it.
    """
    state = _extract_state(app_client.get("/auth/login").headers["location"])
    # Drop the nonce cookie the server set, simulating a cross-browser/CSRF replay.
    app_client.cookies.clear()
    r = app_client.get("/api/auth/callback/google", params={"code": "code-1", "state": state})
    assert r.status_code == 400


def test_returning_user_same_id(app_client):
    s1 = _extract_state(app_client.get("/auth/login").headers["location"])
    app_client.get("/api/auth/callback/google", params={"code": "code-1", "state": s1})
    uid1 = app_client.get("/auth/me").json()["user_id"]

    # Fresh client (clear cookies), same Google sub via the same fake code.
    app_client.cookies.clear()
    s2 = _extract_state(app_client.get("/auth/login").headers["location"])
    app_client.get("/api/auth/callback/google", params={"code": "code-1", "state": s2})
    uid2 = app_client.get("/auth/me").json()["user_id"]
    assert uid1 == uid2


def test_logout_clears_session(app_client):
    s = _extract_state(app_client.get("/auth/login").headers["location"])
    app_client.get("/api/auth/callback/google", params={"code": "code-1", "state": s})
    assert app_client.get("/auth/me").status_code == 200
    app_client.post("/auth/logout")
    app_client.cookies.clear()
    assert app_client.get("/auth/me").status_code == 401


def test_logout_delete_cookie_mirrors_set_attributes(app_client):
    """The logout Set-Cookie must carry the same Path/SameSite as the session cookie so
    browsers reliably clear it (mismatched attributes can be ignored)."""
    s = _extract_state(app_client.get("/auth/login").headers["location"])
    app_client.get("/api/auth/callback/google", params={"code": "code-1", "state": s})
    r = app_client.post("/auth/logout")
    delete_headers = [
        c for c in r.headers.get_list("set-cookie") if c.startswith(f"{SESSION_COOKIE}=")
    ]
    assert delete_headers, "logout must emit a Set-Cookie clearing the session cookie"
    cookie = delete_headers[0].lower()
    assert "path=/" in cookie
    assert "samesite=lax" in cookie


def test_session_cookie_not_accepted_as_bearer(app_client):
    """A long-lived session-cookie JWT must NOT work as a short-lived OAuth access token.

    Distinguishing token types keeps the short access TTL meaningful even if the session
    cookie value leaks.
    """
    s = _extract_state(app_client.get("/auth/login").headers["location"])
    app_client.get("/api/auth/callback/google", params={"code": "code-1", "state": s})
    # Grab the raw session cookie value the server set.
    session_jwt = app_client.cookies.get(SESSION_COOKIE)
    assert session_jwt
    # Used as a Bearer against an auth-gated endpoint it must be rejected.
    app_client.cookies.clear()
    r = app_client.get(
        "/settings/tokens", headers={"Authorization": f"Bearer {session_jwt}"}
    )
    assert r.status_code == 401


def test_me_requires_auth(app_client):
    assert app_client.get("/auth/me").status_code == 401


# --- OAuth 2.1 + PKCE (deliverable 6) -------------------------------------------------


def _login(app_client):
    s = _extract_state(app_client.get("/auth/login").headers["location"])
    app_client.get("/api/auth/callback/google", params={"code": "code-1", "state": s})


def test_oauth_pkce_happy_path(app_client):
    _login(app_client)
    verifier = "v" * 64
    authorize = app_client.get(
        "/oauth/authorize",
        params={
            "client_id": "ext",
            "redirect_uri": _REDIRECT,
            "response_type": "code",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "state": "client-state",
        },
    )
    assert authorize.status_code in (302, 307)
    loc = authorize.headers["location"]
    assert loc.startswith(_REDIRECT)
    assert "state=client-state" in loc
    code = _extract_query(loc, "code")

    token = app_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200
    assert token.json()["access_token"]
    assert token.json()["token_type"].lower() == "bearer"


def test_oauth_non_allowlisted_redirect_rejected(app_client):
    _login(app_client)
    r = app_client.get(
        "/oauth/authorize",
        params={
            "client_id": "ext",
            "redirect_uri": "https://evil.example.com/cb",
            "response_type": "code",
            "code_challenge": _challenge("v" * 64),
            "code_challenge_method": "S256",
            "state": "x",
        },
    )
    assert r.status_code == 400


def test_oauth_missing_challenge_or_state_rejected(app_client):
    _login(app_client)
    base = {
        "client_id": "ext",
        "redirect_uri": _REDIRECT,
        "response_type": "code",
        "code_challenge_method": "S256",
    }
    # Missing code_challenge.
    assert app_client.get(
        "/oauth/authorize", params={**base, "state": "x"}
    ).status_code == 400
    # Missing state.
    assert app_client.get(
        "/oauth/authorize", params={**base, "code_challenge": _challenge("v" * 64)}
    ).status_code == 400


def test_oauth_plain_method_rejected(app_client):
    _login(app_client)
    r = app_client.get(
        "/oauth/authorize",
        params={
            "client_id": "ext",
            "redirect_uri": _REDIRECT,
            "response_type": "code",
            "code_challenge": "v" * 43,
            "code_challenge_method": "plain",
            "state": "x",
        },
    )
    assert r.status_code == 400


def test_oauth_authorize_requires_login(app_client):
    r = app_client.get(
        "/oauth/authorize",
        params={
            "client_id": "ext",
            "redirect_uri": _REDIRECT,
            "response_type": "code",
            "code_challenge": _challenge("v" * 64),
            "code_challenge_method": "S256",
            "state": "x",
        },
    )
    assert r.status_code == 302
    assert "/auth/login" in r.headers["location"]
    assert "next=" in r.headers["location"]


def test_oauth_wrong_verifier_rejected(app_client):
    _login(app_client)
    code = _authorize_code(app_client, "v" * 64)
    r = app_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT,
            "code_verifier": "wrong" * 13,
        },
    )
    assert r.status_code == 400


def test_oauth_reused_code_rejected(app_client):
    _login(app_client)
    verifier = "v" * 64
    code = _authorize_code(app_client, verifier)
    ok = app_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT,
            "code_verifier": verifier,
        },
    )
    assert ok.status_code == 200
    again = app_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT,
            "code_verifier": verifier,
        },
    )
    assert again.status_code == 400


def test_oauth_token_is_valid_bearer(app_client):
    """The issued OAuth access token authenticates a protected REST endpoint."""
    _login(app_client)
    verifier = "v" * 64
    code = _authorize_code(app_client, verifier)
    access = app_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT,
            "code_verifier": verifier,
        },
    ).json()["access_token"]
    # Use it as a Bearer against /settings/tokens (auth-gated).
    listed = app_client.get(
        "/settings/tokens", headers={"Authorization": f"Bearer {access}"}
    )
    assert listed.status_code == 200


# --- helpers --------------------------------------------------------------------------


def _extract_query(url: str, key: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(url).query)[key][0]


def _extract_state(google_url: str) -> str:
    return _extract_query(google_url, "state")


def _authorize_code(app_client, verifier: str) -> str:
    loc = app_client.get(
        "/oauth/authorize",
        params={
            "client_id": "ext",
            "redirect_uri": _REDIRECT,
            "response_type": "code",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "state": "x",
        },
    ).headers["location"]
    return _extract_query(loc, "code")
