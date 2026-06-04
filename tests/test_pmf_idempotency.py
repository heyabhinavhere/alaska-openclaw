"""Funnel-transition idempotency (the §6/§10 gate).

apply_daily_snapshot records a row in pmf_funnel_transitions ONLY for an actual
stage movement. When the funnel re-evaluates to the same stage (from==to →
transition_type 'recomputed') it must record NOTHING — otherwise a same-date
re-run, or a stage-stable user on each later day, accrues no-op rows that break
idempotency and bloat the table. Fixtures only.
"""

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

# real user + 4 meaningful messages → activated_user (deterministic, no metrics → not saver)
ACTIVATED_FACTS = {"onboarding_complete": True, "credit_score": 700, "meaningful_credgpt_messages": 4}


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_idem_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="idem", name="Idem", signup_window_start=WS, signup_window_end=WE, activate=True)
    return store


def _seed(store: PmfStore, user_key: str, bon_user_id: str) -> None:
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "INSERT INTO pmf_cohort_users (cohort_id, user_key, bon_user_id, signup_event_time, current_stage, highest_stage) "
        "VALUES (?,?,?,?,?,?)",
        ("idem", user_key, bon_user_id, "2026-05-28T10:00:00Z", "signed_up", "signed_up"),
    )
    conn.commit()
    conn.close()


def _tcount(store: PmfStore) -> int:
    with store.connect() as conn:
        return conn.execute("SELECT count(*) FROM pmf_funnel_transitions").fetchone()[0]


def test_promotion_recorded_once_then_idempotent_on_same_date_rerun():
    store = _store()
    _seed(store, "user:1", "1")
    # first snapshot: signed_up -> activated_user == exactly one promotion
    store.apply_daily_snapshot("idem", "user:1", "2026-05-28", ACTIVATED_FACTS)
    assert _tcount(store) == 1
    # identical re-run, same date + facts -> stage unchanged -> ZERO new transitions
    store.apply_daily_snapshot("idem", "user:1", "2026-05-28", ACTIVATED_FACTS)
    assert _tcount(store) == 1


def test_no_transition_for_stage_stable_user_on_a_later_day():
    store = _store()
    _seed(store, "user:2", "2")
    store.apply_daily_snapshot("idem", "user:2", "2026-05-28", ACTIVATED_FACTS)  # promotion
    assert _tcount(store) == 1
    # next day, still activated_user (no movement) -> no new transition row
    store.apply_daily_snapshot("idem", "user:2", "2026-05-29", ACTIVATED_FACTS)
    assert _tcount(store) == 1


def test_real_movement_still_records():
    store = _store()
    _seed(store, "user:3", "3")
    # day 1: onboarded real user only (no messages) -> onboarded_real_user (promotion #1)
    store.apply_daily_snapshot("idem", "user:3", "2026-05-28", {"onboarding_complete": True, "credit_score": 700})
    assert _tcount(store) == 1
    # day 2: now activated (4 messages) -> activated_user (promotion #2, a real movement)
    store.apply_daily_snapshot("idem", "user:3", "2026-05-29", ACTIVATED_FACTS)
    assert _tcount(store) == 2


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
