import { describe, it, expect } from "vitest";
import { createVerifier, challengeFromVerifier } from "@/services/auth/pkce";

describe("pkce", () => {
  it("createVerifier returns a 43-128 char unreserved-charset string", () => {
    const v = createVerifier();
    expect(v).toMatch(/^[A-Za-z0-9\-._~]{43,128}$/);
  });

  it("S256 challenge is url-safe base64 of sha256(verifier), no padding", async () => {
    const v = createVerifier();
    const c = await challengeFromVerifier(v);
    expect(c).toMatch(/^[A-Za-z0-9\-_]+$/); // base64url: no +, /, or =
  });

  it("challenge matches the known RFC 7636 Appendix B test vector", async () => {
    // RFC 7636 B.1: verifier "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    // -> challenge "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    const c = await challengeFromVerifier("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk");
    expect(c).toBe("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
  });

  it("verifiers are random across calls", () => {
    expect(createVerifier()).not.toBe(createVerifier());
  });
});
