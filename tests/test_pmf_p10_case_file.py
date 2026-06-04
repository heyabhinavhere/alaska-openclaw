"""P10 tests: the on-demand case-file read (the /pmf user query). Case files are
WRITTEN every snapshot by build_case_file; this is the read path that didn't exist —
plus bon-id -> user_key resolution. Fixtures only."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.store import PmfStore  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WS, WE = "2026-05-27T00:00:00-07:00", "2026-05-29T23:59:59-07:00"


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_p10_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="p10", name="P10", signup_window_start=WS, signup_window_end=WE, activate=True)
    return store


def _seed_user(store: PmfStore, user_key: str, bon_user_id: str) -> None:
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "INSERT INTO pmf_cohort_users (cohort_id, user_key, bon_user_id, signup_event_time, current_stage, highest_stage) "
        "VALUES (?,?,?,?,?,?)",
        ("p10", user_key, bon_user_id, "2026-05-28T10:00:00Z", "signed_up", "signed_up"),
    )
    conn.commit()
    conn.close()


def test_get_case_file_roundtrip_via_snapshot():
    store = _store()
    _seed_user(store, "user:2903", "2903")
    # apply_daily_snapshot is the real write path (build_case_file -> pmf_user_case_files).
    store.apply_daily_snapshot("p10", "user:2903", "2026-05-28", {
        "onboarding_complete": True, "credit_score": 555, "meaningful_credgpt_messages": 0,
        "card_linked": False, "bank_linked": False, "pmf_success_metrics": {},
    })
    cf = store.get_case_file("p10", "user:2903")
    assert cf is not None
    assert cf["funnel_stage"] == "onboarded_real_user"  # real user (cs>0, onboarded), not yet activated
    assert isinstance(cf["case_file"], dict)
    assert cf["case_file"]["identity"]["user_key"] == "user:2903"
    assert isinstance(cf["product_learning_tags"], list)  # JSON column parsed
    assert isinstance(cf["flags"], list)


def test_get_case_file_none_when_absent():
    store = _store()
    assert store.get_case_file("p10", "user:9999") is None


def test_user_key_for_bon_id_resolves_from_registry():
    store = _store()
    _seed_user(store, "user:2903", "2903")
    assert store.user_key_for_bon_id("p10", "2903") == "user:2903"
    assert store.user_key_for_bon_id("p10", 2903) == "user:2903"  # int form
    assert store.user_key_for_bon_id("p10", "0000") is None
    assert store.user_key_for_bon_id("p10", None) is None


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
