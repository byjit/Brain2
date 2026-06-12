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
import html
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlsplit

import jwt as pyjwt
from fastapi import APIRouter, Cookie, Depends, Form, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from brain2.auth import bearer, jwt_service, oauth_clients, oauth_codes, refresh_tokens, users
from brain2.auth.deps import SESSION_COOKIE, get_auth_db, get_session_user
from brain2.auth.providers.identity import build_identity_provider
from brain2.config import get_settings
from brain2.models.auth import CurrentUserResponse, RegisterClientRequest

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


# Purpose claim pinning the consent token so it can't be replayed as any other JWT.
_CONSENT_PURPOSE = "oauth_consent"
_CONSENT_TTL = 600  # 10 minutes to read and act on the consent page.


def _validate_authorize_params(
    conn: sqlite3.Connection,
    settings,
    *,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str | None,
    code_challenge_method: str | None,
    state: str | None,
) -> dict | None:
    """Validate authorize parameters; return the registered client row or None.

    Exact-match redirect validation — never substring; reject before anything else. A
    client registered via /oauth/register (RFC 7591) is matched against ITS redirect
    URIs; everything else (the extension, dev clients) falls back to the static allowlist.
    Returns the ``oauth_clients`` row for a DCR-registered client (its presence is what
    routes the flow through the consent page), or None for an allowlist client.
    """
    registered = oauth_clients.get_client(conn, client_id)
    if registered is not None:
        is_allowed = redirect_uri in registered["redirect_uris"]
    else:
        is_allowed = redirect_uri in settings.oauth_redirect_uris
        # Developer convenience: if the template 'https://<extension-id>.chromiumapp.org/' is in
        # the allowlist, we allow any valid chrome extension redirect URI in development.
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
    return registered


def _resolve_authorize_user(
    conn: sqlite3.Connection, settings, brain2_session: str | None, authorization: str | None
) -> str | None:
    """Resolve the authorize request's user from the session cookie or a Bearer, or None."""
    user_id = None
    if brain2_session:
        user_id = jwt_service.verify_token(
            brain2_session, secret=settings.jwt_secret, expected_typ="session"
        )
        if user_id is not None:
            # Verify the user actually exists in the central users table
            row = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                user_id = None
    if user_id is None:
        user_id = bearer.resolve_bearer(authorization, conn=conn, secret=settings.jwt_secret)
    return user_id


def _issue_consent_token(secret: str, *, user_id: str, client_id: str, redirect_uri: str) -> str:
    """Sign a short-lived consent token binding (user, client, redirect_uri) together."""
    now = int(time.time())
    return pyjwt.encode(
        {
            "purpose": _CONSENT_PURPOSE,
            "sub": user_id,
            "cid": client_id,
            "ruri": redirect_uri,
            "iat": now,
            "exp": now + _CONSENT_TTL,
        },
        secret,
        algorithm="HS256",
    )


def _verify_consent_token(
    token: str, secret: str, *, user_id: str, client_id: str, redirect_uri: str
) -> bool:
    """True iff ``token`` is a valid consent token for exactly this (user, client, uri).

    Binding the token to the session user means a consent token minted in one account
    can never authorize a code for another (kills cross-site replays outright).
    """
    try:
        payload = pyjwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp"]})
    except pyjwt.InvalidTokenError:
        return False
    return (
        payload.get("purpose") == _CONSENT_PURPOSE
        and payload.get("sub") == user_id
        and payload.get("cid") == client_id
        and payload.get("ruri") == redirect_uri
    )


def _issue_code_redirect(
    conn: sqlite3.Connection,
    settings,
    *,
    user_id: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
) -> RedirectResponse:
    """Mint the PKCE-bound single-use code and redirect back to the client."""
    code = oauth_codes.issue_code(
        conn,
        user_id=user_id,
        code_challenge=code_challenge,
        redirect_uri=redirect_uri,
        ttl=settings.auth_code_ttl,
        client_id=client_id,
    )
    location = f"{redirect_uri}?{urlencode({'code': code, 'state': state})}"
    return RedirectResponse(location, status_code=302)


def _consent_page(
    *,
    client_name: str | None,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
    consent_token: str,
) -> HTMLResponse:
    """The consent screen shown for dynamically registered clients.

    Open DCR means ANYONE can mint a client_id pointing at their own https redirect — so
    a DCR client must never receive an authorization code from a silent redirect. The
    user has to see who is asking (client name + redirect host) and explicitly approve.
    All interpolated values are HTML-escaped.
    """
    name = html.escape(client_name or "An unnamed application")
    host = html.escape(urlsplit(redirect_uri).netloc)
    fields = "".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
        for k, v in {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "consent": consent_token,
        }.items()
    )
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Authorize {name} — Brain2</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #f6f7f9; margin: 0;
         display: flex; min-height: 100vh; align-items: center; justify-content: center; }}
  .card {{ background: #fff; border: 1px solid #e3e5e8; border-radius: 12px; padding: 2rem;
           max-width: 26rem; box-shadow: 0 4px 16px rgba(0,0,0,.06); }}
  h1 {{ font-size: 1.1rem; margin: 0 0 .75rem; }}
  p {{ color: #444; font-size: .92rem; line-height: 1.5; }}
  code {{ background: #f1f2f4; padding: .1rem .35rem; border-radius: 4px; font-size: .85em; }}
  .actions {{ display: flex; gap: .75rem; margin-top: 1.5rem; }}
  button {{ flex: 1; padding: .6rem 1rem; border-radius: 8px; font-size: .95rem; cursor: pointer; }}
  .allow {{ background: #1a73e8; color: #fff; border: none; }}
  .deny {{ background: #fff; color: #333; border: 1px solid #ccc; }}
</style></head>
<body><main class="card">
  <h1>Authorize access to your Brain2?</h1>
  <p><strong>{name}</strong> wants to connect to your Brain2 memory store. It will be able
  to <strong>save, search, list, and delete</strong> your entries on your behalf.</p>
  <p>You will be sent back to <code>{host}</code>.</p>
  <form method="post" action="/oauth/authorize">
    {fields}
    <div class="actions">
      <button class="deny" type="submit" name="decision" value="deny">Deny</button>
      <button class="allow" type="submit" name="decision" value="allow">Allow</button>
    </div>
  </form>
</main></body></html>"""
    # no-store: the page embeds a single-use consent token.
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})


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
):
    """OAuth authorize endpoint (spec §12): validate, then consent-gate or issue the code.

    Requires a logged-in Google session (otherwise redirects to the login flow with the
    current URL preserved). Validates the redirect_uri EXACTLY, requires
    ``response_type=code`` + S256 ``code_challenge`` + ``state``. Then the flows split:

    - **Static-allowlist clients** (the extension — operator-configured, first-party):
      issue the PKCE-bound single-use code and redirect back immediately.
    - **DCR-registered clients** (anyone can register one — RFC 7591 is open): render a
      consent page naming the client; the code is only issued by the POST handler after
      the user explicitly clicks Allow. This closes the silent-redirect account-takeover
      hole that open registration would otherwise create.
    """
    settings = get_settings()
    registered = _validate_authorize_params(
        conn,
        settings,
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        state=state,
    )

    user_id = _resolve_authorize_user(conn, settings, brain2_session, authorization)
    if user_id is None:
        # Build the login redirect URL, preserving the current authorize URL with its query parameters.
        query_str = str(request.query_params)
        next_path = f"{request.url.path}?{query_str}" if query_str else request.url.path
        login_url = f"/auth/login?{urlencode({'next': next_path})}"
        return RedirectResponse(login_url, status_code=302)

    if registered is not None:
        consent_token = _issue_consent_token(
            settings.jwt_secret, user_id=user_id, client_id=client_id, redirect_uri=redirect_uri
        )
        return _consent_page(
            client_name=registered["client_name"],
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            state=state,
            consent_token=consent_token,
        )

    return _issue_code_redirect(
        conn,
        settings,
        user_id=user_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
    )


@router.post("/oauth/authorize")
def oauth_authorize_consent(
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    code_challenge: str | None = Form(default=None),
    code_challenge_method: str | None = Form(default=None),
    state: str | None = Form(default=None),
    consent: str = Form(...),
    decision: str = Form(...),
    brain2_session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> RedirectResponse:
    """Consent submission for DCR-registered clients: issue the code only on Allow.

    Everything is re-validated from scratch (the hidden form fields are attacker-visible
    client input), and the ``consent`` token must verify against THIS session's user +
    this exact (client_id, redirect_uri) — a token minted for another user or another
    client is rejected, so a forged or replayed POST can never mint a code.
    """
    settings = get_settings()
    registered = _validate_authorize_params(
        conn,
        settings,
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        state=state,
    )
    if registered is None:
        # Allowlist clients never go through consent; their GET flow issues directly.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unknown client")

    user_id = _resolve_authorize_user(conn, settings, brain2_session, authorization)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    if not _verify_consent_token(
        consent, settings.jwt_secret, user_id=user_id, client_id=client_id, redirect_uri=redirect_uri
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid consent token")

    if decision != "allow":
        # RFC 6749 §4.1.2.1: tell the client the user said no — never issue a code.
        location = f"{redirect_uri}?{urlencode({'error': 'access_denied', 'state': state})}"
        return RedirectResponse(location, status_code=302)

    return _issue_code_redirect(
        conn,
        settings,
        user_id=user_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
    )


def _oauth_error(error: str, description: str | None = None) -> JSONResponse:
    """An RFC 6749 §5.2 token-endpoint error response ({"error": ...}, 400, no-store)."""
    content: dict = {"error": error}
    if description:
        content["error_description"] = description
    return JSONResponse(content, status_code=status.HTTP_400_BAD_REQUEST, headers={"Cache-Control": "no-store"})


@router.post("/oauth/token")
def oauth_token(
    grant_type: str = Form(...),
    code: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
    code_verifier: str | None = Form(default=None),
    refresh_token: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> JSONResponse:
    """OAuth token endpoint (spec §12): two grants, both returning access + refresh tokens.

    - ``authorization_code`` + PKCE: verifies the code (single-use, unexpired,
      redirect_uri + client_id match) and the ``code_verifier`` against the stored S256
      challenge. Reused codes, expired codes, and a mismatched verifier are rejected.
    - ``refresh_token``: rotates the presented refresh token (a replayed token is
      rejected) and issues a fresh pair, so MCP clients outlive the 1h access TTL
      without interactive re-auth.
    """
    settings = get_settings()
    if grant_type == "authorization_code":
        if not code or not redirect_uri or not code_verifier:
            return _oauth_error("invalid_request", "code, redirect_uri and code_verifier are required")
        user_id = oauth_codes.consume_code(
            conn, code=code, code_verifier=code_verifier, redirect_uri=redirect_uri, client_id=client_id
        )
        if user_id is None:
            return _oauth_error("invalid_grant")
        new_refresh = refresh_tokens.issue(
            conn, user_id=user_id, client_id=client_id, ttl=settings.refresh_token_ttl
        )
    elif grant_type == "refresh_token":
        if not refresh_token:
            return _oauth_error("invalid_request", "refresh_token is required")
        rotated = refresh_tokens.consume(
            conn, raw_token=refresh_token, client_id=client_id, ttl=settings.refresh_token_ttl
        )
        if rotated is None:
            return _oauth_error("invalid_grant")
        user_id, new_refresh = rotated
    else:
        return _oauth_error("unsupported_grant_type")

    access_token = jwt_service.issue_token(
        user_id, secret=settings.jwt_secret, ttl=settings.access_token_ttl
    )
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.access_token_ttl,
            "refresh_token": new_refresh,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/oauth/register", status_code=status.HTTP_201_CREATED)
def oauth_register(
    body: RegisterClientRequest,
    conn: sqlite3.Connection = Depends(get_auth_db),
) -> JSONResponse:
    """Dynamic Client Registration (RFC 7591) for MCP clients (spec §12).

    Lets clients like Claude web custom connectors self-register: they POST their
    ``redirect_uris`` (validated: https, or http on loopback only) and get a
    ``client_id``. Only PUBLIC clients are accepted — no secret is issued and
    ``token_endpoint_auth_method`` must be ``none`` (PKCE proves possession).
    """
    if not body.redirect_uris:
        return _oauth_error("invalid_redirect_uri", "redirect_uris must be a non-empty array")
    for uri in body.redirect_uris:
        if not oauth_clients.is_acceptable_redirect_uri(uri):
            return _oauth_error("invalid_redirect_uri", f"redirect_uri not acceptable: {uri}")
    if body.token_endpoint_auth_method not in (None, "none"):
        return _oauth_error(
            "invalid_client_metadata",
            "only public clients are supported (token_endpoint_auth_method 'none')",
        )
    info = oauth_clients.register_client(
        conn, redirect_uris=body.redirect_uris, client_name=body.client_name
    )
    return JSONResponse(info, status_code=status.HTTP_201_CREATED, headers={"Cache-Control": "no-store"})


# --- OAuth Discovery Metadata (RFC 9728 & RFC 8414) -----------------------------------


# The MCP resource path (main.MCP_MOUNT + the SDK's /mcp suffix), duplicated here as a
# literal because importing from brain2.main would be circular.
_MCP_RESOURCE_PATH = "/connect/mcp"


@router.get("/.well-known/oauth-protected-resource")
@router.get(f"/.well-known/oauth-protected-resource{_MCP_RESOURCE_PATH}")
def get_protected_resource_metadata(request: Request) -> JSONResponse:
    """Protected Resource Metadata (RFC 9728) for the MCP server.

    Advertises the authorization servers that this resource server trusts. Served at
    both the root well-known path and the RFC 9728 path-suffix variant
    (``/.well-known/oauth-protected-resource/connect/mcp``), because MCP clients derive
    the metadata URL by inserting the well-known segment before the resource path.
    """
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        {
            "resource": f"{base_url}{_MCP_RESOURCE_PATH}",
            "authorization_servers": [base_url],
            "bearer_methods_supported": ["header"],
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
            "registration_endpoint": f"{base_url}/oauth/register",
            "scopes_supported": ["openid", "email"],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        }
    )

