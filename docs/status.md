# Brain2 — Implementation Status

**As of:** 2026-06-05 · branch `feat/backend-v1` · **232 tests passing (5 live-Gemini smoke tests skip offline)**

This tracks progress against the build sequence in [`spec.md` §14](./spec.md). Backend milestones 1–6 are complete and committed; auth (M7) and the Chrome extension (M8) are the remaining v1 work.

---

## ✅ Done — Backend (M1–M6)

The Python + FastAPI backend lives in [`/backend`](../backend) (managed with `uv`, Python 3.12). See [`backend/ARCHITECTURE.md`](../backend/ARCHITECTURE.md) for the module map.

| Milestone | What shipped | Commit |
| --------- | ------------ | ------ |
| **M1** | Project scaffold; full per-user SQLite schema (§9.2: entries, entry_tags, tags, tag_cooccurrence, tag_aliases, FTS5, `vec0[768]`); WAL + sqlite-vec loading; URL normalization; conditional content persistence; `POST /entries` (upsert by normalized URL, non-destructive) | `9aee9cf` |
| **M2** | FTS5/BM25 indexing kept in lockstep with entries (trigram tokenizer); BM25 search with tag/type pre-filters; MCP server (official SDK, streamable-HTTP at `/mcp`) with `save` + `retrieve`; Bearer→dev-user stub | `53676e7` |
| **M3** | Async enrichment worker (resilient SQLite-backed queue, backoff via `next_retry_at`, stale-`processing` reaper, loop error isolation); Gemini summarization + note-source fallback ladder (body → og/meta → title); provider interfaces (`Summarizer`, `PageFetcher`) with offline fakes | `43952b0` |
| **M4** | Note embeddings (`gemini-embedding-001`, 768-dim, L2-normalized); sqlite-vec KNN vector search (`distance_metric=cosine`); RRF hybrid merge (k=60) of BM25 + vector; `Embedder` provider + similarity-meaningful fake | `6d051e1` |
| **M5** | **Automatic tagging (the core):** structured-source priors (OG/meta keywords + GitHub topics/language) → RAG-grounded nearest-tag retrieval → **one** combined Gemini structured-output call (note + tags + new-tag descriptions) → canonicalize-on-write (conservative normalization w/ tech-term stoplist, snap at cosine ≥ 0.90 else create) → tag-description embeddings in `tags_vec` → counts + co-occurrence | `7e9dfa0` |
| **M6** | `delete` + `get_tags` MCP tools; `PATCH /entries/{id}` repair (re-enrich from user note → active); symmetric counter decrements; `reconcile_tags` single edge-write owner; agent-supplied tags canonicalized + merged additively; `GET /entries/failed` needs-attention surface | `ea940af` |

**All four MCP tools are live and round-trip over HTTP:** `save`, `retrieve`, `delete`, `get_tags`.

**External services are validated against the real API** (Gemini summarize, 768-dim embeddings, paraphrase retrieval, combined tagging, repair re-tagging) — all behind injectable interfaces so the 232-test unit suite runs fully offline.

### Run it
```bash
cd backend
uv run pytest            # full suite (offline)
uv run uvicorn brain2.main:app --reload   # dev server (reads ../.env)
```

---

## ⏳ Pending — v1 remaining

### M7 — Auth + dashboard (`~1–2 days`)
- Google OAuth 2.1 + PKCE (web/extension) and Personal Access Tokens / API keys (CLI/Desktop)
- Bearer validation that resolves a credential → `user_id` (replaces the current dev-user stub in `mcp/auth.py` + `deps.py`)
- Implicit first-time signup creates `{user_id}.db`
- Web dashboard with the "needs attention" repair list (consumes the existing `GET /entries/failed`)
- `@brain2/mcp-bridge` npm stdio bridge for MCP clients that don't support remote transports

### M8 — Chrome extension (`~2–3 days`)
- Toolbar popup, three capture modes: **save page** (with chat-domain → `conversation` detection), **element picker** (DOM-granularity selection + Turndown HTML→Markdown + review card), **custom note**
- OAuth via `chrome.identity` + token refresh; "needs attention" count badge
- Fire-and-forget save with toast confirmation; no keyboard shortcuts
- Scaffold already exists in [`/extension`](../extension) (WXT + React 19 + Tailwind)

### M9–M10 — Dogfood & ship decision
- Two-week solo dogfood; track tag-reuse vs invention and failure rate; ship decision gate

---

## 🔭 Deferred to v2 (designed-for, not built)
- Web management/browse UI · offline tag-clustering/merge job (uses the shipped `tag_aliases` table) · chunk-level content embeddings · import (GitHub stars, Pocket, bookmarks) · Markdown export · self-hosting UX

---

## 📌 Open items to revisit (from spec §15)
- **Tune the 0.90 canonicalize threshold and 3–5 tags-per-entry cap** against real saves during dogfood (currently config knobs).
- Confirm discarding `page` body doesn't hurt exact-identifier recall (watch in dogfood; add page content only if it bites).
- MCP transport diverges from the spec's named SSE to the SDK-recommended **streamable-HTTP** (documented in `backend/ARCHITECTURE.md`).
- Conversation enrichment currently shares the clip `<400-char` verbatim rule (minor §7.3 divergence; revisit if it matters).

---

## How this was built
Each milestone ran through a multi-agent workflow (`.claude/workflows/milestone.mjs`): TDD build → parallel review (correctness/edge-cases + SOLID/simplicity) → triage + fix, with an independent test run and review before each commit. Reviews caught and fixed real bugs before commit each time — e.g. a destructive dedup-UPDATE (M1), a TOCTOU first-save race (M2), worker-loop death + cosmetic backoff (M3), L2-vs-cosine mis-ranking on un-normalized embeddings (M4), a zero-vector KNN crash + counter double-increment (M5), and agent-tags being wiped by the auto-tagger (M6).
