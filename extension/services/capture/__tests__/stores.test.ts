import { describe, it, expect } from "vitest";
import { createMemoryStorage } from "@/services/storage";
import { makeAuthStore } from "@/services/capture/stores";

describe("authStore", () => {
  it("round-trips tokens and defaults to signed-out", async () => {
    const store = makeAuthStore(createMemoryStorage());
    expect(await store.get()).toEqual({ accessToken: null, expiresAt: null });
    await store.set({ accessToken: "a", expiresAt: 123 });
    expect((await store.get()).accessToken).toBe("a");
  });
});
