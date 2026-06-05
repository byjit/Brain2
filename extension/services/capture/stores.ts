import { defineStore, type MemoryStorageBackend } from "@/services/storage";
import { Tokens } from "./types";
import { z } from "zod";

// area 'local': tokens must survive SW restarts ('session' does not) and must NOT
// sync to other machines ('sync'). Chat domains are a static const (Task 6,
// lib/chat-domains.ts), not a store — nothing in v1 edits them (YAGNI).
export const makeAuthStore = (backend?: MemoryStorageBackend) =>
  defineStore({
    key: "auth",
    area: "local",
    schema: Tokens,
    defaultValue: { accessToken: null, expiresAt: null },
    ...(backend ? { _backend: backend } : {}),
  });

export const authStore = makeAuthStore();

export const needsAttentionStore = defineStore({
  key: "needs_attention_count",
  area: "local",
  schema: z.number().int().nonnegative(),
  defaultValue: 0,
});
