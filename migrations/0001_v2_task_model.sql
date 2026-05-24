-- Enable foreign key enforcement for this migration session.
-- Note: PRAGMA foreign_keys is per-connection in SQLite. Also set in
-- entrypoint.sh for the gateway init connection, and per-call in agents.
PRAGMA foreign_keys = ON;

-- Migration 0001: v2 task model schema
-- Spec: docs/superpowers/specs/2026-05-23-alaska-task-model-design.md
-- Creates tables for the new task system. Idempotent via CREATE IF NOT EXISTS.

-- ============================================================
-- 1. tasks — the primary task entity
-- ============================================================
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'blocked', 'pending_acceptance', 'done', 'dropped', 'snoozed')),
  priority TEXT
    CHECK (priority IS NULL OR priority IN ('P0', 'P1', 'P2', 'P3')),
  effort TEXT
    CHECK (effort IS NULL OR effort IN ('XS', 'S', 'M', 'L', 'XL')),
  owner_slack_id TEXT NOT NULL,
  additional_owners TEXT,
  creator_slack_id TEXT NOT NULL,
  assigner_slack_id TEXT,
  visibility TEXT NOT NULL DEFAULT 'personal'
    CHECK (visibility IN ('personal', 'team')),
  category TEXT,
  source TEXT NOT NULL
    CHECK (source IN ('meeting', 'slack_dm', 'slack_channel', 'standup_reply', 'manual')),
  source_ref TEXT,
  due_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  done_at DATETIME,
  parent_task_id TEXT REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_owner_status ON tasks(owner_slack_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON tasks(status, due_at);

-- Auto-update updated_at on every UPDATE so agents don't have to remember.
CREATE TRIGGER IF NOT EXISTS trg_tasks_updated_at
AFTER UPDATE ON tasks
FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at  -- only fire if caller didn't set it explicitly
BEGIN
  UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- 2. task_events — append-only audit log
-- ============================================================
CREATE TABLE IF NOT EXISTS task_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES tasks(task_id),
  event_type TEXT NOT NULL
    CHECK (event_type IN (
      'created', 'status_changed', 'owner_changed', 'due_changed',
      'priority_changed', 'ack', 'pass', 'reassigned', 'dedup_decision',
      'comment', 'mention', 'linked_to_blocker', 'scheduled_action_linked',
      'notion_synced', 'notion_drift_overwritten', 'retroactive_create',
      'matched', 'unknown_t_id_referenced', 'dispatcher_surfaced',
      'scheduled_action_fired'
    )),
  actor_slack_id TEXT,
  old_value TEXT,
  new_value TEXT,
  context TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, created_at);

-- ============================================================
-- 3. task_mentions — every reference to a task across any surface
-- ============================================================
CREATE TABLE IF NOT EXISTS task_mentions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES tasks(task_id),
  surface TEXT NOT NULL
    CHECK (surface IN ('meeting', 'slack_dm', 'slack_channel', 'standup_reply')),
  mention_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actor_slack_id TEXT,
  excerpt TEXT,
  source_ref TEXT,
  mention_type TEXT
    CHECK (mention_type IS NULL OR mention_type IN
           ('status_update', 'discussion', 'assignment', 'commitment', 'reference'))
);

CREATE INDEX IF NOT EXISTS idx_task_mentions_task ON task_mentions(task_id, mention_at);

-- ============================================================
-- 4. task_categories — lightweight grouping
-- ============================================================
CREATE TABLE IF NOT EXISTS task_categories (
  name TEXT PRIMARY KEY,
  description TEXT,
  active BOOLEAN NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed common categories from DAILY_STATE.md This Week's Goals patterns
INSERT OR IGNORE INTO task_categories (name, description) VALUES
  ('V2', 'V2 app build, testing, launch'),
  ('MoneyLine', 'MoneyLine partnership integration'),
  ('Marketing', 'Single-mom campaign, content, growth'),
  ('Infra', 'Platform, CI/CD, observability'),
  ('Card-Matching', 'Plaid integration, card linking, matching engine'),
  ('Customer-IO', 'Push notification + email delivery work'),
  ('Other', 'Catch-all for uncategorized work');

-- ============================================================
-- 5. blockers — extends existing pattern, links to tasks
-- ============================================================
CREATE TABLE IF NOT EXISTS blockers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  blocker_id TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  blocking_task_ids TEXT,
  owner_slack_id TEXT,
  raised_by_slack_id TEXT,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'resolved')),
  raised_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at DATETIME,
  resolution TEXT,
  source TEXT,
  source_ref TEXT
);

CREATE INDEX IF NOT EXISTS idx_blockers_status ON blockers(status, raised_at);

-- ============================================================
-- 6. scheduled_actions — reminders + recurring routines
-- ============================================================
CREATE TABLE IF NOT EXISTS scheduled_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action_id TEXT UNIQUE NOT NULL,
  action_type TEXT NOT NULL
    CHECK (action_type IN ('remind', 'surface_task', 'escalate',
                            'recurring_routine', 'auto_followup')),
  fire_at DATETIME NOT NULL,
  recurrence_rule TEXT,
  recipient_slack_id TEXT,
  recipient_channel_id TEXT,
  linked_task_id TEXT REFERENCES tasks(task_id),
  payload TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'personal'
    CHECK (scope IN ('personal', 'team')),
  created_by_slack_id TEXT NOT NULL,
  approved_by_slack_id TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'fired', 'cancelled', 'snoozed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  next_fire_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fired_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_scheduled_pending ON scheduled_actions(status, fire_at);

-- ============================================================
-- 7. routine_proposals — team-wide routines pending Abhinav approval
-- ============================================================
CREATE TABLE IF NOT EXISTS routine_proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proposal_id TEXT UNIQUE NOT NULL,
  proposed_by_slack_id TEXT NOT NULL,
  description TEXT NOT NULL,
  proposed_payload TEXT NOT NULL,
  proposed_recurrence_rule TEXT NOT NULL,
  proposed_recipient TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'declined', 'expired')),
  abhinav_response TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  responded_at DATETIME,
  expires_at DATETIME
);

-- ============================================================
-- 8. intent_inbox — Slack channel messages awaiting classification
-- ============================================================
CREATE TABLE IF NOT EXISTS intent_inbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_ts TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  author_slack_id TEXT NOT NULL,
  message_text TEXT NOT NULL,
  thread_ts TEXT,
  processed BOOLEAN NOT NULL DEFAULT 0,
  intent TEXT,
  confidence REAL,
  classifier_output TEXT,
  processed_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (channel_id, message_ts)
);

CREATE INDEX IF NOT EXISTS idx_intent_unprocessed ON intent_inbox(processed, created_at);

-- ============================================================
-- 9. classifier_audit — Phase A observation log (no action taken)
-- ============================================================
CREATE TABLE IF NOT EXISTS classifier_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inbox_id INTEGER REFERENCES intent_inbox(id),
  classified_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  intent TEXT NOT NULL,
  confidence REAL NOT NULL,
  entities TEXT,
  reasoning TEXT,
  would_have_done TEXT,
  abhinav_reviewed BOOLEAN NOT NULL DEFAULT 0,
  abhinav_verdict TEXT
);
