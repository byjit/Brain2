import { describe, it, expect } from "vitest";
import { isSignedOutError } from "@/entrypoints/popup/lib/is-signed-out";

describe("isSignedOutError", () => {
  it("detects signed_out in message", () => {
    expect(isSignedOutError(new Error("signed_out"))).toBe(true);
  });
  it("detects signed_out in cause.message", () => {
    expect(
      isSignedOutError({
        message: 'Handler for "save-page" threw',
        cause: { message: "signed_out" },
      }),
    ).toBe(true);
  });
  it("detects signed_out in a string cause", () => {
    expect(
      isSignedOutError({
        message: 'Handler for "save-page" threw',
        cause: "Error: signed_out",
      }),
    ).toBe(true);
  });
  it("false for unrelated errors", () => {
    expect(isSignedOutError(new Error("network down"))).toBe(false);
    expect(isSignedOutError(null)).toBe(false);
  });
});
