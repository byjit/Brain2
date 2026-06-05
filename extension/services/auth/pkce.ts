/**
 * Pure PKCE (RFC 7636) helpers for OAuth 2.1 S256 code challenges.
 *
 * No browser-extension APIs, no DOM — only WebCrypto, which is available in
 * Node 18+ (global `crypto`) and in all modern browsers/extensions.
 *
 * References:
 *   RFC 7636  https://www.rfc-editor.org/rfc/rfc7636
 *   §4.1  code_verifier charset: [A-Z a-z 0-9 - . _ ~]  length 43–128
 *   §4.2  code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
 *   Appendix B  test vectors used in the unit tests
 */

// ---------------------------------------------------------------------------
// Internal helper
// ---------------------------------------------------------------------------

/**
 * Encodes a byte array as base64url (RFC 4648 §5) with no padding characters.
 * Steps: standard base64 → replace '+' with '-', '/' with '_' → strip '='.
 */
function base64UrlEncode(bytes: Uint8Array | ArrayBuffer): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  // btoa expects a binary string; spread is safe for 32- and 64-byte inputs
  const base64 = btoa(String.fromCharCode(...arr));
  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Generate a cryptographically random PKCE code verifier (RFC 7636 §4.1).
 *
 * 32 random bytes → base64url → 43 characters, well within the allowed 43–128
 * range; every character is drawn from the unreserved set [A-Za-z0-9-._~].
 */
export function createVerifier(): string {
  const randomBytes = new Uint8Array(32);
  crypto.getRandomValues(randomBytes);
  return base64UrlEncode(randomBytes);
}

/**
 * Derive the S256 PKCE code challenge from a verifier (RFC 7636 §4.2).
 *
 *   code_challenge = BASE64URL( SHA-256( ASCII( code_verifier ) ) )
 *
 * @param verifier - The code verifier produced by `createVerifier`.
 * @returns A promise that resolves to the base64url-encoded SHA-256 digest.
 */
export async function challengeFromVerifier(verifier: string): Promise<string> {
  // Encode the verifier as ASCII bytes (verifier is always ASCII-safe by §4.1)
  const encoded = new TextEncoder().encode(verifier);
  // SHA-256 digest via WebCrypto
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return base64UrlEncode(digest);
}
