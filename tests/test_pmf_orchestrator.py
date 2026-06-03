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


def test_rerun_is_idempotent():
    store = _store()
    _run(store)
    run2 = _run(store)
    assert run2["users"]["total"] == 2
    assert run2["users"]["enriched"] == 2
    assert len(store.list_users("pmf-orch")) == 2  # no duplicate rows on re-run


def test_no_intake_uses_existing_registry():
    store = _store()
    _run(store)  # seed the registry via intake
    run = _run(store, do_intake=False)
    assert run["intake"] is None
    assert run["users"]["enriched"] == 2


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
