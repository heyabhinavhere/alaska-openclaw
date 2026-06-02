"""DocFlow spec builder for Alaska V5 PMF artifacts.

The external DocFlow package supplied by Abhinav defines the right contract:
build one renderer-neutral JSON document spec, then render DOCX/PDF from that
same spec. This module keeps the contract repo-native and stdlib-only so Alaska
can run in the current production image without npm/pip install steps.
"""

from __future__ import annotations

import html
import json
from typing import Any

from .model import FUNNEL_STAGES


DOCFLOW_SCHEMA_VERSION = "docflow_document_spec.v1"
ALLOWED_BLOCK_TYPES = {"heading", "paragraph", "table", "callout", "spacer", "pagebreak"}
ALLOWED_CALLOUT_STYLES = {"info", "warning", "success", "muted"}


def build_docflow_spec(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical DocFlow document spec for a PMF report snapshot."""
    summary = snapshot.get("summary") or {}
    cohort = snapshot.get("cohort") or {}
    report_type = str(snapshot.get("report_type") or "pmf_report")
    privacy_tier = str(snapshot.get("privacy_tier") or "team")
    title = _title(snapshot)
    date = str(snapshot.get("snapshot_date") or snapshot.get("generated_at") or "")
    total = int(summary.get("total_signup_users") or 0)
    real = int(summary.get("real_users") or 0)
    queues = snapshot.get("queues") or []
    quality = snapshot.get("credgpt_quality") or {}
    clusters = quality.get("clusters") or []
    reviews = quality.get("reviews") or []

    blocks: list[dict[str, Any]] = [
        {
            "type": "callout",
            "style": "info",
            "text": (
                f"{_label(report_type)} for {cohort.get('name') or 'PMF cohort'} "
                f"({privacy_tier} view). Generated from structured PMF evidence."
            ),
        },
        {"type": "heading", "level": 1, "text": "Executive Summary"},
        {
            "type": "table",
            "title": "Core Metrics",
            "columns": ["Metric", "Value"],
            "rows": [
                ["Signup users", _num(total)],
                ["Real users", _num(real)],
                ["Real-user rate", _pct(real, total)],
                ["Open operating queues", _num(sum((summary.get("queue_counts") or {}).values()))],
                ["CredGPT reviews", _num(summary.get("credgpt_reviews") or 0)],
                ["Weak CredGPT reviews", _num(summary.get("weak_credgpt_reviews") or 0)],
                ["Quality clusters", _num(summary.get("quality_clusters") or 0)],
            ],
            "widths": [0.68, 0.32],
            "align": ["left", "right"],
        },
        {"type": "heading", "level": 1, "text": "PMF Funnel"},
        {
            "type": "table",
            "title": "Stage Distribution",
            "columns": ["Stage", "Users", "Share of Signups"],
            "rows": _stage_rows(summary.get("stage_counts") or {}, total),
            "widths": [0.58, 0.18, 0.24],
            "align": ["left", "right", "right"],
        },
        {"type": "heading", "level": 1, "text": "Operating Queues"},
        _queue_counts_block(summary.get("queue_counts") or {}),
        _priority_queues_block(queues),
        {"type": "heading", "level": 1, "text": "CredGPT Quality"},
        {
            "type": "table",
            "title": "Quality Review Summary",
            "columns": ["Metric", "Value"],
            "rows": [
                ["Total reviewed turns", _num(len(reviews))],
                ["Flagged/weak turns", _num(summary.get("weak_credgpt_reviews") or 0)],
                ["Recurring clusters", _num(len(clusters))],
            ],
            "widths": [0.68, 0.32],
            "align": ["left", "right"],
        },
        _clusters_block(clusters),
    ]

    if privacy_tier in {"founder", "internal"}:
        blocks.extend(
            [
                {"type": "heading", "level": 1, "text": "User Case File Sample"},
                _users_block(snapshot.get("users") or []),
            ]
        )

    return {
        "schema_version": DOCFLOW_SCHEMA_VERSION,
        "meta": {
            "title": title,
            "subtitle": f"{cohort.get('name') or 'PMF cohort'} | {privacy_tier} view",
            "author": "Alaska PMF Cohort OS",
            "date": date,
            "format": "letter",
        },
        "options": {
            "cover_page": report_type in {"weekly_pmf", "end_cohort", "founder_daily"},
            "table_of_contents": report_type in {"weekly_pmf", "end_cohort", "founder_daily"},
            "page_numbers": True,
            "running_header": True,
            "font": "Arial",
            "accent_color": "1F4E79",
        },
        "blocks": blocks,
    }


def validate_docflow_spec(spec: dict[str, Any]) -> list[str]:
    """Return validation errors for the subset of DocFlow Alaska emits."""
    errors: list[str] = []
    if spec.get("schema_version") != DOCFLOW_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")
    meta = spec.get("meta")
    if not isinstance(meta, dict) or not str(meta.get("title") or "").strip():
        errors.append("missing_meta_title")
    blocks = spec.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        errors.append("missing_blocks")
        return errors
    for idx, block in enumerate(blocks):
        if not isinstance(block, dict):
            errors.append(f"block_{idx}_not_object")
            continue
        btype = block.get("type")
        if btype not in ALLOWED_BLOCK_TYPES:
            errors.append(f"block_{idx}_unsupported_type:{btype}")
        if btype in {"heading", "paragraph", "callout"} and not isinstance(block.get("text"), str):
            errors.append(f"block_{idx}_missing_text")
        if btype == "heading":
            try:
                level = int(block.get("level") or 0)
            except (TypeError, ValueError):
                level = 0
            if level not in {1, 2, 3}:
                errors.append(f"block_{idx}_bad_heading_level")
        if btype == "callout" and block.get("style", "info") not in ALLOWED_CALLOUT_STYLES:
            errors.append(f"block_{idx}_bad_callout_style")
        if btype == "table":
            _validate_table(block, idx, errors)
    return errors


def docflow_docx_body_xml(spec: dict[str, Any]) -> str:
    """Render DocFlow blocks to WordprocessingML body XML."""
    body: list[str] = []
    options = spec.get("options") or {}
    meta = spec.get("meta") or {}
    if options.get("cover_page"):
        body.extend(
            [
                _docx_paragraph(meta.get("title") or "Untitled", "title", align="center"),
                _docx_paragraph(meta.get("subtitle") or "", "subtitle", align="center"),
                _docx_paragraph(" | ".join(str(meta.get(k)) for k in ("author", "date") if meta.get(k)), "body", align="center"),
                _docx_pagebreak(),
            ]
        )
    for block in spec.get("blocks") or []:
        btype = block.get("type")
        if btype == "heading":
            body.append(_docx_paragraph(block.get("text"), f"heading{block.get('level') or 1}"))
        elif btype == "paragraph":
            body.append(_docx_paragraph(block.get("text"), "body"))
        elif btype == "callout":
            body.append(_docx_callout(block.get("text"), block.get("style", "info")))
        elif btype == "table":
            body.append(_docx_table(block))
        elif btype == "spacer":
            body.append(_docx_paragraph("", "body"))
        elif btype == "pagebreak":
            body.append(_docx_pagebreak())
    return "\n".join(item for item in body if item)


def docflow_pdf_lines(spec: dict[str, Any]) -> list[str]:
    """Flatten DocFlow blocks into text lines for the stdlib PDF writer."""
    lines: list[str] = []
    meta = spec.get("meta") or {}
    lines.extend([str(meta.get("title") or "Untitled"), str(meta.get("subtitle") or ""), str(meta.get("date") or ""), ""])
    for block in spec.get("blocks") or []:
        btype = block.get("type")
        if btype == "heading":
            lines.extend(["", str(block.get("text") or "").upper()])
        elif btype in {"paragraph", "callout"}:
            lines.append(_plain(block.get("text")))
        elif btype == "table":
            if block.get("title"):
                lines.extend(["", str(block.get("title"))])
            columns = [str(col) for col in block.get("columns") or []]
            if columns:
                lines.append(" | ".join(columns))
                lines.append("-" * min(92, len(lines[-1])))
            for row in block.get("rows") or []:
                lines.append(" | ".join(_plain(cell) for cell in row))
        elif btype == "pagebreak":
            lines.append("\f")
    return [line for line in lines if line is not None]


def _validate_table(block: dict[str, Any], idx: int, errors: list[str]) -> None:
    columns = block.get("columns")
    rows = block.get("rows")
    if not isinstance(columns, list) or not columns:
        errors.append(f"block_{idx}_table_missing_columns")
        return
    if not isinstance(rows, list):
        errors.append(f"block_{idx}_table_missing_rows")
        return
    width_count = len(columns)
    for row_idx, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != width_count:
            errors.append(f"block_{idx}_row_{row_idx}_width_mismatch")
    widths = block.get("widths")
    if widths is not None:
        if not isinstance(widths, list) or len(widths) != width_count:
            errors.append(f"block_{idx}_bad_width_count")
        else:
            try:
                width_total = sum(float(item) for item in widths)
            except (TypeError, ValueError):
                errors.append(f"block_{idx}_bad_width_value")
            else:
                if abs(width_total - 1.0) > 0.01:
                    errors.append(f"block_{idx}_widths_do_not_sum_to_1")
    aligns = block.get("align")
    if aligns is not None:
        if not isinstance(aligns, list) or len(aligns) != width_count:
            errors.append(f"block_{idx}_bad_align_count")
        elif any(str(item) not in {"left", "center", "right"} for item in aligns):
            errors.append(f"block_{idx}_bad_align_value")


def _stage_rows(stage_counts: dict[str, int], total: int) -> list[list[str]]:
    return [[_label(stage), _num(stage_counts.get(stage) or 0), _pct(stage_counts.get(stage) or 0, total)] for stage in FUNNEL_STAGES]


def _queue_counts_block(queue_counts: dict[str, int]) -> dict[str, Any]:
    rows = [[_label(queue), _num(count)] for queue, count in sorted(queue_counts.items())]
    if not rows:
        rows = [["No open queues", "0"]]
    return {
        "type": "table",
        "title": "Queue Counts",
        "columns": ["Queue", "Open Items"],
        "rows": rows,
        "widths": [0.72, 0.28],
        "align": ["left", "right"],
    }


def _priority_queues_block(queues: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        [_label(item.get("queue_type")), str(item.get("severity") or "P2"), str(item.get("title") or ""), str(item.get("user_key") or "")]
        for item in queues[:25]
    ]
    if not rows:
        rows = [["No priority queue items", "", "", ""]]
    return {
        "type": "table",
        "title": "Priority Queue Items",
        "columns": ["Queue", "Severity", "Title", "User"],
        "rows": rows,
        "widths": [0.28, 0.14, 0.42, 0.16],
        "align": ["left", "center", "left", "left"],
    }


def _clusters_block(clusters: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        [_label(item.get("cluster_type")), str(item.get("severity") or "P2"), str(item.get("title") or ""), str(item.get("status") or "open")]
        for item in clusters[:25]
    ]
    if not rows:
        rows = [["No recurring quality clusters", "", "", ""]]
    return {
        "type": "table",
        "title": "Recurring Quality Clusters",
        "columns": ["Type", "Severity", "Title", "Status"],
        "rows": rows,
        "widths": [0.30, 0.14, 0.42, 0.14],
        "align": ["left", "center", "left", "center"],
    }


def _users_block(users: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        [
            str(item.get("user_key") or ""),
            str(item.get("name") or ""),
            _label(item.get("current_stage") or item.get("funnel_stage")),
            str(item.get("current_health") or item.get("health") or ""),
        ]
        for item in users[:50]
    ]
    if not rows:
        rows = [["No users in registry", "", "", ""]]
    return {
        "type": "table",
        "title": "User Registry Sample",
        "columns": ["User", "Name", "Stage", "Health"],
        "rows": rows,
        "widths": [0.28, 0.24, 0.30, 0.18],
        "align": ["left", "left", "left", "center"],
    }


def _docx_paragraph(text: Any, style: str, *, align: str = "left") -> str:
    if text is None or text == "":
        return "<w:p/>"
    sizes = {
        "title": "44",
        "subtitle": "26",
        "heading1": "32",
        "heading2": "28",
        "heading3": "24",
        "body": "22",
    }
    colors = {
        "title": "1F4E79",
        "subtitle": "555555",
        "heading1": "1F4E79",
        "heading2": "1F4E79",
        "heading3": "333333",
        "body": "1A1A1A",
    }
    bold = "<w:b/>" if style in {"title", "heading1", "heading2", "heading3"} else ""
    justification = f'<w:pPr><w:jc w:val="{align}"/></w:pPr>' if align != "left" else ""
    return (
        f"<w:p>{justification}<w:r><w:rPr>{bold}<w:color w:val=\"{colors.get(style, '1A1A1A')}\"/>"
        f"<w:sz w:val=\"{sizes.get(style, '22')}\"/></w:rPr><w:t>{_xml(_plain(text))}</w:t></w:r></w:p>"
    )


def _docx_table(block: dict[str, Any]) -> str:
    widths = _table_widths(block)
    aligns = _table_aligns(block)
    title_xml = _docx_paragraph(block.get("title"), "heading3") if block.get("title") else ""
    rows_xml: list[str] = []
    columns = [str(col) for col in block.get("columns") or []]
    if columns:
        rows_xml.append(_docx_table_row(columns, widths, aligns, header=True))
    for row_idx, row in enumerate(block.get("rows") or []):
        rows_xml.append(_docx_table_row([str(cell) for cell in row], widths, aligns, shaded=row_idx % 2 == 1))
    grid = "".join(f'<w:gridCol w:w="{width}"/>' for width in widths)
    borders = (
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:color="D6D6D6"/>'
        '<w:left w:val="single" w:sz="4" w:color="D6D6D6"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="D6D6D6"/>'
        '<w:right w:val="single" w:sz="4" w:color="D6D6D6"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="D6D6D6"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="D6D6D6"/></w:tblBorders>'
    )
    table_xml = f'<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/>{borders}</w:tblPr><w:tblGrid>{grid}</w:tblGrid>{"".join(rows_xml)}</w:tbl>'
    return f"{title_xml}{table_xml}"


def _docx_table_row(values: list[str], widths: list[int], aligns: list[str], *, header: bool = False, shaded: bool = False) -> str:
    fill = "1F4E79" if header else "F4F7FB" if shaded else "FFFFFF"
    color = "FFFFFF" if header else "1A1A1A"
    bold = "<w:b/>" if header else ""
    cells = []
    for idx, value in enumerate(values):
        width = widths[idx] if idx < len(widths) else widths[-1]
        align = aligns[idx] if idx < len(aligns) else "left"
        paragraph_props = f'<w:pPr><w:jc w:val="{align}"/></w:pPr>' if align != "left" else ""
        cells.append(
            f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/><w:shd w:fill="{fill}"/>'
            f'<w:tcMar><w:top w:w="90" w:type="dxa"/><w:bottom w:w="90" w:type="dxa"/>'
            f'<w:left w:w="130" w:type="dxa"/><w:right w:w="130" w:type="dxa"/></w:tcMar>'
            f'</w:tcPr><w:p>{paragraph_props}<w:r><w:rPr>{bold}<w:color w:val="{color}"/><w:sz w:val="20"/></w:rPr>'
            f'<w:t>{_xml(_plain(value))}</w:t></w:r></w:p></w:tc>'
        )
    header_props = "<w:trPr><w:tblHeader/></w:trPr>" if header else ""
    return f"<w:tr>{header_props}{''.join(cells)}</w:tr>"


def _docx_callout(text: Any, style: str) -> str:
    fills = {"info": "EAF2FB", "warning": "FDF3E7", "success": "EAF6EE", "muted": "F2F2F2"}
    accents = {"info": "1F4E79", "warning": "C77700", "success": "2E7D32", "muted": "6B6B6B"}
    fill = fills.get(style, fills["info"])
    accent = accents.get(style, accents["info"])
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/></w:tblPr><w:tblGrid><w:gridCol w:w="9360"/></w:tblGrid>'
        f'<w:tr><w:tc><w:tcPr><w:tcW w:w="9360" w:type="dxa"/><w:shd w:fill="{fill}"/>'
        f'<w:tcBorders><w:left w:val="single" w:sz="24" w:color="{accent}"/></w:tcBorders>'
        '<w:tcMar><w:top w:w="140" w:type="dxa"/><w:bottom w:w="140" w:type="dxa"/><w:left w:w="220" w:type="dxa"/><w:right w:w="160" w:type="dxa"/></w:tcMar>'
        f'</w:tcPr><w:p><w:r><w:rPr><w:sz w:val="22"/></w:rPr><w:t>{_xml(_plain(text))}</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    )


def _docx_pagebreak() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def _table_widths(block: dict[str, Any]) -> list[int]:
    columns = block.get("columns") or []
    count = max(1, len(columns))
    widths = block.get("widths")
    if isinstance(widths, list) and len(widths) == count:
        return [max(360, int(float(width) * 9360)) for width in widths]
    base = int(9360 / count)
    return [base for _ in range(count)]


def _table_aligns(block: dict[str, Any]) -> list[str]:
    columns = block.get("columns") or []
    count = max(1, len(columns))
    aligns = block.get("align")
    if isinstance(aligns, list) and len(aligns) == count:
        return [str(item) if str(item) in {"left", "center", "right"} else "left" for item in aligns]
    return ["left" for _ in range(count)]


def _title(snapshot: dict[str, Any]) -> str:
    label = str(snapshot.get("report_type") or "pmf_report").replace("_", " ").title()
    return f"Alaska V5 {label}"


def _label(value: Any) -> str:
    return str(value or "unknown").replace("_", " ").title()


def _num(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value or "0")


def _pct(part: int, whole: int) -> str:
    if not whole:
        return "0.0%"
    return f"{(part / whole) * 100:.1f}%"


def _plain(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value if value is not None else "").replace("**", "").replace("*", "")


def _xml(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=False)
