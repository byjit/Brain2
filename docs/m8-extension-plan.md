# M8 — Chrome Extension Capture Client: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Also load `wxt-browser-extensions` (perf rules) and `frontend-design` (popup UI).

**Goal:** Build the Brain2 Chrome extension — a capture-only client with three save modes (save page, element picker, custom note), OAuth sign-in, and a "needs attention" failure surface — on top of the existing WXT scaffold in `/extension`.

**Architecture:** Popup is the only entry point (no shortcuts). The **background service worker** owns all network/auth/state; the **content script** does DOM work (Readability extraction + the element picker overlay + Turndown conversion); the **popup** is thin UI that messages the background. All cross-context calls go through the existing `@/services/messaging` (Zod-typed `defineMessage`) and all persisted state through `@/services/storage` (`defineStore`). Saves are fire-and-forget against the M7 backend.

**Tech Stack:** WXT 0.20 · React 19 · Tailwind 4 + shadcn/Base-UI · `webext-bridge` (via the messaging service) · `@mozilla/readability` · `turndown` + `turndown-plugin-gfm` · `chrome.identity` (PKCE OAuth) · Vitest.

---

## App split (the `platform/` vs `extension/` judgment)

| App | Role | Milestone |
| --- | --- | --- |
| **`extension/`** | **Capture client.** Popup + content script + background. Save page / element picker / custom note. OAuth via `chrome.identity`. Failure badge. | **M8 (this plan)** |
| **`platform/`** | **Web dashboard + landing page** (spec §12). Google sign-in, Personal Access Token generation/management, the "needs attention" repair list, marketing/landing/blog/changelog. Already scaffolded with TanStack Router (`_landing`, `_public/login`, `_authed/dashboard` stub). | **M7 frontend** (separate plan — see *Companion* below) |

The extension **captures**; it does not manage. Viewing/bulk-editing/repair-at-scale lives in `platform/`. The extension's only management surface is the narrow failed-entry repair popup (spec §8.4).

**Backend contract this plan targets (built in M7):**
- `POST /entries` `{url?, title?, captured_text?, type, source_url?}` → `{id, status}` (Bearer auth).
- `GET /entries/failed` → `{total, entries:[{id,url,title,note,error_message,updated_at}]}`.
- `PATCH /entries/{id}` `{note, tags?}` → updated entry (repair).
- OAuth 2.1 + PKCE: `GET /oauth/authorize` (S256, redirect_uri allowlist, state) → code; `POST /oauth/token` (authorization_code grant) → `{access_token, token_type, expires_in, refresh_token?}`.

---

## File structure

```
extension/
  wxt.config.ts                      # MODIFY: permissions, host_permissions, action, web_accessible_resources
  .env / .env.example                # NEW: VITE_BRAIN2_API_URL, VITE_BRAIN2_OAUTH_CLIENT_ID
  package.json                       # MODIFY: add readability, turndown, turndown-plugin-gfm

  lib/
    config.ts                        # NEW: typed env (API base URL, OAuth client id, redirect URL)
    chat-domains.ts                  # NEW: detected chat-domain matchers (-> type=conversation)

  services/
    capture/                         # NEW feature: contracts shared across contexts
      messages.ts                    #   defineMessage contracts (popup<->bg<->content)
      stores.ts                      #   defineStore: authStore, settingsStore, needsAttentionStore
      types.ts                       #   Zod schemas: SaveRequest, SaveResult, FailedEntry, Tokens
    api/
      client.ts                      # NEW: typed backend client (save/getFailed/repair) + Bearer
    auth/
      pkce.ts                        # NEW: PURE code_verifier/challenge (S256) helpers
      oauth.ts                       # NEW: chrome.identity launchWebAuthFlow + token exchange/refresh

  entrypoints/
    background.ts                    # MODIFY: sync handler registration, save orchestration, badge, polling
    content.ts                       # MODIFY (or split): Readability + chat extraction + picker overlay
    picker/                          # NEW: element-picker overlay logic + Turndown conversion
      picker-overlay.ts              #   hover/outline/expand-contract/Escape (Shadow DOM)
      html-to-markdown.ts            #   PURE Turndown(+gfm) wrapper
    popup/
      App.tsx                        # MODIFY: 3-mode UI + signed-out + needs-attention list
      modes/SavePage.tsx             # NEW
      modes/CustomNote.tsx           # NEW
      modes/NeedsAttention.tsx       # NEW
      SignIn.tsx                     # NEW

  tests/                             # NEW (Vitest): pkce, html-to-markdown, api client, stores, picker walk
```

**Pattern rules (from `extension/docs/services-guide.md` — follow exactly):**
- Import only from the barrels `@/services/messaging` and `@/services/storage`; never reach into internals or import `webext-bridge`/`wxt/utils/storage` in feature code.
- Declare message/store contracts **near the feature** (`services/capture/`), Zod schemas are the source of truth, types inferred.
- Each entrypoint calls `setDefaultBridge(createWebextBridge(...))` once, after importing its context subpath.

**WXT perf rules that bind this plan:** `svc-register-listeners-synchronously`, `svc-avoid-global-state` (state in stores, not module vars), `inject-use-main-function`, `inject-choose-correct-world` (ISOLATED), `ui-use-shadow-dom` (picker overlay), `manifest-minimal-permissions` (prefer `activeTab` + `scripting` over `<all_urls>`), `ts-use-browser-not-chrome`.

---

## Task 0: Dependencies, env, manifest

**Files:** Modify `extension/package.json`, `extension/wxt.config.ts`; Create `extension/.env.example`, `extension/lib/config.ts`.

- [ ] **Step 1: Add deps**
```bash
cd extension
pnpm add @mozilla/readability turndown turndown-plugin-gfm
pnpm add -D @types/turndown
```
- [ ] **Step 2: `.env.example`** (and a real `.env`, gitignored)
```
VITE_BRAIN2_API_URL=http://localhost:8000
VITE_BRAIN2_OAUTH_CLIENT_ID=brain2-extension
```
- [ ] **Step 3: `lib/config.ts`** — typed accessors; `redirectUrl` from `browser.identity.getRedirectURL()`.
```ts
export const config = {
  apiUrl: import.meta.env.VITE_BRAIN2_API_URL as string,
  oauthClientId: import.meta.env.VITE_BRAIN2_OAUTH_CLIENT_ID as string,
};
```
- [ ] **Step 4: `wxt.config.ts` manifest** — minimal permissions:
```ts
manifest: {
  name: "Brain2",
  permissions: ["activeTab", "scripting", "storage", "identity"],
  host_permissions: [`${import.meta.env.VITE_BRAIN2_API_URL}/*`],
  action: { default_title: "Save to Brain2" },
}
```
Content script (`content.ts`) keeps `matches: ['<all_urls>']` ONLY if Readability must run on arbitrary pages; otherwise prefer programmatic injection via `scripting` + `activeTab` (rule `inject-dynamic-registration`, `manifest-minimal-permissions`). Decide: **use programmatic injection** so no broad host permission is needed at install.
- [ ] **Step 5: Commit** `chore(ext): deps, env, manifest permissions for capture`

---

## Task 1: Shared contracts (Zod types, stores, messages)

**Files:** Create `services/capture/types.ts`, `services/capture/stores.ts`, `services/capture/messages.ts`. Test `tests/stores.test.ts`.

- [ ] **Step 1: Write failing store test**
```ts
import { describe, it, expect } from "vitest";
import { createMemoryStorage } from "@/services/storage";
import { makeAuthStore } from "@/services/capture/stores";

it("auth store round-trips tokens and defaults to signed-out", async () => {
  const store = makeAuthStore(createMemoryStorage());
  expect(await store.get()).toEqual({ accessToken: null, refreshToken: null, expiresAt: null });
  await store.set({ accessToken: "a", refreshToken: "r", expiresAt: 123 });
  expect((await store.get()).accessToken).toBe("a");
});
```
- [ ] **Step 2: Run → FAIL** (`makeAuthStore` undefined). `pnpm test tests/stores.test.ts`
- [ ] **Step 3: `types.ts`**
```ts
import { z } from "zod";
export const SaveType = z.enum(["page", "clip", "conversation", "note"]);
export const SaveRequest = z.object({
  url: z.string().url().optional(),
  title: z.string().optional(),
  captured_text: z.string().optional(),
  type: SaveType,
  source_url: z.string().url().optional(),
});
export const SaveResult = z.object({ id: z.string(), status: z.enum(["saved", "updated"]) });
export const Tokens = z.object({
  accessToken: z.string().nullable(),
  refreshToken: z.string().nullable(),
  expiresAt: z.number().nullable(), // epoch ms
});
export const FailedEntry = z.object({
  id: z.string(), url: z.string().nullable(), title: z.string().nullable(),
  note: z.string().nullable(), error_message: z.string().nullable(), updated_at: z.string(),
});
export type SaveRequest = z.infer<typeof SaveRequest>;
export type Tokens = z.infer<typeof Tokens>;
export type FailedEntry = z.infer<typeof FailedEntry>;
```
- [ ] **Step 4: `stores.ts`** — use `defineStore` (area `local` for tokens, `session` not durable enough; `sync` leaks to other machines — use `local`). Expose `makeAuthStore(backend?)` taking an optional backend so tests inject `createMemoryStorage()`.
```ts
import { defineStore } from "@/services/storage";
import { Tokens } from "./types";
import { z } from "zod";
export const makeAuthStore = (backend?: unknown) => defineStore({
  key: "auth", area: "local", schema: Tokens,
  defaultValue: { accessToken: null, refreshToken: null, expiresAt: null },
  _backend: backend as never,
});
export const authStore = makeAuthStore();
export const needsAttentionStore = defineStore({
  key: "needs_attention_count", area: "local", schema: z.number().int().nonnegative(), defaultValue: 0,
});
export const settingsStore = defineStore({
  key: "settings", area: "local",
  schema: z.object({ chatDomains: z.array(z.string()) }),
  defaultValue: { chatDomains: ["chat.openai.com", "chatgpt.com", "claude.ai", "gemini.google.com"] },
});
```
- [ ] **Step 5: Run → PASS. Commit.**
- [ ] **Step 6: `messages.ts`** — contracts (no separate test; exercised in later tasks):
```ts
import { defineMessage } from "@/services/messaging";
import { SaveRequest, SaveResult } from "./types";
import { z } from "zod";
// popup -> background
export const savePageMsg   = defineMessage({ name: "save-page",   request: z.object({ overrideUrl: z.string().url().optional() }), response: SaveResult });
export const saveNoteMsg   = defineMessage({ name: "save-note",   request: z.object({ text: z.string().min(1) }), response: SaveResult });
export const startPickerMsg= defineMessage({ name: "start-picker",request: z.object({}) /* no response: popup closes */ });
// content -> background
export const saveClipMsg   = defineMessage({ name: "save-clip",   request: SaveRequest, response: SaveResult });
// background -> popup (event)
export const needsAttentionChanged = defineMessage({ name: "needs-attention-changed", request: z.object({ count: z.number() }) });
```

---

## Task 2: PKCE helpers (pure, TDD)

**Files:** Create `services/auth/pkce.ts`; Test `tests/pkce.test.ts`.

- [ ] **Step 1: Failing test**
```ts
import { describe, it, expect } from "vitest";
import { createVerifier, challengeFromVerifier } from "@/services/auth/pkce";

it("S256 challenge is url-safe base64 of sha256(verifier), no padding", async () => {
  const v = createVerifier();
  expect(v).toMatch(/^[A-Za-z0-9\-._~]{43,128}$/);
  const c = await challengeFromVerifier(v);
  expect(c).toMatch(/^[A-Za-z0-9\-_]+$/); // no +,/,=
});
```
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** using WebCrypto (`crypto.getRandomValues`, `crypto.subtle.digest("SHA-256", ...)`), base64url-encode without padding.
- [ ] **Step 4: Run → PASS. Commit.**

---

## Task 3: OAuth flow via chrome.identity

**Files:** Create `services/auth/oauth.ts`. Test the pure URL-building + token-response parsing; the `launchWebAuthFlow` call itself is integration (manual QA).

- [ ] **Step 1: Failing test** for `buildAuthorizeUrl({clientId, redirectUri, challenge, state})` → contains `code_challenge_method=S256`, encoded `redirect_uri`, `state`, `response_type=code`.
- [ ] **Step 2: Run → FAIL → implement → PASS.**
- [ ] **Step 3: `signIn()`**: create verifier+challenge+state → `browser.identity.launchWebAuthFlow({ url: buildAuthorizeUrl(...), interactive: true })` → parse `code`+`state` from the returned redirect (verify state matches) → `POST {apiUrl}/oauth/token` with `grant_type=authorization_code, code, code_verifier, redirect_uri, client_id` → store tokens (compute `expiresAt = Date.now() + expires_in*1000`) in `authStore`.
- [ ] **Step 4: `getValidAccessToken()`**: read `authStore`; if `expiresAt` within 60s and a refresh token exists, `POST /oauth/token grant_type=refresh_token`; else if expired/none → return null (caller triggers `signIn`).
- [ ] **Step 5: `signOut()`** clears `authStore`. **Commit.**

---

## Task 4: Backend API client

**Files:** Create `services/api/client.ts`. Test `tests/api-client.test.ts` (inject a `fetch` stub + a token getter).

- [ ] **Step 1: Failing test** — `createClient({ baseUrl, getToken, fetchImpl })`; `save()` POSTs to `/entries` with `Authorization: Bearer <token>` and parses `SaveResult`; on 401 throws a typed `UnauthorizedError`; on network error throws `NetworkError`.
```ts
it("save() sends Bearer and parses result", async () => {
  const calls: any[] = [];
  const fetchImpl = async (url: string, init: any) => { calls.push([url, init]); return new Response(JSON.stringify({ id: "x", status: "saved" }), { status: 201 }); };
  const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
  const r = await c.save({ type: "note", captured_text: "hi" });
  expect(r.id).toBe("x");
  expect(calls[0][1].headers.Authorization).toBe("Bearer t");
});
```
- [ ] **Step 2: Run → FAIL → implement (`save`, `getFailed`, `repair`; validate responses with the Zod schemas; actionable typed errors) → PASS.**
- [ ] **Step 3: Commit.**

---

## Task 5: Background service worker (orchestration, badge, polling)

**Files:** Modify `entrypoints/background.ts`.

- [ ] **Step 1: Register handlers SYNCHRONOUSLY at top level** (rule `svc-register-listeners-synchronously`): `setDefaultBridge(createWebextBridge(...))`, then `savePageMsg.handle(...)`, `saveNoteMsg.handle(...)`, `saveClipMsg.handle(...)`, `startPickerMsg.handle(...)`.
- [ ] **Step 2: `savePage` handler:** get active tab (`browser.tabs.query({active,currentWindow})`); if its host matches `settingsStore.chatDomains` → inject conversation extractor (`type: "conversation"`, content persisted); else inject Readability extractor → build `SaveRequest{type:"page"}` (no captured_text persisted server-side for page, but send it so the worker can summarize). Call `client.save`. Return result.
- [ ] **Step 3: `saveNote`/`saveClip` handlers** → `client.save`.
- [ ] **Step 4: `startPicker` handler:** `browser.scripting.executeScript` to start picker overlay in the active tab; popup will have closed.
- [ ] **Step 5: Auth gate:** before any save, `getValidAccessToken()`; if null, return a typed `{ error: "signed_out" }` so the popup shows Sign-In.
- [ ] **Step 6: Badge + polling:** `updateBadge()` sets `browser.action.setBadgeText` from `needsAttentionStore`; a polling alarm (`browser.alarms`, every ~5 min, NOT a module-global timer — `svc-avoid-global-state`) calls `client.getFailed`, writes `needsAttentionStore`, updates badge, emits `needsAttentionChanged`. Also refresh after each save error.
- [ ] **Step 7: Tests** for the pure helpers (host→type mapping uses `lib/chat-domains.ts`; badge text formatting). **Commit.**

---

## Task 6: Content extraction (Readability + conversation) — pure helpers TDD

**Files:** Create `lib/chat-domains.ts`, `entrypoints/picker/html-to-markdown.ts`; Modify `entrypoints/content.ts`. Tests `tests/chat-domains.test.ts`, `tests/html-to-markdown.test.ts`.

- [ ] **Step 1: `chat-domains.ts` + test** — `isChatDomain(host, domains)` (suffix match, www-insensitive).
- [ ] **Step 2: `html-to-markdown.ts` + test** — wrap Turndown + `gfm` plugin; `htmlToMarkdown(html)` preserves code blocks/lists/links. Test a `<pre><code>` and a `<ul>` convert correctly.
- [ ] **Step 3: Readability extraction** in content script `main()` (rule `inject-use-main-function`): `new Readability(document.cloneNode(true)).parse()` → `{title, textContent}`; conversation extractor for chat DOMs (best-effort thread text). Return via the message the background expects.
- [ ] **Step 4: Run tests → PASS. Commit.**

---

## Task 7: Element picker overlay (Shadow DOM)

**Files:** Create `entrypoints/picker/picker-overlay.ts`. Test the pure DOM-walk (`tests/picker-walk.test.ts` with jsdom).

- [ ] **Step 1: Failing test** for `expandSelection(el)` / `contractSelection(el)` (walks up/down the DOM to a "logical block"), and `elementToClip(el)` → `{ html, sourceUrl }`.
- [ ] **Step 2: Implement** the walk + a Shadow-DOM overlay (rule `ui-use-shadow-dom`): hover highlights the element under cursor with an **accent-colored** outline box (not red); ArrowUp/Down (or wheel-mod) expand/contract; click captures; **Escape cancels**. On capture → `htmlToMarkdown(el.outerHTML)` → render an editable in-page review card (small, shadow-DOM, Tailwind-scoped) with the Markdown in a textarea + Save/Cancel. On Save → `saveClipMsg.send({ type:"clip", captured_text, source_url, title })` to background.
- [ ] **Step 3: Run pure tests → PASS. Commit.** (Visual behavior validated in manual QA, Task 10.)

---

## Task 8: Popup UI (3 modes + sign-in + needs-attention)

**Files:** Modify `entrypoints/popup/App.tsx`; Create `modes/SavePage.tsx`, `modes/CustomNote.tsx`, `modes/NeedsAttention.tsx`, `SignIn.tsx`. Use `frontend-design` skill for polish.

- [ ] **Step 1:** `App.tsx` boots: `setDefaultBridge` (popup context); read `authStore`. If signed out → `<SignIn/>` (one button → `savePageMsg` path triggers `signIn()` in bg, or a dedicated `signInMsg`). If signed in → mode chooser.
- [ ] **Step 2: SavePage (prominent default):** one button → `savePageMsg.send({})`; on success show a **toast** and auto-close (fire-and-forget, spec §8.2); secondary collapsible field to paste a different URL (`overrideUrl`). No spinner-blocking.
- [ ] **Step 3: Select content:** button → `startPickerMsg.send({})` then `window.close()` (popup must close for picking).
- [ ] **Step 4: Custom note:** textarea + Save → `saveNoteMsg.send({text})` → toast.
- [ ] **Step 5: NeedsAttention:** if `needsAttentionStore > 0` show a section listing failed entries (from a `getFailedMsg` to bg); each row → fill-note textarea → `repair` via bg → removes from list, decrements badge.
- [ ] **Step 6:** Responsive, consistent with shadcn components already in `components/ui`. **Commit.**

---

## Task 9: First-run sign-in + badge wiring

- [ ] **Step 1:** On install (`svc-handle-install-update`), if signed out, set a subtle badge or rely on popup SignIn. Spec §8.3: first run = one-time "Sign in with Google"; thereafter silent except the failure badge.
- [ ] **Step 2:** Confirm badge reflects `needsAttentionStore` on startup and on `needsAttentionChanged`. **Commit.**

---

## Task 10: Build, load, manual QA (dogfood gate)

- [ ] `pnpm compile` (tsc) and `pnpm test` green.
- [ ] `pnpm dev` → load unpacked in Chrome. With the M7 backend running locally (`uv run uvicorn brain2.main:app --reload`) and an OAuth client/redirect registered:
  - [ ] Sign in (chrome.identity → Brain2 OAuth → token stored).
  - [ ] **Save page** on a normal article → toast → appears active in backend within seconds (note + tags).
  - [ ] **Save page** on a chat domain → saved as `conversation` with content persisted.
  - [ ] **Element picker**: hover outline accent-colored, expand/contract works, Escape cancels, click → Markdown review card → save → `clip` with `source_url`.
  - [ ] **Custom note** → `note` saved.
  - [ ] Force a failure (e.g., bad page) → badge count appears → popup needs-attention list → fill note → repairs → badge clears.
- [ ] Update `extension/README.md` + root `AGENTS.md` (extension scripts/permissions) + `docs/status.md` (M8 done). Commit.

---

## Self-review (spec §8 coverage)

- §8.1 three modes → Tasks 5–8. Save page prominent/instant + secondary URL field → Task 8.2. Element picker DOM granularity + Turndown + review + Escape → Task 7. Custom note → Task 8.4. ✅
- §8.2 user never touches tags; fire-and-forget toast → Task 8 (no tag UI; toast, no spinner). ✅
- §8.3 first-run sign-in; failure badge as the only proactive nudge → Tasks 3, 9. ✅
- §8.4 capture-only (management lives in `platform/`) → enforced by scope; only repair list is present. ✅
- §7.1 client scrape (Readability / picked element → Markdown / note text) + POST → Tasks 5–7. ✅
- No keyboard shortcuts → confirmed (popup-only entry). ✅

**Open decisions to confirm before executing:** (1) OAuth redirect — `chrome.identity.getRedirectURL()` must be in the M7 redirect_uri allowlist; (2) whether to ship broad `<all_urls>` content matches or use programmatic `scripting` injection (this plan chooses programmatic injection for minimal permissions); (3) conversation extraction is best-effort per chat site — start with generic visible-text capture, refine in dogfood (spec §15 open question).

---

## Companion: `platform/` dashboard (the M7 frontend, separate plan)

Not built here. When ready, a sibling plan (`docs/platform-dashboard-plan.md`) should cover, against the M7 backend: wire the stubbed `_authed.tsx` guard to a real session (`GET /auth/me`), `_public/login.tsx` → `/auth/login` (Google), a **Personal Access Tokens** page (`/settings/tokens` CRUD, show-once key), and a **Needs Attention** repair view (`GET /entries/failed` + `PATCH /entries/{id}`). Landing/blog/changelog already scaffolded via content-collections. Ask me to write this plan when you want it.
