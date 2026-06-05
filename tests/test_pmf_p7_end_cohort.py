"""P7 tests: end-cohort intelligence memo — deterministic aggregation + the
injectable, key-gated narrator seam. No live LLM; narration is explicit."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.end_cohort import (  # noqa: E402
    build_end_cohort_facts,
    generate_end_cohort_memo,
    normalize_memo,
)
from pmf_os.store import PmfStore  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WS, WE = "2026-05-27T00:00:00-07:00", "2026-05-29T23:59:59-07:00"


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_p7_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="p7", name="P7", signup_window_start=WS, signup_window_end=WE, activate=True)
    return store


def test_build_end_cohort_facts_aggregations():
    users = [
        {"highest_stage": "confirmed_lover", "activated_saver_state": "computed", "current_health": "healthy", "flags": ["potential_lover"]},
        {"highest_stage": "activated_saver", "activated_saver_state": "candidate", "current_health": "watch"},
        {"highest_stage": "activated_user", "current_health": "at_risk", "flags": ["at_risk"]},
        {"highest_stage": "onboarded_real_user", "current_health": "watch"},
        {"highest_stage": "signed_up", "current_health": "stuck", "flags": ["stuck_onboarding"]},
    ]
    quality = [
        {"quality_state": "ok", "needs_llm_review": 0, "llm_review_status": "not_needed", "pmf_usefulness_score": 0.8},
        {"quality_state": "weak", "needs_llm_review": 1, "llm_review_status": "completed", "pmf_usefulness_score": 0.4, "llm_review": {"unsafe_advice": False}},
        {"quality_state": "unsafe", "needs_llm_review": 1, "llm_review_status": "completed", "pmf_usefulness_score": 0.1, "llm_review": {"unsafe_advice": True}},
    ]
    clusters = [
        {"cluster_type": "usefulness", "title": "Thin", "severity": "P2"},
        {"cluster_type": "unsafe_advice", "title": "Unsafe", "severity": "P1"},
    ]
    interventions = [
        {"approval_status": "executed", "action_type": "nudge", "outcome": {"delivered": True, "opened": True, "clicked": False}},
        {"approval_status": "needs_approval", "action_type": "nudge"},
        {"approval_status": "rejected", "action_type": "winback"},
    ]
    metric_records = [
        {"activation_depth": "confirmed", "linked_financial_context": "confirmed", "repeat_engagement": "candidate"},
        {"linked_financial_context": "confirmed", "financial_action": "confirmed"},
    ]
    facts = build_end_cohort_facts(
        cohort={"name": "P7"}, users=users, quality_reviews=quality,
        clusters=clusters, interventions=interventions, metric_records=metric_records,
    )

    f = facts["funnel"]
    assert (f["real_users"], f["activated_users"], f["activated_savers"], f["likely_lovers"], f["confirmed_lovers"]) == (4, 3, 2, 1, 1)
    assert f["rates"]["real_user_rate"] == 0.8 and f["rates"]["activation_rate"] == 0.75
    assert f["rates"]["lover_rate"] == 1.0
    assert f["activated_saver_state"] == {"computed": 1, "candidate": 1}

    d = facts["dropoff"]
    assert d["signed_up_not_onboarded"] == 1 and d["onboarded_not_activated"] == 1 and d["at_risk"] == 1
    assert d["flags"]["stuck_onboarding"] == 1

    q = facts["credgpt_quality"]
    assert q["total_reviews"] == 3 and q["weak_or_worse"] == 2 and q["unsafe_or_risk"] == 1
    assert q["needs_llm_review"] == 2 and q["llm_flagged_unsafe"] == 1
    assert q["clusters"][0]["cluster_type"] == "unsafe_advice"  # P1 sorted first

    i = facts["interventions"]
    assert i["executed"] == 1 and i["by_status"]["rejected"] == 1 and i["outcomes"]["opened"] == 1

    m = facts["pmf_metrics"]
    assert m["linked_financial_context"]["confirmed"] == 2
    assert m["activation_depth"]["confirmed"] == 1 and m["repeat_engagement"]["candidate"] == 1
    assert m["retained_value"] == {"confirmed": 0, "candidate": 0, "deferred": True, "status": "not measured yet"}


def test_normalize_memo_coerces_and_defaults_verdict():
    memo = normalize_memo({
        "executive_summary": "ok", "what_worked": ["a", 2], "what_didnt": [],
        "pmf_verdict": {"rating": "bogus", "reason": "x"}, "recommendations": ["do y"],
    })
    assert memo["pmf_verdict"]["rating"] == "inconclusive"  # invalid -> default
    assert memo["what_worked"] == ["a", "2"]
    valid = normalize_memo({"pmf_verdict": {"rating": "strong", "reason": "r"}})
    assert valid["pmf_verdict"]["rating"] == "strong"


def test_generate_memo_explicit_narration():
    facts = {"funnel": {}, "schema_version": "pmf_end_cohort.v1"}
    assert generate_end_cohort_memo(facts, narrator=None)["narrative_status"] == "skipped"

    def fake(f):
        assert "funnel" in f
        return {"executive_summary": "good cohort", "pmf_verdict": {"rating": "promising", "reason": "r"}}

    done = generate_end_cohort_memo(facts, narrator=fake)
    assert done["narrative_status"] == "completed"
    assert done["narrative"]["pmf_verdict"]["rating"] == "promising"

    def boom(f):
        raise RuntimeError("llm 500")

    failed = generate_end_cohort_memo(facts, narrator=boom)
    assert failed["narrative_status"] == "failed" and "llm 500" in failed["error"]


def test_store_build_end_cohort_report_end_to_end():
    store = _store()
    store.record_credgpt_turn("p7", "user:1001", {
        "thread_id": "t1", "turn_id": "t1:0",
        "question": "how should i pay down my credit card debt",
        "answer": "Just pay only the minimum and ignore the rest.",
        "event_time": "2026-05-28T10:00:00Z",
    })
    iid = store.draft_intervention("p7", {
        "user_key": "user:1001", "channel": "email", "action_type": "nudge_link_card",
        "draft": {"to": "u@example.com", "frequency_cap_checked": True},
        "dry_run": {"ok": True}, "audience_preview": {"count": 1}, "suppression_check": {"suppressed": 0},
    })["intervention_id"]
    store.approve_intervention("p7", iid, "abhinav")
    store.execute_intervention("p7", iid, customerio_ref="ref1")

    art = str(Path(tempfile.mkdtemp(prefix="p7_art_")))
    memo = store.build_end_cohort_report(
        "p7",
        narrator=lambda facts: {"executive_summary": "ok", "pmf_verdict": {"rating": "promising", "reason": "early"}},
        artifact_root=art,
    )
    assert memo["narrative_status"] == "completed"
    assert memo["narrative"]["pmf_verdict"]["rating"] == "promising"
    assert memo["facts"]["interventions"]["executed"] == 1
    assert memo["facts"]["credgpt_quality"]["total_reviews"] == 1
    assert memo["facts"]["credgpt_quality"]["unsafe_or_risk"] == 1
    assert Path(memo["artifact_path"]).exists()


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
