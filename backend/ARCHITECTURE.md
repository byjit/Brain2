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
│   │   └── entries.py        # save_entry: sync upsert pipeline (spec §7.1)
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
  - `entries.save_entry` — normalizes URL, applies content rule, upserts by normalized
    URL (insert `status='pending'` → `saved`; existing → `updated`); notes never dedup.

- **models/entries.py** — Pydantic v2 models with validation: `CreateEntryRequest`
  (type-aware: URL required for URL-backed types, text required for notes),
  `SaveEntryResponse`, and the `EntryType` / `SaveStatus` enums.

- **api/entries.py + main.py** — `POST /entries` returns `201 {id, status}`. The app
  factory adds a `/health` probe and includes routers.

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
