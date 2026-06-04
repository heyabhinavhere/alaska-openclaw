"""P8 tests: the daily briefing (interpretation layer) — facts aggregation, the
narrator seam (skipped/completed/failed), the transitions read, and orchestrator
wiring with a fake narrator (no live LLM)."""

from __future__ import annotations

import gzip
import io
import json
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.daily_briefing import build_briefing_facts, generate_daily_briefing, normalize_briefing  # noqa: E402
from pmf_os.orchestrator import run_cohort_day  # noqa: E402
from pmf_os.store import PmfStore  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WS, WE = "2026-05-27T00:00:00-07:00", "2026-05-29T23:59:59-07:00"


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_p8_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="p8", name="P8", signup_window_start=WS, signup_window_end=WE, activate=True)
    return store


def test_build_briefing_facts_movements_and_queues():
    summary = {"total_signup_users": 100, "real_users": 60, "stage_counts": {"activated_user": 12, "likely_lover": 3}}
    movements = [
        {"user_key": "user:1", "to_stage": "activated_user", "transition_type": "promotion"},
        {"user_key": "user:2", "to_stage": "signed_up", "transition_type": "demotion"},
        {"user_key": "user:3", "to_stage": "activated_user", "transition_type": "recomputed"},  # not promo/demo
    ]
    queues = [
        {"queue_type": "high_intent", "severity": "P1", "user_key": "user:1", "title": "hit link failure", "reason": "x"},
        {"queue_type": "at_risk", "severity": "P2", "user_key": "user:9", "title": "quiet", "reason": "y"},
    ]
    users = [{"user_key": "user:1", "name": "Alicia"}]
    f = build_briefing_facts(snapshot_date="2026-05-28", summary=summary, movements=movements, open_queues=queues, users=users)
    assert f["funnel"]["real_users"] == 60
    assert f["movements"]["promotion_count"] == 1 and f["movements"]["demotion_count"] == 1
    assert f["movements"]["promotions"][0]["name"] == "Alicia"
    assert f["open_queues"]["counts"] == {"at_risk": 1, "high_intent": 1}
    assert len(f["open_queues"]["priority_items"]) == 1  # only P0/P1
    assert f["open_queues"]["priority_items"][0]["queue_type"] == "high_intent"
    assert f["open_queues"]["priority_items"][0]["name"] == "Alicia"


def test_generate_daily_briefing_seam():
    facts = {"funnel": {}, "schema_version": "pmf_daily_briefing.v1"}
    assert generate_daily_briefing(facts, narrator=None)["narrative_status"] == "skipped"

    def fake(f):
        assert "funnel" in f
        return {"headline": "good day", "who_needs_you": [{"user": "Alicia", "why": "stuck", "suggested_action": "nudge"}]}

    done = generate_daily_briefing(facts, narrator=fake)
    assert done["narrative_status"] == "completed"
    assert done["narrative"]["headline"] == "good day"
    assert done["narrative"]["who_needs_you"][0]["user"] == "Alicia"

    def boom(f):
        raise RuntimeError("llm 500")

    failed = generate_daily_briefing(facts, narrator=boom)
    assert failed["narrative_status"] == "failed" and "llm 500" in failed["error"]


def test_normalize_briefing_coerces():
    n = normalize_briefing({
        "headline": "h", "what_changed": ["a", 2],
        "who_needs_you": [{"user": "x"}, "junk"], "recommendations": ["r"],
    })
    assert n["what_changed"] == ["a", "2"]
    assert n["who_needs_you"] == [{"user": "x", "why": "", "suggested_action": ""}]  # dict coerced, "junk" dropped


def test_recent_funnel_transitions_filters_by_type():
    store = _store()
    conn = sqlite3.connect(store.db_path)
    for uk, frm, to, ttype in [
        ("user:1", "signed_up", "activated_user", "promotion"),
        ("user:2", "activated_user", "signed_up", "demotion"),
        ("user:3", "activated_user", "activated_user", "recomputed"),
    ]:
        conn.execute(
            "INSERT INTO pmf_funnel_transitions (cohort_id, user_key, from_stage, to_stage, transition_type, "
            "evidence_state, freshness_state, confidence) VALUES (?,?,?,?,?,?,?,?)",
            ("p8", uk, frm, to, ttype, "confirmed", "confirmed", 1.0),
        )
    conn.commit()
    conn.close()
    moves = store.recent_funnel_transitions("p8")
    assert {m["transition_type"] for m in moves} == {"promotion", "demotion"}  # 'recomputed' filtered out
    assert len(moves) == 2


# ---- orchestrator wiring (no live LLM) ----

def _signup(uid: int) -> dict:
    return {"event_type": "onboarding_step_completed", "event_properties": {"step_name": "phone_number_submitted"},
            "event_time": "2026-05-28 10:00:00", "insert_id": f"ins-{uid}", "user_id": str(uid)}


def _export_zip(events: list) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("p/0.json.gz", gzip.compress("\n".join(json.dumps(e) for e in events).encode()))
    return buf.getvalue()


def _profile(uid: int) -> dict:
    return {
        "user_id": uid,
        "profile": {"first_name": f"U{uid}", "is_card_added": True, "is_bank_added": False, "is_credit_activated": True, "created_at": "2026-05-27T10:00:00Z"},
        "credit_report_history": [{"report_date": "2026-05-24", "credit_score": {"@_Value": "700", "@_ModelNameTypeOtherDescription": "X"}}],
        "plaid_profiles": {"card_profile": {}, "bank_profile": {}},
        "chat": {"recent_turns": [{"thread_id": "t1", "question": "how should i pay down my credit card debt", "answer": f"a{i}", "created_at": "2026-05-28T12:00:00Z"} for i in range(4)]},
    }


def test_orchestrator_populates_briefing_with_fake_narrator():
    store = _store()
    captured: dict = {}

    def export_fetcher(a, b):
        return _export_zip([_signup(1001)])

    def profile_fetcher(uid):
        return 200, json.dumps(_profile(uid)).encode()

    def narrator(facts):
        captured["facts"] = facts
        return {"headline": "day 1 looks healthy", "what_changed": ["1 new real user"]}

    art = str(Path(tempfile.mkdtemp(prefix="p8art_")))
    run = run_cohort_day(store, "p8", "2026-05-28", do_intake=True, render=False, artifact_root=art,
                         export_fetcher=export_fetcher, profile_fetcher=profile_fetcher, daily_narrator=narrator)
    assert run["briefing"]["narrative_status"] == "completed"
    assert run["briefing"]["narrative"]["headline"] == "day 1 looks healthy"
    assert "funnel" in captured["facts"]  # the deterministic facts were handed to the narrator

    # Default (no narrator) -> skipped, no tokens spent, behavior unchanged.
    run2 = run_cohort_day(store, "p8", "2026-05-28", do_intake=False, render=False, artifact_root=art,
                          profile_fetcher=profile_fetcher)
    assert run2["briefing"]["narrative_status"] == "skipped"


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
