"""P9 tests: the queue -> intervention action loop. An open queue becomes a proposed
(human-gated) intervention linked via queue_id; approve -> execute(fake) -> the
originating queue resolves (closed loop). Deterministic map; idempotent; not every
queue maps; nothing sends. Fixtures only."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.queue_actions import plan_interventions_for_queues  # noqa: E402
from pmf_os.store import PmfStore  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WS, WE = "2026-05-27T00:00:00-07:00", "2026-05-29T23:59:59-07:00"


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_p9_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="p9", name="P9", signup_window_start=WS, signup_window_end=WE, activate=True)
    return store


def _seed_queue(store: PmfStore, queue_type: str, user_key: str | None, severity: str = "P1", title: str = "t") -> int:
    conn = sqlite3.connect(store.db_path)
    cur = conn.execute(
        "INSERT INTO pmf_operating_queues (cohort_id, user_key, queue_type, severity, status, title) VALUES (?,?,?,?,?,?)",
        ("p9", user_key, queue_type, severity, "open", title),
    )
    qid = cur.lastrowid
    conn.commit()
    conn.close()
    return qid


# ---- plan_interventions_for_queues (deterministic map) ----

def test_plan_maps_actionable_and_skips_others():
    queues = [
        {"id": 1, "queue_type": "high_intent", "user_key": "user:1", "title": "link fail", "reason": "x"},
        {"id": 2, "queue_type": "potential_lover", "user_key": "user:2", "title": "lover", "reason": "y"},
        {"id": 3, "queue_type": "needs_human_review", "user_key": "user:3", "title": "rev"},  # unmapped -> skip
        {"id": 4, "queue_type": "high_intent", "user_key": None, "title": "no user"},  # no user_key -> skip
    ]
    by_q = {s["queue_id"]: s for s in plan_interventions_for_queues(queues)}
    assert set(by_q) == {1, 2}
    assert by_q[1]["channel"] == "email" and by_q[1]["action_type"] == "nudge_link_card"
    assert by_q[1]["audience_preview"] == {"count": 1, "users": ["user:1"]}
    assert by_q[1]["suppression_check"]["verified"] is False  # honestly unverified
    assert by_q[2]["channel"] == "internal_task"  # potential_lover -> founder task, not an auto-send
    assert by_q[1]["draft"]["body"]  # deterministic fallback body present


def test_plan_uses_injected_copy_drafter():
    captured: dict = {}

    def drafter(ctx):
        captured["ctx"] = ctx
        return {"subject": "Finish linking your card", "body": "You're almost there!"}

    specs = plan_interventions_for_queues(
        [{"id": 1, "queue_type": "high_intent", "user_key": "user:1", "title": "t"}], copy_drafter=drafter,
    )
    assert specs[0]["draft"]["body"] == "You're almost there!"
    assert captured["ctx"]["queue_type"] == "high_intent"


# ---- store: draft from open queues, idempotency, closed loop ----

def test_draft_from_open_queues_and_idempotent():
    store = _store()
    _seed_queue(store, "high_intent", "user:1")
    _seed_queue(store, "needs_human_review", "user:9")  # unmapped -> no draft
    drafted = store.draft_interventions_for_open_queues("p9")
    assert len(drafted) == 1
    assert drafted[0]["channel"] == "email"
    assert drafted[0]["approval_status"] == "needs_approval"
    assert drafted[0]["queue_id"] is not None
    assert store.draft_interventions_for_open_queues("p9") == []  # idempotent — no double-draft


def test_closed_loop_execute_resolves_queue():
    store = _store()
    qid = _seed_queue(store, "high_intent", "user:1")
    iid = store.draft_interventions_for_open_queues("p9")[0]["intervention_id"]
    store.approve_intervention("p9", iid, "abhinav")
    result = store.execute_intervention("p9", iid, cio_executor=lambda a: {"customerio_ref": "cio_1"})
    assert result["status"] == "executed"
    assert store.resolve_queue_for_intervention("p9", iid) == {"queue_id": qid, "queue_type": "high_intent", "resolved": True}
    assert all(q["id"] != qid for q in store.open_queue_items("p9"))  # the queue is closed


def test_resolve_is_noop_without_a_linked_queue():
    store = _store()
    iid = store.draft_intervention("p9", {
        "user_key": "user:1", "channel": "email", "action_type": "x", "draft": {},
        "dry_run": {"r": 1}, "audience_preview": {"count": 1}, "suppression_check": {"verified": False},
    })["intervention_id"]
    assert store.resolve_queue_for_intervention("p9", iid) is None


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
