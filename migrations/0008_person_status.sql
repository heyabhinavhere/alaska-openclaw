-- Migration 0008: person_status — team availability the task graph can render.
--
-- Why: the Cutover parity check (2026-06-12) found a P0 gap — DAILY_STATE.md's
-- generated Per-Person sections had no concept of "Abhinav is traveling June
-- 8–12", so a traveling teammate looked available and working. Availability is
-- a person-level fact, not a task, so it gets its own tiny table.
--
-- Writers: slack-commands AVAILABILITY_UPDATE handler ("I'm traveling till
-- Monday" DM) and Meeting Intelligence (travel/leave heard on a call). One row
-- per person (UPSERT semantics — INSERT OR REPLACE); a row expires when
-- until_date passes (readers ignore expired rows; no deletion required).
-- Reader: lib/generate_daily_state.py renders one STATUS line per person.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS only; safe to re-run on every boot
-- (entrypoint runs all migrations on each deploy, on both DB files).

CREATE TABLE IF NOT EXISTS person_status (
  slack_id    TEXT PRIMARY KEY,            -- roster Slack ID (e.g. U07GKLVA9FE)
  status_text TEXT NOT NULL,               -- "Traveling, returns Monday" / "On leave"
  until_date  TEXT,                        -- ISO date the status expires (NULL = until replaced)
  set_by      TEXT,                        -- slack_id of who reported it (self, or MI from a call)
  updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
