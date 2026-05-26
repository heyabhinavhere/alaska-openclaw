-- Migration 0002: add secondary_intents column to classifier_audit
-- Spec: docs/superpowers/specs/2026-05-23-alaska-task-model-design.md
-- Context: replay validation (May 18-24, 2026) found that single-label
-- classification systematically drops the "second" intent in common patterns:
--   - Standup messages ("today done X, tomorrow will do Y") drop the TASK_CREATE
--   - Audit follow-ups ("I audited N, team fix within 24h") drop one of TASK_UPDATE/TASK_ASSIGN
--   - Reminder + work requests ("build X and remind me on date Y") drop the TASK_CREATE
-- The fix: keep `intent` as the primary (drives Phase B+ handler routing) and
-- add a `secondary_intents` JSON-array column for any additional intents the
-- classifier detected. Sparingly populated — most messages remain single-intent.

PRAGMA foreign_keys = ON;

ALTER TABLE classifier_audit ADD COLUMN secondary_intents TEXT DEFAULT '[]';

-- No CHECK constraint on this column (it's a JSON array of strings, validated
-- at the application layer). Default '[]' (empty array as string) so existing
-- audit rows have a sensible value and downstream parsers don't crash on NULL.
