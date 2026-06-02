-- Migration 0005: Alaska V5 PMF Cohort Operating System
--
-- Adds the durable operating layer for one active 3-day PMF signup cohort.
-- The schema is intentionally append/audit-heavy: derived PMF claims carry
-- evidence, freshness, confidence, and a claim state so Alaska can explain
-- every stage, queue, report, and recommendation.
--
-- Idempotent: CREATE IF NOT EXISTS + INSERT/UPDATE-safe triggers.

PRAGMA foreign_keys = ON;

-- ============================================================
-- 1. pmf_cohorts — one configurable 3-day signup cohort
-- ============================================================
CREATE TABLE IF NOT EXISTS pmf_cohorts (
  cohort_id            TEXT PRIMARY KEY,
  name                 TEXT NOT NULL,
  signup_window_start  DATETIME NOT NULL,
  signup_window_end    DATETIME NOT NULL,
  timezone             TEXT NOT NULL DEFAULT 'America/Los_Angeles',
  source_entry_event   TEXT NOT NULL DEFAULT 'phone_number_submitted',
  status               TEXT NOT NULL DEFAULT 'planned'
                       CHECK (status IN ('planned','active','completed','archived','cancelled')),
  expected_signups     INTEGER,
  expected_real_users  INTEGER,
  config_json          TEXT NOT NULL DEFAULT '{}',
  created_by           TEXT,
  created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  activated_at         DATETIME,
  completed_at         DATETIME,
  updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (julianday(signup_window_end) > julianday(signup_window_start))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pmf_one_active_cohort
  ON pmf_cohorts(status)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_pmf_cohorts_window
  ON pmf_cohorts(signup_window_start, signup_window_end);

CREATE TRIGGER IF NOT EXISTS trg_pmf_cohorts_updated_at
AFTER UPDATE ON pmf_cohorts
FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
  UPDATE pmf_cohorts SET updated_at = CURRENT_TIMESTAMP WHERE cohort_id = NEW.cohort_id;
END;

-- ============================================================
-- 2. pmf_cohort_users — living registry of all signup-window users
-- ============================================================
CREATE TABLE IF NOT EXISTS pmf_cohort_users (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  cohort_id                TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  user_key                 TEXT NOT NULL,
  bon_user_id              TEXT,
  amplitude_user_id        TEXT,
  customerio_id            TEXT,
  name                     TEXT,
  phone_number             TEXT,
  email                    TEXT,
  signup_event_time        DATETIME NOT NULL,
  signup_wave              TEXT,
  signup_status            TEXT NOT NULL DEFAULT 'signed_up'
                            CHECK (signup_status IN ('signed_up','duplicate','excluded','withdrawn')),
  onboarding_status        TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (onboarding_status IN ('unknown','not_started','in_progress','complete','failed')),
  furthest_onboarding_step TEXT,
  card_link_status         TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (card_link_status IN ('unknown','not_started','initiated','linked','failed')),
  bank_link_status         TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (bank_link_status IN ('unknown','not_started','initiated','linked','failed')),
  credit_score             INTEGER,
  is_real_user             INTEGER NOT NULL DEFAULT 0 CHECK (is_real_user IN (0,1)),
  real_user_confirmed_at   DATETIME,
  current_stage            TEXT NOT NULL DEFAULT 'signed_up'
                            CHECK (current_stage IN (
                              'signed_up','onboarded_real_user','activated_user',
                              'activated_saver','likely_lover','confirmed_lover'
                            )),
  highest_stage            TEXT NOT NULL DEFAULT 'signed_up'
                            CHECK (highest_stage IN (
                              'signed_up','onboarded_real_user','activated_user',
                              'activated_saver','likely_lover','confirmed_lover'
                            )),
  activated_saver_state    TEXT
                            CHECK (activated_saver_state IS NULL OR activated_saver_state IN ('computed','candidate')),
  current_health           TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (current_health IN ('unknown','healthy','watch','at_risk','stuck','lost')),
  flags_json               TEXT NOT NULL DEFAULT '[]',
  latest_snapshot_date     DATE,
  stage_updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  data_quality_state       TEXT NOT NULL DEFAULT 'missing'
                            CHECK (data_quality_state IN ('missing','stale','unavailable','false','confirmed')),
  evidence_json            TEXT NOT NULL DEFAULT '{}',
  created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (cohort_id, user_key)
);

CREATE INDEX IF NOT EXISTS idx_pmf_users_cohort_stage
  ON pmf_cohort_users(cohort_id, current_stage, current_health);

CREATE INDEX IF NOT EXISTS idx_pmf_users_real
  ON pmf_cohort_users(cohort_id, is_real_user, signup_event_time);

CREATE INDEX IF NOT EXISTS idx_pmf_users_bon_user
  ON pmf_cohort_users(bon_user_id)
  WHERE bon_user_id IS NOT NULL;

CREATE TRIGGER IF NOT EXISTS trg_pmf_users_updated_at
AFTER UPDATE ON pmf_cohort_users
FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
  UPDATE pmf_cohort_users SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- 3. pmf_signal_facts — normalized signal spine
-- ============================================================
CREATE TABLE IF NOT EXISTS pmf_signal_facts (
  fact_id          TEXT PRIMARY KEY,
  cohort_id        TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  user_key         TEXT NOT NULL,
  source_system    TEXT NOT NULL
                   CHECK (source_system IN ('amplitude','user_360','customerio','credgpt','alaska','manual')),
  source_event_name TEXT,
  source_ref       TEXT,
  observed_at      DATETIME,
  ingested_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fact_type        TEXT NOT NULL,
  fact_json        TEXT NOT NULL DEFAULT '{}',
  raw_json         TEXT,
  evidence_state   TEXT NOT NULL DEFAULT 'confirmed'
                   CHECK (evidence_state IN ('missing','stale','unavailable','false','confirmed')),
  freshness_state  TEXT NOT NULL DEFAULT 'confirmed'
                   CHECK (freshness_state IN ('missing','stale','unavailable','false','confirmed')),
  confidence       REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
  UNIQUE (cohort_id, source_system, source_ref)
);

CREATE INDEX IF NOT EXISTS idx_pmf_signal_user_time
  ON pmf_signal_facts(cohort_id, user_key, observed_at);

CREATE INDEX IF NOT EXISTS idx_pmf_signal_type
  ON pmf_signal_facts(cohort_id, fact_type, observed_at);

-- ============================================================
-- 4. pmf_claim_evidence — evidence for every derived claim
-- ============================================================
CREATE TABLE IF NOT EXISTS pmf_claim_evidence (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  cohort_id           TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  user_key            TEXT,
  entity_type         TEXT NOT NULL,
  entity_id           TEXT NOT NULL,
  claim_key           TEXT NOT NULL,
  source_system       TEXT NOT NULL
                      CHECK (source_system IN ('amplitude','user_360','customerio','credgpt','alaska','manual')),
  source_ref          TEXT,
  source_observed_at  DATETIME,
  ingested_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  freshness_state     TEXT NOT NULL
                      CHECK (freshness_state IN ('missing','stale','unavailable','false','confirmed')),
  evidence_state      TEXT NOT NULL
                      CHECK (evidence_state IN ('missing','stale','unavailable','false','confirmed')),
  confidence          REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  value_json          TEXT NOT NULL DEFAULT '{}',
  evidence_json       TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pmf_claim_entity
  ON pmf_claim_evidence(cohort_id, entity_type, entity_id, claim_key);

CREATE INDEX IF NOT EXISTS idx_pmf_claim_user
  ON pmf_claim_evidence(cohort_id, user_key, claim_key);

-- ============================================================
-- 5. pmf_user_daily_snapshots — daily per-user history
-- ============================================================
CREATE TABLE IF NOT EXISTS pmf_user_daily_snapshots (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  cohort_id             TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  user_key              TEXT NOT NULL,
  snapshot_date         DATE NOT NULL,
  generated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  funnel_stage          TEXT NOT NULL
                        CHECK (funnel_stage IN (
                          'signed_up','onboarded_real_user','activated_user',
                          'activated_saver','likely_lover','confirmed_lover'
                        )),
  activated_saver_state TEXT
                        CHECK (activated_saver_state IS NULL OR activated_saver_state IN ('computed','candidate')),
  health_state          TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (health_state IN ('unknown','healthy','watch','at_risk','stuck','lost')),
  normalized_facts_json TEXT NOT NULL DEFAULT '{}',
  profile_summary_json  TEXT NOT NULL DEFAULT '{}',
  engagement_json       TEXT NOT NULL DEFAULT '{}',
  pmf_metrics_json      TEXT NOT NULL DEFAULT '{}',
  flags_json            TEXT NOT NULL DEFAULT '[]',
  evidence_json         TEXT NOT NULL DEFAULT '{}',
  UNIQUE (cohort_id, user_key, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_pmf_snapshots_date
  ON pmf_user_daily_snapshots(cohort_id, snapshot_date);

-- ============================================================
-- 6. pmf_funnel_transitions — append-only movement audit
-- ============================================================
CREATE TABLE IF NOT EXISTS pmf_funnel_transitions (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  cohort_id             TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  user_key              TEXT NOT NULL,
  from_stage            TEXT,
  to_stage              TEXT NOT NULL
                        CHECK (to_stage IN (
                          'signed_up','onboarded_real_user','activated_user',
                          'activated_saver','likely_lover','confirmed_lover'
                        )),
  activated_saver_state TEXT
                        CHECK (activated_saver_state IS NULL OR activated_saver_state IN ('computed','candidate')),
  transition_type       TEXT NOT NULL DEFAULT 'recomputed'
                        CHECK (transition_type IN ('initial','promotion','demotion','recomputed','manual_override')),
  triggered_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  evidence_state        TEXT NOT NULL
                        CHECK (evidence_state IN ('missing','stale','unavailable','false','confirmed')),
  freshness_state       TEXT NOT NULL
                        CHECK (freshness_state IN ('missing','stale','unavailable','false','confirmed')),
  confidence            REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  evidence_json         TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_pmf_transitions_user
  ON pmf_funnel_transitions(cohort_id, user_key, triggered_at);

-- ============================================================
-- 7. pmf_user_case_files — current per-user operating file
-- ============================================================
CREATE TABLE IF NOT EXISTS pmf_user_case_files (
  cohort_id              TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  user_key               TEXT NOT NULL,
  case_file_version      INTEGER NOT NULL DEFAULT 1,
  privacy_tier           TEXT NOT NULL DEFAULT 'founder'
                         CHECK (privacy_tier IN ('team','founder','internal')),
  funnel_stage           TEXT NOT NULL
                         CHECK (funnel_stage IN (
                           'signed_up','onboarded_real_user','activated_user',
                           'activated_saver','likely_lover','confirmed_lover'
                         )),
  activated_saver_state  TEXT
                         CHECK (activated_saver_state IS NULL OR activated_saver_state IN ('computed','candidate')),
  case_file_json         TEXT NOT NULL DEFAULT '{}',
  flags_json             TEXT NOT NULL DEFAULT '[]',
  product_learning_tags  TEXT NOT NULL DEFAULT '[]',
  qualitative_notes      TEXT,
  evidence_json          TEXT NOT NULL DEFAULT '{}',
  generated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (cohort_id, user_key)
);

CREATE INDEX IF NOT EXISTS idx_pmf_case_stage
  ON pmf_user_case_files(cohort_id, funnel_stage);

CREATE TRIGGER IF NOT EXISTS trg_pmf_case_updated_at
AFTER UPDATE ON pmf_user_case_files
FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
  UPDATE pmf_user_case_files
  SET updated_at = CURRENT_TIMESTAMP, case_file_version = OLD.case_file_version + 1
  WHERE cohort_id = NEW.cohort_id AND user_key = NEW.user_key;
END;

-- ============================================================
-- 8. pmf_operating_queues — actionable operating queues
-- ============================================================
CREATE TABLE IF NOT EXISTS pmf_operating_queues (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  cohort_id       TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  user_key        TEXT,
  queue_type      TEXT NOT NULL
                  CHECK (queue_type IN (
                    'stuck_onboarding','spinwheel_stuck','plaid_failed','high_intent',
                    'at_risk','potential_lover','needs_human_review','weak_credgpt_response',
                    'repeated_product_model_issue_cluster'
                  )),
  severity        TEXT NOT NULL DEFAULT 'P2' CHECK (severity IN ('P0','P1','P2','P3')),
  status          TEXT NOT NULL DEFAULT 'open'
                  CHECK (status IN ('open','acknowledged','resolved','snoozed','dismissed')),
  intake_only     INTEGER NOT NULL DEFAULT 0 CHECK (intake_only IN (0,1)),
  title           TEXT NOT NULL,
  reason          TEXT,
  owner_slack_id  TEXT,
  source_ref      TEXT,
  evidence_state  TEXT NOT NULL DEFAULT 'confirmed'
                  CHECK (evidence_state IN ('missing','stale','unavailable','false','confirmed')),
  freshness_state TEXT NOT NULL DEFAULT 'confirmed'
                  CHECK (freshness_state IN ('missing','stale','unavailable','false','confirmed')),
  confidence      REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
  evidence_json   TEXT NOT NULL DEFAULT '{}',
  opened_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at     DATETIME
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pmf_one_open_queue_item
  ON pmf_operating_queues(cohort_id, user_key, queue_type)
  WHERE status IN ('open','acknowledged','snoozed');

CREATE INDEX IF NOT EXISTS idx_pmf_queues_open
  ON pmf_operating_queues(cohort_id, status, severity, queue_type);

CREATE TRIGGER IF NOT EXISTS trg_pmf_queues_updated_at
AFTER UPDATE ON pmf_operating_queues
FOR EACH ROW
WHEN OLD.updated_at = NEW.updated_at
BEGIN
  UPDATE pmf_operating_queues SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- 9. pmf_interventions — approved email/push actions and internal work
-- ============================================================
CREATE TABLE IF NOT EXISTS pmf_interventions (
  intervention_id        TEXT PRIMARY KEY,
  cohort_id              TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  user_key               TEXT,
  queue_id               INTEGER REFERENCES pmf_operating_queues(id),
  channel                TEXT NOT NULL
                         CHECK (channel IN ('email','push','in_app','slack','customerio_attribute','internal_task')),
  action_type            TEXT NOT NULL,
  draft_json             TEXT NOT NULL DEFAULT '{}',
  approval_status        TEXT NOT NULL DEFAULT 'draft'
                         CHECK (approval_status IN ('draft','needs_approval','approved','rejected','executed','cancelled','failed')),
  approved_by            TEXT,
  approved_at            DATETIME,
  dry_run_json           TEXT,
  audience_preview_json  TEXT,
  suppression_check_json TEXT,
  customerio_ref         TEXT,
  outcome_json           TEXT,
  created_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  executed_at            DATETIME,
  CHECK (channel != 'sms')
);

CREATE INDEX IF NOT EXISTS idx_pmf_interventions_cohort
  ON pmf_interventions(cohort_id, approval_status, channel);

-- ============================================================
-- 10. pmf_report_runs — artifact audit and delivery state
-- ============================================================
CREATE TABLE IF NOT EXISTS pmf_report_runs (
  report_id          TEXT PRIMARY KEY,
  cohort_id          TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  report_type        TEXT NOT NULL
                     CHECK (report_type IN (
                       'daily_cockpit','founder_daily','weekly_pmf','end_cohort',
                       'user_case_study','product_model_issue'
                     )),
  privacy_tier       TEXT NOT NULL CHECK (privacy_tier IN ('team','founder','internal')),
  snapshot_date      DATE,
  snapshot_json_path TEXT,
  html_path          TEXT,
  docx_path          TEXT,
  pdf_path           TEXT,
  qa_json            TEXT NOT NULL DEFAULT '{}',
  status             TEXT NOT NULL DEFAULT 'planned'
                     CHECK (status IN ('planned','rendered','qa_passed','delivered','failed')),
  slack_target       TEXT,
  file_refs_json     TEXT NOT NULL DEFAULT '[]',
  summary_json       TEXT NOT NULL DEFAULT '{}',
  generated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  delivered_at       DATETIME
);

CREATE INDEX IF NOT EXISTS idx_pmf_report_runs
  ON pmf_report_runs(cohort_id, report_type, privacy_tier, generated_at);

-- ============================================================
-- 11. credgpt_quality_reviews — per-turn response quality review
-- ============================================================
CREATE TABLE IF NOT EXISTS credgpt_quality_reviews (
  review_id                     TEXT PRIMARY KEY,
  cohort_id                     TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  user_key                      TEXT NOT NULL,
  thread_id                     TEXT,
  turn_id                       TEXT,
  event_time                    DATETIME,
  question                      TEXT,
  answer                        TEXT,
  deterministic_flags_json      TEXT NOT NULL DEFAULT '[]',
  rubric_scores_json            TEXT NOT NULL DEFAULT '{}',
  needs_llm_review              INTEGER NOT NULL DEFAULT 0 CHECK (needs_llm_review IN (0,1)),
  llm_review_status             TEXT NOT NULL DEFAULT 'not_needed'
                                CHECK (llm_review_status IN ('not_needed','pending','completed','skipped','failed')),
  llm_review_json               TEXT,
  quality_state                 TEXT NOT NULL DEFAULT 'unknown'
                                CHECK (quality_state IN ('unknown','ok','weak','unsafe','hallucination_risk','unavailable')),
  pmf_usefulness_score          REAL CHECK (pmf_usefulness_score IS NULL OR (pmf_usefulness_score >= 0 AND pmf_usefulness_score <= 1)),
  internal_recommendations_json TEXT NOT NULL DEFAULT '[]',
  source_json                   TEXT NOT NULL DEFAULT '{}',
  created_at                    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (cohort_id, user_key, thread_id, turn_id)
);

CREATE INDEX IF NOT EXISTS idx_credgpt_quality_user_time
  ON credgpt_quality_reviews(cohort_id, user_key, event_time);

CREATE INDEX IF NOT EXISTS idx_credgpt_quality_flags
  ON credgpt_quality_reviews(cohort_id, needs_llm_review, quality_state);

-- ============================================================
-- 12. credgpt_quality_clusters — recurring product/model issue clusters
-- ============================================================
CREATE TABLE IF NOT EXISTS credgpt_quality_clusters (
  cluster_id       TEXT PRIMARY KEY,
  cohort_id        TEXT NOT NULL REFERENCES pmf_cohorts(cohort_id) ON DELETE CASCADE,
  cluster_type     TEXT NOT NULL
                   CHECK (cluster_type IN (
                     'correctness','data_grounding','personalization','usefulness',
                     'clarity','empathy_trust','next_step_quality','unsafe_advice',
                     'hallucination_risk','pmf_usefulness','product_gap','instrumentation_gap'
                   )),
  title            TEXT NOT NULL,
  description      TEXT,
  severity         TEXT NOT NULL DEFAULT 'P2' CHECK (severity IN ('P0','P1','P2','P3')),
  status           TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','ignored')),
  review_ids_json  TEXT NOT NULL DEFAULT '[]',
  evidence_json    TEXT NOT NULL DEFAULT '{}',
  task_ref         TEXT,
  first_seen_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_credgpt_clusters_open
  ON credgpt_quality_clusters(cohort_id, status, severity, cluster_type);
