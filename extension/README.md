# Brain2 — Chrome capture extension

A capture-only browser extension for [Brain2](../README.md): save the current page,
a hand-picked element, or a quick note straight into your memory store, and repair
anything that failed to ingest. Built on WXT 0.20 (MV3) + React 19 + Tailwind 4.

## What it does

The popup offers three capture modes plus a repair list:

1. **Save page** (the prominent action) — captures the active tab. Chat domains
   (see [`lib/chat-domains.ts`](lib/chat-domains.ts)) are saved as a `conversation`;
   everything else as a `page`. A secondary, collapsible "save a different URL" lets
   you ingest an arbitrary URL.
2. **Select content** — an element picker overlay. Hover to highlight, expand/contract
   the selection by walking the DOM, then review the HTML→Markdown result before saving.
   `Escape` cancels.
3. **Custom note** — a free-text note.
4. **Needs Attention** — lists entries that failed enrichment on the backend and lets
   you trigger a repair. A toolbar badge surfaces the pending count.

Saves are fire-and-forget: a toast (sonner) confirms, and the popup auto-closes.

## Architecture

The extension keeps responsibilities cleanly separated:

- **Popup** (`entrypoints/popup/`) — thin UI only. Renders the three modes and the
  repair list; it owns no network or auth logic. It reads/writes shared stores and
  sends messages to the background worker.
- **Background service worker** (`entrypoints/background.ts`) — owns **all** network,
  auth, and state. It orchestrates saves (injects the extractor, calls the API client),
  gates on auth (throws `signed_out`, which the popup string-matches to show Sign-In),
  and maintains the "needs attention" badge. The badge is refreshed by a 5-minute
  `chrome.alarms` poll (no `setInterval`), on every `getFailed`/`repair`, and repainted
  on cold start.
- **Content scripts** — do the DOM work, injected programmatically on a user gesture
  (`registration: "runtime"`):
  - `entrypoints/content.ts` — page/conversation extractor (Mozilla Readability plus
    best-effort chat extraction).
  - `entrypoints/picker.content.ts` + `entrypoints/picker/` — the element-picker overlay
    in a Shadow DOM (`createShadowRootUi`), with the DOM-walk selection logic and a
    Turndown-based HTML→Markdown review card.

Shared contracts live in `services/`: Zod types and the `authStore`/`needsAttentionStore`
(`services/capture/`), typed `defineMessage` message contracts (`services/messaging/`),
the typed API client (`services/api/client.ts`), and the OAuth/PKCE helpers
(`services/auth/`).

### Auth

OAuth 2.1 + PKCE (S256) via `chrome.identity.launchWebAuthFlow` against the Brain2
authorization server (M7). PKCE is implemented in `services/auth/pkce.ts`; the flow in
`services/auth/oauth.ts`. **There is no refresh token** — the 1-hour access-token TTL is
handled by a silent (`interactive: false`) re-auth attempt.

### Why these permissions

`extension/wxt.config.ts` requests:

```
permissions:      [activeTab, scripting, storage, identity, alarms]
host_permissions:  [<VITE_BRAIN2_API_URL origin>/*]
```

- **`host_permissions` (the API origin, not `<all_urls>`)** — in MV3, fetches made from
  the background service worker against a host listed in `host_permissions` are
  CORS-exempt. The API client is therefore called **only** from the background worker;
  this is a structural invariant, not a runtime check.
- **`activeTab` + `scripting` instead of `<all_urls>`** — the extractor and picker are
  runtime-registered content scripts injected only when the user clicks a capture
  action. We never request blanket host access to the pages you browse.
- `storage` backs the shared stores; `identity` drives the OAuth flow; `alarms` powers
  the badge poll.

## Setup

```bash
pnpm install
cp .env.example .env   # then fill in the two values below
```

`.env` (see [`.env.example`](.env.example)):

- `VITE_BRAIN2_API_URL` — Brain2 backend origin (drives both the API client and the
  `host_permissions` entry). Defaults to `http://localhost:8000`.
- `VITE_BRAIN2_OAUTH_CLIENT_ID` — the OAuth client id registered with the backend.

## Scripts

Run from `extension/`:

- `pnpm dev` — WXT dev server with hot reload (Chrome).
- `pnpm build` — production bundle (`.output/chrome-mv3/`).
- `pnpm compile` — `tsc --noEmit` type check.
- `pnpm test` — Vitest suite once (`pnpm test:watch` for watch mode).

Firefox variants (`dev:firefox`, `build:firefox`, `zip:firefox`) exist but the
extension is developed against Chrome.

## Manual QA / dogfood checklist

Load the unpacked build (`.output/chrome-mv3/`) in Chrome, then walk through:

- [ ] **Sign in** with Google from the signed-out popup.
- [ ] **Save page** on an ordinary site → ingested as a `page`.
- [ ] **Save a chat** (e.g. a known chat domain) → ingested as a `conversation`.
- [ ] **Element picker** — select content, expand/contract, review Markdown, save.
- [ ] **Custom note** — save a free-text note.
- [ ] **Force a failure** (e.g. backend enrichment error) → badge count appears →
      open **Needs Attention** → repair → badge clears.

### Blocking prerequisite (end-to-end sign-in)

The OAuth flow cannot complete end-to-end until the **M7 backend** is updated:

1. An unauthenticated `GET /oauth/authorize` must **redirect to Google login** rather
   than returning `401`.
2. The extension's `chrome.identity.getRedirectURL()` value must be added to the
   backend `OAUTH_REDIRECT_URIS` allowlist.

Until both ship, the signed-in capture paths can't be exercised against a live backend.
The full extension test suite (102 tests) runs offline and is independent of this gate.
