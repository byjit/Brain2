# Brain2 — Production Setup & Deployment

How to deploy Brain2 for real use: the hosted **backend** (REST + MCP + async worker),
the **platform** dashboard, the published **Chrome / Edge extension**, and MCP-client wiring —
plus the security, OAuth, and backup details that matter once it leaves localhost.

> Behavior reference: [`spec.md`](./spec.md). Build state & open items: [`status.md`](./status.md).
> Local-first instructions: [`local-setup.md`](./local-setup.md).

---

## Topology

```
                       https://brain2.useisbeta.com    (one host, fronted by Caddy)
  Browser / Extension ───►  ├─ /  (+ SPA routes)                  → platform dashboard (static, Caddy file_server)
  AI agents (MCP) ───────►  └─ /health /entries* /auth* /api/*    → FastAPI backend (127.0.0.1:8001)
                               /oauth* /settings* /connect*          REST + /oauth/* + /connect/mcp
                               /.well-known/*
                                       │  per-user SQLite under a persistent volume
                                       ▼
                          /data/users/{user_id}.db  +  /data/auth.db   (must persist & be backed up)
```

One public origin: `https://brain2.useisbeta.com`, served over **HTTPS** by the shared
Caddy reverse proxy. Caddy serves the dashboard SPA from `platform/dist` as static files and
reverse-proxies the API / OAuth / MCP paths to the FastAPI backend on `127.0.0.1:8001` —
there is no separate dashboard process. SQLite lives on a **persistent, single-writer
volume** — Brain2 is not designed for horizontally-scaled stateless replicas writing the
same files.

---

## Prerequisites

- A host that can run a long-lived ASGI process with a persistent disk (a VM, Fly.io,
  Render, Railway, a container on a VPS, etc.). **Not** a stateless/ephemeral FaaS — the
  per-user SQLite files and the in-process async enrichment worker need a durable disk and
  a stable process.
- TLS for the origin (managed certs or a reverse proxy such as Caddy/Nginx/Traefik).
- A **Gemini API key** (live summarization, embeddings, auto-tagging).
- A **Google Cloud OAuth 2.0 Client** (Web application) configured for the prod origin.
- The extension's **published** redirect URL(s) — one per store listing, since each
  store assigns its own extension ID (Chrome Web Store and, if shipping to Edge, Edge Add-ons).

---

## 1. Backend deployment

### Install & run

```bash
cd backend
uv sync --no-dev                                 # production deps only
# run the ASGI app (use multiple workers ONLY if they share the same disk volume;
# SQLite is single-writer per file — keep it modest, e.g. 1 worker per box)
uv run uvicorn brain2.main:app --host 127.0.0.1 --port 8001
```

Bind to `127.0.0.1` only — the backend is reachable solely through Caddy. The shared Caddy
instance terminates TLS for `https://brain2.useisbeta.com` and reverse-proxies the API /
OAuth / MCP paths (`/health`, `/entries*`, `/auth*`, `/api/*`, `/oauth*`, `/settings*`,
`/connect*`, `/.well-known/*`) to `127.0.0.1:8001`; every other path is served as the static
dashboard SPA. Run it under systemd (the `brain2` unit) so it restarts on crash and the async
worker keeps draining. The worker runs in the app lifespan
(`create_app(enable_worker=True)`, the default).

### Production environment (repo-root `.env` or real env vars)

Set these for production — **never commit them**:

```dotenv
# Secrets
GEMINI_API_KEY=...
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...

# Auth / sessions — HARDEN THESE
JWT_SECRET=<64+ chars of high entropy>           # REQUIRED: rotate the dev default out
COOKIE_SECURE=true                               # session cookie only over HTTPS
DASHBOARD_URL=https://brain2.useisbeta.com       # post-login redirect target
ACCESS_TOKEN_TTL=3600                            # 1h access tokens
REFRESH_TOKEN_TTL=2592000                        # 30d rotating refresh tokens (MCP clients)
SESSION_TTL=1209600                              # 14d dashboard session

# Exact-match OAuth redirect allowlist (comma-separated, no substrings/open redirects).
# One entry per store listing — Chrome and Edge get separate published IDs.
OAUTH_REDIRECT_URIS=https://<chrome-extension-id>.chromiumapp.org/,https://<edge-extension-id>.chromiumapp.org/

# Storage — point at the PERSISTENT volume
DATA_DIR=/data/users
AUTH_DB_PATH=/data/auth.db
```

Optional tuning (safe defaults exist; see `backend/src/brain2/config.py`):
`GEMINI_SUMMARY_MODEL`, `GEMINI_EMBEDDING_MODEL`, `WORKER_MAX_ATTEMPTS`,
`CANONICALIZE_THRESHOLD`, `TAGS_PER_ENTRY_MIN/MAX`, `NEAREST_TAGS_LIMIT`.

> **`JWT_SECRET` is load-bearing.** It signs Brain2 access/session JWTs and OAuth codes.
> The built-in default (`dev-insecure-secret-change-me`) is dev-only — deploying with it
> is a critical vulnerability. Generate a fresh secret (`openssl rand -hex 48`) and keep it
> out of source control.

### Health & process checks

```bash
curl -fsS https://brain2.useisbeta.com/health    # -> {"status":"ok"}
```

Wire `/health` to your platform's liveness/readiness probe and uptime monitor.

---

## 2. Google OAuth (production) configuration

In Google Cloud Console → **Credentials** → your **Web application** OAuth client:

- **Authorized JavaScript origins:** `https://brain2.useisbeta.com`
- **Authorized redirect URIs:** `https://brain2.useisbeta.com/api/auth/callback/google`
- Configure the **OAuth consent screen** (app name, support email, scopes:
  `openid email profile`) and move it to **Published** for non-test users.

The **extension** redirect(s) (`https://<extension-id>.chromiumapp.org/`, one per store
listing — Chrome and Edge) go in the backend's `OAUTH_REDIRECT_URIS`, **not** in Google's
redirect list (they are Brain2-issued authorization-code redirects, not Google ones).

> [!TIP]
> **Interactive Sign-In Redirection:**
> If a user is not authenticated when the extension calls `GET /oauth/authorize`, the backend
> automatically redirects the browser/popup window to the Google Sign-in flow and returns
> them back to the authorization sequence seamlessly. Backend-only and API-key (MCP) testing is unaffected.

---

## 3. Platform dashboard deployment

```bash
cd platform
pnpm install
pnpm build                                        # vite build && tsc → dist/
```

Caddy serves `platform/dist/` directly as static files on `https://brain2.useisbeta.com`
(the `file_server` fallback for every path not matched by the API route) — there is no
separate dashboard service to run; a frontend change deploys by rebuilding `platform/dist`,
not by restarting `brain2`. Ensure the dashboard's API base points at the same origin
`https://brain2.useisbeta.com` (configure via the platform's build env; check `platform/`'s
env handling — it uses `@t3-oss/env-core`). `DASHBOARD_URL` on the backend must equal that
origin exactly.

---

## 4. Chrome / Edge extension: build & publish

```bash
cd extension
# production env
cat > .env <<'EOF'
VITE_BRAIN2_API_URL=https://brain2.useisbeta.com
VITE_BRAIN2_OAUTH_CLIENT_ID=brain2-extension
EOF

# point host_permissions at the prod API origin
#   edit extension/wxt.config.ts: host_permissions: ["https://brain2.useisbeta.com/*"]
#   (it derives from VITE_BRAIN2_API_URL via process.env at build time)

pnpm compile && pnpm test                          # gate
pnpm zip                                            # build + zip for the Chrome Web Store
pnpm zip:edge                                       # build + zip for the Edge Add-ons store
```

The extension is Chromium-based, so the same source ships to both stores; only the build
target (`zip` vs `zip:edge`) differs.

**Chrome Web Store** — publish via the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole):

1. Upload `extension/.output/*-chrome.zip`.
2. After the listing is created you get a **stable extension ID**. Its redirect URL is
   `https://<extension-id>.chromiumapp.org/` — add that **exact** string to the backend's
   `OAUTH_REDIRECT_URIS` and redeploy the backend.
3. Submit for review.

**Edge Add-ons** — publish via the [Microsoft Partner Center](https://partner.microsoft.com/dashboard/microsoftedge):

1. Upload `extension/.output/*-edge.zip`.
2. The published Edge build gets its **own** store-assigned extension ID, hence its own
   redirect URL `https://<edge-extension-id>.chromiumapp.org/`. Add that **exact** string
   to `OAUTH_REDIRECT_URIS` **as well** (the allowlist holds both store redirects) and
   redeploy the backend.
3. Submit for review.

> The `manifest.key` pinned in `wxt.config.ts` only fixes the ID for self-distributed /
> unpacked builds; each store assigns its own ID to published listings, which is why both
> store redirect URLs must be allowlisted. (For Firefox: `pnpm zip:firefox`.)

> Keep the extension a thin capture client: all backend calls stay in the background SW,
> which is CORS-exempt only because the prod API origin is in `host_permissions`. No
> `<all_urls>` — the page extractor and picker are injected on a user gesture via
> `activeTab` + `scripting`.

---

## 5. MCP clients in production

### 5a. CLI / Desktop Clients
Users generate a **Personal Access Token** on the dashboard (`/settings/tokens`, shown
once) and configure their MCP client against the hosted endpoint:

```json
{
  "mcpServers": {
    "brain2": {
      "url": "https://brain2.useisbeta.com/connect/mcp",
      "headers": { "Authorization": "Bearer br2_live_..." }
    }
  }
}
```

### 5b. Web Clients / Claude Web (OAuth 2.1)
Our server implements the full MCP OAuth 2.1 authorization stack: discovery (RFC 9728
Protected Resource Metadata at the root **and** path-suffix well-known URLs, RFC 8414 AS
metadata), Dynamic Client Registration (RFC 7591), PKCE S256, and a rotating
`refresh_token` grant. To connect a web-based client that natively supports this (such as
Claude Web custom connectors):

1. In the web client's settings, add a custom connector pointing to the MCP URL: `https://brain2.useisbeta.com/connect/mcp`.
2. The client receives a `401` + `WWW-Authenticate` challenge, discovers the metadata
   endpoints, **registers itself** via `POST /oauth/register` (no manual
   `OAUTH_REDIRECT_URIS` edit needed for DCR-capable clients), and opens the browser flow:
   Google sign-in, then **Brain2's consent screen** naming the client and its redirect
   host — the user must click **Allow** before any code is issued (registration is open,
   so codes are never issued to registered clients via silent redirect).
3. Access tokens expire after 1h; the client refreshes silently via the `refresh_token`
   grant (tokens rotate on every use; a replayed refresh token is rejected). Because
   identities are keyed on the Google `sub`, signing in with the same Google account used
   for the extension/dashboard connects the MCP client to the **same** user data.

Clients **without** DCR support still work: add their callback URI (e.g.
`https://chat.openai.com/aip/g-.../oauth/callback`) to `OAUTH_REDIRECT_URIS` and have them
use any `client_id` — unregistered client ids validate against that static allowlist.

Tools: `save`, `retrieve`, `list`, `delete`, `get_tags`.


---

## 6. Production smoke test

After deploy:

1. `curl -fsS https://brain2.useisbeta.com/health` → `{"status":"ok"}`.
2. Dashboard: open `https://brain2.useisbeta.com`, sign in with Google, confirm
   `GET /auth/me` returns your identity and the session cookie is `Secure`.
3. Create an API key on the dashboard; configure an MCP client; run a `save` then a
   `retrieve` and confirm recall.
4. Install the published extension, sign in, save a page,
   and confirm it lands `active` with a note + tags within a few seconds.
5. Force a failure and confirm it surfaces in `GET /entries/failed` and via the badge,
   then repair it.

---

## 7. Security checklist

- [ ] `JWT_SECRET` set to a strong, unique value (not the dev default); stored as a secret.
- [ ] `COOKIE_SECURE=true`; the origin HTTPS-only; HSTS at the proxy.
- [ ] `OAUTH_REDIRECT_URIS` is an **exact** allowlist (the published extension redirect and
      nothing broader); `DASHBOARD_URL` is the exact dashboard origin.
- [ ] Google OAuth consent screen published; redirect URIs limited to
      `https://brain2.useisbeta.com/api/auth/callback/google`.
- [ ] `GEMINI_API_KEY` / `GOOGLE_CLIENT_SECRET` injected as secrets, never committed; the
      repo-root `.env` and the `data/` dir (`*.db`, `auth.db`) are gitignored.
- [ ] Backend not run with the dev default secret or `COOKIE_SECURE=false`.
- [ ] Reverse proxy forwards the real `Origin`/`Referer`/`Host` (the cookie-authed token
      endpoints apply Origin/Referer defense-in-depth) and sets sane request size limits.
- [ ] Per-user DB isolation verified: each credential resolves to its own
      `{user_id}.db`; `auth.db` lives **outside** `DATA_DIR` so the worker's `{user_id}.db`
      scan never opens it (the default `AUTH_DB_PATH` already satisfies this).

The backend went through a dedicated security review at M7 (PKCE S256, JWT alg-pinning,
exact redirect allowlist, login-CSRF nonce, Google `id_token` aud/iss binding, hash-only
API keys, `email_verified` enforcement) — see `status.md`. Third-party MCP clients now
self-register via RFC 7591 DCR (public clients only — no secrets issued; redirect URIs
must be https or loopback-http and are matched exactly; codes and refresh tokens are
STRICTLY bound to the issuing `client_id`; refresh tokens are hashed at rest and rotate
on every use). Because registration is open, every DCR-registered client goes through an
explicit per-client **consent screen** at `/oauth/authorize` — codes are issued to them
only after the user clicks Allow, never via silent redirect. Only the operator-configured
static-allowlist clients (the extension) skip consent.

---

## 8. Persistence, backups, and upgrades

- **Back up the whole data volume** (`/data/users/*.db` + `/data/auth.db`). Use SQLite
  online backup or snapshot the volume while the process is quiesced; databases run in WAL
  mode, so include the `-wal`/`-shm` sidecars or checkpoint first.
- **Losing `auth.db` logs everyone out and orphans API keys** (identities/key hashes live
  there) — treat it as critical state.
- **Upgrades:** deploy new backend code, `uv sync --no-dev`, restart the process. Schema is
  initialized idempotently per DB on first open; there is no destructive migration step in
  v1. The async worker re-scans `pending`/`failed` entries on startup, so in-flight
  enrichment resumes after a restart.
- **Scaling:** vertical first (SQLite is single-writer per file). If you must run multiple
  app processes, they must share the same disk and you should keep writes to one worker per
  file; do not put the SQLite volume on network storage with weak locking semantics.

---

For local development and the full manual-QA walkthrough, see
[`local-setup.md`](./local-setup.md).
