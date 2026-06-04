"""End-to-end output smoke test: build a synthetic cohort, then drive the
user-facing OUTPUT builders through the CLI exactly as Alaska would — the HTML
cockpit render, the end-cohort memo, the weekly digest, and a case file — and
assert each produces correct structure. Locks the manual structural check
(docs/v5-pmf-manual-e2e-test-plan.md) as a regression guard. No live APIs/LLM
(narratives skipped), no network."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.dogfood import COHORT_ID, SNAPSHOT_DATE, run_dogfood  # noqa: E402

REPO = Path(__file__).parent.parent
CLI = str(REPO / "lib" / "pmf_cohort_os.py")


def _cli(db: str, *args: str) -> dict:
    r = subprocess.run([sys.executable, CLI, "--db", db, *args], capture_output=True, text=True)
    assert r.returncode == 0, f"CLI {args[:1]} failed: {r.stderr}"
    out = json.loads(r.stdout)
    assert out.get("ok") is True, f"CLI {args[:1]} not ok: {out}"
    return out["result"]


def test_e2e_output_builders_produce_correct_structure():
    db = str(Path(tempfile.mkdtemp(prefix="pmf_e2e_")) / "alaska_pmf_test.db")
    run_dogfood(db, n=24)  # registry + snapshots + case files + queues + clusters + reports
    art = str(Path(tempfile.mkdtemp(prefix="pmf_e2e_art_")))

    # 1. HTML cockpit renders + passes structural QA, with real content.
    r = _cli(db, "render-report", "--cohort-id", COHORT_ID, "--report-id", "e2e",
             "--report-type", "daily_cockpit", "--privacy-tier", "team",
             "--snapshot-date", SNAPSHOT_DATE, "--artifact-root", art, "--no-require-visual-qa")
    assert r["status"] in ("qa_passed", "rendered")
    assert os.path.exists(r["html_path"]) and os.path.getsize(r["html_path"]) > 2000

    # 2. End-cohort memo — aggregate facts present; narrative skipped (no LLM).
    r = _cli(db, "end-cohort-memo", "--cohort-id", COHORT_ID, "--artifact-root", art)
    assert {"funnel", "dropoff", "credgpt_quality", "pmf_metrics", "interventions"} <= set(r["facts"])
    assert r["narrative_status"] == "skipped"

    # 3. Weekly digest — facts present; narrative skipped.
    r = _cli(db, "weekly-digest", "--cohort-id", COHORT_ID, "--artifact-root", art)
    assert {"funnel_now", "movement_this_week", "pmf_metrics", "product_friction", "interventions"} <= set(r["facts"])
    assert r["narrative_status"] == "skipped"

    # 4. Case file for a real cohort user — structured, non-null, with a real stage.
    r = _cli(db, "case-file", "--cohort-id", COHORT_ID, "--user-key", "user:2000")
    cf = r["case_file"]
    assert cf is not None
    assert cf["funnel_stage"] == "onboarded_real_user"  # the known stage for user:2000
    assert "evidence" in cf and "case_file" in cf  # stage evidence + the rendered case-file doc


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
