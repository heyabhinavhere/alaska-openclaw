-- Migration 0009: agent_memory.scope — the two-notebook partition.
--
--   scope='team'    : memory from/for team-facing work (Slack channels, teammates'
--                     DMs, team crons). Visible in coworker-mode sessions.
--   scope='builder' : Alaska-internals (system-health observations, self-maintenance,
--                     workshop notes about how Alaska herself works). Visible ONLY in
--                     workshop-mode sessions (the OpenClaw dashboard + system-health crons).
--
-- The mode rules — which notebook a session may read/write — live in
-- skills/agent-memory/SKILL.md (the sole reader/writer of this table). This migration
-- only adds the column + a covering index; it does not encode policy.
--
-- WHY a column and not a second table: the privacy guard (migration 0006) already keeps
-- team-facing readers out of agent_memory entirely. scope is the SECOND axis — within
-- Alaska's own store, it separates her team-facing memory from her self-referential
-- (builder) memory, so a coworker-mode recall can filter `scope='team'` and never
-- surface a workshop note.
--
-- SQLite note: ALTER TABLE ADD COLUMN supports a column-level CHECK together with
-- NOT NULL + a constant DEFAULT. Existing rows backfill to 'team' (which satisfies the
-- CHECK); the CHECK is then enforced on every future INSERT/UPDATE. (ADD COLUMN's
-- documented restrictions — no PRIMARY KEY/UNIQUE, no CURRENT_* or parenthesised
-- defaults — do not apply here.) Verified on the sqlite3 the container ships.
--
-- Idempotency: this file is NOT self-idempotent — re-running the ALTER errors with
-- "duplicate column name: scope". The migration runner's `_migrations` table is the
-- guard (it records 0009 as applied and never re-runs it). NEVER hand-apply this SQL
-- on a live DB — a manual second apply crash-loops the boot.
--
-- Dual-DB: like 0007, run_migrations.sh applies this to BOTH /data/queue/alaska.db and
-- /data/queue/alaska_pmf.db. agent_memory exists (empty) on the PMF DB via 0006, so the
-- ALTER is valid and inert there.
--
-- 0008 is person_status (merged via #156). A filename gap would be fine; there is none.

ALTER TABLE agent_memory ADD COLUMN scope TEXT NOT NULL DEFAULT 'team'
  CHECK (scope IN ('team', 'builder'));

-- Covering index for the coworker-mode hot path (recall/list filtered by scope).
CREATE INDEX IF NOT EXISTS idx_agent_memory_scope_kind_status
  ON agent_memory(scope, kind, status);
