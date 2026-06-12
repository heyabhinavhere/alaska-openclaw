"""P11 tests: the shared metric rollup, the weekly-digest facts (this-week movements,
product friction, intervention outcomes), the narrator seam, and an end-to-end
build_weekly_digest_report. Fixtures only — no live LLM."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.model import rollup_pmf_metrics  # noqa: E402
from pmf_os.store import PmfStore  # noqa: E402
from pmf_os.weekly_digest import build_weekly_facts, generate_weekly_digest, normalize_weekly  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WS, WE = "2026-05-27T00:00:00-07:00", "2026-05-29T23:59:59-07:00"


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_p11_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="p11", name="P11", signup_window_start=WS, signup_window_end=WE, activate=True)
    return store


def _seed_user(store: PmfStore, user_key: str, bon_user_id: str) -> None:
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "INSERT INTO pmf_cohort_users (cohort_id, user_key, bon_user_id, signup_event_time, current_stage, highest_stage) "
        "VALUES (?,?,?,?,?,?)",
        ("p11", user_key, bon_user_id, "2026-05-28T10:00:00Z", "signed_up", "signed_up"),
    )
    conn.commit()
    conn.close()


def test_rollup_pmf_metrics():
    records = [
        {"linked_financial_context": "confirmed", "activation_depth": "candidate"},
        {"linked_financial_context": True, "repeat_engagement": "confirmed"},
        "junk",  # ignored
    ]
    r = rollup_pmf_metrics(records)
    assert r["linked_financial_context"] == {"confirmed": 2, "candidate": 0}  # "confirmed" + True
    assert r["activation_depth"] == {"confirmed": 0, "candidate": 1}
    assert r["repeat_engagement"] == {"confirmed": 1, "candidate": 0}
    # #71: deferred metrics are marked (not a "0 confirmed" false negative); live ones unchanged
    assert r["retained_value"] == {"confirmed": 0, "candidate": 0, "deferred": True, "status": "not measured yet"}
    assert r["qualitative_positive_signal"]["deferred"] is True
    assert "deferred" not in r["activation_depth"]


def test_build_weekly_facts():
    summary = {"total_signup_users": 100, "real_users": 60, "stage_counts": {"activated_user": 10}}
    movements = [
        {"user_key": "user:1", "to_stage": "activated_user", "transition_type": "promotion"},
        {"user_key": "user:2", "to_stage": "activated_saver", "transition_type": "promotion"},
        {"user_key": "user:3", "to_stage": "signed_up", "transition_type": "demotion"},
        {"user_key": "user:4", "to_stage": "activated_user", "transition_type": "initial"},  # not promo/demo
    ]
    queues = [
        {"queue_type": "stuck_onboarding", "user_key": "user:5"},
        {"queue_type": "plaid_failed", "user_key": "user:6"},
        {"queue_type": "potential_lover", "user_key": "user:7"},  # NOT friction
    ]
    interventions = [
        {"approval_status": "executed", "outcome": {"delivered": True, "opened": True}},
        {"approval_status": "needs_approval"},
    ]
    f = build_weekly_facts(
        cohort={"name": "P11"}, summary=summary, week_movements=movements, open_queues=queues,
        clusters=[{"cluster_type": "unsafe_advice", "title": "x", "severity": "P1"}],
        interventions=interventions, metric_records=[{"linked_financial_context": "confirmed"}], week_start="2026-05-26",
    )
    assert f["movement_this_week"]["promotions"] == 2 and f["movement_this_week"]["net"] == 1
    assert f["movement_this_week"]["promotion_to_stages"] == {"activated_saver": 1, "activated_user": 1}
    assert f["product_friction"]["queue_counts"] == {"plaid_failed": 1, "stuck_onboarding": 1}  # potential_lover excluded
    assert len(f["product_friction"]["credgpt_clusters"]) == 1
    assert f["interventions"]["outcomes"]["opened"] == 1 and f["interventions"]["by_status"]["executed"] == 1
    assert f["pmf_metrics"]["linked_financial_context"]["confirmed"] == 1
    assert f["funnel_now"]["real_users"] == 60


def test_weekly_narrator_seam_and_normalize():
    facts = {"funnel_now": {}, "schema_version": "pmf_weekly_digest.v1"}
    assert generate_weekly_digest(facts, narrator=None)["narrative_status"] == "skipped"

    done = generate_weekly_digest(facts, narrator=lambda f: {"headline": "wk", "trajectory": {"rating": "toward_pmf", "reason": "r"}})
    assert done["narrative_status"] == "completed" and done["narrative"]["trajectory"]["rating"] == "toward_pmf"

    def boom(f):
        raise RuntimeError("llm 500")

    assert generate_weekly_digest(facts, narrator=boom)["narrative_status"] == "failed"
    # invalid trajectory rating -> defaulted
    assert normalize_weekly({"trajectory": {"rating": "bogus"}})["trajectory"]["rating"] == "too_early"


def test_build_weekly_digest_report_end_to_end():
    store = _store()
    _seed_user(store, "user:1", "1")
    store.apply_daily_snapshot("p11", "user:1", "2026-05-28", {
        "onboarding_complete": True, "credit_score": 700, "card_linked": True, "bank_linked": False,
        "meaningful_credgpt_messages": 0, "pmf_success_metrics": {"linked_financial_context": "confirmed"},
    })
    art = str(Path(tempfile.mkdtemp(prefix="p11art_")))
    digest = store.build_weekly_digest_report(
        "p11",
        narrator=lambda f: {"headline": "wk1", "trajectory": {"rating": "too_early", "reason": "day 1"}},
        week_start="2026-05-26", artifact_root=art,
    )
    assert digest["narrative_status"] == "completed"
    assert digest["narrative"]["trajectory"]["rating"] == "too_early"
    assert digest["facts"]["pmf_metrics"]["linked_financial_context"]["confirmed"] == 1  # snapshot data flowed through
    assert set(digest["facts"]) >= {"funnel_now", "movement_this_week", "product_friction", "interventions", "pmf_metrics"}
    assert Path(digest["artifact_path"]).exists()


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
