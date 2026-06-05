"""V5 command-taxonomy guard (behavioral — drives the real CLI, not skill text).

Asserts the `case-file` CLI (the `!pmf user <id>` / `!pmf case <id>` query) returns a
self-identifying `label: "PMF cohort case file"` so the model never conflates it with
`!case <id>` (the general 360 file), and that member / non-member / no-active-cohort all
behave cleanly. This is the V5 half of the `!case` vs `!pmf user` taxonomy reconciliation;
the command-layer `routing_eval.jsonl` rows (`!pmf user 2903`→pmf, `!case 1414`→case) are
proposed to the parallel agent in the PR, not owned here."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.store import PmfStore  # noqa: E402

REPO = Path(__file__).parent.parent
MIGRATION = REPO / "migrations" / "0005_pmf_cohort_os.sql"
CLI = REPO / "lib" / "pmf_cohort_os.py"
WS, WE = "2026-05-27T00:00:00-07:00", "2026-05-29T23:59:59-07:00"
LABEL = "PMF cohort case file"


def _db(*, activate: bool = True) -> tuple[str, PmfStore]:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_cmdroute_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="cr", name="CR", signup_window_start=WS, signup_window_end=WE, activate=activate)
    return db, store


def _seed_member(store: PmfStore, db: str) -> None:
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO pmf_cohort_users (cohort_id, user_key, bon_user_id, signup_event_time, current_stage, highest_stage) "
        "VALUES (?,?,?,?,?,?)",
        ("cr", "user:2903", "2903", "2026-05-28T10:00:00Z", "signed_up", "signed_up"),
    )
    conn.commit()
    conn.close()
    # the real write path: build_case_file -> pmf_user_case_files
    store.apply_daily_snapshot("cr", "user:2903", "2026-05-28", {
        "onboarding_complete": True, "credit_score": 555, "meaningful_credgpt_messages": 0,
        "card_linked": False, "bank_linked": False, "pmf_success_metrics": {},
    })


def _run_case_file(db: str, *args: str) -> dict:
    """Invoke the actual `case-file` subcommand and return its `result` payload."""
    env = dict(os.environ, PYTHONPATH=str(REPO / "lib"))
    proc = subprocess.run(
        [sys.executable, str(CLI), "--db", db, "case-file", *args],
        capture_output=True, text=True, env=env, cwd=str(REPO),
    )
    assert proc.returncode == 0, f"CLI failed: {proc.stderr}"
    return json.loads(proc.stdout)["result"]


def test_case_file_member_is_labeled_pmf_cohort():
    db, store = _db()
    _seed_member(store, db)
    r = _run_case_file(db, "--bon-user-id", "2903")
    assert r["label"] == LABEL  # self-identifying — the model titles it correctly
    assert r["case_file"] is not None and r["note"] is None


def test_case_file_non_member_clean_note_still_labeled():
    db, store = _db()
    _seed_member(store, db)
    r = _run_case_file(db, "--bon-user-id", "9999")
    assert r["label"] == LABEL
    assert r["case_file"] is None
    assert "not in this cohort" in r["note"]


def test_case_file_no_active_cohort_is_clean():
    db, _ = _db(activate=False)  # cohort exists but is not active
    r = _run_case_file(db, "--bon-user-id", "1")
    assert r["label"] == LABEL
    assert r["case_file"] is None and r["note"] == "no active cohort"


def test_label_is_pmf_specific_never_general():
    db, store = _db()
    _seed_member(store, db)
    for uid in ("2903", "9999"):
        r = _run_case_file(db, "--bon-user-id", uid)
        assert r["label"] == LABEL
        assert "general" not in r["label"].lower() and "360" not in r["label"]


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
