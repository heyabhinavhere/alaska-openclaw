"""PMF artifact rendering and privacy controls.

Artifacts are generated from a structured snapshot first, then rendered into
human-facing formats. HTML is self-contained. DOCX/PDF are stdlib-generated and
delivery-gated by QA; visual render checks run when the host has soffice and
pdftoppm available.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .docflow import (
    build_docflow_spec,
    docflow_docx_body_xml,
    docflow_pdf_lines,
    validate_docflow_spec,
)
from .model import FUNNEL_STAGES, PII_KEYS, now_utc


def build_report_snapshot(
    *,
    cohort: dict[str, Any],
    users: list[dict[str, Any]],
    queues: list[dict[str, Any]],
    quality_reviews: list[dict[str, Any]] | None = None,
    clusters: list[dict[str, Any]] | None = None,
    privacy_tier: str = "team",
    report_type: str = "daily_cockpit",
    snapshot_date: str | None = None,
) -> dict[str, Any]:
    safe_users = redact_for_privacy(users, privacy_tier)
    counts = _stage_counts(safe_users)
    queue_counts = _count_by(queues, "queue_type")
    quality_reviews = quality_reviews or []
    clusters = clusters or []
    return {
        "schema_version": "pmf_report_snapshot.v1",
        "generated_at": now_utc(),
        "snapshot_date": snapshot_date,
        "report_type": report_type,
        "privacy_tier": privacy_tier,
        "cohort": redact_for_privacy(cohort, privacy_tier),
        "summary": {
            "total_signup_users": len(safe_users),
            "real_users": sum(1 for user in safe_users if user.get("is_real_user")),
            "stage_counts": counts,
            "queue_counts": queue_counts,
            "credgpt_reviews": len(quality_reviews),
            "weak_credgpt_reviews": sum(1 for item in quality_reviews if item.get("quality_state") not in (None, "ok")),
            "quality_clusters": len(clusters),
        },
        "users": safe_users,
        "queues": redact_for_privacy(queues, privacy_tier),
        "credgpt_quality": {
            "reviews": redact_for_privacy(quality_reviews, privacy_tier),
            "clusters": redact_for_privacy(clusters, privacy_tier),
        },
    }


def redact_for_privacy(value: Any, privacy_tier: str) -> Any:
    if privacy_tier != "team":
        return value
    if isinstance(value, list):
        return [redact_for_privacy(item, privacy_tier) for item in value]
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if key_lower in PII_KEYS or any(token in key_lower for token in ("email", "phone", "ssn", "address")):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_for_privacy(item, privacy_tier)
        return redacted
    if isinstance(value, str):
        value = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[redacted-email]", value, flags=re.I)
        value = re.sub(r"\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", "[redacted-phone]", value)
        return value
    return value


def write_snapshot_json(snapshot: dict[str, Any], path: str | Path) -> str:
    path = Path(path)
    _write_private_text(path, json.dumps(snapshot, indent=2, sort_keys=True))
    return str(path)


def write_docflow_spec(spec: dict[str, Any], path: str | Path) -> str:
    errors = validate_docflow_spec(spec)
    if errors:
        raise ValueError(f"invalid DocFlow spec: {', '.join(errors)}")
    path = Path(path)
    _write_private_text(path, json.dumps(spec, indent=2, sort_keys=True))
    return str(path)


def render_html(snapshot: dict[str, Any], path: str | Path) -> str:
    """Render a self-contained PMF cockpit HTML file with no CDN dependency."""
    path = Path(path)
    _prepare_private_path(path)
    summary = snapshot.get("summary", {})
    stage_counts = summary.get("stage_counts", {})
    queue_counts = summary.get("queue_counts", {})
    users = snapshot.get("users", [])[:80]
    queues = snapshot.get("queues", [])[:80]
    clusters = snapshot.get("credgpt_quality", {}).get("clusters", [])[:20]
    max_stage = max(stage_counts.values(), default=1) or 1

    stage_bars = "\n".join(
        f"""
        <div class="bar-row">
          <span>{_label(stage)}</span>
          <div class="bar-track"><div class="bar-fill" style="width:{(stage_counts.get(stage, 0) / max_stage) * 100:.1f}%"></div></div>
          <strong>{stage_counts.get(stage, 0)}</strong>
        </div>
        """
        for stage in FUNNEL_STAGES
    )
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(snapshot.get("report_type", "PMF Report"))}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #15202b;
      --muted: #52616f;
      --line: #d8e0e8;
      --panel: #ffffff;
      --bg: #f6f8fb;
      --blue: #2463eb;
      --green: #168a5b;
      --amber: #b7791f;
      --red: #c2410c;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); }}
    header {{ padding: 28px 32px 18px; background: #0f172a; color: white; }}
    header p {{ margin: 8px 0 0; color: #cbd5e1; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px 20px 40px; }}
    h1 {{ margin: 0; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }}
    .metric .value {{ display: block; font-size: 28px; font-weight: 750; }}
    .metric .label {{ color: var(--muted); font-size: 13px; }}
    .two {{ display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, .9fr); gap: 16px; }}
    .bar-row {{ display: grid; grid-template-columns: 160px minmax(0, 1fr) 44px; gap: 10px; align-items: center; margin: 10px 0; }}
    .bar-track {{ height: 12px; border-radius: 999px; background: #e7edf4; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 999px; background: var(--blue); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 650; }}
    .pill {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: #e7edf4; color: #243447; font-size: 12px; }}
    .P0, .P1 {{ color: var(--red); font-weight: 700; }}
    .P2 {{ color: var(--amber); font-weight: 700; }}
    .P3 {{ color: var(--muted); font-weight: 700; }}
    @media (max-width: 860px) {{ .grid, .two {{ grid-template-columns: 1fr; }} .bar-row {{ grid-template-columns: 120px 1fr 36px; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{_e(_title(snapshot))}</h1>
    <p>{_e(snapshot.get("cohort", {}).get("name", "PMF cohort"))} · {_e(snapshot.get("snapshot_date") or snapshot.get("generated_at"))} · privacy: {_e(snapshot.get("privacy_tier"))}</p>
  </header>
  <main>
    <section class="grid">
      {_metric("Signups", summary.get("total_signup_users", 0))}
      {_metric("Real users", summary.get("real_users", 0))}
      {_metric("Open queues", sum(queue_counts.values()) if isinstance(queue_counts, dict) else 0)}
      {_metric("Weak CredGPT", summary.get("weak_credgpt_reviews", 0))}
    </section>
    <section class="two">
      <div class="panel">
        <h2>PMF Funnel</h2>
        {stage_bars}
      </div>
      <div class="panel">
        <h2>Operating Queues</h2>
        {_queue_count_list(queue_counts)}
      </div>
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>Priority Queue Items</h2>
      {_queues_table(queues)}
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>User Registry Sample</h2>
      {_users_table(users)}
    </section>
    <section class="panel" style="margin-top:16px">
      <h2>CredGPT Quality Clusters</h2>
      {_clusters_table(clusters)}
    </section>
  </main>
</body>
</html>
"""
    _write_private_text(path, html_doc)
    return str(path)


def render_docx(snapshot: dict[str, Any], path: str | Path, *, docflow_spec: dict[str, Any] | None = None) -> str:
    """Render an editable DOCX report from the DocFlow spec using OOXML."""
    path = Path(path)
    _prepare_private_path(path)
    spec = docflow_spec or build_docflow_spec(snapshot)
    errors = validate_docflow_spec(spec)
    if errors:
        raise ValueError(f"invalid DocFlow spec: {', '.join(errors)}")
    body = docflow_docx_body_xml(spec)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1080" w:bottom="1440" w:left="1080"/></w:sectPr>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    _chmod_private_file(path)
    return str(path)


def render_pdf(snapshot: dict[str, Any], path: str | Path, *, docflow_spec: dict[str, Any] | None = None) -> str:
    """Render a lightweight PDF from the DocFlow spec without external deps."""
    path = Path(path)
    _prepare_private_path(path)
    spec = docflow_spec or build_docflow_spec(snapshot)
    errors = validate_docflow_spec(spec)
    if errors:
        raise ValueError(f"invalid DocFlow spec: {', '.join(errors)}")
    lines: list[str] = []
    for line in docflow_pdf_lines(spec):
        if line == "\f":
            lines.extend([""] * 4)
            continue
        lines.extend(_wrap_pdf_line(line, width=92))
    _write_basic_pdf(lines, path)
    _chmod_private_file(path)
    return str(path)


def qa_artifact(path: str | Path, artifact_type: str, *, require_visual: bool = False) -> dict[str, Any]:
    path = Path(path)
    result = {
        "path": str(path),
        "artifact_type": artifact_type,
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "structural_pass": False,
        "visual_render_attempted": False,
        "visual_render_pass": False,
        "passed": False,
        "errors": [],
    }
    if not path.exists():
        result["errors"].append("file_missing")
        return result
    if artifact_type == "html":
        text = path.read_text(encoding="utf-8", errors="replace")
        external_refs = re.findall(r"https?://|//cdn\.|cdnjs|unpkg|jsdelivr", text, flags=re.I)
        result["structural_pass"] = "<html" in text.lower() and "</html>" in text.lower() and not external_refs
        if external_refs:
            result["errors"].append("html_has_external_dependency")
        result["visual_render_pass"] = result["structural_pass"]
    elif artifact_type == "docx":
        result["structural_pass"] = _qa_docx(path, result)
        result["visual_render_pass"] = _visual_qa_docx(path, result)
    elif artifact_type == "pdf":
        result["structural_pass"] = _qa_pdf(path, result)
        result["visual_render_pass"] = _visual_qa_pdf(path, result)
    else:
        result["errors"].append(f"unknown_artifact_type:{artifact_type}")
    result["passed"] = bool(result["structural_pass"] and (result["visual_render_pass"] or not require_visual))
    if require_visual and not result["visual_render_pass"]:
        result["errors"].append("visual_render_qa_not_passed")
    return result


def artifact_ready_for_delivery(qa_results: list[dict[str, Any]]) -> bool:
    """Delivery gate: DOCX/PDF require visual render pass; HTML requires structural pass."""
    for result in qa_results:
        if result.get("artifact_type") in {"docx", "pdf"}:
            if not result.get("structural_pass") or not result.get("visual_render_pass"):
                return False
        elif not result.get("passed"):
            return False
    return True


def _stage_counts(users: list[dict[str, Any]]) -> dict[str, int]:
    counts = {stage: 0 for stage in FUNNEL_STAGES}
    for user in users:
        stage = user.get("current_stage") or user.get("funnel_stage") or "signed_up"
        if stage in counts:
            counts[stage] += 1
    return counts


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _metric(label: str, value: Any) -> str:
    return f"""<div class="panel metric"><span class="value">{_e(value)}</span><span class="label">{_e(label)}</span></div>"""


def _queue_count_list(queue_counts: dict[str, int]) -> str:
    if not queue_counts:
        return "<p>No open operating queues.</p>"
    rows = "".join(f"<tr><td>{_e(_label(key))}</td><td><strong>{count}</strong></td></tr>" for key, count in queue_counts.items())
    return f"<table><tbody>{rows}</tbody></table>"


def _queues_table(queues: list[dict[str, Any]]) -> str:
    if not queues:
        return "<p>No priority queue items.</p>"
    rows = "\n".join(
        f"<tr><td><span class='pill'>{_e(_label(q.get('queue_type')))}</span></td><td class='{_e(q.get('severity', 'P2'))}'>{_e(q.get('severity', 'P2'))}</td><td>{_e(q.get('title'))}</td><td>{_e(q.get('user_key') or '')}</td></tr>"
        for q in queues
    )
    return f"<table><thead><tr><th>Queue</th><th>Severity</th><th>Title</th><th>User</th></tr></thead><tbody>{rows}</tbody></table>"


def _users_table(users: list[dict[str, Any]]) -> str:
    if not users:
        return "<p>No users in registry.</p>"
    rows = "\n".join(
        f"<tr><td>{_e(u.get('user_key'))}</td><td>{_e(u.get('name') or '')}</td><td>{_e(_label(u.get('current_stage') or u.get('funnel_stage')))}</td><td>{_e(u.get('current_health') or u.get('health') or '')}</td><td>{_e(u.get('activated_saver_state') or '')}</td></tr>"
        for u in users
    )
    return f"<table><thead><tr><th>User</th><th>Name</th><th>Stage</th><th>Health</th><th>Saver</th></tr></thead><tbody>{rows}</tbody></table>"


def _clusters_table(clusters: list[dict[str, Any]]) -> str:
    if not clusters:
        return "<p>No recurring CredGPT quality clusters.</p>"
    rows = "\n".join(
        f"<tr><td>{_e(_label(c.get('cluster_type')))}</td><td class='{_e(c.get('severity', 'P2'))}'>{_e(c.get('severity', 'P2'))}</td><td>{_e(c.get('title'))}</td><td>{_e(c.get('description') or '')}</td></tr>"
        for c in clusters
    )
    return f"<table><thead><tr><th>Type</th><th>Severity</th><th>Title</th><th>Description</th></tr></thead><tbody>{rows}</tbody></table>"


def _write_basic_pdf(lines: list[str], path: Path) -> None:
    y_start = 760
    line_height = 14
    pages = [lines[i : i + 48] for i in range(0, len(lines), 48)] or [[]]
    objects: list[bytes] = []
    page_refs = []
    for page_no, page_lines in enumerate(pages):
        content_lines = ["BT", "/F1 10 Tf", f"50 {y_start} Td"]
        for idx, line in enumerate(page_lines):
            if idx:
                content_lines.append(f"0 -{line_height} Td")
            content_lines.append(f"({_pdf_escape(line)}) Tj")
        content_lines.append("ET")
        content = "\n".join(content_lines).encode("latin-1", errors="replace")
        content_obj = len(objects) + 1
        objects.append(f"{content_obj} 0 obj\n<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream\nendobj\n")
        page_obj = len(objects) + 1
        page_refs.append(f"{page_obj} 0 R")
        objects.append(
            f"{page_obj} 0 obj\n<< /Type /Page /Parent PAGES_REF /MediaBox [0 0 612 792] /Resources << /Font << /F1 FONT_REF >> >> /Contents {content_obj} 0 R >>\nendobj\n".encode()
        )
    font_obj = len(objects) + 1
    objects.append(f"{font_obj} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n".encode())
    pages_obj = len(objects) + 1
    pages_blob = f"{pages_obj} 0 obj\n<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>\nendobj\n".encode()
    objects.append(pages_blob)
    catalog_obj = len(objects) + 1
    objects.append(f"{catalog_obj} 0 obj\n<< /Type /Catalog /Pages {pages_obj} 0 R >>\nendobj\n".encode())

    replacements = {
        b"PAGES_REF": f"{pages_obj} 0 R".encode(),
        b"FONT_REF": f"{font_obj} 0 R".encode(),
    }
    rendered = []
    for obj in objects:
        for old, new in replacements.items():
            obj = obj.replace(old, new)
        rendered.append(obj)

    with path.open("wb") as fh:
        fh.write(b"%PDF-1.4\n")
        offsets = [0]
        for obj in rendered:
            offsets.append(fh.tell())
            fh.write(obj)
        xref = fh.tell()
        fh.write(f"xref\n0 {len(rendered) + 1}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]:
            fh.write(f"{offset:010d} 00000 n \n".encode())
        fh.write(
            f"trailer\n<< /Size {len(rendered) + 1} /Root {catalog_obj} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        )


def _qa_docx(path: Path, result: dict[str, Any]) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            ok = "[Content_Types].xml" in names and "word/document.xml" in names
            if not ok:
                result["errors"].append("docx_missing_required_parts")
            return ok
    except zipfile.BadZipFile:
        result["errors"].append("docx_bad_zip")
        return False


def _qa_pdf(path: Path, result: dict[str, Any]) -> bool:
    data = path.read_bytes()
    ok = data.startswith(b"%PDF") and data.rstrip().endswith(b"%%EOF") and len(data) > 300
    if not ok:
        result["errors"].append("pdf_structural_check_failed")
    return ok


def _visual_qa_docx(path: Path, result: dict[str, Any]) -> bool:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    pdftoppm = shutil.which("pdftoppm")
    if not soffice or not pdftoppm:
        return False
    result["visual_render_attempted"] = True
    try:
        with tempfile.TemporaryDirectory(prefix=f"pmf_docx_qa_{path.stem}_") as tmp:
            out_dir = Path(tmp)
            subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            pdf_path = out_dir / f"{path.stem}.pdf"
            if not pdf_path.exists():
                result["errors"].append("docx_pdf_conversion_missing")
                return False
            subprocess.run([pdftoppm, "-png", "-singlefile", str(pdf_path), str(out_dir / "page")], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            return (out_dir / "page.png").exists()
    except (subprocess.SubprocessError, OSError) as exc:
        result["errors"].append(f"docx_visual_render_failed:{exc}")
        return False


def _visual_qa_pdf(path: Path, result: dict[str, Any]) -> bool:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        return False
    result["visual_render_attempted"] = True
    try:
        with tempfile.TemporaryDirectory(prefix=f"pmf_pdf_qa_{path.stem}_") as tmp:
            out_dir = Path(tmp)
            subprocess.run([pdftoppm, "-png", "-singlefile", str(path), str(out_dir / "page")], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            return (out_dir / "page.png").exists()
    except (subprocess.SubprocessError, OSError) as exc:
        result["errors"].append(f"pdf_visual_render_failed:{exc}")
        return False


def _wrap_pdf_line(line: str, width: int) -> list[str]:
    words = line.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _title(snapshot: dict[str, Any]) -> str:
    label = str(snapshot.get("report_type") or "pmf_report").replace("_", " ").title()
    return f"Alaska V5 {label}"


def _label(value: Any) -> str:
    return str(value or "unknown").replace("_", " ").title()


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _xml(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)


def _pdf_escape(value: str) -> str:
    safe = value.encode("latin-1", errors="replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _prepare_private_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass


def _write_private_text(path: Path, text: str) -> None:
    _prepare_private_path(path)
    path.write_text(text, encoding="utf-8")
    _chmod_private_file(path)


def _chmod_private_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
