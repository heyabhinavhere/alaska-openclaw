"""SQLite store for Alaska V5 PMF Cohort OS."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .artifacts import (
    build_report_snapshot,
    qa_artifact,
    render_docx,
    render_html,
    render_pdf,
    write_docflow_spec,
    write_snapshot_json,
)
from .credgpt_quality import (
    cluster_reviews,
    default_judge_fn,
    escalated_quality_state,
    normalize_verdict,
    review_turn,
)
from .customerio_guard import CUSTOMERIO_MUTATION_CHANNELS, validate_customerio_action
from .docflow import build_docflow_spec
from .end_cohort import build_end_cohort_facts, generate_end_cohort_memo
from .funnel import evaluate_funnel
from .model import Evidence, higher_stage, minimize_secrets, now_utc


DEFAULT_DB_PATH = os.environ.get("PMF_DB_PATH", "/data/queue/alaska_pmf.db")
DEFAULT_ARTIFACT_ROOT = "/data/workspace/pmf_artifacts"


class PmfStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ------------------------------------------------------------------
    # Cohorts
    # ------------------------------------------------------------------
    def create_cohort(
        self,
        *,
        cohort_id: str,
        name: str,
        signup_window_start: str,
        signup_window_end: str,
        timezone_name: str = "America/Los_Angeles",
        expected_signups: int | None = None,
        expected_real_users: int | None = None,
        created_by: str | None = None,
        activate: bool = False,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start_dt = parse_dt(signup_window_start)
        end_dt = parse_dt(signup_window_end)
        if end_dt <= start_dt:
            raise ValueError("signup_window_end must be after signup_window_start")
        if end_dt - start_dt > timedelta(days=3, minutes=1):
            raise ValueError("V5 Phase 1 supports one signup window of at most 3 days")
        status = "active" if activate else "planned"
        activated_at = now_utc() if activate else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO pmf_cohorts (
                  cohort_id, name, signup_window_start, signup_window_end, timezone,
                  status, expected_signups, expected_real_users, config_json,
                  created_by, activated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cohort_id) DO UPDATE SET
                  name=excluded.name,
                  signup_window_start=excluded.signup_window_start,
                  signup_window_end=excluded.signup_window_end,
                  timezone=excluded.timezone,
                  status=excluded.status,
                  expected_signups=excluded.expected_signups,
                  expected_real_users=excluded.expected_real_users,
                  config_json=excluded.config_json,
                  created_by=COALESCE(excluded.created_by, pmf_cohorts.created_by),
                  activated_at=COALESCE(excluded.activated_at, pmf_cohorts.activated_at)
                """,
                (
                    cohort_id,
                    name,
                    dt_to_db(start_dt),
                    dt_to_db(end_dt),
                    timezone_name,
                    status,
                    expected_signups,
                    expected_real_users,
                    dumps(config or {}),
                    created_by,
                    activated_at,
                ),
            )
        return self.get_cohort(cohort_id)

    def activate_cohort(self, cohort_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                "UPDATE pmf_cohorts SET status='active', activated_at=COALESCE(activated_at, CURRENT_TIMESTAMP) WHERE cohort_id=?",
                (cohort_id,),
            )
        return self.get_cohort(cohort_id)

    def get_cohort(self, cohort_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM pmf_cohorts WHERE cohort_id=?", (cohort_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown PMF cohort: {cohort_id}")
        return dict(row)

    def active_cohort(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM pmf_cohorts WHERE status='active' ORDER BY activated_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def get_active_cohort_membership(self, bon_user_id: str | int) -> dict[str, Any] | None:
        """Cross-aware pointer support: is this BON user in the ACTIVE PMF cohort?

        Returns {cohort_id, current_stage, activated_saver_state} if the user is a
        registry member of the one active cohort, else None (no active cohort, or not
        a member). Read-only — used by the default user-intel path to append the
        '/pmf for the case file' pointer WITHOUT blending PMF data into the answer.
        """
        if bon_user_id in (None, ""):
            return None
        active = self.active_cohort()
        if not active:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT cohort_id, current_stage, activated_saver_state FROM pmf_cohort_users "
                "WHERE cohort_id=? AND bon_user_id=? LIMIT 1",
                (active["cohort_id"], str(bon_user_id)),
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Registry and signal spine
    # ------------------------------------------------------------------
    def upsert_signup_user(self, cohort_id: str, event: dict[str, Any]) -> dict[str, Any]:
        """Ingest the cohort entry event if it falls inside the signup window.

        Returns {status:"excluded"} for out-of-window or non-entry events and
        does not write a registry row in that case.
        """
        cohort = self.get_cohort(cohort_id)
        if not _is_entry_event(event, cohort.get("source_entry_event", "phone_number_submitted")):
            return {"status": "excluded", "reason": "not_cohort_entry_event"}
        observed_at = parse_dt(str(event.get("event_time") or event.get("observed_at") or event.get("time") or ""))
        start_dt = parse_dt(str(cohort["signup_window_start"]))
        end_dt = parse_dt(str(cohort["signup_window_end"]))
        if not (start_dt <= observed_at <= end_dt):
            return {"status": "excluded", "reason": "outside_signup_window", "observed_at": dt_to_db(observed_at)}

        user_key = user_key_from_event(event)
        bon_user_id = _string_or_none(event.get("bon_user_id") or event.get("user_id") or event.get("gp:user_id"))
        profile = event.get("user_properties") or {}
        name = _string_or_none(event.get("name") or profile.get("gp:first_name") or profile.get("first_name"))
        email = _string_or_none(event.get("email") or profile.get("gp:email"))
        phone = _string_or_none(event.get("phone_number") or event.get("phone") or profile.get("gp:phone_number"))
        amplitude_user_id = _string_or_none(event.get("amplitude_user_id") or event.get("amplitude_id"))
        customerio_id = _string_or_none(event.get("customerio_id") or bon_user_id)
        evidence = Evidence(
            "cohort_entry",
            source_system="amplitude",
            source_ref=_string_or_none(event.get("event_id") or event.get("insert_id") or event.get("source_ref")),
            observed_at=dt_to_db(observed_at),
            value={"event": cohort.get("source_entry_event"), "user_key": user_key},
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO pmf_cohort_users (
                  cohort_id, user_key, bon_user_id, amplitude_user_id, customerio_id,
                  name, phone_number, email, signup_event_time, signup_wave,
                  evidence_json, data_quality_state
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')
                ON CONFLICT(cohort_id, user_key) DO UPDATE SET
                  bon_user_id=COALESCE(excluded.bon_user_id, pmf_cohort_users.bon_user_id),
                  amplitude_user_id=COALESCE(excluded.amplitude_user_id, pmf_cohort_users.amplitude_user_id),
                  customerio_id=COALESCE(excluded.customerio_id, pmf_cohort_users.customerio_id),
                  name=COALESCE(excluded.name, pmf_cohort_users.name),
                  phone_number=COALESCE(excluded.phone_number, pmf_cohort_users.phone_number),
                  email=COALESCE(excluded.email, pmf_cohort_users.email),
                  signup_event_time=MIN(excluded.signup_event_time, pmf_cohort_users.signup_event_time),
                  evidence_json=excluded.evidence_json,
                  data_quality_state='confirmed'
                """,
                (
                    cohort_id,
                    user_key,
                    bon_user_id,
                    amplitude_user_id,
                    customerio_id,
                    name,
                    phone,
                    email,
                    dt_to_db(observed_at),
                    signup_wave(observed_at, start_dt, str(cohort.get("timezone") or "America/Los_Angeles")),
                    dumps({"cohort_entry": evidence.as_dict()}),
                ),
            )
            self._record_claim_evidence(conn, cohort_id, user_key, "pmf_cohort_user", user_key, evidence)
            self._record_signal_fact(
                conn,
                cohort_id,
                user_key,
                source_system="amplitude",
                source_event_name="onboarding_step_completed",
                source_ref=evidence.source_ref or stable_id("amp", cohort_id, user_key, dt_to_db(observed_at)),
                observed_at=dt_to_db(observed_at),
                fact_type="cohort_entry",
                fact_json=evidence.value,
                raw_json=event,
            )
        return {"status": "ingested", "cohort_id": cohort_id, "user_key": user_key}

    def ingest_signup_events(self, cohort_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        results = [self.upsert_signup_user(cohort_id, event) for event in events]
        excluded_by_reason: dict[str, int] = {}
        for result in results:
            if result.get("status") == "excluded":
                reason = result.get("reason") or "unknown"
                excluded_by_reason[reason] = excluded_by_reason.get(reason, 0) + 1
        return {
            "total_events": len(events),
            "ingested": sum(1 for item in results if item.get("status") == "ingested"),
            "excluded": sum(1 for item in results if item.get("status") == "excluded"),
            "excluded_by_reason": excluded_by_reason,
            "user_keys": [item["user_key"] for item in results if item.get("status") == "ingested"],
        }

    def update_user_profile(self, cohort_id: str, user_key: str, profile_facts: dict[str, Any]) -> dict[str, Any]:
        credit_score = _as_int(profile_facts.get("credit_score") or profile_facts.get("gp:credit_score"))
        onboarding_complete = bool(profile_facts.get("onboarding_complete"))
        if profile_facts.get("furthest_onboarding_step") == "onboarding_complete":
            onboarding_complete = True
        is_real_user = bool(onboarding_complete and credit_score and credit_score > 0)
        onboarding_status = "complete" if onboarding_complete else profile_facts.get("onboarding_status") or "in_progress"
        card_status = _link_status(profile_facts.get("card_link_status"), profile_facts.get("is_card_linked") or profile_facts.get("is_card_added"))
        bank_status = _link_status(profile_facts.get("bank_link_status"), profile_facts.get("is_bank_linked") or profile_facts.get("is_bank_added"))
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE pmf_cohort_users
                SET bon_user_id=COALESCE(?, bon_user_id),
                    name=COALESCE(?, name),
                    phone_number=COALESCE(?, phone_number),
                    email=COALESCE(?, email),
                    onboarding_status=?,
                    furthest_onboarding_step=COALESCE(?, furthest_onboarding_step),
                    card_link_status=?,
                    bank_link_status=?,
                    credit_score=COALESCE(?, credit_score),
                    is_real_user=?,
                    real_user_confirmed_at=CASE WHEN ? = 1 AND real_user_confirmed_at IS NULL THEN CURRENT_TIMESTAMP ELSE real_user_confirmed_at END,
                    data_quality_state='confirmed'
                WHERE cohort_id=? AND user_key=?
                """,
                (
                    _string_or_none(profile_facts.get("bon_user_id") or profile_facts.get("user_id")),
                    _string_or_none(profile_facts.get("name") or profile_facts.get("first_name")),
                    _string_or_none(profile_facts.get("phone_number")),
                    _string_or_none(profile_facts.get("email")),
                    onboarding_status,
                    _string_or_none(profile_facts.get("furthest_onboarding_step")),
                    card_status,
                    bank_status,
                    credit_score,
                    1 if is_real_user else 0,
                    1 if is_real_user else 0,
                    cohort_id,
                    user_key,
                ),
            )
            evidence = Evidence(
                "real_user",
                state="confirmed" if is_real_user else "false",
                source_system="user_360",
                source_ref=_string_or_none(profile_facts.get("source_ref")),
                value={"onboarding_complete": onboarding_complete, "credit_score": credit_score},
            )
            self._record_claim_evidence(conn, cohort_id, user_key, "pmf_cohort_user", user_key, evidence)
            self._record_signal_fact(
                conn,
                cohort_id,
                user_key,
                source_system="user_360",
                source_event_name="profile",
                source_ref=_string_or_none(profile_facts.get("source_ref")) or stable_id("u360", cohort_id, user_key, now_utc()),
                observed_at=_string_or_none(profile_facts.get("observed_at")) or now_utc(),
                fact_type="profile_snapshot",
                fact_json=profile_facts,
                raw_json=profile_facts,
            )
        return self.get_user(cohort_id, user_key)

    def get_user(self, cohort_id: str, user_key: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM pmf_cohort_users WHERE cohort_id=? AND user_key=?",
                (cohort_id, user_key),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown cohort user: {cohort_id}/{user_key}")
        return dict(row)

    def list_users(self, cohort_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pmf_cohort_users WHERE cohort_id=? ORDER BY signup_event_time, id",
                (cohort_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Daily snapshots, funnel, case files, queues
    # ------------------------------------------------------------------
    def apply_daily_snapshot(
        self,
        cohort_id: str,
        user_key: str,
        snapshot_date: str | date,
        facts: dict[str, Any],
    ) -> dict[str, Any]:
        user = self.get_user(cohort_id, user_key)
        facts = dict(facts)
        previous_facts = self.latest_snapshot_facts(cohort_id, user_key)
        facts = merge_cumulative_facts(previous_facts, facts)
        if "onboarding_complete" not in facts:
            facts["onboarding_complete"] = user.get("onboarding_status") == "complete" or bool(user.get("is_real_user"))
        if "credit_score" not in facts:
            facts["credit_score"] = user.get("credit_score")
        result = evaluate_funnel(facts, previous_highest_stage=user.get("highest_stage"))
        snapshot_date_s = snapshot_date.isoformat() if isinstance(snapshot_date, date) else str(snapshot_date)
        with self.connect() as conn:
            old_stage = user.get("current_stage")
            highest = higher_stage(user.get("highest_stage"), result.stage)
            conn.execute(
                """
                INSERT INTO pmf_user_daily_snapshots (
                  cohort_id, user_key, snapshot_date, funnel_stage, activated_saver_state,
                  health_state, normalized_facts_json, profile_summary_json, engagement_json,
                  pmf_metrics_json, flags_json, evidence_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cohort_id, user_key, snapshot_date) DO UPDATE SET
                  generated_at=CURRENT_TIMESTAMP,
                  funnel_stage=excluded.funnel_stage,
                  activated_saver_state=excluded.activated_saver_state,
                  health_state=excluded.health_state,
                  normalized_facts_json=excluded.normalized_facts_json,
                  profile_summary_json=excluded.profile_summary_json,
                  engagement_json=excluded.engagement_json,
                  pmf_metrics_json=excluded.pmf_metrics_json,
                  flags_json=excluded.flags_json,
                  evidence_json=excluded.evidence_json
                """,
                (
                    cohort_id,
                    user_key,
                    snapshot_date_s,
                    result.stage,
                    result.activated_saver_state,
                    result.health,
                    dumps(facts),
                    dumps(facts.get("profile_summary") or {}),
                    dumps(facts.get("engagement") or {}),
                    dumps(facts.get("pmf_success_metrics") or {}),
                    dumps(result.flags),
                    dumps([item.as_dict() for item in result.evidence]),
                ),
            )
            conn.execute(
                """
                UPDATE pmf_cohort_users
                SET current_stage=?, highest_stage=?, activated_saver_state=?,
                    current_health=?, flags_json=?, latest_snapshot_date=?,
                    stage_updated_at=CASE WHEN current_stage != ? THEN CURRENT_TIMESTAMP ELSE stage_updated_at END,
                    evidence_json=?
                WHERE cohort_id=? AND user_key=?
                """,
                (
                    result.stage,
                    highest,
                    result.activated_saver_state,
                    result.health,
                    dumps(result.flags),
                    snapshot_date_s,
                    result.stage,
                    dumps([item.as_dict() for item in result.evidence]),
                    cohort_id,
                    user_key,
                ),
            )
            transition_type = _transition_type(old_stage, result.stage)
            conn.execute(
                """
                INSERT INTO pmf_funnel_transitions (
                  cohort_id, user_key, from_stage, to_stage, activated_saver_state,
                  transition_type, evidence_state, freshness_state, confidence, evidence_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cohort_id,
                    user_key,
                    old_stage,
                    result.stage,
                    result.activated_saver_state,
                    transition_type,
                    "confirmed" if result.confidence >= 0.8 else "stale",
                    "confirmed",
                    result.confidence,
                    dumps([item.as_dict() for item in result.evidence]),
                ),
            )
            for evidence in result.evidence:
                self._record_claim_evidence(conn, cohort_id, user_key, "pmf_funnel_stage", user_key, evidence)
            for queue in result.queues:
                self._upsert_queue(conn, cohort_id, user_key, queue)
            if result.health != "at_risk":
                self._resolve_queue_if_open(conn, cohort_id, user_key, "at_risk")
            case_file = build_case_file(user, facts, result.as_dict())
            conn.execute(
                """
                INSERT INTO pmf_user_case_files (
                  cohort_id, user_key, privacy_tier, funnel_stage, activated_saver_state,
                  case_file_json, flags_json, product_learning_tags, evidence_json
                )
                VALUES (?, ?, 'founder', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cohort_id, user_key) DO UPDATE SET
                  funnel_stage=excluded.funnel_stage,
                  activated_saver_state=excluded.activated_saver_state,
                  case_file_json=excluded.case_file_json,
                  flags_json=excluded.flags_json,
                  product_learning_tags=excluded.product_learning_tags,
                  evidence_json=excluded.evidence_json,
                  generated_at=CURRENT_TIMESTAMP
                """,
                (
                    cohort_id,
                    user_key,
                    result.stage,
                    result.activated_saver_state,
                    dumps(case_file),
                    dumps(result.flags),
                    dumps(facts.get("product_learning_tags") or []),
                    dumps([item.as_dict() for item in result.evidence]),
                ),
            )
        return result.as_dict()

    def latest_snapshot_facts(self, cohort_id: str, user_key: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT normalized_facts_json
                FROM pmf_user_daily_snapshots
                WHERE cohort_id=? AND user_key=?
                ORDER BY snapshot_date DESC, generated_at DESC
                LIMIT 1
                """,
                (cohort_id, user_key),
            ).fetchone()
        if row is None:
            return {}
        return loads(row["normalized_facts_json"], {})

    def open_queue_items(self, cohort_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM pmf_operating_queues
                WHERE cohort_id=? AND status IN ('open','acknowledged','snoozed')
                ORDER BY severity, opened_at
                """,
                (cohort_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # CredGPT Quality Observatory
    # ------------------------------------------------------------------
    def record_credgpt_turn(self, cohort_id: str, user_key: str, turn: dict[str, Any]) -> dict[str, Any]:
        payload = {"cohort_id": cohort_id, "user_key": user_key, **turn}
        review = review_turn(payload)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO credgpt_quality_reviews (
                  review_id, cohort_id, user_key, thread_id, turn_id, event_time,
                  question, answer, deterministic_flags_json, rubric_scores_json,
                  needs_llm_review, llm_review_status, quality_state,
                  pmf_usefulness_score, internal_recommendations_json, source_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cohort_id, user_key, thread_id, turn_id) DO UPDATE SET
                  question=excluded.question,
                  answer=excluded.answer,
                  deterministic_flags_json=excluded.deterministic_flags_json,
                  rubric_scores_json=excluded.rubric_scores_json,
                  needs_llm_review=excluded.needs_llm_review,
                  llm_review_status=excluded.llm_review_status,
                  quality_state=excluded.quality_state,
                  pmf_usefulness_score=excluded.pmf_usefulness_score,
                  internal_recommendations_json=excluded.internal_recommendations_json,
                  source_json=excluded.source_json
                """,
                (
                    review.review_id,
                    cohort_id,
                    user_key,
                    _string_or_none(turn.get("thread_id")),
                    _string_or_none(turn.get("turn_id")),
                    _string_or_none(turn.get("event_time") or turn.get("created_at")),
                    _string_or_none(turn.get("question")),
                    _string_or_none(turn.get("answer")),
                    dumps(review.deterministic_flags),
                    dumps(review.rubric_scores),
                    1 if review.needs_llm_review else 0,
                    review.llm_review_status,
                    review.quality_state,
                    review.pmf_usefulness_score,
                    dumps(review.internal_recommendations),
                    dumps(turn),
                ),
            )
            if review.quality_state != "ok":
                self._upsert_queue(
                    conn,
                    cohort_id,
                    user_key,
                    {
                        "queue_type": "weak_credgpt_response",
                        "title": "Weak CredGPT response needs review",
                        "reason": "CredGPT Quality Observatory flagged this turn for internal product/model work.",
                        "severity": "P1" if review.quality_state in {"unsafe", "hallucination_risk"} else "P2",
                        "intake_only": False,
                        "evidence": review.as_dict(),
                    },
                )
        return review.as_dict()

    def refresh_credgpt_clusters(self, cohort_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT review_id, deterministic_flags_json, quality_state
                FROM credgpt_quality_reviews
                WHERE cohort_id=? AND quality_state != 'ok'
                """,
                (cohort_id,),
            ).fetchall()
            reviews = []
            for row in rows:
                item = dict(row)
                item["deterministic_flags"] = loads(item.pop("deterministic_flags_json"), [])
                reviews.append(item)
            clusters = cluster_reviews(reviews)
            for cluster in clusters:
                cluster["cluster_id"] = stable_id("cqcl", cohort_id, cluster["cluster_type"])
                existing = conn.execute(
                    "SELECT status FROM credgpt_quality_clusters WHERE cluster_id=?",
                    (cluster["cluster_id"],),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO credgpt_quality_clusters (
                      cluster_id, cohort_id, cluster_type, title, description,
                      severity, review_ids_json, evidence_json, last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(cluster_id) DO UPDATE SET
                      description=excluded.description,
                      severity=excluded.severity,
                      review_ids_json=excluded.review_ids_json,
                      evidence_json=excluded.evidence_json,
                      last_seen_at=CURRENT_TIMESTAMP
                    """,
                    (
                        cluster["cluster_id"],
                        cohort_id,
                        cluster["cluster_type"],
                        cluster["title"],
                        cluster["description"],
                        cluster["severity"],
                        dumps(cluster["review_ids"]),
                        dumps(cluster["evidence"]),
                    ),
                )
                cluster_status = existing["status"] if existing else "open"
                if cluster_status == "open":
                    self._upsert_queue(
                        conn,
                        cohort_id,
                        f"cluster:{cluster['cluster_type']}",
                        {
                            "queue_type": "repeated_product_model_issue_cluster",
                            "title": cluster["title"],
                            "reason": cluster["description"],
                            "severity": cluster["severity"],
                            "intake_only": False,
                            "evidence": cluster,
                        },
                    )
                else:
                    self._resolve_queue_if_open(
                        conn,
                        cohort_id,
                        f"cluster:{cluster['cluster_type']}",
                        "repeated_product_model_issue_cluster",
                        status="dismissed" if cluster_status == "ignored" else "resolved",
                    )
        return clusters

    def judge_pending_credgpt_reviews(
        self,
        cohort_id: str,
        *,
        judge_fn: Any = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Run the LLM quality/safety judge on deterministically-flagged turns.

        Selects reviews WHERE needs_llm_review=1 AND llm_review_status='pending' and
        runs `judge_fn` (injectable; defaults to the live Anthropic adapter when
        ANTHROPIC_API_KEY is set, else None). With no judge available every pending
        review is marked 'skipped' — never a false 'completed'. The verdict is stored
        in llm_review_json; quality_state is only ever ESCALATED, never cleared.
        """
        result = {"pending": 0, "completed": 0, "skipped": 0, "failed": 0}
        resolved = judge_fn if judge_fn is not None else default_judge_fn()
        with self.connect() as conn:
            sql = (
                "SELECT review_id, question, answer, deterministic_flags_json, "
                "rubric_scores_json, quality_state FROM credgpt_quality_reviews "
                "WHERE cohort_id=? AND needs_llm_review=1 AND llm_review_status='pending' "
                "ORDER BY event_time"
            )
            params: tuple = (cohort_id,)
            if limit:
                sql += " LIMIT ?"
                params = (cohort_id, int(limit))
            rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
            result["pending"] = len(rows)
            for row in rows:
                review_id = row["review_id"]
                if resolved is None:
                    self._write_llm_review(conn, review_id, "skipped", {"reason": "no_judge_available"})
                    result["skipped"] += 1
                    continue
                payload = {
                    "review_id": review_id,
                    "question": row.get("question"),
                    "answer": row.get("answer"),
                    "deterministic_flags": loads(row.get("deterministic_flags_json"), []),
                    "rubric_scores": loads(row.get("rubric_scores_json"), {}),
                }
                try:
                    verdict = normalize_verdict(resolved(payload))
                except Exception as exc:  # noqa: BLE001 - one turn never sinks the batch
                    self._write_llm_review(conn, review_id, "failed", {"error": str(exc)})
                    result["failed"] += 1
                    continue
                new_state = escalated_quality_state(row.get("quality_state"), verdict.get("quality_state"))
                self._write_llm_review(
                    conn, review_id, "completed", verdict,
                    quality_state=new_state, pmf_usefulness=verdict.get("pmf_usefulness_score"),
                )
                result["completed"] += 1
        return result

    def _write_llm_review(
        self,
        conn: sqlite3.Connection,
        review_id: str,
        status: str,
        verdict: dict[str, Any],
        *,
        quality_state: str | None = None,
        pmf_usefulness: float | None = None,
    ) -> None:
        sets = ["llm_review_status=?", "llm_review_json=?"]
        params: list[Any] = [status, dumps(verdict)]
        if quality_state:
            sets.append("quality_state=?")
            params.append(quality_state)
        if pmf_usefulness is not None:
            sets.append("pmf_usefulness_score=?")
            params.append(pmf_usefulness)
        params.append(review_id)
        conn.execute(f"UPDATE credgpt_quality_reviews SET {', '.join(sets)} WHERE review_id=?", params)

    # ----- Customer.io interventions (P6: gated, human-approved, outcome-tracked) -----

    def draft_intervention(self, cohort_id: str, intervention: dict[str, Any]) -> dict[str, Any]:
        """Persist a drafted intervention (never sends). Mutation channels
        (email/push/customerio_attribute) start in 'needs_approval'; others 'draft'.
        Stores the dry-run/audience/suppression previews the guard requires later."""
        self.get_cohort(cohort_id)  # validates the cohort exists
        channel = intervention.get("channel")
        if channel == "sms":
            raise ValueError("SMS interventions are blocked (A2P not approved).")
        intervention_id = intervention.get("intervention_id") or stable_id(
            "pmfint", cohort_id, str(intervention.get("user_key") or ""),
            str(intervention.get("action_type") or ""), now_utc(), os.urandom(6).hex(),
        )
        status = "needs_approval" if channel in CUSTOMERIO_MUTATION_CHANNELS else "draft"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO pmf_interventions (
                  intervention_id, cohort_id, user_key, queue_id, channel, action_type,
                  draft_json, approval_status, dry_run_json, audience_preview_json, suppression_check_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(intervention_id) DO UPDATE SET
                  draft_json=excluded.draft_json,
                  dry_run_json=excluded.dry_run_json,
                  audience_preview_json=excluded.audience_preview_json,
                  suppression_check_json=excluded.suppression_check_json
                """,
                (
                    intervention_id, cohort_id, _string_or_none(intervention.get("user_key")),
                    intervention.get("queue_id"), channel, str(intervention.get("action_type") or "intervention"),
                    dumps(intervention.get("draft") or intervention.get("draft_json") or {}),
                    status,
                    dumps(intervention.get("dry_run")) if intervention.get("dry_run") is not None else None,
                    dumps(intervention.get("audience_preview")) if intervention.get("audience_preview") is not None else None,
                    dumps(intervention.get("suppression_check")) if intervention.get("suppression_check") is not None else None,
                ),
            )
        return self.get_intervention(cohort_id, intervention_id)

    def get_intervention(self, cohort_id: str, intervention_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM pmf_interventions WHERE cohort_id=? AND intervention_id=?",
                (cohort_id, intervention_id),
            ).fetchone()
        if not row:
            raise KeyError(f"intervention {intervention_id} not found in cohort {cohort_id}")
        return self._intervention_row(row)

    def approve_intervention(self, cohort_id: str, intervention_id: str, approved_by: str) -> dict[str, Any]:
        """Human approval gate — sets approved_by/approved_at and status='approved'."""
        if not approved_by:
            raise ValueError("approved_by is required to approve an intervention.")
        current = self.get_intervention(cohort_id, intervention_id)
        if current["approval_status"] in {"executed", "cancelled"}:
            raise ValueError(f"cannot approve an intervention in state {current['approval_status']}")
        with self.connect() as conn:
            conn.execute(
                "UPDATE pmf_interventions SET approval_status='approved', approved_by=?, approved_at=? "
                "WHERE cohort_id=? AND intervention_id=?",
                (approved_by, now_utc(), cohort_id, intervention_id),
            )
        return self.get_intervention(cohort_id, intervention_id)

    def reject_intervention(self, cohort_id: str, intervention_id: str, approved_by: str, reason: str | None = None) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                "UPDATE pmf_interventions SET approval_status='rejected', approved_by=?, approved_at=?, outcome_json=? "
                "WHERE cohort_id=? AND intervention_id=?",
                (approved_by, now_utc(), dumps({"rejected_reason": reason}), cohort_id, intervention_id),
            )
        return self.get_intervention(cohort_id, intervention_id)

    def execute_intervention(
        self,
        cohort_id: str,
        intervention_id: str,
        *,
        cio_executor: Any = None,
        customerio_ref: str | None = None,
    ) -> dict[str, Any]:
        """Execute an APPROVED intervention. Re-validates via the safety guard and
        refuses anything not approved or not passing it. Sends only through the
        injected `cio_executor` (or records a human/skill-provided `customerio_ref`).
        With neither, nothing is sent — returns {'status': 'no_executor'}."""
        current = self.get_intervention(cohort_id, intervention_id)
        if current["approval_status"] != "approved":
            return {"status": "blocked", "reason": f"not_approved (state={current['approval_status']})", "intervention": current}
        decision = validate_customerio_action(self._intervention_action(current))
        if not decision.allowed:
            return {"status": "blocked", "reason": "guard_rejected", "decision": decision.as_dict(), "intervention": current}
        if cio_executor is not None:
            try:
                result = cio_executor(self._intervention_action(current)) or {}
                customerio_ref = result.get("customerio_ref") or result.get("delivery_id") or customerio_ref
            except Exception as exc:  # noqa: BLE001 - a send failure is recorded, not raised
                with self.connect() as conn:
                    conn.execute(
                        "UPDATE pmf_interventions SET approval_status='failed', outcome_json=? "
                        "WHERE cohort_id=? AND intervention_id=?",
                        (dumps({"error": str(exc)}), cohort_id, intervention_id),
                    )
                return {"status": "failed", "error": str(exc), "intervention": self.get_intervention(cohort_id, intervention_id)}
        elif customerio_ref is None:
            return {"status": "no_executor", "reason": "no cio_executor and no customerio_ref; nothing sent", "intervention": current}
        with self.connect() as conn:
            conn.execute(
                "UPDATE pmf_interventions SET approval_status='executed', executed_at=?, customerio_ref=? "
                "WHERE cohort_id=? AND intervention_id=?",
                (now_utc(), _string_or_none(customerio_ref), cohort_id, intervention_id),
            )
        return {"status": "executed", "customerio_ref": customerio_ref, "intervention": self.get_intervention(cohort_id, intervention_id)}

    def record_intervention_outcome(self, cohort_id: str, intervention_id: str, outcome: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                "UPDATE pmf_interventions SET outcome_json=? WHERE cohort_id=? AND intervention_id=?",
                (dumps(outcome), cohort_id, intervention_id),
            )
        return self.get_intervention(cohort_id, intervention_id)

    def list_interventions(self, cohort_id: str, *, approval_status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM pmf_interventions WHERE cohort_id=?"
        params: list[Any] = [cohort_id]
        if approval_status:
            sql += " AND approval_status=?"
            params.append(approval_status)
        sql += " ORDER BY created_at"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._intervention_row(row) for row in rows]

    def _intervention_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key in ("draft_json", "dry_run_json", "audience_preview_json", "suppression_check_json", "outcome_json"):
            if key in item:
                item[key[: -len("_json")]] = loads(item.pop(key), None)
        return item

    def _intervention_action(self, row: dict[str, Any]) -> dict[str, Any]:
        """Build the customerio_guard action dict from a stored intervention row."""
        draft = row.get("draft") if isinstance(row.get("draft"), dict) else {}
        return {
            "channel": row.get("channel"),
            "action_type": row.get("action_type"),
            "cohort_id": row.get("cohort_id"),
            "approved_by": row.get("approved_by"),
            "draft": row.get("draft"),
            "dry_run": row.get("dry_run"),
            "audience_preview": row.get("audience_preview"),
            "suppression_check": row.get("suppression_check"),
            "frequency_cap_checked": draft.get("frequency_cap_checked"),
        }

    # ------------------------------------------------------------------
    # Reports and artifacts
    # ------------------------------------------------------------------
    def generate_report_snapshot(
        self,
        cohort_id: str,
        *,
        report_type: str = "daily_cockpit",
        privacy_tier: str = "team",
        snapshot_date: str | None = None,
    ) -> dict[str, Any]:
        cohort = self.get_cohort(cohort_id)
        users = self.list_users(cohort_id)
        queues = self.open_queue_items(cohort_id)
        with self.connect() as conn:
            quality_rows = conn.execute(
                "SELECT review_id, user_key, quality_state, pmf_usefulness_score, deterministic_flags_json FROM credgpt_quality_reviews WHERE cohort_id=?",
                (cohort_id,),
            ).fetchall()
            cluster_rows = conn.execute(
                "SELECT cluster_id, cluster_type, title, description, severity, status FROM credgpt_quality_clusters WHERE cohort_id=?",
                (cohort_id,),
            ).fetchall()
        quality = []
        for row in quality_rows:
            item = dict(row)
            item["deterministic_flags"] = loads(item.pop("deterministic_flags_json"), [])
            quality.append(item)
        return build_report_snapshot(
            cohort=cohort,
            users=users,
            queues=queues,
            quality_reviews=quality,
            clusters=[dict(row) for row in cluster_rows],
            privacy_tier=privacy_tier,
            report_type=report_type,
            snapshot_date=snapshot_date,
        )

    def build_end_cohort_report(
        self,
        cohort_id: str,
        *,
        narrator: Any = None,
        artifact_root: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate the full end-of-cohort story + (optionally) narrate it.

        Narration is explicit: pass a narrator (e.g. end_cohort.default_narrator())
        to write the memo; otherwise narrative_status is 'skipped'. Writes a JSON
        artifact when artifact_root is given. Aggregate-only — no per-user PII."""
        cohort = self.get_cohort(cohort_id)
        users = self.list_users(cohort_id)
        interventions = self.list_interventions(cohort_id)
        with self.connect() as conn:
            quality_rows = conn.execute(
                "SELECT review_id, user_key, quality_state, pmf_usefulness_score, needs_llm_review, "
                "llm_review_status, llm_review_json FROM credgpt_quality_reviews WHERE cohort_id=?",
                (cohort_id,),
            ).fetchall()
            cluster_rows = conn.execute(
                "SELECT cluster_type, title, severity, status FROM credgpt_quality_clusters WHERE cohort_id=?",
                (cohort_id,),
            ).fetchall()
            metric_rows = conn.execute(
                """
                SELECT s.pmf_metrics_json AS pmf_metrics_json
                FROM pmf_user_daily_snapshots s
                JOIN (
                  SELECT user_key, MAX(snapshot_date) AS md
                  FROM pmf_user_daily_snapshots WHERE cohort_id=? GROUP BY user_key
                ) m ON s.user_key = m.user_key AND s.snapshot_date = m.md
                WHERE s.cohort_id=?
                """,
                (cohort_id, cohort_id),
            ).fetchall()
        quality_reviews = []
        for row in quality_rows:
            item = dict(row)
            item["llm_review"] = loads(item.pop("llm_review_json"), None)
            quality_reviews.append(item)
        metric_records = [loads(dict(row).get("pmf_metrics_json"), {}) for row in metric_rows]
        facts = build_end_cohort_facts(
            cohort=cohort,
            users=users,
            quality_reviews=quality_reviews,
            clusters=[dict(row) for row in cluster_rows],
            interventions=interventions,
            metric_records=metric_records,
        )
        memo = generate_end_cohort_memo(facts, narrator=narrator)
        if artifact_root:
            path = Path(artifact_root) / f"end-cohort-{cohort_id}.json"
            write_snapshot_json(memo, path)
            memo["artifact_path"] = str(path)
        return memo

    def render_report_artifacts(
        self,
        cohort_id: str,
        *,
        report_id: str,
        report_type: str = "daily_cockpit",
        privacy_tier: str = "team",
        artifact_root: str = DEFAULT_ARTIFACT_ROOT,
        snapshot_date: str | None = None,
        include_docx: bool = False,
        include_pdf: bool = False,
        require_visual_qa: bool = True,
    ) -> dict[str, Any]:
        snapshot = self.generate_report_snapshot(
            cohort_id,
            report_type=report_type,
            privacy_tier=privacy_tier,
            snapshot_date=snapshot_date,
        )
        base = Path(artifact_root) / cohort_id / report_id
        snapshot_path = write_snapshot_json(snapshot, base.with_suffix(".json"))
        docflow_spec = build_docflow_spec(snapshot)
        docflow_spec_path = write_docflow_spec(docflow_spec, base.with_suffix(".docflow.json"))
        html_path = render_html(snapshot, base.with_suffix(".html"))
        qa_results = [qa_artifact(html_path, "html")]
        docx_path = None
        pdf_path = None
        if include_docx:
            docx_path = render_docx(snapshot, base.with_suffix(".docx"), docflow_spec=docflow_spec)
            qa_results.append(qa_artifact(docx_path, "docx", require_visual=require_visual_qa))
        if include_pdf:
            pdf_path = render_pdf(snapshot, base.with_suffix(".pdf"), docflow_spec=docflow_spec)
            qa_results.append(qa_artifact(pdf_path, "pdf", require_visual=require_visual_qa))
        status = "qa_passed" if all(item.get("passed") for item in qa_results) else "rendered"
        file_refs = [
            {"type": "snapshot_json", "path": snapshot_path},
            {"type": "docflow_spec", "path": docflow_spec_path},
            {"type": "html", "path": html_path},
        ]
        if docx_path:
            file_refs.append({"type": "docx", "path": docx_path})
        if pdf_path:
            file_refs.append({"type": "pdf", "path": pdf_path})
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO pmf_report_runs (
                  report_id, cohort_id, report_type, privacy_tier, snapshot_date,
                  snapshot_json_path, html_path, docx_path, pdf_path, qa_json,
                  status, file_refs_json, summary_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                  snapshot_json_path=excluded.snapshot_json_path,
                  html_path=excluded.html_path,
                  docx_path=excluded.docx_path,
                  pdf_path=excluded.pdf_path,
                  qa_json=excluded.qa_json,
                  status=excluded.status,
                  file_refs_json=excluded.file_refs_json,
                  summary_json=excluded.summary_json,
                  generated_at=CURRENT_TIMESTAMP
                """,
                (
                    report_id,
                    cohort_id,
                    report_type,
                    privacy_tier,
                    snapshot_date,
                    snapshot_path,
                    html_path,
                    docx_path,
                    pdf_path,
                    dumps(qa_results),
                    status,
                    dumps(file_refs),
                    dumps(snapshot.get("summary") or {}),
                ),
            )
        return {
            "report_id": report_id,
            "status": status,
            "snapshot_json_path": snapshot_path,
            "html_path": html_path,
            "docx_path": docx_path,
            "pdf_path": pdf_path,
            "qa": qa_results,
            "summary": snapshot.get("summary") or {},
            "docflow_spec_path": docflow_spec_path,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _record_claim_evidence(
        self,
        conn: sqlite3.Connection,
        cohort_id: str,
        user_key: str | None,
        entity_type: str,
        entity_id: str,
        evidence: Evidence,
    ) -> None:
        conn.execute(
            """
            INSERT INTO pmf_claim_evidence (
              cohort_id, user_key, entity_type, entity_id, claim_key,
              source_system, source_ref, source_observed_at, freshness_state,
              evidence_state, confidence, value_json, evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cohort_id,
                user_key,
                entity_type,
                entity_id,
                evidence.claim_key,
                evidence.source_system,
                evidence.source_ref,
                evidence.observed_at,
                evidence.freshness,
                evidence.state,
                evidence.confidence,
                dumps(evidence.value if evidence.value is not None else {}),
                dumps(evidence.details),
            ),
        )

    def _record_signal_fact(
        self,
        conn: sqlite3.Connection,
        cohort_id: str,
        user_key: str,
        *,
        source_system: str,
        source_event_name: str,
        source_ref: str,
        observed_at: str,
        fact_type: str,
        fact_json: dict[str, Any],
        raw_json: dict[str, Any],
    ) -> None:
        fact_id = stable_id("fact", cohort_id, user_key, source_system, source_ref, fact_type)
        conn.execute(
            """
            INSERT INTO pmf_signal_facts (
              fact_id, cohort_id, user_key, source_system, source_event_name,
              source_ref, observed_at, fact_type, fact_json, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cohort_id, source_system, source_ref) DO UPDATE SET
              observed_at=excluded.observed_at,
              fact_type=excluded.fact_type,
              fact_json=excluded.fact_json,
              raw_json=excluded.raw_json,
              ingested_at=CURRENT_TIMESTAMP
            """,
            (
                fact_id,
                cohort_id,
                user_key,
                source_system,
                source_event_name,
                source_ref,
                observed_at,
                fact_type,
                dumps(fact_json),
                dumps(raw_json),
            ),
        )

    def _upsert_queue(
        self,
        conn: sqlite3.Connection,
        cohort_id: str,
        user_key: str | None,
        queue: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO pmf_operating_queues (
              cohort_id, user_key, queue_type, severity, status, intake_only,
              title, reason, evidence_json, confidence
            )
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
            ON CONFLICT(cohort_id, user_key, queue_type) WHERE status IN ('open','acknowledged','snoozed')
            DO UPDATE SET
              severity=excluded.severity,
              title=excluded.title,
              reason=excluded.reason,
              evidence_json=excluded.evidence_json,
              confidence=excluded.confidence
            """,
            (
                cohort_id,
                user_key,
                queue["queue_type"],
                queue.get("severity") or "P2",
                1 if queue.get("intake_only") else 0,
                queue.get("title") or queue["queue_type"],
                queue.get("reason"),
                dumps(queue.get("evidence") or {}),
                float(queue.get("confidence", 1.0)),
            ),
        )

    def _resolve_queue_if_open(
        self,
        conn: sqlite3.Connection,
        cohort_id: str,
        user_key: str | None,
        queue_type: str,
        status: str = "resolved",
    ) -> None:
        conn.execute(
            """
            UPDATE pmf_operating_queues
            SET status=?, resolved_at=CURRENT_TIMESTAMP
            WHERE cohort_id=?
              AND (user_key=? OR (user_key IS NULL AND ? IS NULL))
              AND queue_type=?
              AND status IN ('open','acknowledged','snoozed')
            """,
            (status, cohort_id, user_key, user_key, queue_type),
        )


def build_case_file(user: dict[str, Any], facts: dict[str, Any], funnel: dict[str, Any]) -> dict[str, Any]:
    credit_score = _as_int(facts.get("credit_score") or user.get("credit_score"))
    onboarding_complete = bool(facts.get("onboarding_complete")) or user.get("onboarding_status") == "complete"
    return minimize_secrets({
        "identity": {
            "user_key": user.get("user_key"),
            "bon_user_id": user.get("bon_user_id"),
            "name": user.get("name"),
            "phone_number": user.get("phone_number"),
            "email": user.get("email"),
            "signup_event_time": user.get("signup_event_time"),
            "signup_wave": user.get("signup_wave"),
        },
        "onboarding": {
            "status": user.get("onboarding_status"),
            "furthest_step": facts.get("furthest_onboarding_step") or user.get("furthest_onboarding_step"),
            "is_real_user": bool(user.get("is_real_user")) or bool(onboarding_complete and credit_score and credit_score > 0),
            "credit_score": credit_score,
        },
        "linked_accounts": {
            "card_link_status": facts.get("card_link_status") or user.get("card_link_status"),
            "bank_link_status": facts.get("bank_link_status") or user.get("bank_link_status"),
        },
        "financial_context": facts.get("financial_context") or facts.get("profile_summary") or {},
        "activity_timeline": facts.get("activity_timeline") or facts.get("active_days") or [],
        "credgpt": facts.get("credgpt") or {},
        "pmf_funnel": funnel,
        "interventions": facts.get("interventions") or [],
        "qualitative_notes": facts.get("qualitative_notes") or [],
        "product_learning_tags": facts.get("product_learning_tags") or [],
    })


def user_key_from_event(event: dict[str, Any]) -> str:
    bon_user_id = event.get("bon_user_id") or event.get("user_id") or event.get("gp:user_id")
    if bon_user_id:
        return f"user:{bon_user_id}"
    amplitude_id = event.get("amplitude_user_id") or event.get("amplitude_id")
    if amplitude_id:
        return f"amp:{amplitude_id}"
    phone = event.get("phone_number") or event.get("phone") or (event.get("user_properties") or {}).get("gp:phone_number")
    if phone:
        return f"phone:{_hash_identifier(_normalize_phone(str(phone)))}"
    email = event.get("email") or (event.get("user_properties") or {}).get("gp:email")
    if email:
        return f"email:{_hash_identifier(str(email).strip().lower())}"
    return f"anon:{stable_id('anon', dumps(event))}"


def signup_wave(observed_at: datetime, start_dt: datetime, timezone_name: str = "America/Los_Angeles") -> str:
    try:
        cohort_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        cohort_tz = timezone.utc
    observed_local = observed_at.astimezone(cohort_tz)
    start_local = start_dt.astimezone(cohort_tz)
    day = max(1, min(3, int((observed_local.date() - start_local.date()).days) + 1))
    return f"day_{day}"


def merge_cumulative_facts(previous: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge cumulative PMF facts so partial daily payloads don't demote users.

    The live pipeline should still send cumulative values. This merge is a
    defensive guard for missing fields during partial refreshes.
    """
    if not previous:
        return dict(incoming)
    merged = dict(incoming)

    for key in ("meaningful_credgpt_messages", "high_intent_usable_qas", "weak_credgpt_response_count"):
        if key in previous or key in incoming:
            merged[key] = max(_as_int(previous.get(key)) or 0, _as_int(incoming.get(key)) or 0)

    for key in ("value_actions", "failed_link_attempts", "negative_signals", "product_learning_tags"):
        if key in previous or key in incoming:
            merged[key] = _merge_lists(previous.get(key), incoming.get(key))

    if "active_days" in previous or "active_days" in incoming:
        merged["active_days"] = _merge_lists(previous.get("active_days"), incoming.get("active_days"))

    if isinstance(previous.get("pmf_success_metrics"), dict) or isinstance(incoming.get("pmf_success_metrics"), dict):
        metrics = dict(previous.get("pmf_success_metrics") or {})
        metrics.update(incoming.get("pmf_success_metrics") or {})
        merged["pmf_success_metrics"] = metrics

    if previous.get("explicit_love_proof") and "explicit_love_proof" not in incoming:
        merged["explicit_love_proof"] = previous.get("explicit_love_proof")
        for key in ("love_proof", "love_proof_source_ref", "love_proof_source_system"):
            if key in previous and key not in incoming:
                merged[key] = previous[key]

    return merged


def parse_dt(value: str) -> datetime:
    if not value:
        raise ValueError("missing datetime")
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def dt_to_db(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _is_entry_event(event: dict[str, Any], source_entry_event: str) -> bool:
    if event.get("step_name") == source_entry_event:
        return True
    props = event.get("event_properties") or {}
    if props.get("step_name") == source_entry_event:
        return True
    if event.get("event_type") == source_entry_event:
        return True
    return False


def _hash_identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _link_status(explicit: Any, flag: Any) -> str:
    if explicit in {"unknown", "not_started", "initiated", "linked", "failed"}:
        return str(explicit)
    if flag in {True, "true", "True", "1", 1}:
        return "linked"
    if flag in {False, "false", "False", "0", 0}:
        return "not_started"
    return "unknown"


def _merge_lists(left: Any, right: Any) -> list[Any]:
    out: list[Any] = []
    seen = set()
    for collection in (left, right):
        if collection is None:
            continue
        values = collection if isinstance(collection, list) else [collection]
        for value in values:
            marker = json.dumps(value, sort_keys=True, default=str)
            if marker not in seen:
                seen.add(marker)
                out.append(value)
    return out


def _transition_type(old_stage: str | None, new_stage: str) -> str:
    if not old_stage:
        return "initial"
    ranks = {
        "signed_up": 0,
        "onboarded_real_user": 1,
        "activated_user": 2,
        "activated_saver": 3,
        "likely_lover": 4,
        "confirmed_lover": 5,
    }
    if ranks.get(new_stage, 0) > ranks.get(old_stage, 0):
        return "promotion"
    if ranks.get(new_stage, 0) < ranks.get(old_stage, 0):
        return "demotion"
    return "recomputed"
