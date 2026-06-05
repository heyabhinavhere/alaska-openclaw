"""P19: the daily briefing must never post an empty narrative as 'completed'.

Live test (Step 8): the LLM call succeeded but returned no parseable JSON (the
response truncated past max_tokens=1200 → extract_json fell back to {}), and the
briefing was emitted with narrative_status='completed' but every field empty — so
a blank message posted to Slack. Fix: bump the token budget AND mark an empty
narrative 'failed' (the orchestrator only posts on 'completed'). Fixtures only."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.daily_briefing import generate_daily_briefing  # noqa: E402


def test_empty_narrative_is_failed_not_completed():
    # narrator returns {} — exactly what extract_json yields on truncated/unparseable output
    out = generate_daily_briefing({"snapshot_date": "2026-06-05"}, narrator=lambda f: {})
    assert out["narrative_status"] == "failed"
    assert out["narrative"] is None  # → orchestrator skips the Slack post


def test_populated_narrative_is_completed():
    out = generate_daily_briefing(
        {"x": 1},
        narrator=lambda f: {"headline": "H", "who_needs_you": [{"user": "U", "why": "w", "suggested_action": "a"}]},
    )
    assert out["narrative_status"] == "completed"
    assert out["narrative"]["headline"] == "H"
    assert out["narrative"]["who_needs_you"][0]["user"] == "U"


def test_narrator_none_is_skipped():
    out = generate_daily_briefing({"x": 1}, narrator=None)
    assert out["narrative_status"] == "skipped"
    assert out["narrative"] is None


def test_narrator_error_is_failed():
    def boom(_facts):
        raise RuntimeError("llm down")

    out = generate_daily_briefing({"x": 1}, narrator=boom)
    assert out["narrative_status"] == "failed"
    assert out["narrative"] is None


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
