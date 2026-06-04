"""Guardrail tests for the test-only wide signup window (V5 testing-phase prereq).

The `allow_wide_window` affordance must let ONE isolated backfill cohort exceed the
3-day production cap WITHOUT ever weakening production. It is refused unless ALL of:
  (a) the explicit flag is set, (b) the DB is a clearly-isolated test DB, and
  (c) the cohort is NOT being activated. The prod default still caps at 3 days.

Fixtures only — no live APIs, no network. The three "refused" cases raise BEFORE any
DB connection (the window checks run first), so they use bare path strings; only the
success case opens a migrated test DB.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.store import PmfStore, _is_test_db_path  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"

# A 61-day window — well past the 3-day production cap.
WIDE_START, WIDE_END = "2026-03-20T00:00:00-07:00", "2026-05-20T23:59:59-07:00"
# A prod-like path the guard must NEVER treat as a test DB. The window checks raise
# before any DB connection, so this path is never actually opened in the raising tests.
PROD_PATH = "/data/queue/alaska_pmf.db"


def _migrated_test_db(filename: str = "cohort_test.db") -> str:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_ww_")) / filename)
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return db


# ---- the path classifier itself (the security-critical gate) ----

def test_is_test_db_path_classification():
    assert _is_test_db_path("/data/queue/alaska_pmf_test.db") is True   # '_test' in filename
    assert _is_test_db_path("/tmp/pmf-test.db") is True                 # under /tmp/
    assert _is_test_db_path("/private/tmp/pmf.db") is True              # macOS /tmp
    assert _is_test_db_path("/data/queue/alaska_pmf.db") is False       # prod
    assert _is_test_db_path("/var/lib/alaska/alaska_pmf.db") is False   # non-test


# ---- (1) prod default still caps at 3 days (no flag) ----

def test_prod_default_still_caps_at_three_days():
    store = PmfStore(PROD_PATH)
    with pytest.raises(ValueError, match="at most 3 days"):
        store.create_cohort(
            cohort_id="c", name="c",
            signup_window_start=WIDE_START, signup_window_end=WIDE_END,
        )


# ---- (2) flag on a non-test DB path is refused (path guard) ----

def test_wide_window_refused_on_non_test_db_path():
    store = PmfStore(PROD_PATH)
    with pytest.raises(ValueError, match="test-only"):
        store.create_cohort(
            cohort_id="c", name="c",
            signup_window_start=WIDE_START, signup_window_end=WIDE_END,
            allow_wide_window=True,
        )


# ---- (3) flag + activate is refused (must stay planned) ----

def test_wide_window_refused_when_activating():
    store = PmfStore("/tmp/pmf_ww_activate_test.db")  # test path → clears the path guard
    with pytest.raises(ValueError, match="cannot be activated"):
        store.create_cohort(
            cohort_id="c", name="c",
            signup_window_start=WIDE_START, signup_window_end=WIDE_END,
            allow_wide_window=True, activate=True,
        )


# ---- (4) wide window on a test DB, non-active → succeeds (planned) ----

def test_wide_window_succeeds_on_test_db_non_active():
    store = PmfStore(_migrated_test_db())
    out = store.create_cohort(
        cohort_id="pmf-test-mar-may", name="Backfill Mar-May",
        signup_window_start=WIDE_START, signup_window_end=WIDE_END,
        allow_wide_window=True,
    )
    assert out["status"] == "planned"          # never auto-activated
    assert out["cohort_id"] == "pmf-test-mar-may"
    # Prove the flag is genuinely what allowed it: the SAME wide window without the
    # flag is still rejected, even on a test DB (tz-format-agnostic check).
    with pytest.raises(ValueError, match="at most 3 days"):
        store.create_cohort(
            cohort_id="pmf-test-2", name="x",
            signup_window_start=WIDE_START, signup_window_end=WIDE_END,
        )


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
