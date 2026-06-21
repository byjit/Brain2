# Microsoft Edge support — design

**Date:** 2026-06-21
**Scope:** Build/dev tooling + distribution prep for the Brain2 capture extension (`extension/`).

## Goal

Let the extension be developed, built, and distributed for Microsoft Edge in addition
to Chrome. Edge is Chromium-based, so the manifest, content scripts, popup, and all
runtime code are unchanged. The work is (1) build/dev tooling, (2) making the OAuth
flow survive across browsers and store-published builds, and (3) documentation.

## Non-goals

- No changes to capture logic, UI, messaging, or the API/auth *code paths*.
- No Firefox changes (the existing `*:firefox` scripts stay as-is).
- Not in scope: actually submitting to the Edge Add-ons store (we document the steps;
  publishing is a manual, credentialed action).

## Background

- WXT 0.20 treats `edge` as a first-class Chromium build target (`wxt -b edge`),
  emitting to `.output/edge-mv3/`.
- The OAuth redirect URI is computed at runtime from
  `browser.identity.getRedirectURL()` → `https://<extension-id>.chromiumapp.org/`
  (`services/auth/oauth.ts`). The **extension ID** is therefore the only
  browser-dependent input to the auth flow.
- A Chromium extension ID is derived deterministically from the manifest `key`
  (public key). With no `key`, each browser/store assigns its own ID. With a pinned
  `key`, every Chromium browser (Chrome + Edge) derives the **same** ID for
  dev/unpacked builds.

## Design

### 1. Build & dev scripts

Add Edge counterparts to the existing Chrome/Firefox scripts in
`extension/package.json`:

```json
"dev:edge":   "wxt -b edge",
"build:edge": "wxt build -b edge",
"zip:edge":   "wxt zip -b edge"
```

No `vite`/manifest changes are required — `host_permissions`, `permissions`, and the
React/Tailwind pipeline are browser-agnostic.

### 2. Dev runner binary

`extension/web-ext.config.ts` (gitignored, local-only) gains an `edge` binary so
`pnpm dev:edge` launches Edge with hot reload:

```ts
binaries: {
  chrome: '/Applications/chrome.app/Contents/MacOS/Google Chrome',
  edge:   '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
},
```

Because this file is gitignored, the change is documented (README + `.env`/runner
notes) rather than committed; the committed artifact is the documentation that tells a
developer to add the Edge binary path for their OS.

### 3. Pin a deterministic extension ID (`manifest.key`)

Generate an RSA keypair once and set `manifest.key` (base64 public key, DER/SPKI) in
`extension/wxt.config.ts`. Effect:

- Chrome and Edge **dev/unpacked** builds resolve to the **same** extension ID, so
  `getRedirectURL()` returns one `chromiumapp.org` URL for both → only one redirect URI
  to register with the backend during development.
- The private key (`.pem`) is **not** committed; it is stored as a developer/CI secret
  and documented in `.env.example` / README as a required local artifact for producing
  ID-stable builds. The *public* `key` in `wxt.config.ts` is safe to commit.

Generation (documented, run once):

```bash
# private key (keep secret) + the base64 public key to paste into manifest.key
openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -out brain2-extension.pem
openssl rsa -in brain2-extension.pem -pubout -outform DER 2>/dev/null | base64 -w0
```

### 4. OAuth redirect registration (distribution prep)

The backend must allow each build's redirect URI. Document the matrix:

| Build | Extension ID source | Redirect URI to register |
|-------|--------------------|--------------------------|
| Dev/unpacked (Chrome + Edge), key pinned | Derived from `manifest.key` (same for both) | one `https://<id>.chromiumapp.org/` |
| Chrome Web Store | Store-assigned | `https://<cws-id>.chromiumapp.org/` |
| Edge Add-ons | Store-assigned | `https://<edge-id>.chromiumapp.org/` |

For published builds the store assigns the ID, so register each store's redirect URL.
The exact value is obtained by logging `browser.identity.getRedirectURL()` in the
loaded build (or computing it from the published ID). This extends the README's
existing "blocking prerequisite (end-to-end sign-in)" note, which already requires
registering the dev redirect URL.

### 5. Documentation updates

- `extension/README.md` — replace the single-line Firefox/Chrome note with an explicit
  **Edge** subsection under Scripts; add the redirect-registration matrix to the
  blocking-prerequisite section; add an Edge row to the manual QA checklist (load
  `.output/edge-mv3/` in Edge and run the same sign-in/save walkthrough).
- `AGENTS.md` (repo source-of-truth) — add `dev:edge`, `build:edge`, `zip:edge` to the
  Extension scripts list, beside the Firefox entries.
- `CLAUDE.md` — mirror the same three scripts in its Extension scripts list.
- `extension/.env.example` / README — note the optional `brain2-extension.pem` private
  key location for producing ID-stable builds.
- `docs/spec.md` — where the extension is described as a *capability* (the "Save once"
  line, the §6 capability table row, the §8 heading "Capture UX (Chrome Extension)"),
  generalize "Chrome" to "Chrome/Edge" (Chromium). Leave runtime-mechanism references
  to `chrome.storage`/`chrome.identity` as-is — those are the real API names.
- `docs/local-setup.md` / `docs/production-setup.md` — if either documents loading or
  building the extension, add the Edge build path (`.output/edge-mv3/`, `build:edge`)
  alongside Chrome.

## Testing / verification

- `pnpm compile` (tsc) passes — config-only changes must not break types.
- `pnpm test` (Vitest) passes unchanged — no runtime code is touched; the offline OAuth
  unit tests remain valid since the redirect URI is still injected.
- `pnpm build:edge` produces `.output/edge-mv3/` with a manifest containing the pinned
  `key`.
- Manual: load `.output/edge-mv3/` unpacked in Edge; confirm the popup, the three
  capture modes, and (against a backend with the dev redirect URI registered) the
  sign-in round-trip.

## Risks / notes

- **Store IDs still diverge.** Pinning `key` fixes dev parity only; published Chrome and
  Edge builds get store-assigned IDs. This is why the redirect-registration matrix lists
  all three. Documented, not solved in code.
- **`web-ext.config.ts` is gitignored**, so the Edge binary path can't be committed;
  the safeguard is documentation telling developers to add it. Acceptable — it mirrors
  how the Chrome binary is already handled.
- Keep the private signing key out of git; only the public `key` is committed.
