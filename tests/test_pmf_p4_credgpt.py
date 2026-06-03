"""P4 tests: CredGPT turn ingestion, greeting-filtered meaningful count, and the
Amplitude message-count activation fallback. Fixtures only — no live API."""

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

from pmf_os.collectors import amplitude, user360  # noqa: E402
from pmf_os.orchestrator import run_cohort_day  # noqa: E402
from pmf_os.store import PmfStore  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WS, WE = "2026-05-27T00:00:00-07:00", "2026-05-29T23:59:59-07:00"


def test_fetch_message_count_sums_series_and_filters_user():
    seen: dict[str, str] = {}

    def fake(e_json, start, end):
        seen["e"], seen["start"], seen["end"] = e_json, start, end
        return {"data": {"series": [[2, 3, 0]], "xValues": ["a", "b", "c"]}}

    n = amplitude.fetch_message_count(1002, "2026-05-27", "2026-06-03", segmentation_fetcher=fake)
    assert n == 5  # sum of series[0]
    assert "credgpt_message_sent" in seen["e"] and "1002" in seen["e"] and "gp:user_id" in seen["e"]
    assert seen["start"] == "20260527"  # coerced to project-tz YYYYMMDD
    # empty series -> 0
    assert amplitude.fetch_message_count(1, "2026-05-27", "2026-06-03", segmentation_fetcher=lambda *a: {"data": {"series": []}}) == 0


def test_enrich_greeting_filter_and_chat_turns():
    payload = {
        "user_id": 1001,
        "profile": {"first_name": "A", "is_card_added": False, "is_bank_added": False, "is_credit_activated": True},
        "credit_report_history": [{"report_date": "2026-05-24", "credit_score": {"@_Value": "700", "@_ModelNameTypeOtherDescription": "X"}}],
        "plaid_profiles": {"card_profile": {}, "bank_profile": {}},
        "chat": {"recent_turns": [
            {"thread_id": "t1", "question": "hi", "answer": "hello"},
            {"thread_id": "t1", "question": "how do i lower my credit card utilization", "answer": "pay it down"},
            {"thread_id": "t1", "question": "thanks", "answer": "you're welcome"},
        ]},
    }
    r = user360.enrich_facts(payload)
    assert r["daily_facts"]["meaningful_credgpt_messages"] == 1  # greetings filtered out
    assert len(r["chat_turns"]) == 3  # all real (multi-turn thread) — ingested regardless of "meaningful"


def _signup(uid: int) -> dict:
    return {"event_type": "onboarding_step_completed", "event_properties": {"step_name": "phone_number_submitted"},
            "event_time": "2026-05-28 10:00:00", "insert_id": f"ins-{uid}", "user_id": str(uid)}


def _export_zip(events: list[dict]) -> bytes:
    ndjson = "\n".join(json.dumps(e) for e in events).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("p/0.json.gz", gzip.compress(ndjson))
    return buf.getvalue()


def _profile(uid: int, *, with_chat: bool) -> dict:
    turns = (
        [{"thread_id": "t1", "question": "how should i pay down my credit card debt", "answer": f"a{i}", "created_at": "2026-05-28T12:00:00Z"} for i in range(4)]
        if with_chat else []
    )
    return {
        "user_id": uid,
        "profile": {"first_name": f"U{uid}", "is_card_added": False, "is_bank_added": False, "is_credit_activated": True, "created_at": "2026-05-27T10:00:00Z"},
        "credit_report_history": [{"report_date": "2026-05-24", "credit_score": {"@_Value": "700", "@_ModelNameTypeOtherDescription": "X"}}],
        "plaid_profiles": {"card_profile": {}, "bank_profile": {}},
        "chat": {"recent_turns": turns},
    }


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_p4_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="p4", name="P4", signup_window_start=WS, signup_window_end=WE, activate=True)
    return store


def test_orchestrator_ingests_turns_and_uses_amplitude_fallback():
    store = _store()

    def export_fetcher(a, b):
        return _export_zip([_signup(1001), _signup(1002)])

    def profile_fetcher(uid):
        return 200, json.dumps(_profile(uid, with_chat=(uid == 1001))).encode()

    def seg_fetcher(e_json, start, end):
        # 1002 has empty User 360 chat -> orchestrator falls back to Amplitude
        return {"data": {"series": [[5]]}} if "1002" in e_json else {"data": {"series": [[0]]}}

    run = run_cohort_day(
        store, "p4", "2026-05-29", do_intake=True, render=False,
        artifact_root=str(Path(tempfile.mkdtemp(prefix="p4art_"))),
        export_fetcher=export_fetcher, profile_fetcher=profile_fetcher, segmentation_fetcher=seg_fetcher,
    )

    assert run["users"]["enriched"] == 2
    assert run["amplitude_fallback_used"] == 1   # 1002: empty chat -> Amplitude count 5
    assert run["turns_ingested"] == 4            # 1001's 4 real turns ingested
    # both activate: 1001 via User 360 (4 meaningful), 1002 via Amplitude (5)
    assert run["summary"]["stage_counts"]["activated_user"] == 2

    conn = sqlite3.connect(store.db_path)
    reviews_1001 = conn.execute("SELECT COUNT(*) FROM credgpt_quality_reviews WHERE user_key='user:1001'").fetchone()[0]
    reviews_1002 = conn.execute("SELECT COUNT(*) FROM credgpt_quality_reviews WHERE user_key='user:1002'").fetchone()[0]
    conn.close()
    assert reviews_1001 == 4  # observatory populated from ingested turns
    assert reviews_1002 == 0  # no chat to ingest


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
