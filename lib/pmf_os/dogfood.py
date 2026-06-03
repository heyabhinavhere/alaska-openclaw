"""Synthetic PMF cohort generator + end-to-end dogfood harness.

Deterministic (seeded) generation of a realistic-but-fake cohort so the whole
PMF pipeline can be validated end-to-end BEFORE live Amplitude / User 360 data
exists:

    intake -> enrich -> daily snapshot (funnel) -> CredGPT review -> report

The generator shape (signup event + profile facts + daily facts + chat turns)
mirrors what the real Amplitude/User 360 collectors will produce, so the same
harness backs the historical-backfill validation in later phases. Stdlib only.

Manual run:
    PYTHONPATH=lib python3 -m pmf_os.dogfood --n 40
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .store import PmfStore, user_key_from_event

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"

COHORT_ID = "pmf-dogfood"
WINDOW_START = "2026-06-11T00:00:00-07:00"
WINDOW_END = "2026-06-13T23:59:59-07:00"
SNAPSHOT_DATE = "2026-06-13"

# One bucket per funnel/queue path we want exercised. Cycled across N users so a
# synthetic cohort always spreads across the funnel and opens varied queues.
BUCKETS = [
    "onboarded",              # real user, not yet activated
    "activated",              # 3+ meaningful messages
    "saver_computed",         # 2+ confirmed PMF metrics
    "saver_candidate",        # 2+ candidate metrics -> needs_human_review
    "likely_lover",           # saver + repeated engagement
    "high_intent_failed_link",# failed link -> high_intent + plaid_failed
    "at_risk",                # activated then went quiet
    "signed_up_stuck",        # never finished onboarding -> stuck_onboarding
]


def _event_time(day_offset: int, rnd: random.Random) -> str:
    base = datetime(2026, 6, 11, 9, 0, 0)
    dt = base + timedelta(days=day_offset, minutes=rnd.randint(0, 540))
    return dt.strftime("%Y-%m-%dT%H:%M:%S-07:00")


def _profile(bucket: str) -> dict[str, Any]:
    if bucket == "signed_up_stuck":
        return {"onboarding_complete": False, "credit_score": 0, "furthest_onboarding_step": "spinwheel"}
    return {
        "onboarding_complete": True,
        "credit_score": 680,
        "furthest_onboarding_step": "onboarding_complete",
        "is_bank_linked": True,
    }


def _facts(bucket: str) -> dict[str, Any]:
    base: dict[str, Any] = {
        "onboarding_complete": True,
        "credit_score": 680,
        "active_days": ["2026-06-11", "2026-06-12", "2026-06-13"],
    }
    if bucket == "signed_up_stuck":
        return {
            "onboarding_complete": False,
            "credit_score": 0,
            "intake_period": True,
            "furthest_onboarding_step": "spinwheel",
            "spinwheel_failed": True,
        }
    if bucket == "onboarded":
        return {**base, "meaningful_credgpt_messages": 0}
    if bucket == "activated":
        return {**base, "meaningful_credgpt_messages": 4}
    if bucket == "high_intent_failed_link":
        return {**base, "meaningful_credgpt_messages": 1, "failed_link_attempts": ["plaid:timeout"]}
    if bucket == "at_risk":
        return {**base, "meaningful_credgpt_messages": 3, "inactive_days": 5, "active_days": ["2026-06-11"]}
    if bucket == "saver_computed":
        return {
            **base,
            "meaningful_credgpt_messages": 5,
            "value_actions": ["card_link_success"],
            "active_days": ["2026-06-13"],  # single active day -> stays at activated_saver
            "pmf_success_metrics": {
                "activation_depth": "confirmed",
                "linked_financial_context": "confirmed",
                "repeat_engagement": False,
                "financial_action": False,
                "qualitative_positive_signal": False,
                "retained_value": False,
            },
        }
    if bucket == "saver_candidate":
        return {
            **base,
            "meaningful_credgpt_messages": 3,
            "value_actions": ["budget_created"],
            "active_days": ["2026-06-13"],  # single active day -> stays at activated_saver
            "pmf_success_metrics": {
                "activation_depth": "candidate",
                "repeat_engagement": "candidate",
                "financial_action": False,
                "linked_financial_context": False,
                "qualitative_positive_signal": False,
                "retained_value": False,
            },
        }
    if bucket == "likely_lover":
        return {
            **base,
            "meaningful_credgpt_messages": 6,
            "value_actions": ["paydown_plan_created"],
            "pmf_success_metrics": {
                "activation_depth": "confirmed",
                "linked_financial_context": "confirmed",
                "repeat_engagement": "confirmed",
                "financial_action": False,
                "qualitative_positive_signal": False,
                "retained_value": False,
            },
        }
    return base


def _turns(bucket: str, idx: int) -> list[dict[str, Any]]:
    turns = [
        {
            "thread_id": f"t{idx}",
            "turn_id": f"t{idx}-1",
            "event_time": "2026-06-12T18:00:00Z",
            "question": "How should I pay down my credit card balances?",
            "answer": (
                "Target the highest-APR card first while paying minimums on the rest; "
                "getting utilization under 30% should help your score within a cycle."
            ),
            "feedback": "good",
            "user_context_present": True,
        }
    ]
    # A real question CredGPT failed to answer (empty answer) -> a quality failure
    # the Observatory must flag (this is NOT a proactive briefing).
    if bucket in ("high_intent_failed_link", "at_risk", "saver_candidate"):
        turns.append(
            {
                "thread_id": f"t{idx}",
                "turn_id": f"t{idx}-2",
                "event_time": "2026-06-12T18:05:00Z",
                "question": "Why did my bank link fail?",
                "answer": "",
                "feedback": "bad",
                "chat_stopped_by_user": True,
                "user_context_present": True,
            }
        )
    return turns


def build_synthetic_cohort(n: int = 40, *, seed: int = 7) -> dict[str, Any]:
    """Deterministically build N in-window users plus a few excluded events."""
    rnd = random.Random(seed)
    events: list[dict[str, Any]] = []
    users: list[dict[str, Any]] = []
    for i in range(n):
        bucket = BUCKETS[i % len(BUCKETS)]
        uid = str(2000 + i)
        event = {
            "event_type": "onboarding_step_completed",
            "step_name": "phone_number_submitted",
            "event_time": _event_time(i % 3, rnd),
            "event_id": f"amp-{uid}",
            "user_id": uid,
            "user_properties": {
                "gp:first_name": f"User{i}",
                "gp:email": f"user{i}@example.com",
                "gp:phone_number": f"+1555{1000000 + i}",
            },
        }
        events.append(event)
        users.append(
            {
                "user_key": user_key_from_event(event),
                "bucket": bucket,
                "profile": _profile(bucket),
                "facts": _facts(bucket),
                "turns": _turns(bucket, i),
            }
        )
    # Excluded events: outside the window (before/after) + a non-entry step.
    events.append({"event_type": "onboarding_step_completed", "step_name": "phone_number_submitted", "event_time": "2026-06-09T10:00:00-07:00", "event_id": "amp-early", "user_id": "9001", "user_properties": {"gp:first_name": "Early"}})
    events.append({"event_type": "onboarding_step_completed", "step_name": "phone_number_submitted", "event_time": "2026-06-20T10:00:00-07:00", "event_id": "amp-late", "user_id": "9002", "user_properties": {"gp:first_name": "Late"}})
    events.append({"event_type": "onboarding_step_completed", "step_name": "email_submitted", "event_time": _event_time(1, rnd), "event_id": "amp-wrongstep", "user_id": "9003"})
    return {"events": events, "users": users}


def _ensure_migrated(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(MIGRATION.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def run_dogfood(db_path: str | None = None, *, n: int = 40, seed: int = 7, snapshot_date: str = SNAPSHOT_DATE) -> dict[str, Any]:
    """Drive the full pipeline against a synthetic cohort; return rich results."""
    if db_path is None:
        db_path = str(Path(tempfile.mkdtemp(prefix="pmf_dogfood_")) / "alaska_pmf.db")
    _ensure_migrated(db_path)
    store = PmfStore(db_path)
    store.create_cohort(
        cohort_id=COHORT_ID,
        name="PMF Dogfood Cohort",
        signup_window_start=WINDOW_START,
        signup_window_end=WINDOW_END,
        expected_signups=1000,
        expected_real_users=750,
        activate=True,
    )
    spec = build_synthetic_cohort(n, seed=seed)
    ingest = store.ingest_signup_events(COHORT_ID, spec["events"])
    for user in spec["users"]:
        store.update_user_profile(COHORT_ID, user["user_key"], user["profile"])
        store.apply_daily_snapshot(COHORT_ID, user["user_key"], snapshot_date, user["facts"])
        for turn in user["turns"]:
            store.record_credgpt_turn(COHORT_ID, user["user_key"], turn)
    clusters = store.refresh_credgpt_clusters(COHORT_ID)
    team = store.generate_report_snapshot(COHORT_ID, report_type="daily_cockpit", privacy_tier="team", snapshot_date=snapshot_date)
    founder = store.generate_report_snapshot(COHORT_ID, report_type="founder_daily", privacy_tier="founder", snapshot_date=snapshot_date)
    return {"db_path": db_path, "store": store, "ingest": ingest, "clusters": clusters, "team": team, "founder": founder}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PMF Cohort OS dogfood harness")
    parser.add_argument("--db", default=None, help="DB path (default: throwaway temp DB)")
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    result = run_dogfood(args.db, n=args.n, seed=args.seed)
    out = {
        "db_path": result["db_path"],
        "ingest": result["ingest"],
        "summary": result["team"]["summary"],
        "team_user_rows": len(result["team"]["users"]),
        "founder_user_rows": len(result["founder"]["users"]),
        "clusters": len(result["clusters"]),
    }
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
