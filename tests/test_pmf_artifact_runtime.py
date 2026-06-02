"""Tests for PMF artifact runtime readiness.

These tests stay local-friendly: they verify the Dockerfile declares the
production visual-QA packages and run the artifact smoke check in structural
mode. The deployed container must run the smoke check without --structural-only.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent


def test_dockerfile_installs_visual_qa_runtime_packages():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "libreoffice-writer" in dockerfile
    assert "poppler-utils" in dockerfile
    assert "fonts-dejavu-core" in dockerfile


def test_artifact_runtime_smoke_check_structural_mode():
    out_dir = Path(tempfile.mkdtemp(prefix="pmf_artifact_runtime_test_"))
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "lib" / "pmf_artifact_runtime_check.py"),
            "--structural-only",
            "--out-dir",
            str(out_dir),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["mode"] == "structural"
    assert Path(result["artifacts"]["docx"]).exists()
    assert Path(result["artifacts"]["pdf"]).exists()
    assert all(item["structural_pass"] for item in result["qa"])


def run():
    tests = [
        test_dockerfile_installs_visual_qa_runtime_packages,
        test_artifact_runtime_smoke_check_structural_mode,
    ]
    for test in tests:
        test()
    print(f"ok - {len(tests)} PMF artifact runtime tests passed")


if __name__ == "__main__":
    run()
