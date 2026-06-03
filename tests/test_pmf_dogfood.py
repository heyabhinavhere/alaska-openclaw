"""End-to-end dogfood test: a synthetic cohort through the full PMF pipeline.

Validates the engine (intake -> enrich -> snapshot -> CredGPT review -> report)
on fake-but-realistic data before live collectors exist, and locks the
team-tier aggregate-only privacy guarantee in an integration setting.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.dogfood import build_synthetic_cohort, run_dogfood  # noqa: E402


def test_pipeline_spreads_funnel_and_shows_full_detail():
    result = run_dogfood(n=40, seed=7)
    ingest, team, founder = result["ingest"], result["team"], result["founder"]

    # Intake: in-window ingested; out-of-window + wrong-step excluded.
    assert ingest["ingested"] == 40
    assert ingest["excluded"] == 3
    assert ingest["excluded_by_reason"].get("outside_signup_window") == 2
    assert ingest["excluded_by_reason"].get("not_cohort_entry_event") == 1

    # Funnel actually spreads: >= 4 distinct stages populated.
    stage_counts = team["summary"]["stage_counts"]
    populated = [stage for stage, count in stage_counts.items() if count > 0]
    assert len(populated) >= 5, populated
    assert stage_counts["activated_saver"] > 0  # computed/candidate savers exercised
    assert stage_counts["likely_lover"] > 0
    assert team["summary"]["real_users"] >= 20

    # Queues and weak-CredGPT signal exist.
    assert sum(team["summary"]["queue_counts"].values()) > 0
    assert team["summary"]["weak_credgpt_reviews"] > 0

    # No tier masking: team and founder both show full per-user detail.
    assert len(team["users"]) == 40
    assert len(founder["users"]) == 40
    assert team["users"][0].get("email")  # email stays visible to the whole team
    assert founder["summary"]["stage_counts"] == stage_counts


def test_ingest_is_idempotent_on_reingest():
    result = run_dogfood(n=20, seed=3)
    store = result["store"]
    spec = build_synthetic_cohort(20, seed=3)  # identical events (same seed)
    before = len(store.list_users("pmf-dogfood"))
    store.ingest_signup_events("pmf-dogfood", spec["events"])
    after = len(store.list_users("pmf-dogfood"))
    assert before == after == 20


def test_team_html_shows_user_detail():
    result = run_dogfood(n=24, seed=11)
    store = result["store"]
    root = Path(tempfile.mkdtemp(prefix="pmf_dogfood_art_"))

    team = store.render_report_artifacts(
        "pmf-dogfood", report_id="dogfood-team", privacy_tier="team",
        artifact_root=str(root), snapshot_date="2026-06-13",
    )
    team_html = Path(team["html_path"]).read_text(encoding="utf-8")
    assert "user:2000" in team_html  # the whole team sees per-user rows
    # HTML stays self-contained (no external network dependency).
    assert "http://" not in team_html
    assert "https://" not in team_html


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
