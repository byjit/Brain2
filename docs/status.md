# Brain2 — Implementation Status

**As of:** 2026-06-05 · branch `feat/backend-v1` · **314 tests passing (5 live-Gemini smoke tests skip offline)**

This tracks progress against the build sequence in [`spec.md` §14](./spec.md). **The backend is complete (M1–M7).** Remaining v1 work is frontend: the `platform/` dashboard (M7's UI half) and the `extension/` capture client (M8 — see [`m8-extension-plan.md`](./m8-extension-plan.md)).

---

## ✅ Done — Backend (M1–M7)

Python + FastAPI backend in [`/backend`](../backend) (`uv`, Python 3.12). Module map: [`backend/ARCHITECTURE.md`](../backend/ARCHITECTURE.md).

| Milestone | What shipped | Commit |
| --------- | ------------ | ------ |
| **M1** | Scaffold; full per-user SQLite schema (§9.2: entries, entry_tags, tags, tag_cooccurrence, tag_aliases, FTS5, `vec0[768]`); WAL + sqlite-vec; URL normalization; conditional content persistence; `POST /entries` (non-destructive upsert) | `9aee9cf` |
| **M2** | FTS5/BM25 in lockstep with entries (trigram); BM25 search w/ tag/type pre-filters; MCP server (official SDK, streamable-HTTP `/mcp`) with `save` + `retrieve` | `53676e7` |
| **M3** | Async enrichment worker (backoff, stale-reaper, loop isolation); Gemini summarization + note-source fallback ladder; `Summarizer`/`PageFetcher` interfaces + offline fakes | `43952b0` |
| **M4** | Note embeddings (`gemini-embedding-001`, 768-dim, normalized); sqlite-vec KNN (`cosine`); RRF hybrid merge (k=60) | `6d051e1` |
| **M5** | **Auto-tagging (core):** structured priors (OG/meta + GitHub) → RAG nearest-tag → one combined Gemini call (note+tags+descriptions) → canonicalize-on-write (snap ≥0.90 else create) → tag-description embeddings → counts + co-occurrence | `7e9dfa0` |
| **M6** | `delete` + `get_tags` MCP tools; `PATCH /entries/{id}` repair; symmetric counter decrements; `reconcile_tags`; agent-supplied tags canonicalized; `GET /entries/failed` | `ea940af` |
| **M7** | **Hybrid auth (§12):** central `auth.db` (users, api_keys, oauth_codes); API keys (CSPRNG, SHA-256, constant-time verify, owner-scoped revoke); JWT (pyjwt HS256, alg-pinned, access/session typ split); OAuth 2.1 + PKCE S256 AS; Google Sign-In + implicit signup; Bearer wired into REST + all 4 MCP tools | `ac5bb02` |

**All four MCP tools live and Bearer-authed:** `save`, `retrieve`, `delete`, `get_tags`.

**Validated against the real API:** Gemini summarize, 768-dim embeddings, paraphrase retrieval, combined tagging, repair re-tagging — all behind injectable interfaces so the 314-test suite runs fully offline.

**Security:** M7 went through the workflow's security-focused review **plus** a dedicated `/security-review`. Confirmed strong: PKCE S256, JWT alg-pinning + access/session separation, exact redirect_uri allowlist, login-CSRF nonce, Google `id_token` aud/iss binding, hash-only keys, path-safe server-generated `user_id`, full auth coverage. Hardened: Origin/Referer defense-in-depth on cookie-authed token endpoints, one-time `auth.db` schema init, `email_verified` enforcement. Conscious v1 deferral: single first-party OAuth client (no client allowlist/consent screen yet).

### Run it
```bash
cd backend
uv run pytest                               # full suite (offline)
uv run uvicorn brain2.main:app --reload     # dev server (reads ../.env)
```
Set a strong `jwt_secret` and the Google OAuth redirect URIs in `.env` before any real deployment.

---

## ⏳ Pending — v1 remaining (all frontend)

### `platform/` — Web dashboard (M7's UI half) + landing
React 19 + Vite + TanStack Router (scaffolded: `_landing`, `_public/login`, `_authed/dashboard` stub). To build against the M7 backend: wire the auth guard to `GET /auth/me`, login → `/auth/login` (Google), a Personal Access Tokens page (`/settings/tokens` CRUD, show-once key), and a "needs attention" repair view (`GET /entries/failed` + `PATCH /entries/{id}`). Companion plan to be written (`docs/platform-dashboard-plan.md`).

### `extension/` — Chrome capture client (M8)
Detailed task-by-task plan in [`m8-extension-plan.md`](./m8-extension-plan.md): popup with three capture modes (save page w/ chat-domain → conversation, element picker + Turndown, custom note), `chrome.identity` PKCE OAuth against the M7 AS, fire-and-forget toast, "needs attention" badge. Built on the existing WXT `defineStore`/`defineMessage` service patterns.

### M9–M10 — Dogfood & ship decision
Two-week solo dogfood; track tag-reuse vs invention + failure rate; ship gate.

---

## 🔭 Deferred to v2 (designed-for, not built)
Web management/browse UI beyond repair · offline tag-clustering/merge job (uses the shipped `tag_aliases`) · chunk-level content embeddings · import (GitHub stars, Pocket, bookmarks) · Markdown export · self-hosting UX · `@brain2/mcp-bridge` npm stdio bridge for MCP clients without remote transport.

---

## 📌 Open items to revisit (spec §15)
- **Tune the 0.90 canonicalize threshold and 3–5 tags-per-entry cap** against real saves during dogfood (config knobs).
- Confirm discarding `page` body doesn't hurt exact-identifier recall (watch in dogfood).
- MCP transport diverges from the spec's named SSE to SDK-recommended **streamable-HTTP** (documented in `backend/ARCHITECTURE.md`).
- Conversation enrichment currently shares the clip `<400-char` verbatim rule (minor §7.3 divergence).
- OAuth: add a client allowlist / consent screen if third-party MCP clients are ever supported.

---

## How this was built
Each milestone ran a multi-agent workflow (`.claude/workflows/milestone.mjs`): TDD build → parallel review (correctness/edge-cases + SOLID/simplicity) → triage+fix, with an independent test run before each commit. Reviews caught real bugs every time — a destructive dedup-UPDATE (M1), a TOCTOU first-save race (M2), worker-loop death + cosmetic backoff (M3), L2-vs-cosine embedding mis-ranking (M4), a zero-vector KNN crash + counter double-increment (M5), agent-tags wiped by the auto-tagger (M6), and Google `id_token` audience-binding + session/access token confusion (M7).
