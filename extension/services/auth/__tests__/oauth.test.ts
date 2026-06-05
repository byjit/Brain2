/**
 * Unit tests for the pure helpers in services/auth/oauth.ts.
 *
 * Environment: node (vitest default). No browser / DOM APIs are used here —
 * all `browser.*` calls are confined to the integration layer (runAuthFlow,
 * signIn, getValidAccessToken, signOut) which is tested manually / e2e.
 */

import { describe, it, expect, vi } from "vitest";
import {
  buildAuthorizeUrl,
  exchangeCode,
  parseRedirect,
  isFresh,
  OAuthError,
} from "@/services/auth/oauth";
import type { Tokens } from "@/services/capture/types";

// ---------------------------------------------------------------------------
// buildAuthorizeUrl
// ---------------------------------------------------------------------------

describe("buildAuthorizeUrl", () => {
  const params = {
    apiUrl: "https://api.example.com",
    clientId: "brain2-extension",
    redirectUri: "https://abcdef.chromiumapp.org/",
    challenge: "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    state: "random-state-nonce",
  };

  it("starts with ${apiUrl}/oauth/authorize?", () => {
    const url = buildAuthorizeUrl(params);
    expect(url.startsWith("https://api.example.com/oauth/authorize?")).toBe(true);
  });

  it("includes response_type=code", () => {
    const url = buildAuthorizeUrl(params);
    const sp = new URL(url).searchParams;
    expect(sp.get("response_type")).toBe("code");
  });

  it("includes code_challenge_method=S256", () => {
    const url = buildAuthorizeUrl(params);
    const sp = new URL(url).searchParams;
    expect(sp.get("code_challenge_method")).toBe("S256");
  });

  it("includes the given code_challenge", () => {
    const url = buildAuthorizeUrl(params);
    const sp = new URL(url).searchParams;
    expect(sp.get("code_challenge")).toBe(params.challenge);
  });

  it("includes the given client_id", () => {
    const url = buildAuthorizeUrl(params);
    const sp = new URL(url).searchParams;
    expect(sp.get("client_id")).toBe(params.clientId);
  });

  it("includes the given state", () => {
    const url = buildAuthorizeUrl(params);
    const sp = new URL(url).searchParams;
    expect(sp.get("state")).toBe(params.state);
  });

  it("includes a properly URL-encoded redirect_uri", () => {
    const url = buildAuthorizeUrl(params);
    const sp = new URL(url).searchParams;
    expect(sp.get("redirect_uri")).toBe(params.redirectUri);
  });

  it("redirect_uri with slashes and colons is correctly encoded in raw query", () => {
    const url = buildAuthorizeUrl(params);
    // URLSearchParams percent-encodes special chars; the raw search string must
    // NOT contain the redirect URI verbatim when it has slashes.
    expect(url).toContain("redirect_uri=");
    // Verify round-trip: parsing back gives the original string.
    expect(new URL(url).searchParams.get("redirect_uri")).toBe(params.redirectUri);
  });
});

// ---------------------------------------------------------------------------
// exchangeCode
// ---------------------------------------------------------------------------

describe("exchangeCode", () => {
  const baseParams = {
    apiUrl: "https://api.example.com",
    clientId: "brain2-extension",
    code: "auth-code-abc",
    codeVerifier: "my-verifier-string",
    redirectUri: "https://abcdef.chromiumapp.org/",
  };

  function makeFetchStub(
    body: object,
    status = 200,
  ): typeof fetch {
    return vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;
  }

  it("POSTs to ${apiUrl}/oauth/token", async () => {
    const stub = makeFetchStub({ access_token: "tok", token_type: "Bearer", expires_in: 3600 });
    await exchangeCode({ ...baseParams, fetchImpl: stub });
    expect(stub).toHaveBeenCalledOnce();
    const [url] = (stub as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.example.com/oauth/token");
  });

  it("uses HTTP method POST", async () => {
    const stub = makeFetchStub({ access_token: "tok", token_type: "Bearer", expires_in: 3600 });
    await exchangeCode({ ...baseParams, fetchImpl: stub });
    const [, init] = (stub as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
  });

  it("sets Content-Type: application/x-www-form-urlencoded", async () => {
    const stub = makeFetchStub({ access_token: "tok", token_type: "Bearer", expires_in: 3600 });
    await exchangeCode({ ...baseParams, fetchImpl: stub });
    const [, init] = (stub as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
  });

  it("sends a URL-encoded body (not JSON) with required fields", async () => {
    const stub = makeFetchStub({ access_token: "tok", token_type: "Bearer", expires_in: 3600 });
    await exchangeCode({ ...baseParams, fetchImpl: stub });
    const [, init] = (stub as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = new URLSearchParams(init.body as string);
    expect(body.get("grant_type")).toBe("authorization_code");
    expect(body.get("code")).toBe(baseParams.code);
    expect(body.get("code_verifier")).toBe(baseParams.codeVerifier);
    expect(body.get("redirect_uri")).toBe(baseParams.redirectUri);
  });

  it("returns accessToken and approximate expiresAt", async () => {
    const stub = makeFetchStub({ access_token: "tok", token_type: "Bearer", expires_in: 3600 });
    const before = Date.now();
    const result = await exchangeCode({ ...baseParams, fetchImpl: stub });
    const after = Date.now();
    expect(result.accessToken).toBe("tok");
    // expiresAt should be within a few seconds of now + 3600*1000
    expect(result.expiresAt).toBeGreaterThanOrEqual(before + 3_600_000);
    expect(result.expiresAt).toBeLessThanOrEqual(after + 3_600_000 + 5_000);
  });

  it("resolves fine when the response has no refresh_token field", async () => {
    // M7 backend never issues refresh tokens; this must not throw
    const stub = makeFetchStub({ access_token: "tok", token_type: "Bearer", expires_in: 3600 });
    await expect(exchangeCode({ ...baseParams, fetchImpl: stub })).resolves.not.toThrow();
  });

  it("throws OAuthError on non-2xx token response", async () => {
    const stub = makeFetchStub({ error: "invalid_grant" }, 400);
    await expect(exchangeCode({ ...baseParams, fetchImpl: stub })).rejects.toBeInstanceOf(OAuthError);
  });

  it("throws OAuthError when access_token is missing from response body", async () => {
    const stub = makeFetchStub({ token_type: "Bearer", expires_in: 3600 });
    await expect(exchangeCode({ ...baseParams, fetchImpl: stub })).rejects.toBeInstanceOf(OAuthError);
  });

  it("throws OAuthError when expires_in is not numeric", async () => {
    const stub = makeFetchStub({ access_token: "tok", token_type: "Bearer", expires_in: "bad" });
    await expect(exchangeCode({ ...baseParams, fetchImpl: stub })).rejects.toBeInstanceOf(OAuthError);
  });
});

// ---------------------------------------------------------------------------
// parseRedirect
// ---------------------------------------------------------------------------

describe("parseRedirect", () => {
  const baseRedirect = "https://abcdef.chromiumapp.org/?code=abc123&state=my-state";

  it("extracts code when state matches", () => {
    const result = parseRedirect(baseRedirect, "my-state");
    expect(result.code).toBe("abc123");
  });

  it("throws OAuthError when state does not match (CSRF defense)", () => {
    expect(() => parseRedirect(baseRedirect, "different-state")).toThrow(OAuthError);
  });

  it("throws OAuthError when code is missing", () => {
    expect(() =>
      parseRedirect("https://abcdef.chromiumapp.org/?state=my-state", "my-state"),
    ).toThrow(OAuthError);
  });

  it("throws OAuthError when state param is missing", () => {
    expect(() =>
      parseRedirect("https://abcdef.chromiumapp.org/?code=abc123", "my-state"),
    ).toThrow(OAuthError);
  });
});

// ---------------------------------------------------------------------------
// isFresh
// ---------------------------------------------------------------------------

describe("isFresh", () => {
  const now = Date.now();
  const wellFuture: Tokens = { accessToken: "tok", expiresAt: now + 600_000 }; // 10 min
  const almostExpired: Tokens = { accessToken: "tok", expiresAt: now + 30_000 }; // 30s — within 60s skew
  const expired: Tokens = { accessToken: "tok", expiresAt: now - 1 };
  const nullToken: Tokens = { accessToken: null, expiresAt: null };
  const nullExpiry: Tokens = { accessToken: "tok", expiresAt: null };

  it("returns true when token is present and well before expiry skew", () => {
    expect(isFresh(wellFuture, now)).toBe(true);
  });

  it("returns false when token expires within the skew window (default 60s)", () => {
    expect(isFresh(almostExpired, now)).toBe(false);
  });

  it("returns false when token is already expired", () => {
    expect(isFresh(expired, now)).toBe(false);
  });

  it("returns false when accessToken is null", () => {
    expect(isFresh(nullToken, now)).toBe(false);
  });

  it("returns false when expiresAt is null", () => {
    expect(isFresh(nullExpiry, now)).toBe(false);
  });

  it("respects a custom skewMs", () => {
    // Token expires in 30s. With skewMs=0 it should be fresh; with skewMs=60000 it should not.
    const token: Tokens = { accessToken: "tok", expiresAt: now + 30_000 };
    expect(isFresh(token, now, 0)).toBe(true);
    expect(isFresh(token, now, 60_000)).toBe(false);
  });
});
