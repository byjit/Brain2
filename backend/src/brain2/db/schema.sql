-- Brain2 per-user SQLite schema (spec §9.2).
-- Applied idempotently on first open of {user_id}.db.
-- FTS5 + sqlite-vec (vec0) live in the same file as the relational tables.

CREATE TABLE IF NOT EXISTS entries (
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
  -- ISO-8601 UTC time before which a retried (pending) entry must not be re-claimed.
  -- Enforces exponential backoff (spec §7.4); NULL means immediately claimable.
  next_retry_at TEXT,
  error_message TEXT,
  -- ISO-8601 UTC time this entry was last surfaced by the MCP retrieve tool's final
  -- hit set. NULL until first retrieved. Not touched by list/save; not exposed to agents.
  last_accessed_at TEXT
);

-- Dedup key + lookup index for URL-backed entries. Partial so the many
-- url=NULL notes never collide with each other (spec §7.1/§10).
CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_url ON entries(url) WHERE url IS NOT NULL;

-- Supports the `list` tool (spec §10): newest-first ordering + saved_at range scans.
-- Leads with status because list returns only active entries, then saved_at for the
-- ORDER BY / range bounds.
CREATE INDEX IF NOT EXISTS idx_entries_status_saved_at ON entries(status, saved_at DESC);

-- Supports the type pre-filter (services/prefilter.entry_ids_of_type), which otherwise
-- full-scans entries to resolve the allowed id set for the retrieve type filter.
CREATE INDEX IF NOT EXISTS idx_entries_type ON entries(type);

-- Entry <-> tag edges (the bipartite graph)
CREATE TABLE IF NOT EXISTS entry_tags (
  entry_id TEXT REFERENCES entries(id) ON DELETE CASCADE,
  tag      TEXT NOT NULL REFERENCES tags(name),
  PRIMARY KEY (entry_id, tag)
);

-- The PK is (entry_id, tag), so a tag-first lookup (the tag/type pre-filters in
-- services/prefilter.py and services/entries.list_entries) would full-scan the junction
-- table. This reverse index makes ``WHERE tag IN (...)`` an index range scan instead.
CREATE INDEX IF NOT EXISTS idx_entry_tags_tag ON entry_tags(tag);

-- Tag registry with stable concept descriptions
CREATE TABLE IF NOT EXISTS tags (
  name        TEXT PRIMARY KEY,
  description TEXT NOT NULL,         -- concept-level, generated once, stable
  count       INTEGER NOT NULL DEFAULT 0
);

-- Materialized co-occurrence (avoids a self-join on every get_tags at scale)
CREATE TABLE IF NOT EXISTS tag_cooccurrence (
  tag_a TEXT NOT NULL REFERENCES tags(name),
  tag_b TEXT NOT NULL REFERENCES tags(name),
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (tag_a, tag_b)
);

-- The PK is (tag_a, tag_b), so the reverse-direction lookup in tags_service._co_occurs_for
-- (``WHERE tag_b = ?``, used to make co-occurrence symmetric) cannot use the PK. This index
-- covers that leg so the batched get_tags co-occurrence query stays an index scan.
CREATE INDEX IF NOT EXISTS idx_tag_cooccurrence_tag_b ON tag_cooccurrence(tag_b);

-- Reversible merges. Ships in v1 even though the merge job is v2.
CREATE TABLE IF NOT EXISTS tag_aliases (
  alias     TEXT PRIMARY KEY,
  canonical TEXT NOT NULL REFERENCES tags(name)
);

-- BM25: title, tags, and persisted content (catches exact identifiers).
-- tokenize='trigram': 3-char substring matching across scripts so CJK content
-- (which unicode61 stores as one un-splittable token) is searchable by substring
-- (spec §15 CJK recall). Decided before rows accumulate, since changing the virtual
-- table after data exists requires a full index rebuild.
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
  id UNINDEXED,
  title,
  tags_text,        -- denormalized: "rust http async"
  content,          -- present only for clip/conversation/note
  tokenize = 'trigram'
);

-- Semantic search over the note. distance_metric=cosine so KNN ranks by semantic
-- direction (spec §11 "catches paraphrase", §7.2 cosine threshold) rather than the
-- default L2/Euclidean, which mis-ranks any un-normalized vector. Declared pre-data so
-- no migration is needed.
CREATE VIRTUAL TABLE IF NOT EXISTS entries_vec USING vec0(
  id        TEXT PRIMARY KEY,
  embedding FLOAT[768] distance_metric=cosine
);

-- Semantic + dedup over tag descriptions (the tag embedding layer).
-- distance_metric=cosine so the canonicalize snap (cosine >= 0.90, spec §7.2) and the
-- nearest-existing-tag KNN rank by semantic direction; similarity is then 1 - distance.
-- Declared pre-data so no migration is needed.
CREATE VIRTUAL TABLE IF NOT EXISTS tags_vec USING vec0(
  name      TEXT PRIMARY KEY,
  embedding FLOAT[768] distance_metric=cosine  -- embedding of description, not the bare name
);
