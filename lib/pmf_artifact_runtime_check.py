#!/usr/bin/env python3
"""Smoke-check Alaska V5 DOCX/PDF artifact runtime support.

Run inside the deployed container after a runtime/image change:
    python3 /opt/lib/pmf_artifact_runtime_check.py

Local development can run structural checks without LibreOffice/Poppler:
    python3 lib/pmf_artifact_runtime_check.py --structural-only
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from pmf_os.artifacts import (
    artifact_ready_for_delivery,
    build_report_snapshot,
    qa_artifact,
    render_docx,
    render_pdf,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check PMF artifact DOCX/PDF runtime support")
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="Skip the visual delivery gate. Intended for local environments without soffice/pdftoppm.",
    )
    parser.add_argument(
        "--out-dir",
        help="Optional output directory to keep the generated smoke artifacts. Defaults to a temp directory.",
    )
    args = parser.parse_args(argv)

    require_visual = not args.structural_only
    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        result = run_check(out_dir, require_visual=require_visual)
    else:
        with tempfile.TemporaryDirectory(prefix="pmf_artifact_runtime_") as tmp:
            result = run_check(Path(tmp), require_visual=require_visual)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def run_check(out_dir: Path, *, require_visual: bool = True) -> dict[str, Any]:
    snapshot = build_report_snapshot(
        cohort={
            "cohort_id": "artifact-runtime-smoke",
            "name": "Artifact Runtime Smoke",
        },
        users=[
            {
                "user_key": "user:smoke",
                "is_real_user": 1,
                "current_stage": "activated_user",
                "current_health": "watch",
            }
        ],
        queues=[],
        privacy_tier="team",
        report_type="daily_cockpit",
        snapshot_date="2026-06-12",
    )
    docx_path = Path(render_docx(snapshot, out_dir / "artifact-runtime-smoke.docx"))
    pdf_path = Path(render_pdf(snapshot, out_dir / "artifact-runtime-smoke.pdf"))
    qa_results = [
        qa_artifact(docx_path, "docx", require_visual=require_visual),
        qa_artifact(pdf_path, "pdf", require_visual=require_visual),
    ]
    if require_visual:
        ok = artifact_ready_for_delivery(qa_results)
    else:
        ok = all(item.get("structural_pass") for item in qa_results)
    return {
        "ok": ok,
        "mode": "visual" if require_visual else "structural",
        "tools": {
            "soffice": shutil.which("soffice") or shutil.which("libreoffice"),
            "pdftoppm": shutil.which("pdftoppm"),
        },
        "artifacts": {
            "docx": str(docx_path),
            "pdf": str(pdf_path),
        },
        "qa": qa_results,
    }


if __name__ == "__main__":
    raise SystemExit(main())
