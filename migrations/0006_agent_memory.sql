-- Migration 0006: agent_memory — Alaska's private working memory
--
-- Self-tasks (her own to-dos) + notes/references she's asked to remember.
-- This is SEPARATE from the team task graph (tasks/blockers) and from the BON KB:
--   - KB (workspace/knowledge/, Abhinav-only) = curated, durable, team-canonical domain knowledge.
--   - task graph (tasks/blockers)             = team members' real work.
--   - agent_memory (this table)               = Alaska's lightweight, private, self-managed memory.
--
-- PRIVACY GUARD (the whole reason it's a separate table): team-facing readers
-- (Daily Pulse, Follow-Through, Risk Radar, slack-commands "what's X working on")
-- query tasks/blockers and NEVER query agent_memory — so a private self-task or note
-- can never leak into a team report. Safety by construction, not by remembering a filter.
--
-- Idempotent via CREATE IF NOT EXISTS.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS agent_memory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mem_id TEXT UNIQUE NOT NULL,                       -- 'M-N'
  kind TEXT NOT NULL
    CHECK (kind IN ('self_task', 'note', 'reference')),
  title TEXT NOT NULL,                               -- short label, e.g. "Chat/Agent CTA reference"
  content TEXT NOT NULL,                             -- the body: a reference table, a follow-up, an observation
  recall_cue TEXT,                                   -- keywords/tags for retrieval, e.g. 'CTA, chat, agent'
  status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'done', 'archived')),  -- self_task: open->done; note/reference: open/archived
  source TEXT,                                       -- 'self' | '<person> DM' | 'Abhinav' | 'channel:<id>'
  source_ref TEXT,                                   -- deterministic message ref if applicable
  due_at DATETIME,                                   -- optional; for a time-bound self_task
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_kind_status ON agent_memory(kind, status);
CREATE INDEX IF NOT EXISTS idx_agent_memory_recall ON agent_memory(recall_cue);

-- Auto-update updated_at on every UPDATE (mirrors migration 0001's tasks trigger),
-- so callers don't have to remember to set it.
CREATE TRIGGER IF NOT EXISTS trg_agent_memory_updated_at
AFTER UPDATE ON agent_memory
FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
  UPDATE agent_memory SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
