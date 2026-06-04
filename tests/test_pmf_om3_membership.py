"""OM-3 test: the cross-aware cohort-membership lookup. The default user-intel path
appends a '/pmf' pointer ONLY when the user is in the ACTIVE PMF cohort — and returns
nothing otherwise (no active cohort, or non-member), so it never blends sources or
fires a false pointer. Fixtures only."""

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


def _store(activate: bool = True) -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_om3_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="om3", name="OM3", signup_window_start=WS, signup_window_end=WE, activate=activate)
    return store


def _seed_member(store: PmfStore, bon_user_id: str = "2903", stage: str = "activated_user", saver=None) -> None:
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "INSERT INTO pmf_cohort_users (cohort_id, user_key, bon_user_id, signup_event_time, "
        "current_stage, highest_stage, activated_saver_state) VALUES (?,?,?,?,?,?,?)",
        ("om3", f"user:{bon_user_id}", bon_user_id, "2026-05-28T10:00:00Z", stage, stage, saver),
    )
    conn.commit()
    conn.close()


def test_member_of_active_cohort_returns_stage():
    store = _store(activate=True)
    _seed_member(store, "2903", "activated_user")
    assert store.get_active_cohort_membership("2903") == {
        "cohort_id": "om3", "current_stage": "activated_user", "activated_saver_state": None,
    }
    assert store.get_active_cohort_membership(2903)["current_stage"] == "activated_user"  # int form


def test_non_member_returns_none():
    store = _store(activate=True)
    _seed_member(store, "2903")
    assert store.get_active_cohort_membership("9999") is None


def test_no_active_cohort_returns_none():
    store = _store(activate=False)  # 'planned', not active
    _seed_member(store, "2903")
    assert store.get_active_cohort_membership("2903") is None  # member exists, but no ACTIVE cohort -> no pointer


def test_blank_id_returns_none():
    store = _store(activate=True)
    assert store.get_active_cohort_membership("") is None
    assert store.get_active_cohort_membership(None) is None


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
