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
-- client_id records which client the code was issued to (NULL for legacy rows); a token
-- request presenting a different client_id is rejected.
CREATE TABLE IF NOT EXISTS oauth_codes (
  code                  TEXT PRIMARY KEY,
  user_id               TEXT NOT NULL REFERENCES users(user_id),
  code_challenge        TEXT NOT NULL,
  code_challenge_method TEXT NOT NULL,
  redirect_uri          TEXT NOT NULL,
  client_id             TEXT,
  expires_at            TEXT NOT NULL,
  consumed_at           TEXT
);

-- Dynamically registered OAuth clients (RFC 7591) — public clients only. MCP clients
-- that support the MCP authorization flow (e.g. Claude web custom connectors) POST
-- their metadata to /oauth/register and get a client_id; their redirect_uris are then
-- matched EXACTLY at /oauth/authorize. No client secrets: possession is proven by PKCE.
CREATE TABLE IF NOT EXISTS oauth_clients (
  client_id     TEXT PRIMARY KEY,
  client_name   TEXT,
  redirect_uris TEXT NOT NULL,  -- JSON array of exact redirect URI strings
  created_at    TEXT NOT NULL
);

-- Long-lived OAuth refresh tokens, hashed at rest like API keys and ROTATED on every
-- use: consuming a token marks it rotated_at and issues a replacement, so a replayed
-- (stolen) refresh token is rejected. Lets MCP clients outlive the 1h access-token TTL
-- without interactive re-auth.
CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(user_id),
  client_id  TEXT,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  rotated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON oauth_refresh_tokens(user_id);
