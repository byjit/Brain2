"""Dynamic Client Registration (RFC 7591) + refresh-token grant tests (spec §12).

The flows an MCP client like Claude web performs: register itself at /oauth/register,
authorize against ITS registered redirect_uri, exchange the code for an access +
refresh token pair, then rotate the refresh token to outlive the access TTL. All
offline via the FakeIdentityProvider.
"""

import base64
import hashlib

import pytest
from fastapi.testclient import TestClient

from brain2.main import create_app

# In the static allowlist (the extension path); registered clients use their own URIs.
_STATIC_REDIRECT = "https://app.example.com/callback"
# A registered MCP client's callback — NOT in the static allowlist.
_CLIENT_REDIRECT = "https://claude.ai/api/mcp/auth_callback"


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _extract_query(url: str, key: str) -> str:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(url).query)[key][0]


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """A TestClient with an offline FakeIdentityProvider and a tmp data dir + allowlist."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "users"))
    monkeypatch.setenv("OAUTH_REDIRECT_URIS", f'["{_STATIC_REDIRECT}"]')
    monkeypatch.setenv("COOKIE_SECURE", "false")
    from brain2.config import get_settings

    get_settings.cache_clear()
    app = create_app(enable_worker=False)
    return TestClient(app, follow_redirects=False)


def _login(app_client):
    # A code distinct from test_auth_api's "code-1": the fake provider derives the Google
    # sub from the code, and the seeded auth.db is session-scoped — signing up the same
    # sub here would steal test_auth_api's implicit-signup assertion.
    state = _extract_query(app_client.get("/auth/login").headers["location"], "state")
    app_client.get("/api/auth/callback/google", params={"code": "code-dcr", "state": state})


def _register(app_client, redirect_uris=None) -> dict:
    r = app_client.post(
        "/oauth/register",
        json={"redirect_uris": redirect_uris or [_CLIENT_REDIRECT], "client_name": "Claude"},
    )
    assert r.status_code == 201
    return r.json()


def _consent_page(app_client, verifier: str, *, client_id: str, redirect_uri: str):
    """GET /oauth/authorize for a registered client → the consent page response."""
    return app_client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "state": "x",
        },
    )


def _consent_token_of(page_html: str) -> str:
    import re

    match = re.search(r'name="consent" value="([^"]+)"', page_html)
    assert match, "consent page must embed the consent token"
    return match.group(1)


def _submit_consent(
    app_client, verifier: str, *, client_id: str, redirect_uri: str, consent: str, decision: str = "allow"
):
    return app_client.post(
        "/oauth/authorize",
        data={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "state": "x",
            "consent": consent,
            "decision": decision,
        },
    )


def _authorize_code(app_client, verifier: str, *, client_id: str, redirect_uri: str) -> str:
    """Walk the full registered-client flow: consent page → Allow → code."""
    page = _consent_page(app_client, verifier, client_id=client_id, redirect_uri=redirect_uri)
    assert page.status_code == 200
    consent = _consent_token_of(page.text)
    allowed = _submit_consent(
        app_client, verifier, client_id=client_id, redirect_uri=redirect_uri, consent=consent
    )
    assert allowed.status_code == 302
    return _extract_query(allowed.headers["location"], "code")


def _exchange(app_client, code: str, verifier: str, *, client_id: str, redirect_uri: str):
    return app_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
            "client_id": client_id,
        },
    )


# --- Dynamic Client Registration --------------------------------------------------------


def test_register_returns_public_client(app_client):
    info = _register(app_client)
    assert info["client_id"]
    assert info["redirect_uris"] == [_CLIENT_REDIRECT]
    assert info["token_endpoint_auth_method"] == "none"
    assert "refresh_token" in info["grant_types"]


def test_register_rejects_empty_or_bad_redirect_uris(app_client):
    assert app_client.post("/oauth/register", json={"redirect_uris": []}).status_code == 400
    # Plain http on a non-loopback host is never acceptable (RFC 8252 §7.3).
    r = app_client.post("/oauth/register", json={"redirect_uris": ["http://evil.example.com/cb"]})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_redirect_uri"
    # http on loopback IS acceptable (native-client dev).
    ok = app_client.post("/oauth/register", json={"redirect_uris": ["http://localhost:8123/cb"]})
    assert ok.status_code == 201


def test_register_rejects_confidential_clients(app_client):
    r = app_client.post(
        "/oauth/register",
        json={"redirect_uris": [_CLIENT_REDIRECT], "token_endpoint_auth_method": "client_secret_basic"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_client_metadata"


def test_registered_client_full_pkce_flow(app_client):
    """A registered client authorizes against ITS redirect_uri (not in the allowlist)."""
    _login(app_client)
    client_id = _register(app_client)["client_id"]
    verifier = "v" * 64

    code = _authorize_code(app_client, verifier, client_id=client_id, redirect_uri=_CLIENT_REDIRECT)
    token = _exchange(app_client, code, verifier, client_id=client_id, redirect_uri=_CLIENT_REDIRECT)
    assert token.status_code == 200
    body = token.json()
    assert body["access_token"]
    assert body["refresh_token"]

    # The access token authenticates a protected endpoint (cookies cleared so the
    # session cookie cannot mask a broken Bearer path).
    app_client.cookies.clear()
    listed = app_client.get(
        "/settings/tokens", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert listed.status_code == 200


def test_registered_client_other_redirect_rejected(app_client):
    """A registered client may NOT use a static-allowlist URI it didn't register."""
    _login(app_client)
    client_id = _register(app_client)["client_id"]
    r = app_client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": _STATIC_REDIRECT,
            "response_type": "code",
            "code_challenge": _challenge("v" * 64),
            "code_challenge_method": "S256",
            "state": "x",
        },
    )
    assert r.status_code == 400


def test_code_bound_to_client_id(app_client):
    """A code issued to client A cannot be redeemed claiming client B."""
    _login(app_client)
    client_a = _register(app_client)["client_id"]
    client_b = _register(app_client)["client_id"]
    verifier = "v" * 64
    code = _authorize_code(app_client, verifier, client_id=client_a, redirect_uri=_CLIENT_REDIRECT)
    r = _exchange(app_client, code, verifier, client_id=client_b, redirect_uri=_CLIENT_REDIRECT)
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


# --- Consent screen (registered clients only) -------------------------------------------


def test_registered_client_gets_consent_page_not_silent_redirect(app_client):
    """Open DCR means anyone can mint a client; a code must NEVER be issued silently."""
    _login(app_client)
    info = _register(app_client)
    page = _consent_page(app_client, "v" * 64, client_id=info["client_id"], redirect_uri=_CLIENT_REDIRECT)
    assert page.status_code == 200
    assert "Claude" in page.text  # names the asking client
    assert "claude.ai" in page.text  # names the redirect host
    assert 'name="consent"' in page.text


def test_consent_deny_redirects_with_access_denied(app_client):
    _login(app_client)
    client_id = _register(app_client)["client_id"]
    verifier = "v" * 64
    consent = _consent_token_of(
        _consent_page(app_client, verifier, client_id=client_id, redirect_uri=_CLIENT_REDIRECT).text
    )
    denied = _submit_consent(
        app_client, verifier, client_id=client_id, redirect_uri=_CLIENT_REDIRECT,
        consent=consent, decision="deny",
    )
    assert denied.status_code == 302
    loc = denied.headers["location"]
    assert "error=access_denied" in loc
    assert "code=" not in loc


def test_consent_post_rejects_garbage_token(app_client):
    _login(app_client)
    client_id = _register(app_client)["client_id"]
    r = _submit_consent(
        app_client, "v" * 64, client_id=client_id, redirect_uri=_CLIENT_REDIRECT, consent="forged"
    )
    assert r.status_code == 400


def test_consent_token_bound_to_client(app_client):
    """A consent token minted for client A cannot authorize a code for client B."""
    _login(app_client)
    client_a = _register(app_client)["client_id"]
    client_b = _register(app_client)["client_id"]
    verifier = "v" * 64
    consent_a = _consent_token_of(
        _consent_page(app_client, verifier, client_id=client_a, redirect_uri=_CLIENT_REDIRECT).text
    )
    r = _submit_consent(
        app_client, verifier, client_id=client_b, redirect_uri=_CLIENT_REDIRECT, consent=consent_a
    )
    assert r.status_code == 400


def test_consent_post_rejected_for_unregistered_client(app_client):
    """Allowlist clients never go through consent; the POST path is DCR-only."""
    _login(app_client)
    r = _submit_consent(
        app_client, "v" * 64, client_id="ext", redirect_uri=_STATIC_REDIRECT, consent="anything"
    )
    assert r.status_code == 400


def test_allowlist_client_still_redirects_immediately(app_client):
    """First-party (operator-configured) clients keep the seamless no-consent flow."""
    _login(app_client)
    r = app_client.get(
        "/oauth/authorize",
        params={
            "client_id": "ext",
            "redirect_uri": _STATIC_REDIRECT,
            "response_type": "code",
            "code_challenge": _challenge("v" * 64),
            "code_challenge_method": "S256",
            "state": "x",
        },
    )
    assert r.status_code == 302
    assert r.headers["location"].startswith(_STATIC_REDIRECT)


def test_code_redemption_requires_matching_client_id(app_client):
    """STRICT binding: a code bound to a client cannot be redeemed without client_id."""
    _login(app_client)
    client_id = _register(app_client)["client_id"]
    verifier = "v" * 64
    code = _authorize_code(app_client, verifier, client_id=client_id, redirect_uri=_CLIENT_REDIRECT)
    r = app_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _CLIENT_REDIRECT,
            "code_verifier": verifier,
            # client_id deliberately omitted
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


# --- Refresh-token grant ----------------------------------------------------------------


def _full_token_response(app_client, client_id: str) -> dict:
    verifier = "v" * 64
    code = _authorize_code(app_client, verifier, client_id=client_id, redirect_uri=_CLIENT_REDIRECT)
    return _exchange(
        app_client, code, verifier, client_id=client_id, redirect_uri=_CLIENT_REDIRECT
    ).json()


def test_refresh_grant_rotates_and_issues_new_access(app_client):
    _login(app_client)
    client_id = _register(app_client)["client_id"]
    first = _full_token_response(app_client, client_id)

    refreshed = app_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": first["refresh_token"],
            "client_id": client_id,
        },
    )
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["access_token"]
    # Rotation: a NEW refresh token is issued.
    assert body["refresh_token"] != first["refresh_token"]
    # The refreshed access token is a valid Bearer (cookies cleared first).
    app_client.cookies.clear()
    me = app_client.get(
        "/settings/tokens", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200


def test_replayed_refresh_token_rejected(app_client):
    """A rotated (already-used) refresh token must be rejected — replay defense."""
    _login(app_client)
    client_id = _register(app_client)["client_id"]
    first = _full_token_response(app_client, client_id)

    data = {
        "grant_type": "refresh_token",
        "refresh_token": first["refresh_token"],
        "client_id": client_id,
    }
    assert app_client.post("/oauth/token", data=data).status_code == 200
    replay = app_client.post("/oauth/token", data=data)
    assert replay.status_code == 400
    assert replay.json()["error"] == "invalid_grant"


def test_refresh_token_bound_to_client(app_client):
    """A refresh token issued to client A is rejected when presented as client B."""
    _login(app_client)
    client_a = _register(app_client)["client_id"]
    client_b = _register(app_client)["client_id"]
    first = _full_token_response(app_client, client_a)

    r = app_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": first["refresh_token"],
            "client_id": client_b,
        },
    )
    assert r.status_code == 400


def test_unknown_grant_type_rejected(app_client):
    r = app_client.post("/oauth/token", data={"grant_type": "password"})
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_grant_type"


def test_refresh_token_is_not_a_bearer_credential(app_client):
    """A refresh token must never authenticate an API call directly."""
    _login(app_client)
    client_id = _register(app_client)["client_id"]
    first = _full_token_response(app_client, client_id)
    app_client.cookies.clear()
    r = app_client.get(
        "/settings/tokens", headers={"Authorization": f"Bearer {first['refresh_token']}"}
    )
    assert r.status_code == 401
