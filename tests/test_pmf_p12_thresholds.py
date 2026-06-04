"""P12 tests: per-cohort tunable thresholds. resolve_thresholds (defaults + validated
overrides), the funnel honoring overrides, defaults reproducing today's behavior, and a
cohort's config flowing through apply_daily_snapshot to the funnel. Fixtures only."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.funnel import compute_pmf_success_metrics, evaluate_funnel  # noqa: E402
from pmf_os.store import PmfStore  # noqa: E402
from pmf_os.thresholds import DEFAULT_THRESHOLDS, resolve_thresholds  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WS, WE = "2026-05-27T00:00:00-07:00", "2026-05-29T23:59:59-07:00"


def _store(config: dict | None = None) -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_p12_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="p12", name="P12", signup_window_start=WS, signup_window_end=WE,
                        activate=True, config=config)
    return store


def _seed_user(store: PmfStore, user_key: str, bon_user_id: str) -> None:
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "INSERT INTO pmf_cohort_users (cohort_id, user_key, bon_user_id, signup_event_time, current_stage, highest_stage) "
        "VALUES (?,?,?,?,?,?)",
        ("p12", user_key, bon_user_id, "2026-05-28T10:00:00Z", "signed_up", "signed_up"),
    )
    conn.commit()
    conn.close()


# ---- resolve_thresholds ----

def test_resolve_defaults_and_overrides():
    assert resolve_thresholds(None) == DEFAULT_THRESHOLDS
    assert resolve_thresholds({}) == DEFAULT_THRESHOLDS
    r = resolve_thresholds({"thresholds": {"activated_saver_confirmed_metrics": 1, "at_risk_inactive_days": 5}})
    assert r["activated_saver_confirmed_metrics"] == 1 and r["at_risk_inactive_days"] == 5
    assert r["activation_meaningful_messages"] == DEFAULT_THRESHOLDS["activation_meaningful_messages"]  # untouched
    # the config_json column is a JSON string — it must be parsed
    assert resolve_thresholds(json.dumps({"thresholds": {"likely_lover_active_days": 4}}))["likely_lover_active_days"] == 4


def test_resolve_rejects_invalid():
    r = resolve_thresholds({"thresholds": {
        "unknown_key": 9, "activation_meaningful_messages": -1, "at_risk_inactive_days": "x", "likely_lover_active_days": True,
    }})
    assert "unknown_key" not in r
    assert r["activation_meaningful_messages"] == DEFAULT_THRESHOLDS["activation_meaningful_messages"]  # negative rejected
    assert r["at_risk_inactive_days"] == DEFAULT_THRESHOLDS["at_risk_inactive_days"]                    # string rejected
    assert r["likely_lover_active_days"] == DEFAULT_THRESHOLDS["likely_lover_active_days"]              # bool rejected


# ---- funnel honors overrides; defaults reproduce behavior ----

def test_saver_bar_override_changes_stage():
    facts = {"onboarding_complete": True, "credit_score": 700, "meaningful_credgpt_messages": 3,
             "pmf_success_metrics": {"linked_financial_context": "confirmed"}}  # activated + exactly 1 confirmed metric
    assert evaluate_funnel(facts).stage == "activated_user"  # default bar = 2 confirmed: 1 < 2
    lowered = resolve_thresholds({"thresholds": {"activated_saver_confirmed_metrics": 1}})
    assert evaluate_funnel(facts, thresholds=lowered).stage == "activated_saver"  # bar = 1: 1 >= 1


def test_metric_threshold_override():
    facts = {"meaningful_threads": 1, "meaningful_credgpt_messages": 3}
    assert "activation_depth" not in compute_pmf_success_metrics(facts)  # default: threads<2 and msgs<5
    lowered = resolve_thresholds({"thresholds": {"activation_depth_messages": 3}})
    assert compute_pmf_success_metrics(facts, thresholds=lowered).get("activation_depth") == "confirmed"  # msgs>=3 now


def test_defaults_reproduce_behavior():
    facts = {"onboarding_complete": True, "credit_score": 700, "meaningful_credgpt_messages": 3,
             "pmf_success_metrics": {"linked_financial_context": "confirmed", "activation_depth": "confirmed"}}
    assert evaluate_funnel(facts).stage == evaluate_funnel(facts, thresholds=DEFAULT_THRESHOLDS).stage == "activated_saver"


# ---- end-to-end: cohort config flows to the snapshot funnel ----

def test_cohort_config_threshold_flows_to_snapshot():
    store = _store(config={"thresholds": {"activated_saver_confirmed_metrics": 1}})
    _seed_user(store, "user:1", "1")
    result = store.apply_daily_snapshot("p12", "user:1", "2026-05-28", {
        "onboarding_complete": True, "credit_score": 700, "meaningful_credgpt_messages": 3,
        "pmf_success_metrics": {"linked_financial_context": "confirmed"},
    })
    # The cohort's bar=1 override is resolved from config_json and used by the funnel;
    # with the default bar=2 this same user would be only activated_user.
    assert result["stage"] == "activated_saver"


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
