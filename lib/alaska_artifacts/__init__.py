"""Alaska Artifact Service — reusable DOCX/PDF generation + Slack delivery.

Stdlib-only platform layer that any Alaska capability (audit reports, PMF memos,
user case files, weekly digests, internal docs) can reuse to produce a beautiful
document and deliver it to Slack. No heavy dependencies (no python-docx,
reportlab, LibreOffice, weasyprint) — the slim OpenClaw/Railway image ships only
Python 3.9 + stdlib, which is all this needs.

This package is Alaska-owned. It STUDIES, but never imports, the V5 PMF artifact
code (lib/pmf_os/*) or the audit skill (skills/bon-internal-audit/*).

Typical use:

    from alaska_artifacts import (
        render_docx_from_docflow, render_docx_from_template, validate_docx,
        store_artifact, upload_artifact_to_slack,
    )

    spec = {"meta": {"title": "Weekly Digest"}, "blocks": [...]}
    res = render_docx_from_docflow(spec, "/tmp/digest.docx")
    assert validate_docx(res["path"])["ok"]
    meta = store_artifact(res["path"], "docx", "weekly-digest", "2026-06-05")
    upload_artifact_to_slack(meta["path"], channel_id="C123")
"""
from __future__ import annotations

from .docflow import build_docx_body_xml, validate_docflow
from .docx import (
    DEFAULT_PLACEHOLDER_PATTERNS,
    DocflowValidationError,
    TemplateRenderError,
    render_docx_from_docflow,
    render_docx_from_template,
    validate_docx,
    validate_docx_no_placeholders,
)
from .pdf import flatten_docflow_to_lines, render_pdf_from_docflow, validate_pdf
from .slack_upload import SlackAuthError, post_message, upload_artifact_to_slack
from .store import (
    ArtifactExistsError,
    artifacts_base,
    get_artifact_metadata,
    list_artifacts,
    store_artifact,
)

__version__ = "0.1.0"

__all__ = [
    # docflow
    "validate_docflow",
    "build_docx_body_xml",
    # docx
    "render_docx_from_docflow",
    "render_docx_from_template",
    "validate_docx",
    "validate_docx_no_placeholders",
    "DEFAULT_PLACEHOLDER_PATTERNS",
    "DocflowValidationError",
    "TemplateRenderError",
    # pdf
    "render_pdf_from_docflow",
    "validate_pdf",
    "flatten_docflow_to_lines",
    # store
    "store_artifact",
    "get_artifact_metadata",
    "list_artifacts",
    "artifacts_base",
    "ArtifactExistsError",
    # slack
    "upload_artifact_to_slack",
    "post_message",
    "SlackAuthError",
    "__version__",
]
