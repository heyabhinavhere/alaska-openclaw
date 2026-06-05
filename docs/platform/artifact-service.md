# Artifact Service

Reusable, stdlib-only document generation + delivery for every Alaska capability.
This is the integration reference: the API, the DocFlow model, template-fill,
storage, validation, Slack delivery, and how Audit migrates onto it.

Code: `lib/alaska_artifacts/` · Skill: `skills/artifact-service/SKILL.md`
Tests: `tests/test_alaska_artifacts.py`

## Why stdlib-only

The OpenClaw/Railway image is slim (no python-docx, reportlab, LibreOffice,
weasyprint). A `.docx` is a zip of XML and a `.pdf` is a simple object file, so we
hand-build both with `zipfile` + `xml.etree` (DOCX) and a tiny PDF writer — zero
heavy dependencies. This is the proven approach already used (independently) by
the V5 PMF artifact code and the audit renderer; the platform re-implements it
generically and **does not import** that workstream code.

## API

```python
from alaska_artifacts import (
    render_docx_from_docflow,        # (spec, output_path) -> {path, bytes, parts, blocks}
    render_docx_from_template,       # (template_path, replacements, output_path, *, table_fills=, ...) -> {path, ...}
    render_pdf_from_docflow,         # (spec, output_path) -> {path, bytes, pages}   (text-only)
    validate_docx,                   # (path, ...) -> {ok, errors, bytes, parts}
    validate_docx_no_placeholders,   # (path, ...) -> [leftover placeholder strings]
    validate_pdf,                    # (path) -> {ok, errors, bytes}
    store_artifact,                  # (path, artifact_type, owner_skill, run_id, *, overwrite=False) -> metadata
    get_artifact_metadata,           # (artifact_id) -> metadata | None
    list_artifacts,                  # (owner_skill=None) -> [index rows]
    upload_artifact_to_slack,        # (path, channel_id, *, thread_ts=, title=, ...) -> {ok, step, ...}
    post_message,                    # (channel_id, text, ...) -> {ok, ts, ...}
)
```

CLI (subprocess, e.g. from a cron prompt; `PYTHONPATH=/opt/lib`):

```
python3 -m alaska_artifacts.cli render-docflow spec.json out.docx
python3 -m alaska_artifacts.cli render-pdf      spec.json out.pdf
python3 -m alaska_artifacts.cli fill-template   tpl.docx repl.json out.docx [--table-fills tf.json]
python3 -m alaska_artifacts.cli validate        out.docx
python3 -m alaska_artifacts.cli store           out.docx --type docx --owner audit --run 1414
python3 -m alaska_artifacts.cli upload          out.docx --channel C123 [--thread TS] [--comment "..."]
python3 -m alaska_artifacts.cli metadata        audit/1414/report.docx
```

## DocFlow document model

A spec is a JSON-friendly dict (mirrors
`Artifacts and docx/docflow-agent/schema/document-spec.schema.json`):

```jsonc
{
  "meta":   {"title": "Weekly Digest",      // required
             "subtitle": "BON Credit", "author": "Alaska",
             "date": "2026-06-05", "format": "letter"},   // letter | a4
  "options":{"accent_color": "1F4E79", "font": "Calibri"},
  "blocks": [
    {"type": "heading",   "level": 1, "text": "Summary"},
    {"type": "paragraph", "text": "Shipped 4 tasks this week."},
    {"type": "bullets",   "items": ["First", "Second"]},
    {"type": "numbered",  "items": ["Step one", "Step two"]},
    {"type": "table",     "title": "Owners", "columns": ["Name", "Tasks"],
                          "rows": [["Sandeep", "2"], ["Pankaj", "3"]],
                          "align": ["left", "right"], "widths": [0.7, 0.3]},
    {"type": "callout",   "style": "warning", "text": "One blocker is overdue."},
    {"type": "spacer"},
    {"type": "pagebreak"}
  ]
}
```

`validate_docflow(spec)` returns a list of human-readable errors (`[]` = valid);
`render_docx_from_docflow` raises `DocflowValidationError` on an invalid spec
before writing anything.

## Template fill

`render_docx_from_template(template_path, replacements, output_path, *, table_fills=None, forbid_placeholder_patterns=DEFAULT, forbid_substrings=())`

- Rewrites only `word/document.xml`; copies every other part byte-for-byte, so
  the template's styles/header/footer/fonts are preserved exactly.
- **Scalar tokens:** each `replacements` key is substring-replaced inside every
  `<w:t>` run. Use **clean single-run tokens** in templates (`{{user_id}}`,
  `[User ID]`); a token Word split across runs is caught by the post-fill guard
  rather than silently half-filled.
- **Table rows:** `table_fills=[{"locate": "<header substring>", "rows": [[...], ...]}]`
  finds the table whose header contains `locate`, clones its prototype data row
  per item (preserving cell styling), and fills positionally.
- **Guards (each raises `TemplateRenderError`):** any provided key still present;
  any leftover `[...]`/`{{...}}` placeholder (pass `forbid_placeholder_patterns=()`
  for templates that use brackets legitimately); any `forbid_substrings`
  (e.g. `("—",)` to forbid em dashes — a BON house-style rule).

## Storage (filesystem JSON, no DB)

```
<base>/<owner_skill>/<run_id>/<file>            # the artifact (chmod 600)
<base>/<owner_skill>/<run_id>/<file>.meta.json  # metadata sidecar
<base>/index.jsonl                              # append-only registry
```

`<base>` = `$ALASKA_ARTIFACTS_DIR` or `/data/workspace/artifacts`.
`store_artifact` copies (never moves) the source, computes `sha256`/`bytes`, and
**refuses to overwrite** an existing artifact unless `overwrite=True` (a retry
can't clobber a prior good report). Path segments are sanitized (no traversal).
`artifact_id` is `"<owner_skill>/<run_id>/<file>"`. No database is touched.

## Validation rules (the delivery gate)

`validate_docx` returns `{ok, errors, bytes, parts}` and checks: file exists,
size > 0, opens as a valid zip, required parts present
(`[Content_Types].xml` + `word/document.xml`), `word/document.xml` is well-formed
XML, no unresolved placeholders, no forbidden substrings. `validate_pdf` checks
exists / non-empty / `%PDF-` header / `%%EOF` trailer. Slack upload failures
never delete the artifact, so a failed delivery is always retryable.

## Slack delivery

`upload_artifact_to_slack(path, channel_id, thread_ts=None, ...)` uses Slack's
3-step external-upload flow (`files.getUploadURLExternal` → PUT bytes →
`files.completeUploadExternal`). The transport is **injectable** (`http_request=`)
so tests run with a fake — and delivery is **best-effort**: it returns a
structured result, never raises, and never deletes the file. Needs
`SLACK_BOT_TOKEN`.

## PDF scope

`render_pdf_from_docflow` produces a **text-only** PDF (single Helvetica face) —
great for plain memos and briefs, and proven valid (recognized as `PDF document,
version 1.4`). For a styled deliverable use **DOCX**. Rich, print-styled PDF
(DOCX→PDF via LibreOffice) is the **P2** path and would require adding packages
to the image — explicitly out of scope here and gated on approval (it would also
break `tests/test_pmf_artifact_runtime.py`'s slim-image guard).

## How Audit migrates onto the service (platform PR #4)

Audit v1 ships its own `audit_render.py` (correct for shipping fast). To migrate
without disruption, later and with approval:

1. Keep producing the audit JSON from `bon-internal-audit`.
2. Replace audit's bespoke render+upload with the platform:
   `render_docx_from_template(audit_template, replacements, out, table_fills=[...])`
   → `validate_docx(out)` → `store_artifact(out, "docx", "bon-internal-audit", audit_id)`
   → `upload_artifact_to_slack(meta["path"], channel, thread_ts=...)`.
3. Record `store_artifact`'s returned `path` in audit's existing
   `audit_runs.artifact_path` (its own `alaska_audit.db`). The platform adds no
   schema and writes no DB.

This consolidates one stdlib OOXML implementation behind a tested, reusable API
while leaving Audit v1's behavior unchanged until the swap is approved.
