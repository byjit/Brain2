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
│   │   ├── prefilter.py      # shared tag/type pre-filter id-set helpers (spec §11)
│   │   ├── vector.py         # entries_vec upsert/remove + sqlite-vec KNN (spec §9.2/§11)
│   │   ├── search.py         # hybrid BM25+vector RRF retrieval + BM25-only (spec §11)
│   │   ├── entries.py        # save_entry + delete_entry: sync upsert pipeline (spec §7.1)
│   │   ├── note_resolver.py  # note-source fallback ladder body→og→title (spec §7.3)
│   │   ├── worker.py         # async enrichment worker + drain + lifespan loop (spec §7.1/§7.4)
│   │   └── providers/        # external-service interfaces (DI) + fakes (spec §7)
│   │       ├── summarizer.py    # Summarizer Protocol; GeminiSummarizer + FakeSummarizer
│   │       ├── embedder.py      # Embedder Protocol; GeminiEmbedder + FakeEmbedder (768-dim)
│   │       ├── page_fetcher.py  # PageFetcher Protocol + PageContent; Httpx + Fake impls
│   │       └── factory.py       # build_providers: real-vs-fake wiring by config
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
  Also holds the worker knobs: `gemini_summary_model` (default `gemini-3.5-flash` — the
  current Flash model per the gemini-api-dev skill; the M4 embedding model is
  `gemini-embedding-001` at 768-dim) and `worker_max_attempts` (retry ceiling, default 3).
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
  - `prefilter` — the single place owning the tag/type pre-filter id-set SQL
    (`entry_ids_with_all_tags` conjunctive over `entry_tags`; `entry_ids_of_type`). Both
    retrieval legs import it so the BM25 and vector legs filter identically (DRY).
  - `vector` — the semantic leg over `entries_vec` (spec §9.2/§11). `index_entry_vector`
    delete-then-inserts the 768-dim note vector (vec0 has no UPSERT, so this guarantees
    one row per entry and the clear/replace-on-re-enrichment the spec requires);
    `remove_entry_vector` drops it on delete; `vector_search` runs the sqlite-vec
    `vec0` KNN (`WHERE embedding MATCH ? AND k = ?`, vectors via `sqlite_vec.serialize_float32`)
    and returns ranked ids. Tag/type pre-filters are applied around the KNN via `prefilter`
    (over-fetching when filtered, since vec0 KNN can't join arbitrary WHERE clauses).
    A dimension mismatch raises a typed `ValueError` rather than silently corrupting the
    index (sqlite-vec would also reject it, but later and opaquely).
  - `search.search_entries` — BM25 leg: ranking via FTS5 `MATCH` + `bm25()` over
    title+tags_text+content, with optional `tags`/`type` pre-filters (via `prefilter`) and
    a `limit` (default 10). User query text is reduced to quoted word tokens so FTS5
    operators (quotes, NEAR, AND/OR, `*`, `:`, parens) can't cause syntax errors. Returns
    the compact spec §10 shape (incl. `content`); `score` is `-bm25()` (higher = better).
    Kept as the internal BM25-only path.
  - `search.hybrid_search` — the public retrieve path (spec §10/§11). Fuses BM25 (set A,
    reusing `search_entries` — no second BM25 copy) and `vector_search` (set B) with
    Reciprocal Rank Fusion: `score = Σ 1/(60 + rank_i)`. Both legs run under the SAME
    tag/type pre-filters, so a filtered entry never appears in either leg or the fused
    result. Each leg over-fetches a candidate pool (50) so an entry strong in only one leg
    still surfaces; an empty/whitespace query (no searchable tokens) returns `[]`. Returns
    the compact §10 shape ordered by fused score (default limit 10), so an entry found
    only by vector (a paraphrase with no lexical overlap) is still retrieved. Decoupled
    from transport so REST (future) and MCP share it.
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
  - `entries.delete_entry` — removes the entry (cascading `entry_tags`), its FTS row, and
    its `entries_vec` note vector (spec §10 delete).
  - `providers/` — external services behind abstractions (dependency inversion) so the
    worker is unit-testable offline (spec §7). `summarizer.Summarizer` (2-3 sentence note;
    real `GeminiSummarizer` uses the **google-genai** SDK + Gemini Flash, fake is
    deterministic and records calls); `embedder.Embedder` (768-dim note/query vector; real
    `GeminiEmbedder` uses the **google-genai** SDK `embed_content` with
    `gemini-embedding-001` at `output_dimensionality=768`, fake is a deterministic hashed
    bag-of-words unit vector — *similarity-meaningful* so token overlap raises cosine and
    KNN/RRF ordering is genuinely testable offline); `page_fetcher.PageFetcher` returns a
    `PageContent` (`body_text`, `og_description`, `meta_description`, `title`); real
    `HttpxPageFetcher` fetches with **httpx** and extracts with **trafilatura** (its
    `description` folds og:description/meta into the spec's combined rung), fake returns
    canned content. `factory.build_providers(settings)` returns the real
    `(summarizer, fetcher, embedder)` triple when `gemini_api_key` is set, else the fakes —
    so dev/CI run offline by configuration alone. SDK imports are lazy so the SDK is only
    required when the real provider is used.
  - `note_resolver.resolve_note(entry, *, fetcher, summarizer)` — the single cohesive
    fallback ladder (spec §7.3). `note` type → user text verbatim (`note_source=user`, no
    LLM); `clip`/`conversation` → persisted `content`, verbatim when < ~400 chars else
    summarized (`note_source=body`); `page` → **re-fetch** the URL (bodies are not
    persisted) then walk body→og/meta→title, summarizing the body and taking og/title
    verbatim (`note_source=body|og|title`). Returns a `ResolvedNote(note, note_source)`.
  - `worker.process_entry(conn, id, *, fetcher, summarizer, embedder=None, max_attempts=None)`
    — the deterministic, synchronous, idempotent core (spec §7.1/§7.4). Atomically
    **claims** a `pending`/`failed` row below the ceiling by flipping it to `processing` and
    incrementing `attempts` in one UPDATE (so `active`/`processing` rows are never
    re-summarized and a concurrent run can't double-pick). On success: writes
    `note`/`note_source`, sets `active`, clears `error_message`, bumps `updated_at`,
    re-indexes FTS, and — when an `embedder` is supplied — embeds the resolved **note**
    (not the body) into `entries_vec` via `vector.index_entry_vector` (clear/replace on
    re-enrichment); a failed entry leaves no vector. The `embedder` is threaded through
    `process_pending` / `drain_all_users` / `run_worker_loop` (which builds it from config);
    it is optional only so note-only unit tests need not wire one. An empty resolved note
    is treated as a
    failure (actionable `error_message`), never a silently-active blank entry. The claim
    UPDATE stamps `updated_at` so staleness is measurable. On exception: rolls back, then
    `_record_failure` sets `failed` + `error_message` at the ceiling, else returns to
    `pending` and stamps `next_retry_at = now + 2**attempts s`. That `next_retry_at` is
    **enforced**: the claim UPDATE and `process_pending` SELECT both gate on
    `next_retry_at <= now`, so a retried entry is not re-claimed until its backoff
    elapses (spec §7.4). `process_pending` drains one DB; `reset_stale_processing`
    requeues `processing` rows abandoned past the lease (crash mid-pipeline);
    `drain_all_users` scans every `{user_id}.db` under `DATA_DIR`, runs the reaper, and
    isolates per-DB failures (logged and skipped) so one bad DB never aborts the scan;
    `run_worker_loop` is the async lifespan loop (drains on startup, then every
    `poll_interval`, blocking DB work offloaded via `asyncio.to_thread`, logs and
    continues on an unexpected cycle error, cancels cleanly).

- **mcp/** — The MCP server, mounted into FastAPI (spec §10):
  - `auth.resolve_token_to_user_id` — maps a `Bearer <token>` header to a `user_id`.
    M2 stub: any well-formed token resolves to `settings.dev_user_id` (real API-key/JWT
    validation is M7), so per-user DB routing already flows through MCP. `user_scope` /
    `current_user_id` bind the resolved user in a `ContextVar` for the request.
  - `tools.save_tool` / `tools.retrieve_tool` — transport-free tool logic. They resolve
    the current user, open that user's DB, and **delegate to the shared `save_entry` /
    `hybrid_search`** so REST and MCP have one implementation (DRY). `retrieve_tool` is the
    public hybrid path (BM25 + vector + RRF); it builds the embedder from config (real
    Gemini when keyed, else fake). Per spec §10 `save` treats `note` as authored text: for
    `type=note` it is the user's note (its only copy → `captured_text`); for URL-backed
    types it is the override that skips summarization (→ the `note` column, reflected back
    in retrieve). Agent-supplied `tags` are deferred to M5.
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
  streamable-HTTP ASGI app at `/mcp` (tools reachable at `/mcp/mcp`). The FastAPI lifespan
  runs the MCP `session_manager` and (when `enable_worker=True`, the default) launches the
  background `run_worker_loop` task, cancelling it cleanly on shutdown. Tests pass
  `enable_worker=False` (they drive a tmp `DATA_DIR` through dependency overrides, so the
  loop — which scans the real configured `DATA_DIR` — must stay off).

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
- **External services behind interfaces with fakes.** Gemini and page fetch (and, later,
  Google OAuth) sit behind provider abstractions in `services/providers/` with
  deterministic fakes, so all logic — including the M3 enrichment worker — stays unit
  testable without live keys or network. `factory.build_providers` selects real-vs-fake
  by config (summarizer + page-fetcher + **embedder**); no test requires `GEMINI_API_KEY`.
  The optional live Gemini tests (`tests/test_gemini_smoke.py` — summarizer, embedder
  768-dim, and a real-embedding paraphrase retrieval) self-skip unless `GEMINI_API_KEY` is
  in the *environment* (the repo `.env` is read by config but not exported to `os.environ`,
  so the default suite still skips them). The `FakeEmbedder` is deliberately
  similarity-meaningful so the offline KNN/RRF tests assert real ordering.
- **Per-user isolation.** All DB access flows through `get_db` so routing to
  `{user_id}.db` is centralized; never open ad-hoc connections in routes/services.
- **Async enrichment.** New entries are `pending`; the worker resolves the note basis
  (fallback ladder), summarizes, records `note_source`, re-indexes FTS, embeds the **note**
  into `entries_vec` (M4), and sets `active`. Auto-tagging (and `tags_text`/`tags_vec`)
  remains deferred to M5. Keep the sync save path under 2s.
- **Hybrid retrieval (M4).** `retrieve` fuses BM25 (set A) and vector KNN over the note
  embedding (set B) with RRF (`k=60`). Tag/type are pre-filters on both legs (`prefilter`).
  `search.search_entries` stays as the internal BM25-only path; `search.hybrid_search` is
  the public path the MCP `retrieve` tool calls.

## Commands (run from `backend/`)

- `uv run pytest -q` — run the test suite
- `uv run uvicorn brain2.main:app --reload` — run the dev server
- `uv sync` — install/sync dependencies
