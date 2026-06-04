"""P6 tests: the gated Customer.io intervention state machine — draft -> human
approve -> guard-validated execute -> outcome. Injectable executor; no live send,
no autonomous send, SMS blocked."""

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
    db = str(Path(tempfile.mkdtemp(prefix="pmf_p6_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="p6", name="P6", signup_window_start=WS, signup_window_end=WE, activate=True)
    return store


def _email_intervention(**overrides) -> dict:
    base = {
        "user_key": "user:1001", "channel": "email", "action_type": "nudge_link_card",
        "draft": {"to": "u@example.com", "subject": "Link your card", "body": "...", "frequency_cap_checked": True},
        "dry_run": {"rendered": True},
        "audience_preview": {"count": 1, "users": ["user:1001"]},
        "suppression_check": {"suppressed": 0},
    }
    base.update(overrides)
    return base


def test_draft_status_by_channel_and_sms_blocked():
    store = _store()
    email = store.draft_intervention("p6", _email_intervention())
    assert email["approval_status"] == "needs_approval"   # mutation channel gated
    task = store.draft_intervention("p6", {"channel": "internal_task", "action_type": "followup"})
    assert task["approval_status"] == "draft"
    try:
        store.draft_intervention("p6", {"channel": "sms", "action_type": "x"})
        raise AssertionError("SMS should be blocked")
    except ValueError as exc:
        assert "SMS" in str(exc)


def test_happy_path_draft_approve_execute_outcome():
    store = _store()
    seen = []

    def fake_executor(action):
        seen.append(action)
        return {"customerio_ref": "cio_123", "status": 200}

    drafted = store.draft_intervention("p6", _email_intervention())
    iid = drafted["intervention_id"]

    # cannot execute before approval
    blocked = store.execute_intervention("p6", iid, cio_executor=fake_executor)
    assert blocked["status"] == "blocked" and "not_approved" in blocked["reason"]
    assert not seen  # executor was never called

    approved = store.approve_intervention("p6", iid, "abhinav")
    assert approved["approval_status"] == "approved" and approved["approved_by"] == "abhinav" and approved["approved_at"]

    done = store.execute_intervention("p6", iid, cio_executor=fake_executor)
    assert done["status"] == "executed" and done["customerio_ref"] == "cio_123"
    assert len(seen) == 1 and seen[0]["channel"] == "email" and seen[0]["approved_by"] == "abhinav"
    assert store.get_intervention("p6", iid)["approval_status"] == "executed"

    out = store.record_intervention_outcome("p6", iid, {"delivered": True, "opened": True, "clicked": False})
    assert out["outcome"]["delivered"] is True and out["outcome"]["opened"] is True


def test_execute_blocked_by_guard_when_validations_missing():
    store = _store()
    # no dry_run / audience / suppression -> guard must refuse even after approval
    drafted = store.draft_intervention("p6", {"user_key": "user:1", "channel": "email", "action_type": "x",
                                              "draft": {"to": "a@b.com"}})
    iid = drafted["intervention_id"]
    store.approve_intervention("p6", iid, "abhinav")
    result = store.execute_intervention("p6", iid, cio_executor=lambda a: {"customerio_ref": "z"})
    assert result["status"] == "blocked" and result["reason"] == "guard_rejected"
    assert any("dry-run" in r.lower() for r in result["decision"]["reasons"])
    assert store.get_intervention("p6", iid)["approval_status"] == "approved"  # not executed


def test_execute_without_executor_or_ref_sends_nothing():
    store = _store()
    iid = store.draft_intervention("p6", _email_intervention())["intervention_id"]
    store.approve_intervention("p6", iid, "abhinav")
    result = store.execute_intervention("p6", iid)  # no executor, no ref
    assert result["status"] == "no_executor"
    assert store.get_intervention("p6", iid)["approval_status"] == "approved"  # unchanged


def test_execute_records_human_provided_ref():
    store = _store()
    iid = store.draft_intervention("p6", _email_intervention())["intervention_id"]
    store.approve_intervention("p6", iid, "abhinav")
    result = store.execute_intervention("p6", iid, customerio_ref="manual_send_1")
    assert result["status"] == "executed" and result["customerio_ref"] == "manual_send_1"
    assert store.get_intervention("p6", iid)["customerio_ref"] == "manual_send_1"


def test_executor_failure_is_recorded_not_raised():
    store = _store()
    iid = store.draft_intervention("p6", _email_intervention())["intervention_id"]
    store.approve_intervention("p6", iid, "abhinav")

    def boom(action):
        raise RuntimeError("cio 503")

    result = store.execute_intervention("p6", iid, cio_executor=boom)
    assert result["status"] == "failed" and "cio 503" in result["error"]
    row = store.get_intervention("p6", iid)
    assert row["approval_status"] == "failed" and "cio 503" in (row["outcome"] or {}).get("error", "")


def test_reject_and_list_filter():
    store = _store()
    a = store.draft_intervention("p6", _email_intervention(user_key="user:1"))["intervention_id"]
    b = store.draft_intervention("p6", _email_intervention(user_key="user:2"))["intervention_id"]
    store.reject_intervention("p6", a, "abhinav", reason="off-message")
    assert store.get_intervention("p6", a)["approval_status"] == "rejected"
    needs = store.list_interventions("p6", approval_status="needs_approval")
    assert [i["intervention_id"] for i in needs] == [b]
    assert len(store.list_interventions("p6")) == 2


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
