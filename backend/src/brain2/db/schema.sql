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
  error_message TEXT
);

-- Dedup key + lookup index for URL-backed entries. Partial so the many
-- url=NULL notes never collide with each other (spec §7.1/§10).
CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_url ON entries(url) WHERE url IS NOT NULL;

-- Entry <-> tag edges (the bipartite graph)
CREATE TABLE IF NOT EXISTS entry_tags (
  entry_id TEXT REFERENCES entries(id) ON DELETE CASCADE,
  tag      TEXT NOT NULL REFERENCES tags(name),
  PRIMARY KEY (entry_id, tag)
);

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

-- Reversible merges. Ships in v1 even though the merge job is v2.
CREATE TABLE IF NOT EXISTS tag_aliases (
  alias     TEXT PRIMARY KEY,
  canonical TEXT NOT NULL REFERENCES tags(name)
);

-- BM25: title, tags, and persisted content (catches exact identifiers)
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
  id UNINDEXED,
  title,
  tags_text,        -- denormalized: "rust http async"
  content           -- present only for clip/conversation/note
);

-- Semantic search over the note
CREATE VIRTUAL TABLE IF NOT EXISTS entries_vec USING vec0(
  id        TEXT PRIMARY KEY,
  embedding FLOAT[768]
);

-- Semantic + dedup over tag descriptions (the tag embedding layer)
CREATE VIRTUAL TABLE IF NOT EXISTS tags_vec USING vec0(
  name      TEXT PRIMARY KEY,
  embedding FLOAT[768]              -- embedding of description, not the bare name
);
