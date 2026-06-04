"""End-to-end tests for the PMF daily orchestrator — fixtures only, no live API.

Drives run_cohort_day with injected collectors (Amplitude export, User 360 search +
profile) and the real file-loaded summarizer, covering: the full intake -> enrich ->
snapshot -> report loop, partial-failure tolerance, idempotent re-runs, and the
no-intake path.
"""

from __future__ import annotations

import gzip
import io
import json
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.orchestrator import run_cohort_day  # noqa: E402
from pmf_os.store import PmfStore  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WINDOW_START = "2026-06-11T00:00:00-07:00"
WINDOW_END = "2026-06-13T23:59:59-07:00"
DATE = "2026-06-13"

EMAIL_TO_UID = {"aaa@example.com": 1001, "bbb@example.com": 1002}


def _signup_event(amplitude_id: int, email: str) -> dict:
    return {
        "event_type": "onboarding_step_completed",
        "event_properties": {"step_name": "phone_number_submitted"},
        "event_time": "2026-06-11 10:15:00",
        "insert_id": f"ins-{amplitude_id}",
        "amplitude_id": amplitude_id,
        "user_properties": {"gp:email": email},
    }


def _export_zip(events: list[dict]) -> bytes:
    ndjson = "\n".join(json.dumps(e) for e in events).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("645917/2026-06-11/0.json.gz", gzip.compress(ndjson))
    return buf.getvalue()


def _profile(uid: int, *, real_turns: int = 3) -> dict:
    turns = [
        {"thread_id": "t1", "question": "how should i pay down my credit card debt", "answer": f"a{i}", "created_at": "2026-06-12T18:00:00Z"}
        for i in range(real_turns)
    ]
    return {
        "user_id": uid,
        "profile": {
            "first_name": f"U{uid}",
            "is_card_added": True,
            "is_bank_added": False,
            "is_credit_activated": True,
            "created_at": "2026-06-11T10:20:00Z",
        },
        "credit_report_history": [
            {
                "report_date": "2026-05-24",
                "credit_score": {
                    "@_Value": "700",
                    "@_Date": "2026-05-24",
                    "@CreditRepositorySourceType": "Equifax",
                    "@_ModelNameTypeOtherDescription": "EquifaxVantageScore3.0",
                },
            }
        ],
        "plaid_profiles": {"card_profile": {"total_cc_balance_exact": 1000}, "bank_profile": {}},
        "chat": {"total_threads": 1, "recent_turns": turns, "intent_breakdown": {"debt": real_turns}, "feedback_summary": {}},
    }


def _fake_export(start_t: str, end_t: str) -> bytes:
    return _export_zip([_signup_event(501, "aaa@example.com"), _signup_event(502, "bbb@example.com")])


def _fake_search(query_type: str, value: str) -> "tuple[int, bytes]":
    if query_type != "email":
        return 200, b"[]"
    uid = EMAIL_TO_UID.get(value)
    return 200, json.dumps([{"user_id": uid}] if uid else []).encode()


def _fake_profile(uid: int) -> "tuple[int, bytes]":
    return 200, json.dumps(_profile(uid)).encode()


def _fake_profile_b_fails(uid: int) -> "tuple[int, bytes]":
    if uid == 1002:
        return 404, b""
    return 200, json.dumps(_profile(uid)).encode()


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_orch_")) / "alaska_pmf.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="pmf-orch", name="Orch", signup_window_start=WINDOW_START, signup_window_end=WINDOW_END, activate=True)
    return store


def _run(store, *, profile_fetcher=None, do_intake=True):
    return run_cohort_day(
        store, "pmf-orch", DATE,
        do_intake=do_intake,
        artifact_root=str(Path(tempfile.mkdtemp(prefix="pmf_orch_art_"))),
        export_fetcher=_fake_export, search_fetcher=_fake_search,
        profile_fetcher=profile_fetcher or _fake_profile,
    )


def test_run_cohort_day_end_to_end():
    store = _store()
    run = _run(store)

    assert run["intake"]["ingested"] == 2
    assert run["users"] == {"total": 2, "enriched": 2, "unresolved": 0, "failed": 0}
    assert run["errors"] == []
    assert run["summary"]["real_users"] == 2
    assert run["summary"]["stage_counts"]["activated_user"] == 2  # real + 3 meaningful turns
    assert run["report"]["status"] in ("qa_passed", "rendered")
    assert Path(run["report"]["html_path"]).exists()
    assert "Enriched: 2/2" in run["slack_summary"]


def test_partial_failure_one_user_does_not_sink_run():
    store = _store()
    run = _run(store, profile_fetcher=_fake_profile_b_fails)
    assert run["users"]["enriched"] == 1
    assert run["users"]["failed"] == 1
    assert any(e.get("step") == "fetch_profile" for e in run["errors"])
    assert run["report"] is not None  # run completed and still rendered


def _fake_profile_no_turns(uid: int) -> "tuple[int, bytes]":
    return 200, json.dumps(_profile(uid, real_turns=0)).encode()


def _fake_segmentation(definition: str, start: str, end: str) -> dict:
    return {"data": {"series": [[4]]}}  # 4 messages → fallback supplies activation


def test_latency_record_structure_and_counts():
    store = _store()
    run = _run(store)
    lat = run["latency"]
    assert set(lat) == {"resolve", "profile", "amplitude_fallback", "per_user_enrich"}
    for phase in lat.values():
        assert set(phase) == {"count", "total_s", "mean_s", "p50_s", "p95_s"}
    assert lat["resolve"]["count"] == 2
    assert lat["profile"]["count"] == 2
    assert lat["per_user_enrich"]["count"] == 2
    assert lat["amplitude_fallback"]["count"] == 0  # 3 real turns each → no fallback
    # partial failure: profile is timed for both (before the status check); only 1 fully enriched
    run2 = _run(_store(), profile_fetcher=_fake_profile_b_fails)
    assert run2["latency"]["profile"]["count"] == 2
    assert run2["latency"]["per_user_enrich"]["count"] == 1


def test_latency_captures_amplitude_fallback():
    store = _store()
    run = run_cohort_day(
        store, "pmf-orch", DATE,
        artifact_root=str(Path(tempfile.mkdtemp(prefix="pmf_orch_art_"))),
        export_fetcher=_fake_export, search_fetcher=_fake_search,
        profile_fetcher=_fake_profile_no_turns, segmentation_fetcher=_fake_segmentation,
    )
    assert run["amplitude_fallback_used"] == 2  # both users had no 360 chat → fell back
    assert run["latency"]["amplitude_fallback"]["count"] == 2  # both fallback calls timed
    assert run["latency"]["per_user_enrich"]["count"] == 2


def test_default_enrichment_mode_is_full_and_selects_everyone():
    store = _store()
    run = _run(store)
    assert run["enrichment"]["mode"] == "full"  # default — unchanged behavior
    assert run["enrichment"]["selected"] == run["enrichment"]["registry_total"] == 2
    assert run["enrichment"]["skipped_not_due"] == 0


def test_incremental_mode_wires_through_first_run_selects_all_new():
    store = _store()
    # Reconfigure the cohort to incremental with cap=0 (upsert via create_cohort).
    store.create_cohort(
        cohort_id="pmf-orch", name="Orch",
        signup_window_start=WINDOW_START, signup_window_end=WINDOW_END, activate=True,
        config={"enrichment": {"mode": "incremental", "slow_refresh_cap": 0}},
    )
    run = _run(store)
    assert run["enrichment"]["mode"] == "incremental"
    assert run["enrichment"]["registry_total"] == 2
    # Both users are NEW (no prior snapshot) → enriched even with slow_refresh_cap=0.
    assert run["enrichment"]["selected"] == 2
    assert run["users"]["enriched"] == 2


def _slow_then_fail_for_1002(uid: int) -> "tuple[int, bytes]":
    # Simulate a hung User-360 profile call: block past the deadline, then error
    # (so the abandoned worker does no late DB write — race-free).
    if uid == 1002:
        time.sleep(1.0)
        return 500, b""
    return 200, json.dumps(_profile(uid)).encode()


def test_per_user_deadline_skips_hung_user_without_sinking_run():
    store = _store()
    run = run_cohort_day(
        store, "pmf-orch", DATE,
        artifact_root=str(Path(tempfile.mkdtemp(prefix="pmf_orch_art_"))),
        export_fetcher=_fake_export, search_fetcher=_fake_search,
        profile_fetcher=_slow_then_fail_for_1002,
        enrich_user_timeout=0.3,  # < the 1s hang → the stuck user is abandoned, not blocking
    )
    assert run["users"]["enriched"] == 1  # the fast user still completes
    assert run["users"]["failed"] == 1    # the hung user is skipped by the watchdog
    assert any(e.get("step") == "enrich_timeout" for e in run["errors"])
    assert run["report"] is not None       # the run completed end-to-end


def _unlinked_onboarded_profile(uid: int) -> "tuple[int, bytes]":
    p = _profile(uid)
    p["profile"]["is_card_added"] = False  # onboarded but neither channel linked
    p["profile"]["is_bank_added"] = False
    return 200, json.dumps(p).encode()


def _seg_card_failed(e_json: str, start: str, end: str) -> dict:
    ev = json.loads(e_json)["event_type"]
    return {"data": {"series": [[1 if ev == "add_card_unsuccessful" else 0]]}}


def test_failed_link_amplitude_fallback_opens_high_intent():
    store = _store()
    run = run_cohort_day(
        store, "pmf-orch", DATE,
        artifact_root=str(Path(tempfile.mkdtemp(prefix="pmf_orch_art_"))),
        export_fetcher=_fake_export, search_fetcher=_fake_search,
        profile_fetcher=_unlinked_onboarded_profile, segmentation_fetcher=_seg_card_failed,
    )
    assert run["users"]["enriched"] == 2
    # onboarded + unlinked + a card-link failure (from Amplitude) → high_intent opens
    qtypes = {q["queue_type"] for q in store.open_queue_items("pmf-orch")}
    assert "high_intent" in qtypes
    assert "plaid_failed" in qtypes


def test_rerun_is_idempotent():
    store = _store()
    _run(store)
    with store.connect() as conn:
        transitions_after_first = conn.execute("SELECT count(*) FROM pmf_funnel_transitions").fetchone()[0]
    run2 = _run(store)
    assert run2["users"]["total"] == 2
    assert run2["users"]["enriched"] == 2
    assert len(store.list_users("pmf-orch")) == 2  # no duplicate rows on re-run
    with store.connect() as conn:
        transitions_after_rerun = conn.execute("SELECT count(*) FROM pmf_funnel_transitions").fetchone()[0]
    # An identical re-run must add ZERO funnel transitions — no no-op 'recomputed'
    # rows (the §6/§10 idempotency gate). Regression guard for the doubling bug.
    assert transitions_after_rerun == transitions_after_first


def test_no_intake_uses_existing_registry():
    store = _store()
    _run(store)  # seed the registry via intake
    run = _run(store, do_intake=False)
    assert run["intake"] is None
    assert run["users"]["enriched"] == 2


def test_run_cohort_day_delivers_to_slack():
    store = _store()
    sent = {}

    def fake_sender(channel, summary, html_path):
        sent.update(channel=channel, summary=summary, html_path=html_path)
        return {"ok": True, "summary": {"ok": True, "ts": "1.1"}, "file": {"ok": True}}

    run = run_cohort_day(
        store, "pmf-orch", DATE, do_intake=True,
        artifact_root=str(Path(tempfile.mkdtemp(prefix="pmf_orch_art_"))),
        export_fetcher=_fake_export, search_fetcher=_fake_search, profile_fetcher=_fake_profile,
        slack_sender=fake_sender, slack_channel="C123",
    )
    assert run["delivery"]["ok"] is True
    assert sent["channel"] == "C123"
    assert "PMF Cohort daily run" in sent["summary"]
    assert sent["html_path"] and Path(sent["html_path"]).exists()


def test_run_cohort_day_delivery_failure_is_captured():
    store = _store()

    def boom(channel, summary, html_path):
        raise RuntimeError("slack 503")

    run = run_cohort_day(
        store, "pmf-orch", DATE, do_intake=True,
        artifact_root=str(Path(tempfile.mkdtemp(prefix="pmf_orch_art_"))),
        export_fetcher=_fake_export, search_fetcher=_fake_search, profile_fetcher=_fake_profile,
        slack_sender=boom, slack_channel="C123",
    )
    assert run["delivery"]["ok"] is False
    assert any(e.get("step") == "deliver" for e in run["errors"])
    assert run["report"] is not None  # delivery failure didn't sink the run


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
