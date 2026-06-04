"""P4.1 tests: the CredGPT LLM quality/safety judge — verdict normalization,
safety-forward escalation, key-gated availability, and the store write-back over
pending reviews. Injectable judge_fn; no live LLM call."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os import credgpt_quality  # noqa: E402
from pmf_os.credgpt_quality import (  # noqa: E402
    default_judge_fn,
    escalated_quality_state,
    normalize_verdict,
)
from pmf_os.store import PmfStore  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WS, WE = "2026-05-27T00:00:00-07:00", "2026-05-29T23:59:59-07:00"


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_p41_")) / "a.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="p41", name="P41", signup_window_start=WS, signup_window_end=WE, activate=True)
    return store


def _flagged_turn(turn_id: str = "t1:0") -> dict:
    # High-intent question + a thin (but not unsafe) answer -> deterministic
    # quality_state='weak', needs_llm_review=1, llm_review_status='pending'.
    return {
        "thread_id": "t1", "turn_id": turn_id,
        "question": "how should i pay down my credit card debt fastest",
        "answer": "Pay it down.",
        "event_time": "2026-05-28T10:00:00Z",
    }


def _review_row(store: PmfStore) -> sqlite3.Row:
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT llm_review_status, llm_review_json, quality_state, pmf_usefulness_score "
        "FROM credgpt_quality_reviews WHERE cohort_id='p41'"
    ).fetchone()
    conn.close()
    return row


# ---- pure helpers ----------------------------------------------------------

def test_normalize_verdict_coerces_and_clamps():
    raw = {
        "rubric_scores": {"correctness": 1.4, "data_grounding": -0.2, "pmf_usefulness": "0.5", "bogus": 9},
        "unsafe_advice": True, "unsafe_rationale": "x", "quality_state": "unsafe", "rationale": "y",
    }
    v = normalize_verdict(raw)
    assert v["rubric_scores"]["correctness"] == 1.0   # clamped high
    assert v["rubric_scores"]["data_grounding"] == 0.0  # clamped low
    assert v["rubric_scores"]["pmf_usefulness"] == 0.5  # string coerced
    assert "bogus" not in v["rubric_scores"]            # unknown key dropped
    assert v["unsafe_advice"] is True and v["quality_state"] == "unsafe"
    assert v["pmf_usefulness_score"] == 0.5


def test_normalize_verdict_infers_or_nulls_state():
    assert normalize_verdict({"unsafe_advice": True})["quality_state"] == "unsafe"
    # invalid state + not unsafe -> None, so it won't override the deterministic state
    assert normalize_verdict({"unsafe_advice": False, "quality_state": "nonsense"})["quality_state"] is None


def test_escalated_quality_state_never_de_escalates():
    assert escalated_quality_state("ok", "unsafe") == "unsafe"            # escalate
    assert escalated_quality_state("unsafe", "ok") == "unsafe"            # never clear
    assert escalated_quality_state("weak", "hallucination_risk") == "hallucination_risk"
    assert escalated_quality_state("unsafe", None) == "unsafe"


def test_default_judge_fn_gated_on_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert default_judge_fn() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert default_judge_fn() is not None  # the live adapter (not invoked here)


# ---- store write-back ------------------------------------------------------

def test_judge_pending_completes_and_escalates_with_fake_judge():
    store = _store()
    store.record_credgpt_turn("p41", "user:1001", _flagged_turn())
    seen = {}

    def fake_judge(row):
        seen["review_id"], seen["question"] = row["review_id"], row["question"]
        return {
            "rubric_scores": {k: 0.2 for k in credgpt_quality.JUDGE_RUBRIC_KEYS},
            "unsafe_advice": True, "unsafe_rationale": "advises paying only the minimum",
            "quality_state": "unsafe", "rationale": "non-compliant guidance",
        }

    result = store.judge_pending_credgpt_reviews("p41", judge_fn=fake_judge)
    assert result == {"pending": 1, "completed": 1, "skipped": 0, "failed": 0}
    assert seen["review_id"] and "pay down" in seen["question"]

    row = _review_row(store)
    assert row["llm_review_status"] == "completed"
    verdict = json.loads(row["llm_review_json"])
    assert verdict["unsafe_advice"] is True and verdict["quality_state"] == "unsafe"
    assert row["quality_state"] == "unsafe"        # escalated from deterministic 'weak'
    assert row["pmf_usefulness_score"] == 0.2

    # idempotent: status is no longer 'pending', so a re-run finds nothing
    assert store.judge_pending_credgpt_reviews("p41", judge_fn=fake_judge)["pending"] == 0


def test_judge_pending_skips_when_no_judge_available(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    store = _store()
    store.record_credgpt_turn("p41", "user:1002", _flagged_turn("t2:0"))
    result = store.judge_pending_credgpt_reviews("p41", judge_fn=None)  # -> default -> None (no key)
    assert result["pending"] == 1 and result["skipped"] == 1 and result["completed"] == 0
    assert _review_row(store)["llm_review_status"] == "skipped"


def test_judge_pending_records_failure_without_sinking_batch():
    store = _store()
    store.record_credgpt_turn("p41", "user:1003", _flagged_turn("t3:0"))

    def boom(row):
        raise RuntimeError("llm 500")

    result = store.judge_pending_credgpt_reviews("p41", judge_fn=boom)
    assert result["failed"] == 1 and result["completed"] == 0
    row = _review_row(store)
    assert row["llm_review_status"] == "failed"
    assert "llm 500" in row["llm_review_json"]


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
