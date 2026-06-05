-- Central auth store (spec §12). Separate from per-user {user_id}.db files because a
-- credential must resolve to a user_id BEFORE any per-user DB can be opened.

-- One row per identity. user_id is a server-generated nanoid (never client-supplied),
-- so it is path-safe for {user_id}.db routing. google_sub is the stable Google subject.
CREATE TABLE IF NOT EXISTS users (
  user_id    TEXT PRIMARY KEY,
  google_sub TEXT UNIQUE,
  email      TEXT,
  created_at TEXT NOT NULL
);

-- Personal Access Tokens (API keys). Only the SHA-256 hash is stored (never the raw
-- key); `prefix` is a short non-secret display fragment for the dashboard listing.
CREATE TABLE IF NOT EXISTS api_keys (
  id           TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL REFERENCES users(user_id),
  token_hash   TEXT NOT NULL UNIQUE,
  prefix       TEXT NOT NULL,
  name         TEXT,
  created_at   TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);

-- Short-lived, single-use OAuth 2.1 authorization codes bound to a PKCE S256 challenge
-- and the client redirect_uri (spec §12). Consumed on /oauth/token; reuse is rejected.
CREATE TABLE IF NOT EXISTS oauth_codes (
  code                  TEXT PRIMARY KEY,
  user_id               TEXT NOT NULL REFERENCES users(user_id),
  code_challenge        TEXT NOT NULL,
  code_challenge_method TEXT NOT NULL,
  redirect_uri          TEXT NOT NULL,
  expires_at            TEXT NOT NULL,
  consumed_at           TEXT
);
