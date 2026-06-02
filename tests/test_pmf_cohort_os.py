"""Tests for Alaska V5 PMF Cohort OS.

Stdlib only. Runnable directly:
    python3 tests/test_pmf_cohort_os.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.artifacts import artifact_ready_for_delivery, qa_artifact, redact_for_privacy  # noqa: E402
from pmf_os.credgpt_quality import review_turn  # noqa: E402
from pmf_os.customerio_guard import validate_customerio_action  # noqa: E402
from pmf_os.funnel import evaluate_funnel, is_meaningful_credgpt_message  # noqa: E402
from pmf_os.store import PmfStore, signup_wave, parse_dt  # noqa: E402


REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"


def _db() -> str:
    tmp = tempfile.mkdtemp(prefix="alaska_pmf_")
    db = str(Path(tmp) / "alaska.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return db


def _store() -> PmfStore:
    store = PmfStore(_db())
    store.create_cohort(
        cohort_id="pmf-test",
        name="PMF Test Cohort",
        signup_window_start="2026-06-11T00:00:00-07:00",
        signup_window_end="2026-06-13T23:59:59-07:00",
        expected_signups=1000,
        expected_real_users=750,
        activate=True,
    )
    return store


def _signup(user_id: str, event_time: str = "2026-06-12T10:00:00-07:00") -> dict:
    return {
        "event_type": "onboarding_step_completed",
        "step_name": "phone_number_submitted",
        "event_time": event_time,
        "event_id": f"evt-{user_id}-{event_time}",
        "user_id": user_id,
        "user_properties": {
            "gp:first_name": "Asha",
            "gp:email": "asha@example.com",
            "gp:phone_number": "+1 555 123 4567",
        },
    }


def test_cohort_window_is_configurable_and_excludes_out_of_window_users():
    store = _store()
    inside = store.upsert_signup_user("pmf-test", _signup("2714"))
    outside = store.upsert_signup_user("pmf-test", _signup("9999", "2026-06-14T00:01:00-07:00"))
    wrong_event = store.upsert_signup_user(
        "pmf-test",
        {**_signup("8888"), "step_name": "otp_verified", "event_id": "evt-wrong"},
    )

    assert inside["status"] == "ingested"
    assert outside == {
        "status": "excluded",
        "reason": "outside_signup_window",
        "observed_at": "2026-06-14 07:01:00",
    }
    assert wrong_event["reason"] == "not_cohort_entry_event"
    assert len(store.list_users("pmf-test")) == 1

    batch = store.ingest_signup_events(
        "pmf-test",
        [_signup("3001", "2026-06-13T11:00:00-07:00"), _signup("3002", "2026-06-15T11:00:00-07:00")],
    )
    assert batch["ingested"] == 1
    assert batch["excluded_by_reason"] == {"outside_signup_window": 1}
    assert len(store.list_users("pmf-test")) == 2

    duplicate = store.ingest_signup_events("pmf-test", [_signup("3001", "2026-06-13T11:00:00-07:00")])
    assert duplicate["ingested"] == 1
    assert len(store.list_users("pmf-test")) == 2
    conn = sqlite3.connect(store.db_path)
    signal_count = conn.execute("SELECT COUNT(*) FROM pmf_signal_facts WHERE source_ref=?", ("evt-3001-2026-06-13T11:00:00-07:00",)).fetchone()[0]
    conn.close()
    assert signal_count == 1


def test_real_user_requires_onboarding_complete_and_credit_score_gt_zero():
    store = _store()
    user_key = store.upsert_signup_user("pmf-test", _signup("2714"))["user_key"]

    profile = store.update_user_profile(
        "pmf-test",
        user_key,
        {"onboarding_complete": True, "credit_score": 0, "source_ref": "u360:2714"},
    )
    assert profile["is_real_user"] == 0

    profile = store.update_user_profile(
        "pmf-test",
        user_key,
        {"onboarding_complete": True, "credit_score": 711, "source_ref": "u360:2714"},
    )
    assert profile["is_real_user"] == 1
    assert profile["onboarding_status"] == "complete"


def test_activated_user_rules_and_failed_linking_high_intent_not_activation():
    failed_link_only = evaluate_funnel(
        {
            "onboarding_complete": True,
            "credit_score": 700,
            "meaningful_credgpt_messages": 0,
            "high_intent_usable_qas": 0,
            "failed_link_attempts": ["card"],
        }
    )
    assert failed_link_only.stage == "onboarded_real_user"
    assert "high_intent" in failed_link_only.flags
    assert any(q["queue_type"] == "plaid_failed" for q in failed_link_only.queues)

    activated = evaluate_funnel(
        {
            "onboarding_complete": True,
            "credit_score": 700,
            "meaningful_credgpt_messages": 3,
        }
    )
    assert activated.stage == "activated_user"

    value_action = evaluate_funnel(
        {
            "onboarding_complete": True,
            "credit_score": 700,
            "value_actions": ["bank_link_success"],
        }
    )
    assert value_action.stage == "activated_user"


def test_meaningful_message_classifier_excludes_greetings_and_keeps_financial_questions():
    assert not is_meaningful_credgpt_message("hello")
    assert not is_meaningful_credgpt_message("thanks")
    assert is_meaningful_credgpt_message("How should I pay down my highest APR card first?")


def test_activated_saver_computed_and_candidate_remain_separate():
    computed = evaluate_funnel(
        {
            "onboarding_complete": True,
            "credit_score": 700,
            "meaningful_credgpt_messages": 3,
            "pmf_success_metrics": {
                "activation_depth": "confirmed",
                "linked_financial_context": "confirmed",
            },
        }
    )
    assert computed.stage == "activated_saver"
    assert computed.activated_saver_state == "computed"

    candidate = evaluate_funnel(
        {
            "onboarding_complete": True,
            "credit_score": 700,
            "meaningful_credgpt_messages": 3,
            "pmf_success_metrics": {
                "activation_depth": "confirmed",
                "repeat_engagement": "candidate",
            },
        }
    )
    assert candidate.stage == "activated_saver"
    assert candidate.activated_saver_state == "candidate"
    assert "activated_saver_candidate" in candidate.flags


def test_likely_and_confirmed_lover_require_right_evidence():
    likely = evaluate_funnel(
        {
            "onboarding_complete": True,
            "credit_score": 700,
            "meaningful_credgpt_messages": 3,
            "pmf_success_metrics": {
                "activation_depth": "confirmed",
                "linked_financial_context": "confirmed",
            },
            "active_days": ["2026-06-11", "2026-06-12"],
            "negative_signals": [],
        }
    )
    assert likely.stage == "likely_lover"
    assert "potential_lover" in likely.flags

    negative = evaluate_funnel(
        {
            "onboarding_complete": True,
            "credit_score": 700,
            "meaningful_credgpt_messages": 3,
            "pmf_success_metrics": {
                "activation_depth": "confirmed",
                "linked_financial_context": "confirmed",
            },
            "active_days": ["2026-06-11", "2026-06-12"],
            "negative_signals": ["bad_feedback"],
        }
    )
    assert negative.stage == "activated_saver"

    confirmed = evaluate_funnel(
        {
            "onboarding_complete": True,
            "credit_score": 700,
            "explicit_love_proof": True,
            "love_proof": "BON helped me save money.",
            "love_proof_source_ref": "interview:1",
        }
    )
    assert confirmed.stage == "confirmed_lover"


def test_store_snapshot_writes_transition_case_file_and_queues():
    store = _store()
    user_key = store.upsert_signup_user("pmf-test", _signup("2714"))["user_key"]
    store.update_user_profile("pmf-test", user_key, {"onboarding_complete": True, "credit_score": 711})
    result = store.apply_daily_snapshot(
        "pmf-test",
        user_key,
        "2026-06-12",
        {
            "meaningful_credgpt_messages": 3,
            "pmf_success_metrics": {
                "activation_depth": "confirmed",
                "repeat_engagement": "candidate",
            },
            "active_days": ["2026-06-11"],
        },
    )
    assert result["stage"] == "activated_saver"
    assert result["activated_saver_state"] == "candidate"

    conn = sqlite3.connect(store.db_path)
    transition_count = conn.execute("SELECT COUNT(*) FROM pmf_funnel_transitions").fetchone()[0]
    case_count = conn.execute("SELECT COUNT(*) FROM pmf_user_case_files").fetchone()[0]
    queue_count = conn.execute("SELECT COUNT(*) FROM pmf_operating_queues WHERE queue_type='needs_human_review'").fetchone()[0]
    conn.close()
    assert transition_count == 1
    assert case_count == 1
    assert queue_count == 1


def test_partial_daily_snapshot_does_not_demote_existing_activation():
    store = _store()
    user_key = store.upsert_signup_user("pmf-test", _signup("2714"))["user_key"]
    store.update_user_profile("pmf-test", user_key, {"onboarding_complete": True, "credit_score": 711})

    first = store.apply_daily_snapshot("pmf-test", user_key, "2026-06-12", {"meaningful_credgpt_messages": 3})
    assert first["stage"] == "activated_user"

    second = store.apply_daily_snapshot("pmf-test", user_key, "2026-06-13", {})
    assert second["stage"] == "activated_user"


def test_at_risk_queue_uses_fresh_inactivity_value():
    store = _store()
    user_key = store.upsert_signup_user("pmf-test", _signup("2714"))["user_key"]
    store.update_user_profile("pmf-test", user_key, {"onboarding_complete": True, "credit_score": 711})

    at_risk = store.apply_daily_snapshot("pmf-test", user_key, "2026-06-12", {"inactive_days": 3})
    assert at_risk["health"] == "at_risk"
    assert any(q["queue_type"] == "at_risk" for q in at_risk["queues"])

    returned = store.apply_daily_snapshot("pmf-test", user_key, "2026-06-13", {"inactive_days": 0})
    assert returned["health"] == "watch"
    assert not any(q["queue_type"] == "at_risk" for q in store.open_queue_items("pmf-test"))

    missing_inactivity = store.apply_daily_snapshot("pmf-test", user_key, "2026-06-14", {})
    assert missing_inactivity["health"] == "watch"


def test_credgpt_quality_creates_internal_review_and_queue_only():
    store = _store()
    user_key = store.upsert_signup_user("pmf-test", _signup("2714"))["user_key"]
    review = store.record_credgpt_turn(
        "pmf-test",
        user_key,
        {
            "thread_id": "t1",
            "turn_id": "1",
            "question": "How should I pay down my credit card debt?",
            "answer": "You should pay it.",
            "event_time": "2026-06-12T10:10:00Z",
            "feedback": "bad",
            "user_context_present": True,
        },
    )
    assert review["needs_llm_review"] is True
    assert review["quality_state"] in {"weak", "hallucination_risk"}
    assert review["internal_recommendations"]

    clusters = store.refresh_credgpt_clusters("pmf-test")
    assert clusters
    conn = sqlite3.connect(store.db_path)
    intervention_count = conn.execute("SELECT COUNT(*) FROM pmf_interventions").fetchone()[0]
    weak_queue_count = conn.execute("SELECT COUNT(*) FROM pmf_operating_queues WHERE queue_type='weak_credgpt_response'").fetchone()[0]
    conn.close()
    assert intervention_count == 0
    assert weak_queue_count == 1


def test_credgpt_quality_labels_grounding_and_safety_as_review_triage():
    qualitative = review_turn(
        {
            "cohort_id": "pmf-test",
            "user_key": "user:1",
            "thread_id": "t1",
            "turn_id": "qual",
            "question": "Should I close a credit card?",
            "answer": "Usually, keeping an older account open can help preserve account age. Review fees and usage before deciding. Next step: compare the card's fee with how often you use it.",
            "user_context_present": True,
        }
    )
    assert qualitative.quality_state == "weak"
    assert "personalization_or_grounding_review_needed" in qualitative.deterministic_flags
    assert "numeric_financial_claim_needs_source_review" not in qualitative.deterministic_flags

    numeric_without_source = review_turn(
        {
            "cohort_id": "pmf-test",
            "user_key": "user:1",
            "thread_id": "t1",
            "turn_id": "num",
            "question": "How should I pay down my credit card debt?",
            "answer": "Your $4,200 balance should be paid down first because utilization is high. Next step: pay $300 this month.",
            "user_context_present": True,
        }
    )
    assert numeric_without_source.quality_state == "hallucination_risk"
    assert "numeric_financial_claim_needs_source_review" in numeric_without_source.deterministic_flags

    unsafe = review_turn(
        {
            "cohort_id": "pmf-test",
            "user_key": "user:1",
            "thread_id": "t1",
            "turn_id": "unsafe",
            "question": "How do I improve my credit score?",
            "answer": "Close your oldest credit card to improve your score. Next step: close it today.",
            "user_context_present": True,
        }
    )
    assert unsafe.quality_state == "unsafe"
    assert "unsafe_or_overconfident_language" in unsafe.deterministic_flags


def test_resolved_credgpt_clusters_do_not_reopen_on_refresh():
    store = _store()
    user_key = store.upsert_signup_user("pmf-test", _signup("2714"))["user_key"]
    store.record_credgpt_turn(
        "pmf-test",
        user_key,
        {
            "thread_id": "t1",
            "turn_id": "1",
            "question": "How should I pay down my credit card debt?",
            "answer": "Your $4,200 balance should be paid down first because utilization is high. Next step: pay $300 this month.",
            "event_time": "2026-06-12T10:10:00Z",
            "user_context_present": True,
        },
    )
    clusters = store.refresh_credgpt_clusters("pmf-test")
    target_id = [cluster["cluster_id"] for cluster in clusters if cluster["cluster_type"] == "hallucination_risk"][0]

    conn = sqlite3.connect(store.db_path)
    conn.execute("UPDATE credgpt_quality_clusters SET status='resolved' WHERE cluster_id=?", (target_id,))
    conn.commit()
    conn.close()

    store.refresh_credgpt_clusters("pmf-test")
    conn = sqlite3.connect(store.db_path)
    status = conn.execute("SELECT status FROM credgpt_quality_clusters WHERE cluster_id=?", (target_id,)).fetchone()[0]
    open_queue_count = conn.execute(
        "SELECT COUNT(*) FROM pmf_operating_queues WHERE queue_type='repeated_product_model_issue_cluster' AND status IN ('open','acknowledged','snoozed')"
    ).fetchone()[0]
    conn.close()
    assert status == "resolved"
    assert open_queue_count == 0


def test_customerio_guard_blocks_sms_and_unapproved_actions():
    sms = validate_customerio_action({"channel": "sms"})
    assert sms.allowed is False
    assert any("SMS is blocked" in reason for reason in sms.reasons)

    missing_gates = validate_customerio_action({"channel": "push", "approved_by": "U07GKLVA9FE"})
    assert missing_gates.allowed is False
    assert "Missing dry-run result." in missing_gates.reasons
    assert "Missing audience preview." in missing_gates.reasons
    assert "Missing suppression check." in missing_gates.reasons

    allowed = validate_customerio_action(
        {
            "channel": "email",
            "approved_by": "U07GKLVA9FE",
            "dry_run": {"ok": True},
            "audience_preview": {"count": 10},
            "suppression_check": {"suppressed": 1},
            "frequency_cap_checked": True,
        }
    )
    assert allowed.allowed is True


def test_reports_redact_team_pii_and_render_self_contained_artifacts():
    store = _store()
    user_key = store.upsert_signup_user("pmf-test", _signup("2714"))["user_key"]
    store.update_user_profile("pmf-test", user_key, {"onboarding_complete": True, "credit_score": 711})
    store.apply_daily_snapshot("pmf-test", user_key, "2026-06-12", {"meaningful_credgpt_messages": 3})

    artifact_root = Path(tempfile.mkdtemp(prefix="alaska_pmf_artifacts_"))
    rendered = store.render_report_artifacts(
        "pmf-test",
        report_id="daily-team",
        report_type="daily_cockpit",
        privacy_tier="team",
        artifact_root=str(artifact_root),
        snapshot_date="2026-06-12",
        include_docx=True,
        include_pdf=True,
        require_visual_qa=False,
    )
    assert rendered["status"] == "qa_passed"
    assert Path(rendered["html_path"]).exists()
    assert Path(rendered["docx_path"]).exists()
    assert Path(rendered["pdf_path"]).exists()
    assert all(item["structural_pass"] for item in rendered["qa"])

    html_text = Path(rendered["html_path"]).read_text(encoding="utf-8")
    assert "asha@example.com" not in html_text
    assert "555 123 4567" not in html_text
    assert "http://" not in html_text
    assert "https://" not in html_text

    snapshot = json.loads(Path(rendered["snapshot_json_path"]).read_text(encoding="utf-8"))
    assert snapshot["users"][0]["email"] == "[redacted]"
    assert qa_artifact(rendered["html_path"], "html")["passed"] is True
    for key in ("snapshot_json_path", "html_path", "docx_path", "pdf_path"):
        mode = stat.S_IMODE(os.stat(rendered[key]).st_mode)
        assert mode == 0o600


def test_docx_pdf_delivery_gate_requires_visual_qa():
    assert not artifact_ready_for_delivery(
        [
            {"artifact_type": "html", "passed": True},
            {"artifact_type": "docx", "structural_pass": True, "visual_render_pass": False},
            {"artifact_type": "pdf", "structural_pass": True, "visual_render_pass": True},
        ]
    )


def test_founder_privacy_preserves_user_level_details():
    assert redact_for_privacy({"email": "asha@example.com"}, "founder") == {"email": "asha@example.com"}
    assert redact_for_privacy({"email": "asha@example.com"}, "team") == {"email": "[redacted]"}


def test_signup_wave_uses_cohort_timezone_not_utc_date():
    start = parse_dt("2026-06-11T00:00:00-07:00")
    observed = parse_dt("2026-06-12T06:30:00Z")  # 2026-06-11 23:30 Pacific
    assert signup_wave(observed, start, "America/Los_Angeles") == "day_1"


def test_cli_batch_ingest_and_summary_smoke():
    tmp = Path(tempfile.mkdtemp(prefix="alaska_pmf_cli_test_"))
    db = tmp / "alaska.db"
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    events_file = tmp / "events.jsonl"
    events_file.write_text(json.dumps(_signup("2714")) + "\n", encoding="utf-8")

    create = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "lib" / "pmf_cohort_os.py"),
            "--db",
            str(db),
            "create-cohort",
            "--cohort-id",
            "pmf-cli",
            "--name",
            "PMF CLI",
            "--signup-window-start",
            "2026-06-11T00:00:00-07:00",
            "--signup-window-end",
            "2026-06-13T23:59:59-07:00",
            "--activate",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    ingest = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "lib" / "pmf_cohort_os.py"),
            "--db",
            str(db),
            "ingest-signups-file",
            "--cohort-id",
            "pmf-cli",
            "--events-file",
            str(events_file),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    summary = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "lib" / "pmf_cohort_os.py"),
            "--db",
            str(db),
            "summary",
            "--cohort-id",
            "pmf-cli",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    assert json.loads(create.stdout)["ok"] is True
    assert json.loads(ingest.stdout)["result"]["ingested"] == 1
    assert json.loads(summary.stdout)["result"]["summary"]["total_signup_users"] == 1


def run():
    tests = [
        test_cohort_window_is_configurable_and_excludes_out_of_window_users,
        test_real_user_requires_onboarding_complete_and_credit_score_gt_zero,
        test_activated_user_rules_and_failed_linking_high_intent_not_activation,
        test_meaningful_message_classifier_excludes_greetings_and_keeps_financial_questions,
        test_activated_saver_computed_and_candidate_remain_separate,
        test_likely_and_confirmed_lover_require_right_evidence,
        test_store_snapshot_writes_transition_case_file_and_queues,
        test_partial_daily_snapshot_does_not_demote_existing_activation,
        test_at_risk_queue_uses_fresh_inactivity_value,
        test_credgpt_quality_creates_internal_review_and_queue_only,
        test_credgpt_quality_labels_grounding_and_safety_as_review_triage,
        test_resolved_credgpt_clusters_do_not_reopen_on_refresh,
        test_customerio_guard_blocks_sms_and_unapproved_actions,
        test_reports_redact_team_pii_and_render_self_contained_artifacts,
        test_docx_pdf_delivery_gate_requires_visual_qa,
        test_founder_privacy_preserves_user_level_details,
        test_signup_wave_uses_cohort_timezone_not_utc_date,
        test_cli_batch_ingest_and_summary_smoke,
    ]
    for test in tests:
        test()
    print(f"ok - {len(tests)} PMF Cohort OS tests passed")


if __name__ == "__main__":
    run()
