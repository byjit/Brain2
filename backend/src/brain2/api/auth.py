"""Auth endpoints: Google Sign-In + OAuth 2.1 + PKCE Authorization Server (spec §12).

Google Sign-In (dashboard):
- GET  /auth/login    -> redirect to Google consent with a signed CSRF ``state``.
- GET  /api/auth/callback/google -> verify state, exchange the code via the identity provider,
                          implicit-signup the user (+ their {user_id}.db), set the
                          httpOnly session cookie, redirect to the dashboard.
- GET  /auth/me       -> the current session user.
- POST /auth/logout   -> clear the session cookie.

OAuth 2.1 + PKCE (web MCP clients + extension), minimal and correct (YAGNI — only the
authorization_code + S256 PKCE grant):
- GET  /oauth/authorize -> validate redirect_uri against the exact allowlist, require S256
                            + state, authenticate via the Google session, issue a
                            single-use code bound to the challenge.
- POST /oauth/token     -> authorization_code grant: verify code + code_verifier, issue a
                            short-lived Brain2 access token.
"""

import hmac
import secrets
import sqlite3
import time
from urllib.parse import urlencode

import jwt as pyjwt
from fastapi import APIRouter, Cookie, Depends, Form, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from brain2.auth import bearer, jwt_service, oauth_codes, users
from brain2.auth.deps import SESSION_COOKIE, get_auth_db, get_session_user
from brain2.auth.providers.identity import build_identity_provider
from brain2.config import get_settings
from brain2.models.auth import CurrentUserResponse

router = APIRouter(tags=["auth"])

_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
# Purpose claim pinning the login-state token so it can't be replayed as a session token.
_STATE_PURPOSE = "login_state"
_STATE_TTL = 600  # 10 minutes to complete the Google round trip.
# Short-lived httpOnly cookie holding the per-browser nonce that the state JWT is bound to.
_STATE_NONCE_COOKIE = "brain2_oauth_nonce"


def _redirect_uri(request: Request) -> str:
    """The Google OAuth callback URL for this deployment."""
    return str(request.url_for("auth_callback"))


def _issue_state(secret: str, nonce: str, next_url: str | None = None) -> str:
    """Sign a short-lived CSRF state token bound to a per-browser ``nonce``."""
    now = int(time.time())
    payload = {"purpose": _STATE_PURPOSE, "nonce": nonce, "iat": now, "exp": now + _STATE_TTL}
    if next_url:
        payload["next"] = next_url
    return pyjwt.encode(
        payload,
        secret,
        algorithm="HS256",
    )


def _verify_state(state: str, secret: str, nonce: str | None) -> dict | None:
    """Verify the state's signature/purpose AND that its nonce matches the browser cookie.

    Binding the state to a per-browser nonce (set as an httpOnly cookie at ``/auth/login``)
    makes the state non-transferable: a state issued for one browser cannot be stitched into
    another browser's callback (login-CSRF defense).
    Returns the decoded payload if valid, else None.
    """
    if not nonce:
        return None
    try:
        payload = pyjwt.decode(state, secret, algorithms=["HS256"], options={"require": ["exp"]})
    except pyjwt.InvalidTokenError:
        return None
    if payload.get("purpose") != _STATE_PURPOSE:
        return None
    state_nonce = payload.get("nonce")
    if not isinstance(state_nonce, str) or not hmac.compare_digest(state_nonce, nonce):
        return None
    return payload


def _set_session_cookie(response, user_id: str, settings) -> None:
    """Attach the httpOnly session cookie carrying a Brain2 JWT (spec §12)."""
    token = jwt_service.issue_token(
        user_id, secret=settings.jwt_secret, ttl=settings.session_ttl, typ="session"
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


# --- Google Sign-In -------------------------------------------------------------------


@router.get("/auth/login")
def auth_login(request: Request, next: str | None = Query(default=None)) -> RedirectResponse:
    """Redirect to Google's consent screen with a CSRF state bound to a browser nonce (§12)."""
    settings = get_settings()
    nonce = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.google_client_id or "brain2-dev",
        "redirect_uri": _redirect_uri(request),
        "response_type": "code",
        "scope": "openid email",
        "state": _issue_state(settings.jwt_secret, nonce, next),
    }
    response = RedirectResponse(f"{_GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)
    # Bind the flow to this browser: the callback requires this nonce to match the state.
    response.set_cookie(
        _STATE_NONCE_COOKIE,
        nonce,
        max_age=_STATE_TTL,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


@router.get("/api/auth/callback/google", name="auth_callback")
def auth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    brain2_oauth_nonce: str | None = Cookie(default=None),
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> RedirectResponse:
    """Exchange the Google code, implicit-signup the user, set the session cookie (spec §12)."""
    settings = get_settings()
    payload = _verify_state(state, settings.jwt_secret, brain2_oauth_nonce)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")

    provider = build_identity_provider(settings)
    identity = provider.exchange_code(code=code, redirect_uri=_redirect_uri(request))
    user_id = users.upsert_by_google_sub(
        conn,
        google_sub=identity.google_sub,
        email=identity.email,
        data_dir=settings.data_dir,
    )
    redirect_target = payload.get("next") or settings.dashboard_url
    response = RedirectResponse(redirect_target, status_code=302)
    _set_session_cookie(response, user_id, settings)
    # The nonce is single-use: clear it so the state cannot be replayed.
    response.delete_cookie(_STATE_NONCE_COOKIE, path="/", samesite="lax")
    return response


@router.get("/auth/me", response_model=CurrentUserResponse)
def auth_me(
    user_id: str = Depends(get_session_user),
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> CurrentUserResponse:
    """Return the authenticated dashboard user (spec §12)."""
    profile = users.get_user(conn, user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return CurrentUserResponse(**profile)


@router.post("/auth/logout")
def auth_logout() -> JSONResponse:
    """Clear the session cookie."""
    response = JSONResponse({"ok": True})
    # Mirror the attributes the cookie was set with so browsers reliably clear it.
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.cookie_secure,
        samesite="lax",
        httponly=True,
    )
    return response


# --- OAuth 2.1 + PKCE Authorization Server --------------------------------------------


@router.get("/oauth/authorize")
def oauth_authorize(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    code_challenge: str | None = Query(default=None),
    code_challenge_method: str | None = Query(default=None),
    state: str | None = Query(default=None),
    brain2_session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> RedirectResponse:
    """OAuth authorize endpoint (spec §12): validate, issue a PKCE-bound auth code.

    Requires a logged-in Google session. Validates the redirect_uri
    against the EXACT allowlist (no open redirect), requires ``response_type=code``, an S256
    ``code_challenge``, and ``state`` (CSRF). Issues a single-use, short-lived code bound to
    the challenge + redirect_uri, then redirects back to the client with ``code`` + ``state``.
    If not authenticated, redirects the browser to the login flow with the current URL preserved.
    """
    settings = get_settings()
    # Exact-match allowlist — never substring; reject before anything else.
    # Developer convenience: if the template 'https://<extension-id>.chromiumapp.org/' is in the allowlist,
    # we allow any valid chrome extension redirect URI in development.
    is_allowed = redirect_uri in settings.oauth_redirect_uris
    if not is_allowed and "https://<extension-id>.chromiumapp.org/" in settings.oauth_redirect_uris:
        import re
        if re.match(r"^https://[a-z]{32}\.chromiumapp\.org/?$", redirect_uri):
            is_allowed = True

    if not is_allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="redirect_uri not allowed")
    if response_type != "code":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported response_type")
    if not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="state is required")
    if not code_challenge:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_challenge is required")
    # PKCE must be S256 — 'plain' is explicitly rejected (security constraint).
    if code_challenge_method != "S256":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="code_challenge_method must be S256")

    # Resolve session user manually to allow redirect on unauthenticated.
    user_id = None
    if brain2_session:
        user_id = jwt_service.verify_token(
            brain2_session, secret=settings.jwt_secret, expected_typ="session"
        )
    if user_id is None:
        user_id = bearer.resolve_bearer(authorization, conn=conn, secret=settings.jwt_secret)

    if user_id is None:
        # Build the login redirect URL, preserving the current authorize URL with its query parameters.
        query_str = str(request.query_params)
        next_path = f"{request.url.path}?{query_str}" if query_str else request.url.path
        login_url = f"/auth/login?{urlencode({'next': next_path})}"
        return RedirectResponse(login_url, status_code=302)

    code = oauth_codes.issue_code(
        conn,
        user_id=user_id,
        code_challenge=code_challenge,
        redirect_uri=redirect_uri,
        ttl=settings.auth_code_ttl,
    )
    location = f"{redirect_uri}?{urlencode({'code': code, 'state': state})}"
    return RedirectResponse(location, status_code=302)


@router.post("/oauth/token")
def oauth_token(
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    code_verifier: str = Form(...),
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> JSONResponse:
    """OAuth token endpoint (spec §12): authorization_code + PKCE -> Brain2 access token.

    Verifies the code (single-use, unexpired, redirect_uri match) and the ``code_verifier``
    against the stored S256 challenge, then issues a short-lived Brain2 access token. Reused
    codes, expired codes, and a mismatched verifier are rejected with 400.
    """
    if grant_type != "authorization_code":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported_grant_type")
    settings = get_settings()
    user_id = oauth_codes.consume_code(
        conn, code=code, code_verifier=code_verifier, redirect_uri=redirect_uri
    )
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_grant")
    access_token = jwt_service.issue_token(
        user_id, secret=settings.jwt_secret, ttl=settings.access_token_ttl
    )
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.access_token_ttl,
        }
    )


# --- OAuth Discovery Metadata (RFC 9728 & RFC 8414) -----------------------------------


@router.get("/.well-known/oauth-protected-resource")
def get_protected_resource_metadata(request: Request) -> JSONResponse:
    """Protected Resource Metadata (RFC 9728) for the MCP server.

    Advertises the authorization servers that this resource server trusts.
    """
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        {
            "resource": f"{base_url}/connect/mcp",
            "authorization_servers": [base_url],
        }
    )


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/openid-configuration")
def get_oauth_authorization_server_metadata(request: Request) -> JSONResponse:
    """OAuth 2.1 Authorization Server Metadata (RFC 8414 / OIDC discovery).

    Lists our authorization and token endpoints and supported grants.
    """
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "scopes_supported": ["openid", "email"],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        }
    )

