"""P21 tests: Slack composers for the weekly digest + end-of-cohort memo.

These render the (already-built) report dict into a Slack mrkdwn string for
`--deliver`. Two paths each: (a) a completed LLM narrative renders headline +
sections; (b) no narrative (skipped/failed) falls back to a facts-only line so
delivery always posts something meaningful. Pure functions — no live Slack."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.end_cohort import compose_memo_slack  # noqa: E402
from pmf_os.weekly_digest import compose_weekly_slack  # noqa: E402


def test_weekly_compose_renders_narrative():
    report = {
        "narrative_status": "completed",
        "facts": {"week_start": "2026-05-25", "week_end": "2026-05-31", "funnel_now": {"real_users": 42}},
        "narrative": {
            "headline": "Activation is climbing, onboarding is the leak.",
            "trajectory": {"rating": "improving", "reason": "activation +6 this week"},
            "whats_working": ["card-link nudge converting"],
            "whats_blocking": ["spinwheel stall at step 3"],
            "do_this_week": ["ship resume-onboarding email"],
        },
    }
    text = compose_weekly_slack(report)
    assert "📈" in text and "Weekly PMF digest" in text
    assert "2026-05-25 – 2026-05-31" in text
    assert "Activation is climbing" in text
    assert "*Trajectory:* improving — activation +6 this week" in text
    assert "card-link nudge converting" in text
    assert "spinwheel stall at step 3" in text
    assert "ship resume-onboarding email" in text


def test_weekly_compose_facts_only_fallback():
    report = {
        "narrative_status": "skipped",
        "narrative": None,
        "facts": {"week_start": "2026-05-25", "week_end": "2026-05-31", "funnel_now": {"real_users": 42, "stage_counts": {"signed_up": 50}}},
    }
    text = compose_weekly_slack(report)
    assert "📈" in text and "facts only" in text
    assert "Real users: 42" in text
    assert "signed up 50" in text  # clean humanized line, not a raw dict
    assert "{'signed_up'" not in text  # never dump a Python dict
    # never invents prose when the narrative is absent
    assert "Trajectory" not in text


def test_memo_compose_renders_narrative():
    report = {
        "narrative_status": "completed",
        "facts": {"funnel": {"rates": {"activation_rate": 0.3}}},
        "narrative": {
            "executive_summary": "Weak-but-present PMF signal; onboarding is the gate.",
            "pmf_verdict": {"rating": "weak-signal", "reason": "savers 12% of real users"},
            "what_worked": ["card linking once reached"],
            "what_didnt": ["onboarding completion"],
            "recommendations": ["pre-fill bank step for next cohort"],
        },
    }
    text = compose_memo_slack(report)
    assert "🏁" in text and "End-of-cohort PMF memo" in text
    assert "Weak-but-present PMF signal" in text
    assert "*Verdict:* weak-signal — savers 12% of real users" in text
    assert "card linking once reached" in text
    assert "onboarding completion" in text
    assert "pre-fill bank step for next cohort" in text


def test_memo_compose_facts_only_fallback():
    report = {
        "narrative_status": "failed",
        "narrative": None,
        "facts": {"funnel": {"rates": {"activation_rate": 0.3}}},
    }
    text = compose_memo_slack(report)
    assert "🏁" in text and "facts only" in text
    assert "activation rate" in text  # humanized, not the raw key/dict
    assert "{'activation_rate'" not in text
    assert "Verdict" not in text


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
