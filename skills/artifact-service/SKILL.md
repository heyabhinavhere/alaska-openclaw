---
name: artifact-service
description: >-
  Reusable platform service for generating beautiful documents (DOCX, text PDF)
  from a structured DocFlow model or a DOCX template, validating them, storing
  them, and delivering them to Slack. Stdlib-only — no heavy document packages.
  Use when any skill needs to produce a downloadable report, memo, case file,
  digest, or internal doc. Library lives in lib/alaska_artifacts/.
version: 0.1.0
metadata:
  openclaw:
    always: false
    emoji: "📄"
    requires:
      bins: [python3]
      env: [SLACK_BOT_TOKEN]
---

# Artifact Service

Platform layer (P0) for on-demand document generation and delivery. Any Alaska
capability — audit reports, PMF memos, user case files, weekly digests, internal
docs — produces a document the same way: build a **DocFlow** spec (or fill a DOCX
template), validate, store, deliver to Slack.

It is **stdlib-only** (Python 3.9 `zipfile` + `xml.etree`). It adds **no** heavy
packages (no python-docx, reportlab, LibreOffice, weasyprint), so it runs on the
slim OpenClaw/Railway image unchanged.

## How to use it

**From Python (inside a skill/agent step):**

```python
import sys; sys.path.insert(0, "/opt/lib")   # or repo lib/ locally
from alaska_artifacts import (
    render_docx_from_docflow, render_docx_from_template, validate_docx,
    store_artifact, upload_artifact_to_slack,
)

spec = {
  "meta": {"title": "Weekly Digest", "subtitle": "BON Credit", "date": "2026-06-05"},
  "blocks": [
    {"type": "heading", "level": 1, "text": "Shipped"},
    {"type": "bullets", "items": ["Task A", "Task B"]},
    {"type": "table", "columns": ["Owner", "Count"], "rows": [["Sandeep", "2"]]},
    {"type": "callout", "style": "success", "text": "On track for launch."},
  ],
}
res  = render_docx_from_docflow(spec, "/tmp/digest.docx")
assert validate_docx(res["path"])["ok"]
meta = store_artifact(res["path"], "docx", owner_skill="weekly-digest", run_id="2026-06-05")
upload_artifact_to_slack(meta["path"], channel_id="C0123", initial_comment="This week's digest")
```

**From the CLI (subprocess, e.g. from a cron prompt):**

```bash
PYTHONPATH=/opt/lib python3 -m alaska_artifacts.cli render-docflow spec.json out.docx
PYTHONPATH=/opt/lib python3 -m alaska_artifacts.cli fill-template tpl.docx repl.json out.docx
PYTHONPATH=/opt/lib python3 -m alaska_artifacts.cli validate out.docx
PYTHONPATH=/opt/lib python3 -m alaska_artifacts.cli store out.docx --type docx --owner audit --run 1414
PYTHONPATH=/opt/lib python3 -m alaska_artifacts.cli upload out.docx --channel C0123
```

## DocFlow blocks

`heading` (level 1-3), `paragraph`, `bullets`, `numbered`, `table`
(`columns`, `rows`, optional `title`/`widths`/`align`), `callout`
(`style`: info|warning|success|muted), `spacer`, `pagebreak`.
`meta.title` is required; `meta.format` is `letter` (default) or `a4`;
`options.accent_color` / `options.font` theme the document.

## Template fill

`render_docx_from_template(template_path, replacements, output_path, table_fills=...)`
rewrites `word/document.xml` and copies every other part untouched, so the
template's exact styling is preserved. Use **clean single-run tokens** in the
template (e.g. `{{user_id}}` or `[User ID]`). The fill is a loud failure (raises
`TemplateRenderError`) if any provided key, generic `[...]`/`{{...}}` placeholder,
or forbidden substring survives — it never emits a half-filled document.

## Storage & validation rules

- Artifacts: `/data/workspace/artifacts/<owner_skill>/<run_id>/<file>` (override
  base with `$ALASKA_ARTIFACTS_DIR`). Metadata sidecar `<file>.meta.json` +
  append-only `index.jsonl`. **No database writes.**
- Re-runs never overwrite an existing artifact unless `overwrite=True`.
- `validate_docx` is the delivery gate: valid zip, non-empty, required parts,
  well-formed XML, no unresolved placeholders / forbidden substrings.
- Slack upload is best-effort: a failure is reported but never raises and never
  deletes the on-disk artifact (so a retry can re-send).

## PDF

`render_pdf_from_docflow` produces a **text-only** PDF (single Helvetica face) —
ideal for plain memos/briefs. For a styled deliverable use DOCX. Rich,
print-styled PDF (DOCX→PDF via LibreOffice) is the P2 path and would require
adding packages to the image — not enabled here.

## Boundaries

This service is Alaska-owned and **studies but never imports** V5 PMF artifact
code (`lib/pmf_os/*`) or the audit skill (`skills/bon-internal-audit/*`). It does
**not** send Customer.io / SMS / email — Slack file delivery only.
