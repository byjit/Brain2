# Brain2 — Local Setup & Testing

How to run the whole Brain2 stack on your machine and exercise it end to end:
the **backend** (FastAPI + per-user SQLite + MCP), the **platform** dashboard, the
**Chrome extension**, and an **MCP client** (Claude Code / Cursor).

> Source of truth for behavior is [`spec.md`](./spec.md); current build state is
> [`status.md`](./status.md). This guide is operational only.

> [!TIP]
> **Quick Start with Makefile:**
> You can set up and run the services concurrently using the root `Makefile`:
> - Run `make setup` to initialize all dependencies and environment files.
> - Run `make dev` to start the backend and platform concurrently.
> - Run `make help` to see all available commands.

---

## Components & ports

| Component | Dir | Dev command | Default URL |
| --- | --- | --- | --- |
| Backend (REST + MCP) | [`backend/`](../backend) | `uv run uvicorn brain2.main:app --reload` | `http://localhost:8000` |
| MCP endpoint | (mounted in backend) | — | `http://localhost:8000/connect/mcp` (streamable HTTP) |
| Platform dashboard | [`platform/`](../platform) | `pnpm dev` | `http://localhost:3000` |
| Chrome extension | [`extension/`](../extension) | `pnpm dev` | loads into a dev Chrome profile |

Per-user databases are written to `data/users/{user_id}.db`; the central credential
store is `data/auth.db`. Both are gitignored and created on first use.

---

## Prerequisites

- **Python 3.12** (pinned in `backend/.python-version`)
- **[uv](https://docs.astral.sh/uv/)** — backend package manager
- **Node.js 20+** and **pnpm** — platform & extension
- **Google Chrome** (or a Chromium build) for the extension
- A **Google Cloud OAuth 2.0 Client** (Web application) for Google Sign-In — see
  [§5](#5-google-oauth-dev-configuration). Optional for backend-only / API-key testing.
- A **Gemini API key** if you want real summarization/embeddings/auto-tagging. Without
  it the backend still runs; the enrichment worker uses offline fakes in tests, but live
  enrichment of real saves needs the key.

---

## 1. Clone and create the root `.env`

All secrets live in a single **repo-root `.env`** (gitignored), read by the backend via
pydantic-settings. There is no committed `.env.example` at the root — create `.env` with:

```dotenv
# --- LLM / enrichment (optional locally; required for live notes/tags) ---
GEMINI_API_KEY=your-gemini-key

# --- Google OAuth (required for Google Sign-In; optional for API-key-only testing) ---
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-secret

# --- Auth / sessions ---
JWT_SECRET=dev-insecure-secret-change-me        # any value locally; MUST be strong in prod
COOKIE_SECURE=false                              # allow the session cookie over http://localhost
DASHBOARD_URL=http://localhost:3000              # MUST match the platform dev port (see note)
ACCESS_TOKEN_TTL=3600                            # optional; lower temporarily to test silent re-auth
REFRESH_TOKEN_TTL=2592000                        # optional; OAuth refresh-token TTL (rotated on use)

# Exact-match allowlist of OAuth redirect URIs (comma-separated). Add the extension's
# redirect URL here once you have it (see §5). The dashboard login does not need one.
OAUTH_REDIRECT_URIS=https://<extension-id>.chromiumapp.org/
```

> **Port note:** the backend's built-in default `DASHBOARD_URL` is `http://localhost:5173`,
> but the platform dev server runs on **`http://localhost:3000`** (`vite --port 3000`).
> Set `DASHBOARD_URL=http://localhost:3000` so `/api/auth/callback/google` redirects back to the
> running dashboard. (Or run the platform on 5173 — just keep the two in sync.)

Every other setting has a safe default (see `backend/src/brain2/config.py`): `DATA_DIR`,
`AUTH_DB_PATH`, `WORKER_MAX_ATTEMPTS`, `CANONICALIZE_THRESHOLD`, `TAGS_PER_ENTRY_MAX/MIN`,
`GEMINI_SUMMARY_MODEL`, `GEMINI_EMBEDDING_MODEL`, etc. Override only when you need to.

---

## 2. Backend

```bash
cd backend
uv sync                                          # create .venv, install deps
uv run pytest -q                                 # full offline suite (no live keys needed)
uv run uvicorn brain2.main:app --reload          # dev server on :8000 (reads ../.env)
```

Smoke-check it:

```bash
curl -s http://localhost:8000/health             # -> {"status":"ok"}
```

REST surface (all entry endpoints require a `Bearer` credential):

- `POST /entries` — save (non-destructive upsert)
- `GET  /entries/failed` — needs-attention list
- `PATCH /entries/{id}` — repair
- `GET  /auth/login` → Google → `GET /api/auth/callback/google` (sets the dashboard session cookie)
- `GET  /auth/me`, `POST /auth/logout`
- `GET  /oauth/authorize`, `POST /oauth/token` — OAuth 2.1 + PKCE (web/extension);
  the token endpoint supports `authorization_code` **and** `refresh_token` grants and
  returns a rotating refresh token alongside the 1h access token
- `POST /oauth/register` — Dynamic Client Registration (RFC 7591) for MCP clients that
  self-register (e.g. Claude Web custom connectors)
- `POST/GET/DELETE /settings/tokens` — Personal Access Tokens (API keys)
- MCP tools at `http://localhost:8000/connect/mcp` (streamable HTTP); missing **or**
  invalid/expired tokens are challenged with `401` + `WWW-Authenticate`

---

## 3. Platform dashboard

```bash
cd platform
pnpm install
pnpm dev                                          # http://localhost:3000
pnpm test                                         # unit tests
pnpm build                                         # production build (vite build && tsc)
```

The dashboard is where you **sign in with Google** and **generate a Personal Access
Token** for MCP clients. (Its auth-guard / tokens / repair wiring against the M7 backend
is the platform's own milestone — see `status.md`.) Local login flow:
`pnpm dev` → open `:3000` → "Sign in" → `http://localhost:8000/auth/login` → Google →
`/api/auth/callback/google` → back to `DASHBOARD_URL`.

---

## 4. Chrome extension

```bash
cd extension
pnpm install
cp .env.example .env                              # then edit if your backend isn't on :8000
pnpm compile                                       # tsc --noEmit
pnpm test                                          # vitest (unit suite)
pnpm dev                                            # launches a dev Chrome with the extension + HMR
```

`extension/.env`:

```dotenv
VITE_BRAIN2_API_URL=http://localhost:8000
VITE_BRAIN2_OAUTH_CLIENT_ID=brain2-extension
```

`pnpm dev` opens a Chrome instance with the extension loaded. To load it into your normal
Chrome instead, run `pnpm build` and load the unpacked `extension/.output/chrome-mv3/`
directory via `chrome://extensions` → enable **Developer mode** → **Load unpacked**.

> The extension only ever calls the backend **from its background service worker**
> (CORS-exempt via `host_permissions`). The popup and content scripts talk to the
> background over typed messages — never `fetch` the backend directly. If you point the
> extension at a different backend origin, update `VITE_BRAIN2_API_URL` **and** the
> `host_permissions` origin in `extension/wxt.config.ts`.

---

## 5. Google OAuth (dev) configuration

In the [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services →
Credentials**, create an **OAuth client ID** of type **Web application** and set:

- **Authorized JavaScript origins:** `http://localhost:3000` (dashboard),
  `http://localhost:8000` (backend)
- **Authorized redirect URIs:** the backend callback
  `http://localhost:8000/api/auth/callback/google`

Put the client id/secret in the root `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`).

**Extension redirect URL.** `chrome.identity` uses a per-extension redirect of the form
`https://<extension-id>.chromiumapp.org/`. Get the exact value at runtime: open the
extension's background service worker console (`chrome://extensions` → the extension →
**service worker** → Inspect) and run:

```js
browser.identity.getRedirectURL()
```

Add that exact string to the backend's `OAUTH_REDIRECT_URIS` allowlist (it is matched
exactly — no substrings). `client_id` validation is two-tier: a client registered via
`POST /oauth/register` (RFC 7591) is validated against **its own** registered redirect
URIs; any other `client_id` (like the extension's `VITE_BRAIN2_OAUTH_CLIENT_ID`) falls
back to the static `OAUTH_REDIRECT_URIS` allowlist, so it only needs to be present, not
registered.

> [!TIP]
> **Interactive Sign-In Redirection:**
> If a user is not authenticated when the extension calls `GET /oauth/authorize`, the backend
> automatically redirects the browser/popup window to the Google Sign-in flow and returns
> them back to the authorization sequence seamlessly. Backend-only and API-key (MCP) testing is unaffected.

---

## 6. End-to-end local test (manual QA)

With backend (`:8000`), platform (`:3000`), and the extension all running:

1. **Sign in** — dashboard "Sign in with Google" (and, per the caveat above, this also
   unblocks the extension popup's sign-in in the same profile).
2. **Save page** — on a normal article, click the extension → **Save this page** → expect
   a toast; within seconds the entry appears `active` in the backend with a note + tags
   (needs `GEMINI_API_KEY` for real enrichment).
3. **Save a conversation** — on a detected chat domain (`chatgpt.com`, `claude.ai`,
   `chat.openai.com`, `gemini.google.com`) the same button saves as `conversation` with
   content persisted.
4. **Element picker** — **Select content** → hover (accent outline), `ArrowUp`/`ArrowDown`
   to expand/contract, click → Markdown review card → Save → stored as a `clip` with
   `source_url`. `Escape` cancels.
5. **Custom note** — type text → Save → stored as a `note`.
6. **Repair flow** — force a failure (e.g. a page that yields nothing) → the toolbar badge
   shows a count → open the popup's needs-attention list → fill a note → repair → badge
   clears.
7. **Silent re-auth** — temporarily set `ACCESS_TOKEN_TTL` low, restart the backend, and
   confirm a save still succeeds without a sign-in prompt (background does
   `interactive:false` re-auth). If it forces interactive login, that's a backend
   TTL/refresh concern, not an extension bug.

Inspect saved data directly if needed:

```bash
sqlite3 data/users/<user_id>.db "select id,type,status,note from entries order by saved_at desc limit 5;"
```

---

## 7. Connect an MCP client locally

### 7a. CLI / Desktop Clients (Claude Code / Cursor)
1. Sign in on the dashboard and create a **Personal Access Token** (`/settings/tokens` —
   shown once, format `br2_live_…`).
2. Point your MCP client at the local streamable-HTTP endpoint with a Bearer header.
   Example (Claude Code `mcp` config / Cursor MCP settings):

```json
{
  "mcpServers": {
    "brain2": {
      "url": "http://localhost:8000/connect/mcp",
      "headers": { "Authorization": "Bearer br2_live_..." }
    }
  }
}
```

3. Ask the agent something you saved (e.g. *"what was that Rust HTTP library I saved?"*).
   The five tools are `save`, `retrieve`, `list`, `delete`, `get_tags`.

### 7b. Web Clients (Claude Web / ChatGPT Actions)
Our server implements the MCP OAuth 2.1 authorization stack: discovery (RFC 9728 Protected
Resource Metadata — root **and** path-suffix variants — and RFC 8414 AS metadata), Dynamic
Client Registration (RFC 7591 at `POST /oauth/register`), PKCE S256, and a rotating
`refresh_token` grant so connectors outlive the 1h access-token TTL without re-prompting.
Because web-based clients like Claude Web (`claude.ai`) run in the cloud, they cannot
connect directly to `localhost`. You must expose your local server to the public internet
using a secure tunnel:

1. **Expose localhost via a tunnel:**
   * **Using Ngrok:** Run `ngrok http 8000`. This will output a public URL like `https://a1b2-34-56-78-90.ngrok-free.app`.
   * **Using Cloudflare Tunnel:** Run `cloudflared tunnel --url http://localhost:8000`. This will output a public URL like `https://some-subdomain.trycloudflare.com`.
2. **Register the connector:**
   In your web client's connector settings, add your public tunnel URL with the MCP path (e.g., `https://<your-tunnel-subdomain>.ngrok-free.app/connect/mcp`).
3. **Authorize:**
   The client discovers the metadata endpoints from the `401` challenge, **registers itself**
   via `POST /oauth/register` (no manual `OAUTH_REDIRECT_URIS` edit needed for clients that
   support DCR), and launches the browser flow: sign in with Google, then click **Allow**
   on Brain2's consent screen (shown for every dynamically registered client — open
   registration means codes are never issued to them silently). Clients **without** DCR
   support still work the old way: add their callback URL
   (e.g. `https://chat.openai.com/aip/g-.../oauth/callback`) to `OAUTH_REDIRECT_URIS`.

### 7c. Interactive Tool Testing (MCP Inspector)
The official `@modelcontextprotocol/inspector` is a browser-based developer GUI for testing and debugging MCP tools. It's the ideal way to verify tool inputs, outputs, and schemas without needing a full AI client. It can authenticate either way Brain2 supports — an API key header (quickest) or the full OAuth flow (tests exactly what Claude Web does):

1. **Launch the Inspector:** In a separate terminal, run:
   ```bash
   npx @modelcontextprotocol/inspector
   ```
   It opens `http://localhost:6274` in your browser (the proxy listens on `:6277`).

**Option A — API key (quickest):**

2. **Create a Personal Access Token:** Sign in on the dashboard (`http://localhost:3000`) and generate a token (format `br2_live_…`).
3. **Connect in the Browser:**
   * Under **Transport Type**, select **Streamable HTTP**.
   * In the URL field, enter: `http://localhost:8000/connect/mcp`
   * Under **Authentication**, add a custom header:
     * Key: `Authorization`
     * Value: `Bearer br2_live_...` (replace with your generated token)
   * Click **Connect**.

**Option B — OAuth 2.1 (exercises discovery + DCR + refresh):**

2. **Connect in the Browser:**
   * Under **Transport Type**, select **Streamable HTTP** and enter `http://localhost:8000/connect/mcp`.
   * Do **not** set an Authorization header — click **Connect** (or use the **Open Auth Settings** / **Quick OAuth Flow** button).
   * The Inspector receives the `401` challenge, discovers `/.well-known/oauth-protected-resource/connect/mcp` → `/.well-known/oauth-authorization-server`, registers itself at `POST /oauth/register`, and pops the browser flow: Google sign-in, then Brain2's **consent screen** (it's a DCR-registered client) — click **Allow**. Its callback (`http://localhost:6274/oauth/callback`) is accepted automatically because DCR allows `http` on loopback — no allowlist edit needed.
   * After allowing, you land back in the Inspector with an access + refresh token pair.

3. **Verify Tools:** You will see the `save`, `retrieve`, `list`, `delete`, and `get_tags` tools listed. You can fill out their arguments in the UI and execute them to verify that the backend database changes correctly.
4. **Verify the 401 challenge (optional):** connect with a garbage header value
   (`Bearer nope`) and confirm the connection fails immediately — the backend answers
   `401` with `WWW-Authenticate: Bearer error="invalid_token", resource_metadata=…`
   instead of accepting the session.

> Clients that only speak stdio MCP need a remote→stdio bridge (a `@brain2/mcp-bridge` is
> a designed-for v2 item; see `status.md`).

----

## Troubleshooting

- **`/oauth/authorize` fails to load** → verify that the backend is running and that the extension's redirect URI is matching the allowlist in the root `.env` under `OAUTH_REDIRECT_URIS` (or the default template is present in development).
- **Login redirects to the wrong place / blank page** → `DASHBOARD_URL` must match the
  platform port (`:3000`).
- **Session cookie not set over http** → set `COOKIE_SECURE=false` locally.
- **Extension save fails with a CORS/network error** → you're likely calling the backend
  from the popup/content script, or `host_permissions` doesn't include the API origin.
  All backend calls must go through the background SW; check `wxt.config.ts`.
- **Notes/tags never fill in** → missing/invalid `GEMINI_API_KEY`, or the entry is stuck
  in `failed` (check `GET /entries/failed`).
- **Tests:** backend `uv run pytest -q`; extension `pnpm test`; platform `pnpm test`.

For production hosting, see [`production-setup.md`](./production-setup.md).
