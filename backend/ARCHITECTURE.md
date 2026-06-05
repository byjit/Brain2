# Brain2 Backend — Architecture

Python + FastAPI backend for Brain2, a per-user SQLite memory store. Managed with
**uv**, Python pinned to **3.12**. This document is the coherence contract for later
milestones; update it whenever the layout, module responsibilities, or conventions change.

## Directory layout

```
backend/
├── pyproject.toml            # uv project: deps, dev deps, hatch packaging, pytest config
├── .python-version           # 3.12
├── ARCHITECTURE.md           # this file
├── src/brain2/
│   ├── main.py               # FastAPI app factory (create_app) + module-level `app`
│   ├── config.py             # pydantic-settings; reads repo-root ../.env; get_settings()
│   ├── deps.py               # FastAPI deps: get_current_user (stub) + get_db
│   ├── db/
│   │   ├── connection.py     # open_user_db / user_db_path; WAL + sqlite-vec + schema
│   │   ├── migrations.py     # apply_schema: idempotent schema runner
│   │   └── schema.sql        # full per-user schema verbatim (spec §9.2)
│   ├── models/
│   │   └── entries.py        # Pydantic request/response models for entries
│   ├── services/
│   │   ├── url_normalize.py  # pure URL normalization for dedup (spec §7.1)
│   │   ├── content.py        # conditional content persistence rule (spec §7.3)
│   │   ├── fts.py            # entries_fts (BM25) index sync: index/remove (spec §9.2)
│   │   ├── search.py         # BM25 keyword retrieval w/ tag+type pre-filters (spec §11)
│   │   └── entries.py        # save_entry + delete_entry: sync upsert pipeline (spec §7.1)
│   ├── mcp/
│   │   ├── auth.py           # Bearer -> user_id resolution + per-request user ContextVar
│   │   ├── tools.py          # transport-free save/retrieve tool logic (reuses services)
│   │   └── server.py         # FastMCP server (streamable HTTP) exposing save/retrieve
│   └── api/
│       └── entries.py        # POST /entries router
└── tests/                    # pytest; conftest wires a TestClient to a tmp DATA_DIR
```

## Module responsibilities

- **config.py** — Single source of settings. Reads the repo-root `.env` (one level
  above `backend/`) via pydantic-settings. Holds `DATA_DIR` (default `<repo>/data/users`,
  gitignored), a `dev_user_id` stub, and optional placeholders for `GEMINI_API_KEY`,
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`. Secrets are read from env, never hardcoded.
  Access via the cached `get_settings()`.

- **db/connection.py** — Per-user DB routing (spec §12). `open_user_db(user_id, data_dir)`
  opens `{data_dir}/{user_id}.db`, enforces `PRAGMA journal_mode=WAL`, loads the
  **sqlite-vec** extension (`enable_load_extension(True)` → `sqlite_vec.load`), enables
  foreign keys, and applies the schema. Returns a context-managed `sqlite3.Connection`
  with `Row` row factory.

- **db/migrations.py + schema.sql** — `schema.sql` is the spec §9.2 schema verbatim,
  every statement `IF NOT EXISTS`. `apply_schema()` runs it on every open (idempotent).
  vec0 tables are `entries_vec` / `tags_vec` at `FLOAT[768]`.

- **deps.py** — `get_current_user()` is the auth stub returning `settings.dev_user_id`
  (real auth is M7). `get_db()` depends on it and yields the user's connection per request.

- **services/** — Pure, framework-free logic so it is unit-testable without HTTP:
  - `url_normalize.normalize_url` — lowercase scheme/host, drop fragment, strip `utm_*`
    and tracking params, sort remaining query, strip trailing slash on non-root paths.
  - `content.persisted_content` — the one place encoding which types persist content
    (`clip`/`conversation`/`note` yes; `page` no — re-fetchable via URL).
  - `fts.index_entry` / `fts.remove_entry` — the single place that keeps `entries_fts`
    (id UNINDEXED, title, tags_text, content) in lockstep with `entries`. `tags_text` is
    the space-joined tags (empty until auto-tagging lands in M5). Caller commits.
    `entries_fts` uses the **trigram** tokenizer (`tokenize='trigram'`) so CJK content —
    which the default unicode61 tokenizer stores as one un-splittable token — is matchable
    by ≥3-char substring (spec §15 CJK recall). Chosen before rows accumulate, since
    changing a populated virtual table requires a full rebuild.
  - `search.search_entries` — BM25 ranking via FTS5 `MATCH` + `bm25()` over
    title+tags_text+content, with optional `tags` (entry must carry ALL) and `type`
    pre-filters and a `limit` (default 10). User query text is reduced to quoted word
    tokens so FTS5 operators (quotes, NEAR, AND/OR, `*`, `:`, parens) can't cause syntax
    errors. Returns the compact spec §10 shape (now including `content`); `score` is
    `-bm25()` (higher = better). Decoupled from transport so REST (future) and MCP share it.
    The projection surfaces `content` alongside `note`: pre-enrichment (M2) a clip/
    conversation matches on its body in `content` while `note` is NULL until summarization
    (M5), so the agent can read what BM25 matched on instead of getting id+score only.
  - `entries.save_entry` — normalizes URL, applies content rule, upserts by normalized
    URL (insert `status='pending'` → `saved`; existing → `updated`); notes never dedup.
    Calls `fts.index_entry` on every insert/update (re-indexing from the post-COALESCE row).
    The INSERT is wrapped in `try/except sqlite3.IntegrityError`: on a TOCTOU race (two
    first-saves of the same URL) the loser converges on the committed row via the shared
    `_update_existing` helper and returns `updated`, preserving idempotent re-save (spec
    §10) instead of surfacing a 500. An explicit `note` override (spec §10) is written to
    the `note` column with `note_source='user'` on both insert and update, independent of
    the page/clip content-persistence rule, so an agent-supplied note survives and shows in
    retrieve.
  - `entries.delete_entry` — removes the entry (cascading `entry_tags`) and its FTS row.

- **mcp/** — The MCP server, mounted into FastAPI (spec §10):
  - `auth.resolve_token_to_user_id` — maps a `Bearer <token>` header to a `user_id`.
    M2 stub: any well-formed token resolves to `settings.dev_user_id` (real API-key/JWT
    validation is M7), so per-user DB routing already flows through MCP. `user_scope` /
    `current_user_id` bind the resolved user in a `ContextVar` for the request.
  - `tools.save_tool` / `tools.retrieve_tool` — transport-free tool logic. They resolve
    the current user, open that user's DB, and **delegate to the shared `save_entry` /
    `search_entries`** so REST and MCP have one implementation (DRY). Per spec §10 `save`
    treats `note` as authored text: for `type=note` it is the user's note (its only copy →
    `captured_text`); for URL-backed types it is the override that skips summarization (→ the
    `note` column, reflected back in retrieve). Agent-supplied `tags` are deferred to M5.
  - `server.build_mcp_server` — FastMCP server `brain2_mcp` exposing `save`
    (destructive/idempotent upsert, openWorld) and `retrieve` (readOnly). Flat, typed tool
    parameters (clean `inputSchema`) and typed returns (structured output). Each tool reads
    the request's Bearer header, resolves the user, and runs inside `auth.user_scope`.

- **models/entries.py** — Pydantic v2 models with validation: `CreateEntryRequest`
  (type-aware: URL required for URL-backed types, text required for notes; carries a
  distinct `note` override field per spec §10; string fields bounded via `max_length` —
  short fields 2 KB, body fields ~256 KB — so an oversized input yields 422 instead of a
  silently persisted/indexed blob), `SaveEntryResponse`, and the `EntryType` / `SaveStatus`
  enums.

- **api/entries.py + main.py** — `POST /entries` returns `201 {id, status}`. The app
  factory adds a `/health` probe, includes routers, and mounts the MCP server's
  streamable-HTTP ASGI app at `/mcp` (tools reachable at `/mcp/mcp`). A FastAPI lifespan
  runs the MCP `session_manager` for the app's lifetime.

## MCP transport (spec §6 divergence)

The spec §6 diagram names an SSE transport (`GET /mcp/sse`, `POST /mcp/msg`). We instead
use the **streamable HTTP** transport, which the current MCP Python SDK recommends and the
mcp-builder best-practices mark SSE as deprecated in favor of. The server is **stateless**
with JSON responses (`stateless_http=True, json_response=True`) so it scales horizontally
with no server-side session affinity. The single endpoint is `POST /mcp/mcp`. DNS-rebinding
protection (Host/Origin allow-list) is left on by default for production; `create_app` and
`build_mcp_server` accept a `transport_security` override so in-process ASGI tests can relax
it. Auth is a Bearer-token check today (M2 stub → dev user); full OAuth 2.1 + API keys is M7.

## Conventions

- **TDD.** Write a failing test first, then minimal code. Services are pure for unit
  testing; the API is covered through a `TestClient` with `get_db`/`get_current_user`
  overridden to a temp `DATA_DIR` (never the real `./data`).
- **No external calls in M1–M2.** External services (Gemini, Google OAuth) will sit
  behind provider interfaces with fakes so logic stays testable without live keys.
- **Per-user isolation.** All DB access flows through `get_db` so routing to
  `{user_id}.db` is centralized; never open ad-hoc connections in routes/services.
- **Async enrichment is deferred.** New entries are `pending`; the worker (M3+) fills
  note, tags, and vectors. Keep the sync save path under 2s.

## Commands (run from `backend/`)

- `uv run pytest -q` — run the test suite
- `uv run uvicorn brain2.main:app --reload` — run the dev server
- `uv sync` — install/sync dependencies
