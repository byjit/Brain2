/**
 * OAuth 2.1 + PKCE (S256) sign-in for the Brain2 Chrome extension.
 *
 * Flow (against the shipped M7 backend):
 *   1. Build the authorize URL (S256 PKCE challenge + opaque CSRF state).
 *   2. Hand it to `chrome.identity` via the WXT `browser` global; the backend
 *      bounces through Google sign-in and 302s back to our extension redirect
 *      URI with `?code=...&state=...`.
 *   3. Exchange the code for an access token at /oauth/token (form-encoded).
 *   4. Persist the token + absolute expiry in `authStore`.
 *
 * Design notes:
 *   - NO refresh tokens. The M7 backend never issues one (the token response
 *     has only access_token / token_type / expires_in). Access tokens live 1h;
 *     we cope with that via *silent* re-auth (interactive:false), not refresh.
 *   - The CSRF `state` returned by the redirect is verified against the one we
 *     sent (see `parseRedirect`).
 *   - All `browser.*` calls are confined to the integration layer below; the
 *     pure helpers (`buildAuthorizeUrl`, `exchangeCode`, `parseRedirect`,
 *     `isFresh`) take no browser dependency so they are unit-testable in node.
 */

import { createVerifier, challengeFromVerifier } from "./pkce";
import { authStore } from "@/services/capture/stores";
import type { Tokens } from "@/services/capture/types";
import { config } from "@/lib/config";

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/** Typed error for any OAuth failure (bad token response, CSRF mismatch, …). */
export class OAuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OAuthError";
  }
}

// ---------------------------------------------------------------------------
// Pure helpers (no browser / DOM dependency — unit tested)
// ---------------------------------------------------------------------------

interface AuthorizeParams {
  apiUrl: string;
  clientId: string;
  redirectUri: string;
  challenge: string;
  state: string;
}

/**
 * Build the `/oauth/authorize` URL. Uses URLSearchParams so every value
 * (notably `redirect_uri`) is correctly percent-encoded.
 */
export function buildAuthorizeUrl({
  apiUrl,
  clientId,
  redirectUri,
  challenge,
  state,
}: AuthorizeParams): string {
  const url = new URL(`${apiUrl}/oauth/authorize`);
  url.search = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    code_challenge: challenge,
    code_challenge_method: "S256",
    state,
  }).toString();
  return url.toString();
}

interface ExchangeParams {
  apiUrl: string;
  clientId: string;
  code: string;
  codeVerifier: string;
  redirectUri: string;
  /** Injectable for tests; defaults to the global `fetch` in production. */
  fetchImpl?: typeof fetch;
}

/**
 * Exchange an authorization code for an access token at `/oauth/token`.
 *
 * The backend requires `application/x-www-form-urlencoded`. `client_id` is
 * included for forward-compat (the backend ignores it). The response has no
 * refresh_token — we never read one.
 */
export async function exchangeCode({
  apiUrl,
  clientId,
  code,
  codeVerifier,
  redirectUri,
  fetchImpl = fetch,
}: ExchangeParams): Promise<{ accessToken: string; expiresAt: number }> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri,
    code_verifier: codeVerifier,
    client_id: clientId, // forward-compat; backend ignores it
  }).toString();

  const res = await fetchImpl(`${apiUrl}/oauth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!res.ok) {
    throw new OAuthError(`Token exchange failed with status ${res.status}`);
  }

  let data: unknown;
  try {
    data = await res.json();
  } catch {
    throw new OAuthError("Token response was not valid JSON");
  }

  const token = data as { access_token?: unknown; expires_in?: unknown };
  if (typeof token.access_token !== "string" || typeof token.expires_in !== "number") {
    throw new OAuthError("Token response missing access_token or expires_in");
  }

  return {
    accessToken: token.access_token,
    expiresAt: Date.now() + token.expires_in * 1000,
  };
}

/**
 * Parse the redirect URL returned by `launchWebAuthFlow`, verifying the CSRF
 * `state` matches what we sent. Throws OAuthError on mismatch or missing code.
 */
export function parseRedirect(redirect: string, expectedState: string): { code: string } {
  const params = new URL(redirect).searchParams;
  const state = params.get("state");
  if (state !== expectedState) {
    throw new OAuthError("OAuth state mismatch — possible CSRF, aborting");
  }
  const code = params.get("code");
  if (!code) {
    throw new OAuthError("OAuth redirect did not include an authorization code");
  }
  return { code };
}

/**
 * Whether the stored token is usable now: present and expiring more than
 * `skewMs` (default 60s) in the future. Pure — `now` is injected.
 */
export function isFresh(tokens: Tokens, now: number, skewMs = 60_000): boolean {
  return (
    tokens.accessToken !== null &&
    tokens.expiresAt !== null &&
    tokens.expiresAt - skewMs > now
  );
}

// ---------------------------------------------------------------------------
// Integration layer (browser.* lives ONLY here)
// ---------------------------------------------------------------------------

/**
 * Run the full PKCE flow via chrome.identity and persist the resulting token.
 * `interactive:false` performs a silent attempt (used for re-auth); it rejects
 * if user interaction would be required.
 */
async function runAuthFlow({ interactive }: { interactive: boolean }): Promise<Tokens> {
  const verifier = createVerifier();
  const challenge = await challengeFromVerifier(verifier);
  // Reuse the CSPRNG verifier generator as an opaque CSRF state nonce.
  const state = createVerifier();
  const redirectUri = browser.identity.getRedirectURL();

  const url = buildAuthorizeUrl({
    apiUrl: config.apiUrl,
    clientId: config.oauthClientId,
    redirectUri,
    challenge,
    state,
  });

  // Rejections (user closed the window, or non-interactive with no session)
  // propagate to the caller.
  const redirect = await browser.identity.launchWebAuthFlow({ url, interactive });
  if (!redirect) {
    // No redirect URL means the flow was aborted (e.g. silent attempt with no session).
    throw new OAuthError("Auth flow did not return a redirect URL");
  }
  const { code } = parseRedirect(redirect, state);

  const tokens = await exchangeCode({
    apiUrl: config.apiUrl,
    clientId: config.oauthClientId,
    code,
    codeVerifier: verifier,
    redirectUri,
  });

  const stored: Tokens = { accessToken: tokens.accessToken, expiresAt: tokens.expiresAt };
  await authStore.set(stored);
  return stored;
}

/**
 * Interactive sign-in. Requires the M7 backend's authorize→Google bounce when
 * there is no existing session (tracked separately).
 */
export function signIn(): Promise<Tokens> {
  return runAuthFlow({ interactive: true });
}

/**
 * Return a usable access token, or null if the caller must surface Sign-In.
 *
 * If the stored token is fresh, return it. Otherwise attempt a silent re-auth
 * (interactive:false) — this replaces refresh tokens and copes with the 1h TTL.
 */
export async function getValidAccessToken(): Promise<string | null> {
  const tokens = await authStore.get();
  if (isFresh(tokens, Date.now())) {
    return tokens.accessToken;
  }
  try {
    const refreshed = await runAuthFlow({ interactive: false });
    return refreshed.accessToken;
  } catch {
    return null;
  }
}

/** Forget the stored token. */
export async function signOut(): Promise<void> {
  await authStore.remove();
}
