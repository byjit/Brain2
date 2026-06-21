# Brain2 — Product Spec

**Version:** 0.6
**Date:** 2026-06-05
**Status:** Draft · Technical decisions finalized, not yet implemented
**Author:** Prasanjit Dutta

> **Changes from 0.5:** Added §8 Capture UX - the three popup-driven save modes (save page, element picker, custom note), no keyboard shortcuts, fire-and-forget confirmation, and the two moments the extension asks for attention (first-run sign-in, failure badge). Added §7.5 Large content and capture size bounds - the note-is-a-routing-card rationale, tiered prefix caps (page capture / note-writer / embedder), and a §15 open question on uncapped persisted content. Subsequent sections renumbered.

---

## 1. The One-Liner

Save your context in one place, and bring it to all AI agents you use.

---

## 2. The Problem

Developers save useful things constantly. The saves scatter across GitHub stars, Notion, bookmarks, and notes. Two failures follow:

1. **Saves die.** Items pile up unused. Another place to save becomes another inbox to abandon.
2. **Agents can't see any of it.** Every Claude / Cursor / ChatGPT session starts blind. The developer becomes the retrieval layer: search the silo, find the thing, paste it into the chat. This happens multiple times a day.

A third failure shows up over time, once a store actually gets used: **the organizational layer rots.** Tags drift into near-duplicates (`python`, `python3`, `py`), nothing reconciles them, and the store turns into noise. This is the failure that kills a memory tool slowly instead of fast, so the tag system in this spec is built to resist it from the start.

---

## 3. Target User (ICP)

The developer with **400 GitHub stars and a dead Notion**:

- Uses Claude Code, Cursor, or ChatGPT every working day
- Collects tools, repos, articles, docs habitually - retrieves them manually
- Understands MCP; comfortable connecting remote servers
- Has been burned by a tool shutdown; leads with "can I export?" before features
- Found in: r/mcp, r/ClaudeAI, r/selfhosted, r/PKMS, build-in-public X

The founder is the ICP. Scratch-your-own-itch. Highest-confidence demand signal available.

**Expected scale:** a committed user accumulates thousands of entries over time - design target is up to ~10k entries and several hundred tags per user. The tag and retrieval systems are sized for that, not for a 300-entry toy.

---

## 4. What Brain2 Is

An open-source personal memory store with two ways in and one way out everywhere.

- **Save once** - Chrome/Edge extension (one click) or from inside any agent conversation. Saving is the only thing the user does. Tagging, summarizing, and indexing all happen automatically in the background. The user stays in their flow.
- **Recall anywhere** - every AI tool reads the same store over MCP; ask your agent, it answers from what you saved.

The core promise: **whatever is saved is accessible by any AI that connects the MCP.** All your context, available to all your AI tools, with zero filing effort.

---

## 5. v1 Scope

### In scope

| Feature                         | Notes                                                                                                                                                                                                                         |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Chrome/Edge extension save      | Popup-first, three capture modes - save page, element picker, custom note (see §8). No keyboard shortcuts. DOM scraped client-side. Chromium build, ships to both the Chrome Web Store and Edge Add-ons                       |
| Conditional content persistence | Keep raw captured text only when it can't be re-fetched from a URL (clips, notes, conversations). Discard scraped body for `page` saves - the URL is stored and an agent can re-fetch it (see §7, §9)                         |
| LLM-generated note              | Gemini Flash summarizes captured content into 2-3 sentences; stored as the `note` field; user-editable; this is what gets vectorized. Falls back to OG/meta description, then title, when the body can't be parsed (see §7.3) |
| Automatic tagging               | No manual tagging. Tags are generated in the background, grounded in the user's existing tags, then canonicalized before write (see §7.2). Tags remain viewable and editable, never required                                  |
| Tag embedding layer             | Each tag has a stable concept-level description, embedded once at creation. Tag vectors power canonicalization and related-tag expansion (see §7.2, §9.3)                                                                     |
| Structured-source tags          | Free, high-confidence tags pulled from page metadata before any LLM inference: GitHub repo topics + detected language + README, OG/meta keywords. Used as priors, not guesses                                                 |
| Failure recovery                | Entries whose background processing fails (after retries) are flagged and surfaced to the user, who can fill the note to recover them (see §7.4, §8)                                                                          |
| Tags as the graph               | The only organizational primitive - flat, multi-assignable. Same concept as "spaces." No distinction. Structure emerges from shared tags + co-occurrence                                                                      |
| Remote MCP server (hosted)      | Five tools: `save`, `retrieve`, `list`, `delete`, `get_tags`. Users paste the MCP URL into their AI app                                                                                                                       |
| Hybrid search                   | BM25 on title + tags + persisted content; vector on note; merged with RRF. Related-tag expansion fuses embedding similarity + co-occurrence + lexical match (see §11)                                                         |
| Per-user SQLite DB              | Each user gets an isolated `{user_id}.db`; FTS5 + sqlite-vec in the same file                                                                                                                                                 |
| Hybrid Auth & API Keys          | Personal Access Tokens (API keys) for CLI/Desktop (Claude Code, Cursor); OAuth 2.1 for web app & Extension                                                                                                                    |
| Agent write-back                | Agents call `save` directly; in scope from day one - same tool, no extra build                                                                                                                                                |
| URL normalization               | Strip tracking params, utm\_\*, trailing slashes before dedup check                                                                                                                                                           |

### Out of scope for v1

| Excluded                                 | Reason                                                                                                                                                                                                                  |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| General viewing UI / browse list         | The agent is the interface. The one exception is a narrow "needs attention" list of failed entries (§7.4, §8) - that's a repair surface, not a browse list. A craving for a full list view is product data - log it     |
| Keyboard shortcuts / hotkeys             | Capture always starts from the toolbar popup, so the entry point is discoverable. Shortcuts can come later if the daily-habit users ask                                                                                 |
| Management UI in the extension           | The extension captures; it does not manage. Viewing, editing tags, and bulk repair belong to a later web app. Keeping the extension capture-only is what preserves the in-flow property                                 |
| In-server spreading activation           | Rejected, not deferred. The agent navigates the graph itself via `get_tags` + filtered `retrieve`. An in-server activation engine adds tuning burden for navigation the agent already does, steerably (see §11)         |
| Offline tag-clustering / merge job       | The write-time guards (RAG-grounding + canonicalize-on-write) carry v1. The periodic batch merge of stragglers is v2; its `tag_aliases` table ships in v1 so merges are reversible later                                |
| Content vector embeddings (chunked)      | v1 embeds the note, not the body. Persisted content is lexically searchable via BM25, which is where exact identifiers live. Chunk-level content embeddings are a v2 option if semantic recall on body text proves weak |
| Import (GitHub stars, Pocket, bookmarks) | High day-one value - v2 after recall loop is proven                                                                                                                                                                     |
| Self-hosting UX                          | Code is open source; self-hosting is _possible_ but no installer or docs for v1                                                                                                                                         |
| Markdown file export                     | "Files you own" trust story - v2; schema is designed for lossless export                                                                                                                                                |
| Mobile                                   | ICP lives in Chrome and the terminal                                                                                                                                                                                    |
| Team / shared spaces                     | Single-player value must exist first                                                                                                                                                                                    |
| Automatic resurfacing / digests          | Strong v2 candidate; not needed to prove the loop                                                                                                                                                                       |

---

## 6. Architecture

### Components

```
┌─────────────────────┐     ┌──────────────────────────────────────────┐
│  Chrome Extension   │     │          Brain2 Backend (hosted)         │
│                     │     │                                          │
│  Toolbar popup:     │     │  FastAPI                                 │
│   - Save page       │     │  ├─ POST  /entries   (REST, extension)   │
│   - Select content  ├────►│  ├─ PATCH /entries/{id} (edit / repair)  │
│   - Custom note     │     │  ├─ POST  /connect/mcp (MCP transport)   │
│  In-page picker      │     │                                          │
│  "Needs attention"  │     │  ├─ /oauth/* (authorize, token, PKCE)    │
│  badge for failures │     │  └─ /settings/tokens (API Key gen)       │
│  OAuth tokens in    │     │                                          │
│  chrome.storage     │     │  On save (sync, returns immediately):    │
└─────────────────────┘     │  1. Extract canonical URL & normalize    │
                            │  2. Persist content IF non-re-fetchable  │
┌─────────────────────┐     │  3. Upsert entry (status=pending)        │
│  AI Agents          │     │  4. Return ID immediately                │
│  Claude Code        ├────►│                                          │
│  Claude (web)       │     │  Async worker pool:                      │
│  Cursor / ChatGPT   │     │  5. Resolve note basis (body→og→title)   │
│  (connect via       │     │  6. Embed basis; fetch nearest tags      │
│   API Key or OAuth) │     │  7. One Gemini call → note + tags + descs│
└─────────────────────┘     │  8. Canonicalize tags; embed note + descs│
                            │  9. Index FTS + vectors; co-occurrence   │
                            │     status=active                        │
                            │     On failure after retries → failed →  │
                            │     notify user (§7.4)                   │
                            └────────────────┬─────────────────────────┘
                                             │
                            ┌────────────────▼─────────────────────────┐
                            │            Per-User Storage              │
                            │                                          │
                            │  /data/users/{user_id}.db (isolated)     │
                            │    entries · entry_tags · tags           │
                            │    tag_cooccurrence · tag_aliases        │
                            │    entries_vec · tags_vec  (FTS5 + vec0) │
                            └──────────────────────────────────────────┘
```

### Tech Stack

| Layer                   | Choice                             | Reason                                                                                            |
| ----------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------- |
| Backend                 | **Python + FastAPI**               | Official MCP Python SDK + Google AI SDK; both first-class                                         |
| MCP transport           | **HTTP + SSE**                     | Required for web/mobile AI clients; stdio only works local                                        |
| Full-text search        | **SQLite FTS5 + BM25**             | Indexes title + tags + persisted content; zero extra deps                                         |
| Vector search           | **sqlite-vec** (`vec0`)            | Same SQLite file; no separate infra; 768-dim vectors for both note and tag-description embeddings |
| Embeddings              | **Gemini embedding 2**             | Async on save; 768-dim; same model for note and tag descriptions; no local GPU                    |
| Summarization & tagging | **Gemini Flash**                   | One call returns note + candidate tags + concept descriptions (see §7.2)                          |
| Extension capture       | **Readability.js + Turndown**      | Readability for full pages; Turndown (+ GFM) for HTML→Markdown on picked elements                 |
| Primary store           | **Per-user SQLite** `{user_id}.db` | Isolated; FTS5 + vec0 in the same file                                                            |

---

## 7. Save Pipeline

Every save - from the extension or an agent - goes through the same flow. The save call returns in under 2 seconds; all enrichment is async, so the user never waits and never files anything by hand.

### 7.1 Flow

```
┌─── Client (extension or agent) ──────────────────────────────────┐
│  1. User picks a capture mode (§8) or an agent calls save        │
│  2. Scrape: Readability.js on full page, OR picked element →     │
│     Markdown, OR custom note text                                │
│  3. POST /entries {url, title, captured_text, type}              │
│     (no tags sent - tagging is automatic)                        │
└──────────────────────────────────────────────────────────────────┘
                │
┌─── Backend (sync, returns immediately) ──────────────────────────┐
│  1. URL: extract canonical link; normalize (strip utm_*,         │
│     tracking params, trailing slash). Save raw + normalized.     │
│  2. Content: persist captured_text ONLY if non-re-fetchable      │
│     (clip / note / conversation). For `page`, discard after the  │
│     async summary runs - the URL is the recovery path.           │
│  3. Upsert: if URL exists → update; if new → insert pending.     │
│  4. Return {id, status: "saved" | "updated"}                     │
└──────────────────────────────────────────────────────────────────┘
                │
┌─── Resilient SQLite-backed queue (async worker pool) ────────────┐
│  1. On startup, scan user DBs for status in (pending, failed)    │
│     with attempts below the retry ceiling.                       │
│  2. Resolve note basis via the fallback ladder (§7.3):           │
│     Readability body → og:description / meta → title.            │
│     Record note_source.                                          │
│  3. Embed the basis text → query vector for nearest-tag lookup.  │
│  4. Pull structured-source tags (README/topics/lang, OG meta).   │
│  5. Fetch nearest existing tags from tags_vec (query vector).    │
│  6. ONE Gemini Flash call: input = basis text + structured tags  │
│     + nearest existing tags. Output = note + candidate tags      │
│     + a concept description per NEW tag.                         │
│  7. Canonicalize each candidate (§7.2): embed its description,   │
│     snap to nearest existing tag if cosine ≥ 0.90, else create   │
│     and persist its vector. Cap ~3-5 tags; bias to reuse.        │
│  8. Embed the final note → entry vector. Write entry_tags;       │
│     increment tag counts + tag_cooccurrence.                     │
│  9. Index FTS (title + tags + content-if-present).               │
│     status → active.                                             │
│     On unrecoverable failure → failed (+ message) → notify (§7.4)│
└──────────────────────────────────────────────────────────────────┘
```

Ordering matters here: the basis text is embedded (step 3) _before_ tagging (step 6) because RAG-grounded tagging needs a query vector to find nearest existing tags, and canonicalization needs each candidate's embedding to snap it. Embeddings are cheap relative to LLM calls, so a separate basis embedding plus the final note embedding is fine - what we avoid is a second LLM call.

### 7.2 Automatic tagging

The user never tags. The tagger replaces the human's memory of "what tags do I already use" with two grounding mechanisms, because an LLM tagging each save in isolation will fragment the vocabulary at scale.

1. **Structured-source priors first.** Before any inference, pull tags that already exist as real metadata: a GitHub repo gives topics + detected language + README; most pages give OG/meta keywords. These are high-confidence and don't fragment, so they seed the candidate set.
2. **RAG-grounded proposal.** Embed the basis text, fetch the **nearest existing tags by vector similarity** (not all tags - at hundreds of tags they won't fit the prompt), and pass them to the single LLM call: _"existing related tags in this library: python, flask, tutorial - reuse these if they fit; only invent a new tag if nothing matches."_ This is the single biggest lever against fragmentation.
3. **Canonicalize-on-write.** The LLM never writes to the tag table directly. Each candidate is normalized (see below), embedded, then snapped to the nearest existing tag if cosine ≥ **0.90**, else created as new with a stable concept description stored and embedded once.
4. **Bias to under-merge live.** The threshold is deliberately high. With no human watching, over-merging is invisible (nobody notices two real concepts collapsed), while fragmentation is recoverable later. So merge conservatively at write time and leave aggressive merging to the v2 offline job, behind the reversible `tag_aliases` table.
5. **Cap and bias.** Limit to ~3-5 tags per entry and bias toward reuse over invention, so the tagger can't spray and manufacture hub tags.

**Normalization is conservative.** Lowercase, trim, strip punctuation. Plurals are collapsed only by a safe rule with a tech-term stoplist - never blindly stem, or `redis` becomes `redi` and `kubernetes` becomes `kubernete`. When in doubt, leave the token alone and let embedding-based canonicalization catch the duplicate.

### 7.3 Content types and the note-source ladder

The note is built from the best available source. When the body parses, summarize it. When it doesn't (paywalls, JS-only pages, blocked scrapes), fall back rather than summarizing garbage:

**Readability body → `og:description` / `<meta name="description">` → `<title>` alone.**

Each entry records `note_source` (`body | og | title | user`) so the user and the retrieval layer know how shallow the note is. OG/meta is publisher teaser copy, not the article - useful, but worth flagging for editing.

| Type           | Capture mode (§8)                   | Note generation                                        | Content persisted?                                                                     |
| -------------- | ----------------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| `page`         | Save page                           | Summary of body; OG/meta or title fallback             | **No** - re-fetchable via URL                                                          |
| `clip`         | Select content (element picker)     | If < 400 chars: selection is the note. Else: summarize | **Yes** - the highlight is the value; re-fetching the page won't recover the selection |
| `conversation` | Save page on a detected chat domain | Summary; long threads → concise summary                | **Yes** - conversation URLs are private/auth-gated and not externally re-fetchable     |
| `note`         | Custom note                         | Note = what the user typed; no summarization           | **Yes** - no URL, the text is the only copy                                            |

**Why discard `page` content:** at 10k entries, persisting every page body is storage the agent doesn't need - it has the URL and can fetch the live page when it wants depth. The tradeoff: exact identifiers that appear in a page body but not in the summary note aren't directly searchable; recall on those depends on the agent re-fetching. Accepted for v1 (see §15).

**Paywalled pages:** the OG/meta fallback usually yields the publisher's real teaser instead of a note describing the paywall wall. If even that is missing, the note is the title, and the user can edit it.

### 7.4 Failure handling and repair

Background processing can fail - Gemini rate limits, a page that yields nothing, an embedding error.

- **Transient failures retry quietly.** Exponential backoff up to a retry ceiling. The user is not bothered; most failures resolve here.
- **Exhausted retries set `status = failed`** with `error_message`, and the entry surfaces as a **"needs attention"** count in the extension badge and the web dashboard. This narrow list of failed entries is the only browse surface in v1 - it exists to repair, not to browse.
- **The user repairs it** by filling the note (and optionally tags) via `PATCH /entries/{id}`. On submit, the entry re-enters processing using the user's text as the basis: embed note → auto-tag from it → index → `active`. A failed entry is never a silent black hole; it is always recoverable by the user.

### 7.5 Large content and capture size bounds

A long article (a Medium deep-dive can be hundreds of KB) must not break the pipeline. The handling follows directly from the **note-is-a-routing-card** model (§7.3): the note exists so an agent can judge, _from the note alone_, whether to open the URL / re-fetch the body. It is not a faithful compression of the source. So reading a generous **prefix** of the body is sufficient to write a good note — an article's thesis, scope, and key specifics live up front. This makes bounding the input an alignment with the goal, not a lossy compromise.

Three tiered caps, each a prefix, with the full source never lost (re-fetchable for `page`, FTS-indexed for `clip`/`conversation`/`note`):

| Bound | Where | Size | Why |
| ----- | ----- | ---- | --- |
| **Page capture** | Extension, `page` only | ~32k chars | The body is discarded server-side after summarizing, so shipping a whole long article only wastes bandwidth and risks the backend body-size limit. A generous prefix is sent. `conversation`/`clip`/`note` bodies are persisted (not re-fetchable) and are **not** capped here. |
| **Note-writer input** | Backend, before the Gemini note/tag call | ~16k chars | How much source the LLM reads to write the routing-card note. Larger than the embedder cap so a long article still yields a meaningful note; bounded so LLM cost/latency stays constant regardless of length. |
| **Embedder input** | Backend, before every embed | ~8k chars | The embedding model has a hard ~2k-token budget; an oversized text would fail every retry and turn a valid entry into a permanent failure. A bounded prefix still yields a representative vector. |

The note-writer and embedder caps are **deliberately decoupled**: the embedder's is a hard model limit, while the note-writer's is a quality/cost knob the LLM can comfortably exceed the embedder on. Collapsing them to one value (an earlier shortcut) starved the summary on long articles.

---

## 8. Capture UX (Chrome / Edge Extension)

The extension is the only capture surface in v1, and the only place the user actively does anything. The design rule, top to bottom: **friction is proportional to how likely a capture is to be wrong.** High-confidence captures commit instantly; error-prone ones get a quick review; everything downstream (tags, summary, indexing) is invisible. There are no keyboard shortcuts - capture always begins from the toolbar popup, so the entry point is always discoverable.

### 8.1 The three capture modes

Clicking the toolbar icon opens a popup with three choices.

1. **Save page.** Saves the current tab. One click, commits instantly, a toast confirms. No review step - this is high-confidence and the common case. The popup makes this the prominent default. If the tab is on a detected chat domain, the same button captures the conversation thread instead of running Readability, mapping to the `conversation` type.
2. **Select content (element picker).** The popup closes and the page enters pick mode with an in-page overlay. As the cursor moves, the element under it is outlined with a highlight box (an accent color, not red - red reads as destructive). The box snaps to a logical block, and the user can expand or contract the selection up and down the DOM to grab the right block rather than a single nested node. A click captures that element; its HTML is converted to Markdown - preserving code blocks, lists, and links - and dropped into an editable field in a small in-page card. The user trims if needed and saves. The review step is deliberate: picking is the most error-prone mode, so it earns the extra look. Escape cancels pick mode. Maps to the `clip` type.
3. **Custom note.** A text field in the popup. The user types and saves. No URL, no summarization. Maps to the `note` type.

### 8.2 What the user never touches at save time

- **Tags.** Automatic and async - they don't exist yet at the moment of saving, so the user is never prompted for them. Tags are something to view or correct later, never to file at capture.
- **Processing.** The save commits and returns immediately; the note, tags, and indexes fill in seconds later in the background. Confirmation is a toast, not a spinner. Fire and forget - the user is already back in their flow.

### 8.3 The two moments the extension asks for attention

- **First run:** a one-time "Sign in with Google." After that the extension is silent.
- **Failures:** a quiet count badge on the toolbar icon when an entry needs attention (§7.4). Opening the popup shows the failed item; the user fills the note and it recovers. This is the only proactive nudge the tool ever makes.

### 8.4 Scope boundary

The extension captures; it does not manage. Viewing the library, editing tags in bulk, and reviewing the store belong to a later web app. Keeping the extension capture-only is what preserves the in-flow property that is its entire reason to exist. As new capture surfaces arrive (web app, mobile), each stays a thin capture client; management consolidates in the web app.

---

## 9. Data Model

SQLite is the primary store. Each user has one isolated DB file.

### 9.1 Entry fields

| Field           | Type    | Required | Notes                                                                              |
| --------------- | ------- | -------- | ---------------------------------------------------------------------------------- |
| `id`            | TEXT    | yes      | nanoid; primary key                                                                |
| `url`           | TEXT    | no       | Normalized before storage                                                          |
| `original_url`  | TEXT    | no       | Raw URL before normalization                                                       |
| `title`         | TEXT    | no       | From page `<title>` or OG title                                                    |
| `note`          | TEXT    | no       | LLM summary or fallback; user-editable; what gets vectorized                       |
| `note_source`   | TEXT    | yes      | `body`, `og`, `title`, or `user` - provenance of the note                          |
| `content`       | TEXT    | no       | Raw captured text. Populated for `clip` / `conversation` / `note`; NULL for `page` |
| `type`          | TEXT    | yes      | `page`, `clip`, `conversation`, `note`                                             |
| `source_url`    | TEXT    | no       | For clips: the page URL the selection came from                                    |
| `saved_at`      | TEXT    | yes      | ISO 8601                                                                           |
| `updated_at`    | TEXT    | yes      | ISO 8601; bumped on any edit. A note edit re-embeds and re-indexes the entry       |
| `status`        | TEXT    | yes      | `pending`, `processing`, `active`, `failed`                                        |
| `attempts`      | INTEGER | yes      | Processing attempts; gates retry ceiling                                           |
| `error_message` | TEXT    | no       | Error details if background processing failed                                      |

Tags live in `entry_tags` and `tags`, not on `entries`, so the embedding layer and co-occurrence have somewhere to attach.

### 9.2 SQLite schema

```sql
CREATE TABLE entries (
  id            TEXT PRIMARY KEY,
  url           TEXT,
  original_url  TEXT,
  title         TEXT,
  note          TEXT,
  note_source   TEXT NOT NULL DEFAULT 'body',
  content       TEXT,                -- NULL for page-type (re-fetchable)
  type          TEXT NOT NULL DEFAULT 'page',
  source_url    TEXT,
  saved_at      TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'pending',
  attempts      INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);

-- Entry ↔ tag edges (the bipartite graph)
CREATE TABLE entry_tags (
  entry_id TEXT REFERENCES entries(id) ON DELETE CASCADE,
  tag      TEXT NOT NULL REFERENCES tags(name),
  PRIMARY KEY (entry_id, tag)
);

-- Tag registry with stable concept descriptions
CREATE TABLE tags (
  name        TEXT PRIMARY KEY,
  description TEXT NOT NULL,         -- concept-level, generated once, stable
  count       INTEGER NOT NULL DEFAULT 0
);

-- Materialized co-occurrence (avoids a self-join on every get_tags at scale)
CREATE TABLE tag_cooccurrence (
  tag_a TEXT NOT NULL REFERENCES tags(name),
  tag_b TEXT NOT NULL REFERENCES tags(name),
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (tag_a, tag_b)
);

-- Reversible merges. Ships in v1 even though the merge job is v2.
CREATE TABLE tag_aliases (
  alias     TEXT PRIMARY KEY,
  canonical TEXT NOT NULL REFERENCES tags(name)
);

-- BM25: title, tags, and persisted content (catches exact identifiers)
CREATE VIRTUAL TABLE entries_fts USING fts5(
  id UNINDEXED,
  title,
  tags_text,        -- denormalized: "rust http async"
  content           -- present only for clip/conversation/note
);

-- Semantic search over the note
CREATE VIRTUAL TABLE entries_vec USING vec0(
  id        TEXT PRIMARY KEY,
  embedding FLOAT[768]
);

-- Semantic + dedup over tag descriptions (the tag embedding layer)
CREATE VIRTUAL TABLE tags_vec USING vec0(
  name      TEXT PRIMARY KEY,
  embedding FLOAT[768]              -- embedding of description, not the bare name
);
```

Counters are maintained on write: inserting an `entry_tags` row increments `tags.count` and every tag-pair in `tag_cooccurrence`; `delete` decrements both. A tag whose count hits zero is left in place - its description and vector stay useful for canonicalization.

### 9.3 The tag graph

Three relatedness signals make the graph navigable, and each catches what the others miss:

- **Embedding similarity** over tag descriptions - conceptually similar tags (`python` ≈ `programming`). Descriptions, not bare names, because a one-token name embeds generically and ambiguously; a stable description (`"Python programming language; backend, scripting, data work"`) embeds richly and disambiguates.
- **Co-occurrence** - empirically related in _this user's_ world (`flask` and `todo` aren't semantically similar but co-occur in their saves). This is the personal-ontology signal embeddings structurally miss.
- **Lexical / fuzzy** - morphological and spelling variants (`py`, `python3`) via FTS over tag names.

The graph emerges from usage: at 30 entries it's just filters; at thousands it's a traversable web the agent walks via `get_tags` then filtered `retrieve`.

**One discipline that makes the embedding layer pay off, not drift:** generate each tag's description once at creation and keep it stable - never regenerate on reuse, or you re-embed constantly and tags drift. And describe the _concept_, not the bookmark that happened to create the tag.

---

## 10. MCP Tools

The MCP server exposes five tools. All require a valid API Key or OAuth access token as a Bearer token.

`retrieve` and `list` are complementary read paths: `retrieve` ranks by relevance (hybrid BM25 + vector) and needs a query; `list` is a deterministic browse/filter (tag + date range, newest-first, paged) with no query and no relevance score — for "show me everything tagged X from last month" rather than "find the thing about Y".

### `save`

Upsert an entry. Deduplicates by normalized URL.

```json
{
  "url": "https://github.com/user/repo",
  "title": "string (optional - auto-fetched if omitted)",
  "tags": ["rust", "http"],
  "note": "optional override - skips LLM summarization if provided",
  "type": "page | clip | conversation | note"
}
```

- `tags` optional - if omitted, automatic tagging runs (§7.2). Agent-supplied tags are still normalized and canonicalized before write.
- `type: note` has no URL - no dedup; the `note` field is what the user typed, no summarization.
- If URL already exists (after normalization): merges tags (additive), updates note only if explicitly provided. Re-saving does not re-summarize or re-tag an already-active entry.
- If new: inserts with `status: pending`, triggers the async worker.
- Returns: `{id, status: "saved" | "updated"}`

### `retrieve`

Hybrid search: BM25 on title + tags + persisted content, vector on note, merged with RRF (see §11).

```json
{
  "query": "that rust http library from last month",
  "tags": ["rust"],
  "type": "page",
  "limit": 10
}
```

All filter fields optional. `tags` and `type` are applied as pre-filters before ranking. Results are compact - everything an agent needs in one call, so there is no separate `get` tool:

```json
[
  {
    "id": "abc123",
    "url": "https://...",
    "title": "hyper - fast HTTP for Rust",
    "tags": ["rust", "http", "async"],
    "note": "Fast async HTTP client for Rust; considered for the data ingestion service",
    "type": "page",
    "saved_at": "2026-05-20T14:23:00Z",
    "score": 0.91
  }
]
```

### `list`

Deterministic browse/filter — no search query, no relevance ranking. Filter by tag and/or a `saved_at` date range, ordered newest-first, paged. The complement to `retrieve`'s relevance search.

```json
{
  "tags": ["rust"],
  "saved_after": "2026-05-01T00:00:00Z",
  "saved_before": "2026-06-01T00:00:00Z",
  "limit": 20,
  "offset": 0
}
```

All fields optional. `tags` match **ANY** (union — an entry carrying any of them qualifies), deliberately unlike `retrieve`'s conjunctive (ALL) pre-filter, because `list` browses by topic. `saved_after` / `saved_before` are inclusive bounds on `saved_at`. Only `active` entries are returned (pending/failed aren't ready to surface; failures live in the §7.4 repair surface). With no filters it returns the most recent saves. Results use the same compact shape as `retrieve` minus `score`:

```json
[
  {
    "id": "abc123",
    "url": "https://...",
    "title": "hyper - fast HTTP for Rust",
    "tags": ["rust", "http", "async"],
    "note": "Fast async HTTP client for Rust",
    "type": "page",
    "saved_at": "2026-05-20T14:23:00Z"
  }
]
```

### `delete`

Remove an entry and all derived data (FTS row, entry vector, tag junction rows). Decrements tag counts and co-occurrence.

```json
{ "id": "abc123" }
```

Returns: `{deleted: true}`.

### `get_tags`

List tags with counts, co-occurrence, and description, so the agent can understand the landscape and pick tags to filter on in `retrieve`. Paged, because a heavy user has hundreds of tags.

```json
{ "limit": 50, "sort": "count" }
```

Both optional - default is top 50 by count. Response:

```json
[
  {
    "tag": "rust",
    "description": "Rust programming language; systems, async, CLI tooling",
    "count": 14,
    "co_occurs_with": ["http", "async", "wasm", "cli"]
  }
]
```

---

## 11. Search Strategy

```
Query: "rust http library"
         │
         ├─── BM25 ───────────────────────────────────────────────┐
         │    FTS5 on title + tags_text + content (when present)   │
         │    Catches exact terms vectors blur: library names,     │
         │    code identifiers, error strings, proper nouns        │
         │    → Result set A                                       │
         │                                                         │
         ├─── Vector ──────────────────────────────────────────────┤
         │    Embed query → search entries_vec (note embedding)    │
         │    Catches paraphrase: "http networking in rust"        │
         │    → Result set B                                       │
         │                                                         │
         └─── RRF merge ───────────────────────────────────────────┘
              RRF(A, B) = Σ 1/(k + rank_i),  k=60
              (tags/type applied as pre-filters)
              → Final ranked list
```

**Why this split:**

- BM25 wins on exact vocabulary: tags and identifiers like `rust`, `hyper`, `useEffect`, `SQLAlchemy` lexically match perfectly. Persisting content for clips/notes keeps those identifiers searchable instead of being smeared by the note summary.
- Vector wins on paraphrase: a query never matching the stored words still hits the right note.
- Neither alone is sufficient; together they cover each other's failure modes.

**Related-tag expansion (query → tags).** To widen a query, fuse the three signals from §9.3: embedding similarity (conceptual), co-occurrence (this user's associations), and lexical/fuzzy (variants). Embedding + co-occurrence is the strong pair; lexical mops up the edge cases.

**No in-server spreading activation.** The graph is navigated by the agent, not by a server-side activation engine. The agent calls `get_tags`, reasons about which tags to filter on, and issues one or more `retrieve` calls - smarter and steerable, with nothing to tune.

---

## 12. Auth Model

**Hybrid Auth: Personal Access Tokens + OAuth 2.1.**
Because many developer-centric MCP clients (Claude Code, Cursor, Claude Desktop) do not natively support browser redirect loops, OAuth discovery, or Dynamic Client Registration (DCR), Brain2 implements a hybrid approach:

1. **Personal Access Tokens (API Keys):** For terminal/desktop environments. The user signs in via the web dashboard and generates a long-lived token passed in the MCP connection headers.
2. **OAuth 2.1 + PKCE:** For web-based AI clients (ChatGPT Custom GPTs / Actions) and the Chrome Extension.
3. **MCP Authorization Discovery (RFC 9728 & RFC 8414):** For web-based AI clients that natively support automatic OAuth 2.1 discovery (such as Claude Web custom connectors). The server exposes Protected Resource Metadata and OAuth Authorization Server Metadata endpoints, combined with CORS support.

```
                  ┌──────────────────────────────────┐
                  │   Brain2 Web Dashboard & Server  │
                  │   /oauth/authorize               │
                  │   /oauth/token                   │
                  │   /settings/tokens (API Keys)    │
                  │   Login = "Sign in with Google"  │
                  └───────┬──────────────┬───────────┘
                          │              │
        CLI/Desktop ──────┘              └────── Web Clients / Ext
        (Claude Code, Cursor)                    (ChatGPT Actions,
        uses API Key Header                      Extension Popup via
        "Authorization: Bearer"                  OAuth 2.1 flow)
```

**CLI/Desktop MCP connection flow:**

```
1. User logs into https://brain2.app on a web browser.
2. User generates a Personal Access Token in developer settings.
3. User adds the server config to their local MCP client config:
   {
     "mcpServers": {
       "brain2": {
         "url": "https://api.brain2.app/connect/mcp",
         "headers": { "Authorization": "Bearer br2_live_..." }
       }
     }
   }
4. Every request is verified using the Bearer token mapped to the user's isolated DB.
```

**Web / Extension OAuth flow:**

```
1. User clicks "Sign in" in the Extension or triggers OAuth on a web client (e.g. Claude Web custom connector).
2. For web clients, the client automatically discovers the OAuth endpoints via standard metadata calls to `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server` or `/.well-known/openid-configuration` (facilitated by CORS exposing `WWW-Authenticate`).
3. Client redirects to Brain2 OAuth authorize endpoint → Google Login → Consent.
4. Redirect back with auth code → client exchanges it with PKCE for an access token.
```


**Token validation & DB routing:**

- Every API call (API Key or short-lived JWT) is authenticated.
- The backend resolves the credential to a unique `user_id`.
- The connection opens `/data/users/{user_id}.db`.
- Connections enforce **WAL mode** and are pooled/closed efficiently.

**First-time signup is implicit.** The first successful authentication (Google Sign-In or new API key) creates `/data/users/{user_id}.db` and runs the schema.

---

## 13. Success Criteria

**v1 succeeds when:**

1. The founder saves via the extension and recalls via Claude Code, daily, for two-plus consecutive weeks without abandoning it.
2. A paraphrased query ("that rust http thing") returns the right entry most of the time.
3. Saving takes under 2 seconds; summarization and tagging complete in the background without blocking.
4. Tags stay coherent: new saves reuse existing tags far more often than they invent near-duplicates. Fragmentation does not visibly grow with entry count.
5. A query for an exact identifier found in a saved highlight or note (e.g. `useEffect`) returns that entry.
6. Failed entries surface and get repaired - they don't silently accumulate as dead, unretrievable rows.
7. The MCP connection works (API key config for CLI/Desktop, OAuth for web clients).

**v1 fails when:**

- The store accumulates entries that are never recalled (Notion v2).
- Auto-generated notes are consistently wrong and no one edits them.
- The tag vocabulary fragments despite the write-time guards, and recall degrades as the store grows.
- Retrieval quality is weak enough that the founder falls back to manual search.

---

## 14. Build Sequence

The tag embedding layer and auto-tagging stack make this a larger v1 than a bare bookmark store - honestly, ~2 weeks to the dogfood gate, not one. The sequence front-loads a testable recall loop, then layers tag intelligence on top.

| Step | What                                                                                                                                                                                                                                                                                      | Time      |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| 1    | SQLite schema (entries, entry_tags, tags, tag_cooccurrence, tag_aliases, vec tables) + URL normalization + conditional content persistence + `POST /entries`                                                                                                                              | ~1 day    |
| 2    | FTS5 + BM25 over title + tags + content; MCP `save` + `retrieve` (keyword only); manually test recall                                                                                                                                                                                     | ~1 day    |
| 3    | Async summarization → `note` with OG/meta/title fallback ladder; test note quality and provenance across page types                                                                                                                                                                       | ~1 day    |
| 4    | Gemini embeddings: note vector + vector search + RRF merge; test paraphrased queries                                                                                                                                                                                                      | ~1 day    |
| 5    | Auto-tagging: structured-source extraction → embed basis → nearest-tag RAG → single LLM call → canonicalize-on-write → tag-description embedding → co-occurrence. The core of v1                                                                                                          | ~2-3 days |
| 6    | `delete` + `get_tags` (paged; counts, co-occurrence, descriptions); failure/retry + `PATCH /entries/{id}` repair endpoint                                                                                                                                                                 | ~1 day    |
| 7    | Auth: Google OAuth 2.1 (web/ext) + API Key gen + Bearer validation + dashboard with "needs attention" repair list; test against CLI/Desktop & web client                                                                                                                                  | ~1-2 days |
| 8    | Chrome extension: toolbar popup with three capture modes - save page (with chat-domain detection), element picker (DOM-granularity selection + Turndown HTML→Markdown + review), custom note; OAuth via `chrome.identity` + token refresh; "needs attention" badge. No keyboard shortcuts | ~2-3 days |
| 9    | **Two-week dogfood** - no Notion, no GitHub Stars, no bookmarks. Only Brain2. Log every friction point; track tag-reuse vs tag-invention and failure rate                                                                                                                                 | 2 weeks   |
| 10   | **Ship decision** - daily use holds and tags stay coherent? Open source, MCP registries, demo clip. Doesn't? You spent ~2 weeks, not 3 months                                                                                                                                             | —         |

v2 candidates already designed-for: web management app, offline tag-clustering/merge job (uses `tag_aliases`), chunk-level content embeddings, import, export.

---

## 15. Open Questions

| Question                                                                                                                                                                                       | Priority | Gate                                                         |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------ |
| Conversation content is persisted (URLs aren't externally re-fetchable). Is "Save page with chat-domain detection" the right capture path, or does conversation deserve its own explicit mode? | Medium   | Decide in step 8; start with auto-detection                  |
| Does discarding `page` body hurt exact-identifier recall on pages, given the agent can re-fetch the URL?                                                                                       | High     | Watch in dogfood (step 9); add page content only if it bites |
| `conversation`/`clip` content is persisted and NOT capped at capture (it isn't re-fetchable, §7.5), so a very long chat thread can hit the backend body-size limit and 422. Chunk, raise the cap, or truncate-with-marker?                                  | Medium   | Watch in dogfood (step 9); only act if a long thread is rejected |
| Element picker: is DOM expand/contract granularity enough, or do users still mis-grab blocks?                                                                                                  | Medium   | Observe in dogfood (step 9)                                  |
| Is the canonicalize threshold (~0.90) right, or does it over- or under-merge in practice?                                                                                                      | High     | Tune against real saves in step 5; start high                |
| Right tags-per-entry cap (3-5)?                                                                                                                                                                | Medium   | Observe in step 5                                            |
| How should the "needs attention" notification surface - badge only, or also a browser notification?                                                                                            | Medium   | Decide in step 7-8; start with in-app badge                  |
| Does note quality hold across page types (GitHub, Substack, docs), including OG-fallback cases?                                                                                                | High     | Answered in step 3                                           |
| Karakeep + its MCP server: is there a genuine gap?                                                                                                                                             | Medium   | Do before public ship                                        |
| Will developers pay for the hosted tier?                                                                                                                                                       | High     | Concierge test after 5 external users                        |
| Do hybrid auth methods work reliably on all MCP clients?                                                                                                                                       | High     | Test in step 7 against Claude Code, Cursor, ChatGPT          |

---

## 16. Distribution

The pain is invisible. The demo does the work:

> Ask Claude: _"What was that Rust HTTP library I starred a few weeks ago?"_
> It answers - with the note and the link.

**Channels (post-dogfood):**

- Open source on GitHub
- List in mcp.so, Glama, Awesome-MCP
- Post the demo clip on X (@jit_infinity), r/mcp, r/ClaudeAI, r/selfhosted
- Pocket-refugee threads in r/macapps still get comments - warm, free distribution

**Distribution does not start until the loop is good enough to show.**
