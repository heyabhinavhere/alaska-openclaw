-- audit_runs: one row per /audit invocation. Lives in its OWN database file
-- (alaska_audit.db) so it never touches the V4 task graph (alaska.db) or the
-- V5 PMF store (alaska_pmf.db). Applied idempotently by audit_agent.init_db.
CREATE TABLE IF NOT EXISTS audit_runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  audit_id        TEXT UNIQUE NOT NULL,
  user_id         INTEGER NOT NULL,
  status          TEXT NOT NULL,            -- success | validation_failed | render_error | fetch_error | failed
  persona         TEXT,
  lead_opportunity TEXT,
  data_available  TEXT,
  artifact_path   TEXT,
  error_reason    TEXT,
  invoked_by      TEXT,                      -- slack id of the team member who ran /audit
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_runs_user ON audit_runs (user_id);
