-- Migration 0007: command_audit — routing-decision log for the !-command layer (OM-4)
--
-- ONE append-only row per command routing decision, so we can MEASURE routing
-- reliability — model-mediated recognition (did Alaska decide to dispatch?) cannot
-- be unit-tested, so it must be observed in production. Two writers:
--   - a DETERMINISTIC insert inside lib/alaska_command_gateway/execute.route()
--     (every executor invocation → matched 'route' | 'unknown'), and
--   - a best-effort SKILL-emitted row via `python3 -m alaska_command_gateway.audit`
--     for the 'fallthrough' case the executor never sees (Alaska answered a
--     command-like message conversationally instead of routing).
-- See docs/platform/command-gateway.md → "Reliability & observability" and the 4-part
-- promotion bar in docs/superpowers/research/2026-06-05-command-routing-eval.md.
--
-- PRIVACY: raw_text holds the command text only (e.g. 'case 2762') — never a whole DM,
-- never PII. user-profile-360's redactor strips SSN/DOB/address upstream regardless.
--
-- Idempotent via CREATE IF NOT EXISTS. The migration runner applies it to BOTH
-- alaska.db and alaska_pmf.db; it is INERT on the PMF DB (nothing writes there).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS command_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  raw_text TEXT,                       -- command text only, e.g. 'case 2762'
  verb TEXT,                           -- matched/attempted verb (e.g. 'case', 'pmf') or NULL
  matched TEXT NOT NULL
    CHECK (matched IN ('route', 'unknown', 'fallthrough')),
  routed_target TEXT,                  -- skill/executor that handled it (NULL for unknown/fallthrough)
  ok INTEGER,                          -- 1 | 0 | NULL — executor success
  status TEXT,                         -- executor status (ok / not_found / handler_error / ...)
  invoker TEXT,                        -- Slack user id (best-effort)
  channel TEXT,                        -- Slack channel id (best-effort)
  channel_type TEXT,                   -- channel | dm | group
  gateway_version TEXT                 -- for cross-deploy comparison
);

CREATE INDEX IF NOT EXISTS idx_command_audit_created ON command_audit(created_at);
CREATE INDEX IF NOT EXISTS idx_command_audit_matched ON command_audit(matched, created_at);
