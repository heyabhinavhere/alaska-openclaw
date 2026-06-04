"""P14: friction-fact derivation in enrich_facts.

intake_period (recent signup + not onboarded → stuck_onboarding) and inactive_days
(a chat-activity proxy → at_risk) are derived from the summarizer/360 profile and
drive the funnel's friction queues. failed_link_attempts (→ high_intent) is
intentionally NOT derived — the 360 profile carries no link-failure signal (a
deferred data source). The summarizer is injected for deterministic dates.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.collectors import user360  # noqa: E402
from pmf_os.funnel import evaluate_funnel  # noqa: E402


def _summary(*, days_since_signup, onboarded, score=0):
    return {
        "identity": {"days_since_signup": days_since_signup, "name": "U"},
        "linking": {"card_linked": False, "bank_linked": False, "credit_activated": onboarded},
        "credit": {"score": score} if score else {},
        "debt": {}, "liquidity": {}, "income": {}, "spending": {}, "subscriptions": {},
    }


def _payload(turns=None):
    return {"user_id": 5001, "profile": {}, "chat": {"recent_turns": turns or []}, "tasks": [], "budgeting": {}}


def _turn(day):
    return {
        "thread_id": "t1",
        "question": "How do I pay down my highest-APR credit card balance?",
        "answer": "Target the highest-APR card first while paying minimums on the rest.",
        "created_at": f"{day}T18:00:00Z",
    }


def _enrich(summary, payload, as_of=None):
    return user360.enrich_facts(payload, summarize_fn=lambda p: summary, as_of_date=as_of)["daily_facts"]


def test_intake_period_drives_stuck_onboarding():
    df = _enrich(_summary(days_since_signup=2, onboarded=False), _payload())
    assert df["intake_period"] is True
    assert "stuck_onboarding" in evaluate_funnel(df).flags


def test_intake_period_false_when_onboarded_or_old():
    onboarded = _enrich(_summary(days_since_signup=2, onboarded=True, score=700), _payload())
    assert onboarded["intake_period"] is False
    old = _enrich(_summary(days_since_signup=30, onboarded=False), _payload())
    assert old["intake_period"] is False
    assert "stuck_onboarding" not in evaluate_funnel(old).flags


def test_inactive_days_chat_proxy_drives_at_risk():
    # real user (score>0) who last chatted 9 days before the snapshot → at_risk
    df = _enrich(
        _summary(days_since_signup=20, onboarded=True, score=700),
        _payload([_turn("2026-06-01")]), as_of="2026-06-10",
    )
    assert df["inactive_days"] == 9
    assert "at_risk" in evaluate_funnel(df).flags


def test_inactive_days_unset_without_activity_or_reference():
    no_activity = _enrich(
        _summary(days_since_signup=20, onboarded=True, score=700), _payload(), as_of="2026-06-10",
    )
    assert "inactive_days" not in no_activity  # never chatted → not flagged at_risk
    no_ref = _enrich(
        _summary(days_since_signup=20, onboarded=True, score=700), _payload([_turn("2026-06-01")]),
    )
    assert "inactive_days" not in no_ref  # no as_of_date → not computed


def test_failed_link_attempts_not_derived():
    # Documents the deferral: enrich_facts does NOT set failed_link_attempts (no 360
    # link-failure signal), so high_intent stays dark until a data source exists.
    df = _enrich(_summary(days_since_signup=2, onboarded=False), _payload())
    assert "failed_link_attempts" not in df


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
