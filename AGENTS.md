## Project Overview

Save content from anywhere, and bring it as context to every AI agents you use.

> [!IMPORTANT]
> Any changes in the repository structure, tech stack, or scripts must be updated in the [AGENTS.md](/AGENTS.md) file.
> The project's source of truth is the [AGENTS.md](/AGENTS.md) and `docs/spec.md` file.

## Repository Structure

- [extension/](/extension): Chrome capture extension (WXT + React + TypeScript + Tailwind CSS). Popup with three capture modes (save page → chat domains become `conversation`; element picker; custom note) plus a "needs attention" repair list. Thin popup UI; the background service worker owns all network/auth/state; content scripts (`entrypoints/`) do DOM extraction (Readability) and the Shadow-DOM element picker (Turndown HTML→Markdown). Shared contracts in `services/` (`auth` PKCE OAuth, `api` client, `capture` stores/types, `messaging`, `storage`). See [extension/README.md](/extension/README.md).
- [backend/](/backend): Python + FastAPI backend (per-user SQLite memory store). Managed with **uv**, Python pinned to **3.12**. See [backend/ARCHITECTURE.md](/backend/ARCHITECTURE.md) for layout and conventions.
- [platform/](/platform): Web platform and user dashboard built using React, TypeScript, Vite, and TanStack Router.
- [mcp/](/mcp): Directory for Model Context Protocol (MCP) servers.
- [docs/](/docs): Product documentation and specifications (e.g., [spec.md](/docs/spec.md)).
- [.agents/](/.agents) / [.claude/](/.claude): AI agent configurations and shared skills (symlinked).

# Coding standards you must follow

- Write elegant, clean, and maintainable code.
- Ensure a good directory structure and modularity.
- Add explanatory comments to the code where necessary.
- Use meaningful variable and function names relevant to the language.
- Use consistent naming conventions.
- When working on the frontend, ensure responsiveness and a beautiful, consistent UI.
- When working on the backend, ensure efficient code that follows best practices for security and performance.
- When working on the database, ensure the schema is well defined and follows best practices for data integrity and performance.
- Do not delete any files or code to fix errors; ask the user for clarification if unsure.
- Apply the following principles in all code you generate:
- **DRY (Don't Repeat Yourself):** Abstract repeated logic into functions or modules to avoid duplication.
- **YAGNI (You Aren't Gonna Need It):** Only implement features and code that are currently required; avoid speculative additions.
- **SOLID Principles:**
- _Single Responsibility:_ Each module/class/function should have one clear responsibility.
- _Open/Closed:_ Code should be open for extension but closed for modification.
- _Liskov Substitution:_ Subtypes must be substitutable for their base types without altering correctness.
- _Interface Segregation:_ Prefer small, specific interfaces over large, general ones.
- _Dependency Inversion:_ Depend on abstractions, not concrete implementations.
- Write clean, maintainable, and modular code that adheres to these principles.
- Add comments where necessary for clarity, but avoid excessive commenting.
- Structure code into smaller, modular files and follow best practices.
- Do not repeat yourself; keep solutions simple.

## Tech Stack

- **Framework**: [WXT](https://wxt.dev/) 0.20 (Web Extension Framework, MV3) for building the Chrome extension
- **Frontend & UI**: React 19, TypeScript, Tailwind CSS 4, Base UI, Radix UI, sonner (toasts) (configured in [extension/package.json](/extension/package.json))
- **Capture deps**: `@mozilla/readability` (page/article extraction), `turndown` + `turndown-plugin-gfm` (HTML→Markdown for the element picker), `zod` (shared contracts); `jsdom` (dev) for offline extraction tests
- **Auth**: OAuth 2.1 + PKCE (S256) via `chrome.identity.launchWebAuthFlow` against the M7 AS; no refresh token (silent `interactive:false` re-auth handles the 1h access-token TTL)
- **Manifest** ([extension/wxt.config.ts](/extension/wxt.config.ts)): `permissions: [activeTab, scripting, storage, identity, alarms]`, `host_permissions: [<API origin>/*]` (background fetches are CORS-exempt via host permissions; no `<all_urls>` — extractor/picker injected on a user gesture). Env: `VITE_BRAIN2_API_URL`, `VITE_BRAIN2_OAUTH_CLIENT_ID` (see `extension/.env.example`)
- **Build Tool**: Vite (under the hood via WXT and [vitest.config.ts](/extension/vitest.config.ts))
- **Testing**: Vitest
- **Package Manager**: pnpm (uses [pnpm-lock.yaml](/extension/pnpm-lock.yaml))

### Backend (FastAPI)

- **Language/Runtime**: Python 3.12 (pinned via `backend/.python-version`)
- **Framework**: FastAPI + Uvicorn
- **MCP**: official MCP Python SDK (`mcp`, FastMCP) mounted into FastAPI over the
  streamable-HTTP transport at `/mcp` (the spec §6 names SSE; see backend/ARCHITECTURE.md)
- **Storage**: Per-user SQLite (`{user_id}.db`) with FTS5 (BM25 keyword search) + sqlite-vec (`vec0`, 768-dim).
  A separate central `auth.db` (default `{DATA_DIR}/../auth.db`, gitignored) holds identities,
  API-key hashes, and OAuth codes — credentials resolve to a `user_id` there before the per-user DB opens
- **Auth (spec §12)**: Hybrid — Personal Access Tokens (API keys, `br2_live_…`, SHA-256 hashed) for
  CLI/Desktop, Google Sign-In + Brain2-issued OAuth 2.1 + PKCE (S256) for web/extension. Brain2 access +
  session tokens are HS256 JWTs via `pyjwt`. Google identity verification sits behind an
  `IdentityProvider` interface with an offline fake, so the suite never contacts Google. Endpoints:
  `GET /auth/login`, `GET /auth/callback`, `GET /auth/me`, `POST /auth/logout`, `GET /oauth/authorize`,
  `POST /oauth/token`, and `/settings/tokens` (POST/GET/DELETE). Every REST entry endpoint and all four
  MCP tools require a valid `Bearer` credential
- **LLM / enrichment**: `google-genai` SDK + Gemini Flash for note summarization and the
  M5 single combined auto-tagging call (structured output: note + tags + new-tag
  descriptions), `gemini-embedding-001` (768-dim) for note/query/tag-description embeddings
  (async worker); `httpx` + `trafilatura` for page re-fetch and body/metadata extraction,
  and `httpx` for the unauthenticated GitHub REST API (structured-source tag priors). All
  sit behind injectable provider interfaces with offline fakes (see backend/ARCHITECTURE.md
  `services/providers` + the M5 auto-tagging services)
- **Config**: pydantic-settings, reading the repo-root `.env`
- **Testing**: pytest
- **Package Manager**: uv (uses `backend/pyproject.toml` + `uv.lock`)

## Available Scripts

### Extension scripts

All extension scripts are executed from the [extension/](/extension) directory:

- `pnpm dev`: Start WXT development server (launches Chrome extension with hot reload)
- `pnpm dev:firefox`: Start WXT development server targeting Firefox
- `pnpm build`: Build production extension bundle
- `pnpm build:firefox`: Build production extension bundle for Firefox
- `pnpm zip`: Build and zip Chrome extension for distribution
- `pnpm zip:firefox`: Build and zip Firefox extension for distribution
- `pnpm compile`: Run TypeScript compilation check (`tsc --noEmit`)
- `pnpm test`: Run tests with Vitest once
- `pnpm test:watch`: Run tests with Vitest in watch mode

### Backend scripts

All backend scripts are executed from the [backend/](/backend) directory:

- `uv sync`: Install / sync Python dependencies into `.venv`
- `uv run pytest -q`: Run the backend test suite
- `uv run uvicorn brain2.main:app --reload`: Start the FastAPI dev server
