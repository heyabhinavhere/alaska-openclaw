-- Migration 0004: Watcher Gen 1 schema
-- Spec:  docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md (locked decisions #1-#16)
-- Plan:  docs/superpowers/plans/2026-05-27-alaska-watchers-v1.md (+ "Gen 1 — locked updates")
--
-- Adds the proactive-agency primitive: watchers + watcher_fires (audit) + event_pollers
-- (shared event-poll state). The Watcher = trigger + action_chain + recipient + memory +
-- approval, plus an autonomy_rung (Gen 1 uses 0/1; 2 is the Gen-2 "earned autonomy" baseline).
--
-- (0001/0002/0003 are taken — v2 task model / classifier secondary_intents /
--  user_profile_360. The runner globs lexically, so this 0004 applies after them.)
-- Idempotent: IF NOT EXISTS + INSERT OR IGNORE — safe to re-run.

PRAGMA foreign_keys = ON;

-- ============================================================
-- 1. watchers — the watcher primitive (one row per watcher)
-- ============================================================
CREATE TABLE IF NOT EXISTS watchers (
  -- Identity
  watcher_id           TEXT PRIMARY KEY,              -- W-1, W-2, ... (generated like T-N, shared-toolkit §1.7)
  description          TEXT NOT NULL,                 -- short NL summary for display

  -- Lifecycle
  created_by_slack_id  TEXT NOT NULL,
  created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_from_msg     TEXT,                          -- Slack permalink to the original request
  status               TEXT NOT NULL
                        -- Lifecycle: pending_approval (id reserved at draft; awaiting self/Abhinav confirm)
                        --   -> pending_cron_create (confirmed; cron registration in flight — write-ahead marker,
                        --      row exists with openclaw_cron_id NULL; janitor reconciles if stuck here)
                        --   -> active -> paused/expired ; or pending_approval -> cancelled (declined).
                        CHECK (status IN ('pending_approval','pending_cron_create','active','paused','expired','cancelled')),
  cost_class           TEXT NOT NULL
                        CHECK (cost_class IN ('free','low','medium','high')),
  approved_by_slack_id TEXT,                          -- NULL if self-approved
  approved_at          DATETIME,
  decline_reason       TEXT,                          -- populated if status='cancelled' via decline

  -- Trigger
  trigger_type         TEXT NOT NULL
                        CHECK (trigger_type IN ('cron','event')),
  trigger_config       TEXT NOT NULL,                 -- JSON: {expr,tz} (cron) or {event_name,filter} (event)

  -- Time bounds
  starts_at            DATETIME,                      -- NULL = immediately
  expires_at           DATETIME,                      -- NULL = forever

  -- Action
  action_chain         TEXT NOT NULL,                 -- JSON array of steps (load_knowledge/invoke_skill/format/...)
  recipient            TEXT NOT NULL,                 -- JSON: {type:'slack_dm'|'slack_channel'|'email', id:'...'}
  per_fire_approval    BOOLEAN NOT NULL DEFAULT 0,    -- 1 = pause each fire at draft_for_approval (Rung 0)
  per_fire_approver    TEXT,                          -- Slack ID (creator, per locked decision #14)
  autonomy_rung        INTEGER NOT NULL DEFAULT 1     -- Gen 1: 0 = draft-only (per_fire_approval ON),
                        CHECK (autonomy_rung IN (0,1,2)), --       1 = act-and-report (per_fire OFF, safe actions).
                                                       -- 2 = earned autonomy (graduation) — Gen 2 only; reject at
                                                       -- creation in Gen 1. Column exists now as the baseline.
  volume_cap           INTEGER,                       -- max items per fire (e.g. 50 users); NULL = no cap

  -- Memory (dedup so it doesn't repeat on the same fact)
  memory_strategy      TEXT NOT NULL DEFAULT 'none'
                        CHECK (memory_strategy IN ('none','strict_entity_set')),
  memory_state         TEXT,                          -- JSON: {last_fact_key, last_fired_at}
  cool_down_seconds    INTEGER NOT NULL DEFAULT 0,    -- minimum gap between fires

  -- Knowledge-base provenance (which KB files were used at creation)
  knowledge_sources    TEXT,                          -- JSON array of KB file paths

  -- Stats
  fire_count           INTEGER NOT NULL DEFAULT 0,
  last_fired_at        DATETIME,
  last_action_summary  TEXT,                          -- JSON of last fire's outcome

  -- OpenClaw integration
  openclaw_cron_id     TEXT,                          -- cron entry OpenClaw assigned (cron-type only; for lifecycle)
  stagger_seconds      INTEGER NOT NULL DEFAULT 0     -- random 0-300 offset to avoid thundering-herd at common times
);

CREATE INDEX IF NOT EXISTS idx_watchers_status_trigger ON watchers(status, trigger_type);
CREATE INDEX IF NOT EXISTS idx_watchers_created_by     ON watchers(created_by_slack_id);
CREATE INDEX IF NOT EXISTS idx_watchers_expires        ON watchers(expires_at)      WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_watchers_cron_lookup    ON watchers(openclaw_cron_id) WHERE openclaw_cron_id IS NOT NULL;

-- ============================================================
-- 2. watcher_fires — execution audit log (one row per fire)
-- ============================================================
CREATE TABLE IF NOT EXISTS watcher_fires (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  watcher_id      TEXT NOT NULL REFERENCES watchers(watcher_id),
  fired_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fact_key        TEXT,                               -- the fact that triggered this fire (memory dedup)
  outcome         TEXT NOT NULL
                  -- skipped_pending_approval: a rung-0 (per_fire_approval) watcher's cron fired again
                  -- while a prior fire's draft is still awaiting the creator's yes — don't double-prompt.
                  CHECK (outcome IN ('acted','skipped_memory','skipped_cooldown','skipped_empty',
                                     'skipped_pending_approval','failed','awaiting_approval',
                                     'approved','declined')),
  action_summary  TEXT,                               -- JSON of what was done
  error           TEXT                                -- populated if outcome='failed'
);

CREATE INDEX IF NOT EXISTS idx_watcher_fires_watcher ON watcher_fires(watcher_id, fired_at);

-- ============================================================
-- 3. event_pollers — shared poll state, one row per event type
--    (a single poller-cron per event type scans its source and
--     dispatches matching event-triggered watchers)
-- ============================================================
CREATE TABLE IF NOT EXISTS event_pollers (
  event_type      TEXT PRIMARY KEY,
  last_polled_at  DATETIME NOT NULL,
  last_run_count  INTEGER NOT NULL DEFAULT 0
);

-- Seed the Gen-1 event types (deploy_succeeded is added when Sandeep wires the deploy event source).
INSERT OR IGNORE INTO event_pollers (event_type, last_polled_at) VALUES
  ('new_signup',          CURRENT_TIMESTAMP),
  ('bug_closed',          CURRENT_TIMESTAMP),
  ('pr_merged',           CURRENT_TIMESTAMP),
  ('task_status_changed', CURRENT_TIMESTAMP);
