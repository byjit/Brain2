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
│   │   ├── entries.py        # save_entry + delete_entry + failed_entries (spec §7.1/§7.4/§10)
│   │   ├── note_resolver.py  # note-source ladder body→og→title; resolve_basis (no-LLM) (spec §7.3)
│   │   ├── structured_tags.py # structured-source priors: OG keywords + GitHub topics/lang (spec §7.2)
│   │   ├── tags_vector.py    # tags_vec upsert + nearest-tag KNN (description embeddings) (spec §9.2/§9.3)
│   │   ├── tag_counters.py   # symmetric tags.count + tag_cooccurrence math (apply_edge_diff) (spec §9.2)
│   │   ├── canonicalize.py   # conservative normalize + snap-to-existing-or-create (spec §7.2)
│   │   ├── tagging.py        # auto-tag orchestration + reconcile_tags + apply_agent_tags (spec §7.2/§7.4/§10)
│   │   ├── tags_service.py   # get_tags read model: paged counts/descriptions/co-occurrence (spec §10)
│   │   ├── repair.py         # PATCH repair: re-enrich a failed entry from the user note (spec §7.4)
│   │   ├── worker.py         # async enrichment worker + drain + lifespan loop (spec §7.1/§7.4)
│   │   └── providers/        # external-service interfaces (DI) + fakes (spec §7)
│   │       ├── summarizer.py    # Summarizer Protocol; GeminiSummarizer + FakeSummarizer
│   │       ├── embedder.py      # Embedder Protocol; GeminiEmbedder + FakeEmbedder (768-dim)
│   │       ├── page_fetcher.py  # PageFetcher Protocol + PageContent; Httpx + Fake impls
│   │       ├── tagger.py        # Tagger Protocol; GeminiTagger (structured output) + FakeTagger
│   │       └── factory.py       # build_providers + build_tagging_providers: real-vs-fake by config
│   ├── mcp/
│   │   ├── auth.py           # Bearer -> user_id resolution + per-request user ContextVar
│   │   ├── tools.py          # transport-free save/retrieve/delete/get_tags tool logic (reuses services)
│   │   └── server.py         # FastMCP server (streamable HTTP) exposing all four spec §10 tools
│   └── api/
│       └── entries.py        # POST /entries + GET /entries/failed + PATCH /entries/{id} repair
└── tests/                    # pytest; conftest wires a TestClient to a tmp DATA_DIR
```

## Module responsibilities

- **config.py** — Single source of settings. Reads the repo-root `.env` (one level
  above `backend/`) via pydantic-settings. Holds `DATA_DIR` (default `<repo>/data/users`,
  gitignored), a `dev_user_id` stub, and optional placeholders for `GEMINI_API_KEY`,
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`. Secrets are read from env, never hardcoded.
  Also holds the worker knobs: `gemini_summary_model` (default `gemini-3.5-flash` — the
  current Flash model per the gemini-api-dev skill, used for both summarization and the M5
  combined tagging call; the M4 embedding model is `gemini-embedding-001` at 768-dim) and
  `worker_max_attempts` (retry ceiling, default 3). The M5 auto-tagging knobs are the
  spec's deliberate anti-fragmentation choices and the ONLY tuning surface (spec §15):
  `canonicalize_threshold` (default 0.90 — bias to under-merge live), `tags_per_entry_max`
  / `tags_per_entry_min` (5 / 3 — bias to reuse over invention), and `nearest_tags_limit`
  (10 — keep the prompt small at hundreds of tags). Access via the cached `get_settings()`.

- **db/connection.py** — Per-user DB routing (spec §12). `open_user_db(user_id, data_dir)`
  opens `{data_dir}/{user_id}.db`, enforces `PRAGMA journal_mode=WAL`, loads the
  **sqlite-vec** extension (`enable_load_extension(True)` → `sqlite_vec.load`), enables
  foreign keys, and applies the schema. Returns a context-managed `sqlite3.Connection`
  with `Row` row factory.

- **db/migrations.py + schema.sql** — `schema.sql` is the spec §9.2 schema verbatim,
  every statement `IF NOT EXISTS`. `apply_schema()` runs it on every open (idempotent).
  vec0 tables are `entries_vec` / `tags_vec` at `FLOAT[768]`, both `distance_metric=cosine`
  (so the M5 canonicalize snap is a true cosine threshold and KNN ranks by direction).

- **deps.py** — `get_current_user()` is the auth stub returning `settings.dev_user_id`
  (real auth is M7). `get_db()` depends on it and yields the user's connection per request.

- **services/** — Pure, framework-free logic so it is unit-testable without HTTP:
  - `url_normalize.normalize_url` — lowercase scheme/host, drop fragment, strip `utm_*`
    and tracking params, sort remaining query, strip trailing slash on non-root paths.
  - `content.persisted_content` — the one place encoding which types persist content
    (`clip`/`conversation`/`note` yes; `page` no — re-fetchable via URL).
  - `fts.index_entry` / `fts.remove_entry` — the single place that keeps `entries_fts`
    (id UNINDEXED, title, tags_text, content) in lockstep with `entries`. `tags_text` is
    the space-joined tags read from `entry_tags` (populated by M5 auto-tagging, so re-index
    AFTER writing the edges so BM25 matches tag keywords). Caller commits.
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
    its `entries_vec` note vector, then SYMMETRICALLY decrements `tags.count` +
    `tag_cooccurrence` for the removed edge set via `tag_counters.decrement_for_tags` — the
    exact inverse of the M5 write (same canonical pair order, floor at 0). A tag at count 0
    is LEFT in place (its description + `tags_vec` vector stay useful for canonicalization,
    spec §9.2). Returns False for an absent id so `delete` can answer `{deleted:false}`.
    `entries.failed_entries` is the read for the §7.4 "needs attention" surface (failed rows
    newest-first, scoped to the user's DB).
  - `tag_counters` — the single owner of count math (spec §9.2). `apply_edge_diff(added,
    removed, kept)` applies the exact counter delta for a partial re-tag: `tags.count` ±1
    per added/removed tag, and `tag_cooccurrence` ± for every pair that becomes/stops being
    co-present (added×{added,kept} rise, removed×{removed,kept} fall), all in canonical
    `tag_a<tag_b` order and floored at 0. `decrement_for_tags` is the whole-edge-set inverse
    used by delete. Keeping increment and decrement here guarantees they mirror exactly.
  - `tagging.reconcile_tags` — the single owner of edge writes shared by first-tag, worker
    reprocess, and repair. Diffs the entry's current edges against the desired set and
    routes the add/remove/keep split through `apply_edge_diff`, so counters always equal the
    live edge set (closing the partial-overlap case M5 deferred), then refreshes
    `entries_fts.tags_text`. `_persist_tags` is a thin wrapper over it.
  - `tagging.apply_agent_tags` — canonicalize-on-write for agent-supplied `save` tags
    (spec §10): normalize → snap-or-create (reusing `canonicalize_candidates`) → UNION with
    the entry's current edges → `reconcile_tags`. Agent tags skip the LLM proposal but still
    canonicalize, so they cannot fragment the vocabulary; the merge is additive.
  - `tags_service.list_tags` — the `get_tags` read model (spec §10): paged (`limit` default
    50) tags with `name`/`description`/`count` and `co_occurs_with` (top co-occurring names,
    both pair directions, zero-count pairs excluded). `sort` is `count` (default desc) or
    `name` (asc); no other knobs (YAGNI).
  - `repair.repair_entry` — the §7.4 PATCH flow. Sets note=user text, note_source='user',
    clears `error_message`, resets `attempts`/`next_retry_at`, then re-enters the SAME
    enrichment path the worker uses (`tagging.apply_tags`) with the basis forced to the
    user's note and `needs_summary=False` (no LLM note rewrite — the user's text IS the
    note), applies optional user tags additively, embeds the note into `entries_vec`, and
    flips to `active`. Returns the updated row (None for an absent id → 404).
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
    required when the real provider is used. `tagger.Tagger` is the M5 single combined
    call: real `GeminiTagger` uses **google-genai structured output**
    (`response_mime_type='application/json'` + a Pydantic `response_schema`) to return
    note + candidate tags + per-new-tag descriptions in ONE round trip; `FakeTagger` is
    deterministic and records calls so tests assert exactly-one-call. `build_tagging_providers(settings)`
    returns `(tagger, structured_source)` — kept separate from `build_providers` so its
    3-tuple contract stays stable.
  - `note_resolver.resolve_note(entry, *, fetcher, summarizer)` — the single cohesive
    fallback ladder (spec §7.3). `note` type → user text verbatim (`note_source=user`, no
    LLM); `clip`/`conversation` → persisted `content`, verbatim when < ~400 chars else
    summarized (`note_source=body`); `page` → **re-fetch** the URL (bodies are not
    persisted) then walk body→og/meta→title, summarizing the body and taking og/title
    verbatim (`note_source=body|og|title`). Returns a `ResolvedNote(note, note_source)`.
    `note_resolver.resolve_basis(entry, *, fetcher)` is the M5 sibling: it walks the SAME
    source ladder but **defers summarization**, returning a `NoteBasis(text, note_source,
    needs_summary, note)` — so the worker embeds the basis for nearest-tag lookup and folds
    the summary into the single tagging call (the verbatim short-circuits set `note`
    directly with `needs_summary=False`). This is how "exactly one LLM call per entry"
    (spec §7.2) is honored without a separate summarizer call on the summarize path.

- **Auto-tagging (M5, spec §7.2) — the anti-fragmentation stack.** Four small,
  single-responsibility services compose the pipeline `tagging.apply_tags` runs:
  - `structured_tags` — high-confidence **priors** from real metadata BEFORE inference
    (spec §7.2 mechanism 1), behind the `StructuredTagSource` interface. `parse_github_repo`
    + the GitHub REST API give a repo's topics + primary language (`HttpxStructuredTagSource`,
    unauthenticated, tolerating 403/404/network errors gracefully); `extract_keyword_tags`
    normalizes OG/meta keywords. `FakeStructuredTagSource` returns canned repo metadata.
    Priors seed the candidate set; they are not guesses.
  - `tags_vector` — the tag embedding layer over `tags_vec`, which embeds each tag's stable
    concept **description**, never the bare name (spec §9.3). `nearest_tags` (KNN, capped by
    `nearest_tags_limit`) fetches the nearest EXISTING tags to ground the LLM proposal — the
    single biggest anti-fragmentation lever; `nearest_tag` returns the single closest for the
    canonicalize snap. `tags_vec` uses `distance_metric=cosine`, so similarity is
    `1 - distance` and the 0.90 snap threshold is a true cosine.
  - `canonicalize` — `normalize_tag` is **conservative** (lowercase, trim, strip surrounding
    punctuation; collapse a plural ONLY via a safe rule guarded by a tech-term stoplist so
    `redis`/`kubernetes`/`css` are never mangled — never blind-stem). `canonicalize_candidates`
    embeds each candidate's **description** and snaps to the nearest existing tag at cosine ≥
    threshold (default 0.90, bias to reuse), else creates the tag with its stable description
    embedded into `tags_vec` (generated once, never regenerated on reuse). The LLM never
    writes the tag table — only this does. Capped to `tags_per_entry_max`.
  - `tagging.apply_tags(conn, id, *, basis_text, needs_summary, source, tagger, embedder, …)`
    — orchestrates the whole flow: priors → embed basis → nearest existing tags → ONE tagger
    call → canonicalize → persist. `_persist_tags` writes `entry_tags` edges, increments
    `tags.count` per edge and `tag_cooccurrence.count` for every unordered tag-pair stored in
    canonical order (`tag_a < tag_b`, so (a,b)/(b,a) never split — and a symmetric M6 decrement
    is trivial), then denormalizes the final tags into `entries_fts.tags_text` so BM25 matches
    tags. Returns the resolved note (the LLM summary on the summarize path, else `""`).
  - `worker.process_entry(conn, id, *, fetcher, summarizer, embedder=None, tagger=None,
    structured_source=None, max_attempts=None)` — the deterministic, synchronous,
    idempotent core (spec §7.1/§7.4). Atomically **claims** a `pending`/`failed` row below
    the ceiling by flipping it to `processing` and incrementing `attempts` in one UPDATE
    (so `active`/`processing` rows are never re-summarized and a concurrent run can't
    double-pick). On success: writes `note`/`note_source`, sets `active`, clears
    `error_message`, bumps `updated_at`, re-indexes FTS, and — when an `embedder` is
    supplied — embeds the resolved **note** (not the body) into `entries_vec` via
    `vector.index_entry_vector` (clear/replace on re-enrichment); a failed entry leaves no
    vector. **When `tagger` AND `structured_source` AND `embedder` are all supplied (the M5
    path, the production default), `_enrich_with_tags` resolves the basis without
    summarizing and delegates to `tagging.apply_tags` — one combined call yields the note +
    tags in a single LLM round trip (no separate summarizer call on the summarize path).
    Without them the legacy M3/M4 path (standalone summarizer, no tags) runs, so note-only
    unit tests need not wire a tagger.** The providers are threaded through `process_pending`
    / `drain_all_users` / `run_worker_loop` (which builds them from config via
    `build_providers` + `build_tagging_providers`); they are optional only for those unit
    tests. An empty resolved note
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
  - `tools.{save,retrieve,delete,get_tags}_tool` — transport-free tool logic. They resolve
    the current user, open that user's DB, and **delegate to the shared services** so REST
    and MCP have one implementation (DRY): `save_tool`→`save_entry` (+ `apply_agent_tags`
    when `tags` are given), `retrieve_tool`→`hybrid_search`, `delete_tool`→`delete_entry`,
    `get_tags_tool`→`tags_service.list_tags`. Per spec §10 `save` treats `note` as authored
    text: for `type=note` it is the user's note (its only copy → `captured_text`); for
    URL-backed types it is the override that skips summarization. Optional `save` `tags` are
    agent-supplied: canonicalized + merged additively (so the agent cannot fragment the
    vocabulary), while automatic worker tagging still runs.
  - `server.build_mcp_server` — FastMCP server `brain2_mcp` exposing all four spec §10
    tools: `save` (destructive/idempotent upsert), `retrieve` (readOnly), `delete`
    (readOnly=false, destructive, idempotent — removes the entry + derived data and
    decrements counters), and `get_tags` (readOnly, paged landscape). Flat, typed tool
    parameters (clean `inputSchema`) and typed returns (structured output). Each tool reads
    the request's Bearer header, resolves the user, and runs inside `auth.user_scope`.

- **models/entries.py** — Pydantic v2 models with validation: `CreateEntryRequest`
  (type-aware: URL required for URL-backed types, text required for notes; carries a
  distinct `note` override field per spec §10; string fields bounded via `max_length` —
  short fields 2 KB, body fields ~256 KB — so an oversized input yields 422 instead of a
  silently persisted/indexed blob), `SaveEntryResponse`, the §7.4 repair models
  (`RepairEntryRequest` with a required note + optional tags, `EntryResponse` for the
  repaired entry), the failed-entry surface models (`FailedEntry` + `FailedEntriesResponse`
  with a `total`), and the `EntryType` / `SaveStatus` enums.

- **api/entries.py + main.py** — `POST /entries` returns `201 {id, status}`. `GET
  /entries/failed` returns the §7.4 "needs attention" surface (`{total, entries}`), and is
  registered BEFORE the parameterized route so the literal path is not captured as an id.
  `PATCH /entries/{id}` is the §7.4 repair flow (`repair.repair_entry`; providers wired from
  config; 404 for an absent id). The app
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
  by config (summarizer + page-fetcher + **embedder**) and `factory.build_tagging_providers`
  the M5 pair (**tagger** + **structured_source**); no test requires `GEMINI_API_KEY`.
  The optional live Gemini tests (`tests/test_gemini_smoke.py` — summarizer, embedder
  768-dim, a real-embedding paraphrase retrieval, and the M5 combined structured-output
  tagger call) self-skip unless `GEMINI_API_KEY` is in the *environment*. Because the repo
  `.env` IS read by config, a session-autouse conftest fixture forces
  `Settings.gemini_api_key=None` for the offline suite whenever the key is absent from
  `os.environ` — so config and the smoke-test skip condition agree and the default suite
  never makes a real call. The `FakeEmbedder` is deliberately similarity-meaningful and
  `FakeTagger` records calls so the offline KNN/RRF/canonicalize and exactly-one-call tests
  assert real behavior.
- **Per-user isolation.** All DB access flows through `get_db` so routing to
  `{user_id}.db` is centralized; never open ad-hoc connections in routes/services.
- **Async enrichment.** New entries are `pending`; the worker resolves the note basis
  (fallback ladder), records `note_source`, re-indexes FTS, embeds the **note** into
  `entries_vec` (M4), and sets `active`. Keep the sync save path under 2s.
- **Auto-tagging (M5).** After the basis is resolved, the worker runs `tagging.apply_tags`:
  structured priors → embed basis → nearest existing tags (`tags_vec`) → **exactly one**
  Gemini structured-output call (note + tags + new-tag descriptions) → canonicalize-on-write
  (snap at cosine ≥ 0.90 or create) → persist `entry_tags`, `tags.count`, `tag_cooccurrence`
  (canonical pair order), and the denormalized `entries_fts.tags_text`. The summary is folded
  into that single call on the summarize path; the verbatim short-circuits (note / short clip /
  og / title) set the note directly. The 0.90 threshold + 3-5 cap bias to under-merge and to
  reuse over invention (spec §7.2). `tag_aliases` ships in the schema but the reversible-merge
  job is v2.
- **Delete + counters (M6).** `delete` removes the entry + all derived data (FTS, vector,
  edges) and SYMMETRICALLY decrements `tags.count` + `tag_cooccurrence` via
  `tag_counters` — the exact inverse of the write (canonical pair order, floor at 0). A tag
  at count 0 is left in place (spec §9.2). All edge writes (first-tag, reprocess, repair,
  agent tags) funnel through `tagging.reconcile_tags`, which diffs current↔desired and
  applies the precise partial-overlap counter delta (`apply_edge_diff`), so counts always
  equal the live edge set.
- **Repair (M6, spec §7.4).** `PATCH /entries/{id}` (`repair.repair_entry`) recovers a
  failed/active entry from a user note: note_source='user', clears error/attempts, then
  re-enters the SAME worker enrichment path with the basis forced to the user's note and no
  summarization, re-tags + re-indexes, and flips to `active`. `GET /entries/failed` is the
  read-only "needs attention" surface for M7/M8.
- **Agent tags (M6, spec §10).** The `save` tool's optional `tags` skip the LLM proposal but
  still go through canonicalize-on-write (`tagging.apply_agent_tags`) and merge additively,
  so an agent cannot fragment the vocabulary.
- **Hybrid retrieval (M4).** `retrieve` fuses BM25 (set A) and vector KNN over the note
  embedding (set B) with RRF (`k=60`). Tag/type are pre-filters on both legs (`prefilter`).
  `search.search_entries` stays as the internal BM25-only path; `search.hybrid_search` is
  the public path the MCP `retrieve` tool calls.

## Commands (run from `backend/`)

- `uv run pytest -q` — run the test suite
- `uv run uvicorn brain2.main:app --reload` — run the dev server
- `uv sync` — install/sync dependencies
