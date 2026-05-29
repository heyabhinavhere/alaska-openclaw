-- Enable foreign key enforcement for this migration session.
-- Note: PRAGMA foreign_keys is per-connection in SQLite. Also set in
-- entrypoint.sh for the gateway init connection, and per-call in agents
-- (see shared-toolkit Section 1.5).
PRAGMA foreign_keys = ON;

-- Migration 0003: user-profile-360 cache + audit + identity-search storage
-- Backs the user-profile-360 skill (BON Credit user lookup via Sandeep's
-- /api/admin/users/{id}/profile endpoint). All tables are standalone — no
-- foreign keys outward, because user data lives in BON's backend, not here.
-- Idempotent via CREATE IF NOT EXISTS.

-- ============================================================
-- 1. user_profile_cache — per-section cache with TTL
-- ============================================================
-- One row per (user_id, section). The whole payload from the API is split
-- by section and stored row-by-row so we can cache cheap sections aggressively
-- and evict expensive ones (plaid_transactions.recent_200, chat.recent_turns)
-- on a shorter cycle.
--
-- data_json is nullable — empty sections (the API returns {} or [] for them)
-- are cached as NULL with payload_bytes=0, so we don't refetch them on next
-- ask. They're still "valid" cache entries.
--
-- api_response_user_id is a defense check: every fetch verifies the API's
-- top-level user_id equals what we asked for. Mismatch implies a routing bug
-- in the backend; we don't cache and we alert.
CREATE TABLE IF NOT EXISTS user_profile_cache (
  user_id INTEGER NOT NULL,
  section TEXT NOT NULL,
  data_json TEXT,
  fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  payload_bytes INTEGER NOT NULL DEFAULT 0,
  api_response_user_id INTEGER,
  PRIMARY KEY (user_id, section)
);
CREATE INDEX IF NOT EXISTS idx_upc_fetched ON user_profile_cache(fetched_at);
CREATE INDEX IF NOT EXISTS idx_upc_user ON user_profile_cache(user_id);

-- ============================================================
-- 2. user_profile_inflight — concurrent-fetch dedup
-- ============================================================
-- A short-lived "I'm fetching this right now" claim. Prevents two skills
-- (e.g. Thinker and slack-commands) from making the same 2-3s API call at
-- the same moment.
--
-- Pattern: claim via INSERT (PK conflict if another claim is open); release
-- by DELETE after cache write. Orphans older than 60s are reaped on entry.
CREATE TABLE IF NOT EXISTS user_profile_inflight (
  user_id INTEGER NOT NULL,
  section TEXT NOT NULL,
  claimed_by TEXT NOT NULL,
  claimed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, section)
);

-- ============================================================
-- 3. user_profile_access_log — PII access audit trail
-- ============================================================
-- Append-only. Every invocation of the user-profile-360 skill writes one row
-- here, including DENIED attempts (engineer trying to access, unknown caller,
-- wrong channel). Used for: anomaly detection, compliance audit, weekly digest.
--
-- requester_authority includes 'engineer' and 'unknown' specifically so
-- denied attempts are still loggable — denied access is itself signal.
--
-- outcome separates the "what happened" from "who asked":
--   granted          — call went through, data returned
--   denied_authority — caller's tier doesn't permit user lookups
--   denied_channel   — caller authorized but wrong surface (e.g. public ch.
--                      where we don't expose user PII even if allowed)
--   denied_unknown   — caller's Slack ID not in Team Roster
--   error            — API/cache/parse failure mid-call
CREATE TABLE IF NOT EXISTS user_profile_access_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  accessed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  user_id INTEGER NOT NULL,
  requester_slack_id TEXT NOT NULL,
  requester_authority TEXT NOT NULL
    CHECK (requester_authority IN ('admin', 'founder', 'engineer', 'system', 'unknown')),
  outcome TEXT NOT NULL DEFAULT 'granted'
    CHECK (outcome IN ('granted', 'denied_authority', 'denied_channel', 'denied_unknown', 'error')),
  invoking_skill TEXT NOT NULL,
  channel_id TEXT,
  channel_type TEXT
    CHECK (channel_type IS NULL OR channel_type IN ('dm', 'channel', 'cron', 'agent_signal')),
  sections_requested TEXT,
  cache_hits INTEGER NOT NULL DEFAULT 0,
  api_calls INTEGER NOT NULL DEFAULT 0,
  response_bytes INTEGER,
  intent_summary TEXT,
  redaction_tier TEXT
    CHECK (redaction_tier IS NULL OR redaction_tier IN ('full', 'minimal', 'medium'))
);
CREATE INDEX IF NOT EXISTS idx_upal_user ON user_profile_access_log(user_id, accessed_at);
CREATE INDEX IF NOT EXISTS idx_upal_requester ON user_profile_access_log(requester_slack_id, accessed_at);
CREATE INDEX IF NOT EXISTS idx_upal_outcome ON user_profile_access_log(outcome, accessed_at);

-- ============================================================
-- 4. user_profile_search_cache — identity-resolution cache
-- ============================================================
-- Caches search results for email / phone / name → user_id. Saves an extra
-- HTTP round-trip when the same identifier is looked up multiple times.
--
-- user_id is nullable so we can cache the negative result ("no user with
-- this email") for a short window — without it, every typo'd email triggers
-- another search call. Negative cache TTL is shorter (10 min) than positive
-- (24h) — enforced in the cache.py layer, not the schema.
CREATE TABLE IF NOT EXISTS user_profile_search_cache (
  query_type TEXT NOT NULL
    CHECK (query_type IN ('email', 'phone', 'name')),
  query_value TEXT NOT NULL,
  user_id INTEGER,
  cached_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (query_type, query_value)
);
CREATE INDEX IF NOT EXISTS idx_upsc_cached ON user_profile_search_cache(cached_at);
