"""PDF rendering from a DocFlow spec — stdlib only, text-only.

A .pdf is hand-written using the raw PDF 1.4 object format (catalog, pages,
Helvetica font, content streams, xref, trailer). No reportlab, no weasyprint, no
wkhtmltopdf — none of which exist in the slim OpenClaw/Railway image.

Scope is deliberately honest: this renders the document's TEXT (headings,
paragraphs, bullets, numbered lists, tables flattened to aligned rows, callouts)
in a single Helvetica face. It is ideal for plain memos and briefs. It does NOT
do colors, bold, real table borders, or images — for a styled deliverable use
render_docx_from_docflow (DOCX). Rich/printable PDF (DOCX->PDF via LibreOffice)
is the P2 path and would require adding packages to the image.

    render_pdf_from_docflow(spec, output_path) -> dict
    flatten_docflow_to_lines(spec) -> list[str]
    validate_pdf(path) -> dict
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from . import docflow
from .docx import DocflowValidationError

PAGE_W, PAGE_H = 612, 792          # US Letter, points
MARGIN_X, TOP_Y = 54, 750
LEADING = 14
LINES_PER_PAGE = 48
WRAP = 95
FORM_FEED = "\f"


# --------------------------------------------------------------------------
# flatten a DocFlow spec to plain text lines
# --------------------------------------------------------------------------

def _wrap(text: str, width: int = WRAP) -> List[str]:
    text = text.rstrip()
    if not text:
        return [""]
    out: List[str] = []
    line = ""
    for word in text.split(" "):
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = word if not line else (line + " " + word)
    out.append(line)
    return out


def flatten_docflow_to_lines(spec: dict) -> List[str]:
    """Turn a DocFlow spec into a flat list of text lines (with FORM_FEED markers
    for page breaks). Used by the PDF writer; also handy for plain-text export."""
    meta = spec.get("meta") or {}
    lines: List[str] = []
    if meta.get("title"):
        lines.append(str(meta["title"]).upper())
    if meta.get("subtitle"):
        lines.append(str(meta["subtitle"]))
    byline = " · ".join(str(meta[k]) for k in ("author", "date") if meta.get(k))
    if byline:
        lines.append(byline)
    if lines:
        lines.append("")

    for block in spec.get("blocks", []):
        btype = block.get("type")
        if btype == "heading":
            lines.append("")
            lines.append(str(block.get("text", "")).upper() if block.get("level", 1) == 1
                         else str(block.get("text", "")))
            lines.append("")
        elif btype == "paragraph":
            lines.append(str(block.get("text", "")))
            lines.append("")
        elif btype == "bullets":
            for item in block.get("items", []):
                lines.append("  - " + str(item))
            lines.append("")
        elif btype == "numbered":
            for i, item in enumerate(block.get("items", []), start=1):
                lines.append("  %d. %s" % (i, item))
            lines.append("")
        elif btype == "table":
            cols = [str(c) for c in block.get("columns", [])]
            rows = block.get("rows", [])
            if block.get("title"):
                lines.append(str(block["title"]))
            widths = [len(c) for c in cols]
            for row in rows:
                for i, cell in enumerate(row):
                    if i < len(widths):
                        widths[i] = max(widths[i], len(str(cell)))
            def fmt(cells: list) -> str:
                return " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(cells) if i < len(widths))
            if cols:
                lines.append(fmt(cols))
                lines.append("-+-".join("-" * w for w in widths))
            for row in rows:
                lines.append(fmt(row))
            lines.append("")
        elif btype == "callout":
            label = block.get("style", "info").upper()
            lines.append("[%s] %s" % (label, block.get("text", "")))
            lines.append("")
        elif btype == "spacer":
            lines.append("")
        elif btype == "pagebreak":
            lines.append(FORM_FEED)
    return lines


# --------------------------------------------------------------------------
# minimal PDF writer
# --------------------------------------------------------------------------

def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _paginate(lines: List[str]) -> List[List[str]]:
    pages: List[List[str]] = []
    cur: List[str] = []
    for raw in lines:
        if raw == FORM_FEED:
            pages.append(cur)
            cur = []
            continue
        for wrapped in _wrap(raw):
            if len(cur) >= LINES_PER_PAGE:
                pages.append(cur)
                cur = []
            cur.append(wrapped)
    if cur or not pages:
        pages.append(cur)
    return pages


def _content_stream(page_lines: List[str]) -> bytes:
    parts = ["BT", "/F1 10 Tf", "%d TL" % LEADING, "%d %d Td" % (MARGIN_X, TOP_Y)]
    for line in page_lines:
        parts.append("(%s) Tj" % _esc(line))
        parts.append("T*")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1", "replace")


def _write_pdf(pages: List[List[str]], path: str) -> int:
    objects: List[bytes] = []          # object bodies in order, 1-indexed
    # 1: Catalog, 2: Pages, 3: Font, then (content, page) pairs.
    page_obj_nums = [5 + 2 * i for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join("%d 0 R" % n for n in page_obj_nums)
    objects.append(("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(pages))).encode("latin-1"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, page_lines in enumerate(pages):
        stream = _content_stream(page_lines)
        content = (b"<< /Length %d >>\nstream\n" % len(stream)) + stream + b"\nendstream"
        objects.append(content)
        page = ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
                "/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>"
                % (PAGE_W, PAGE_H, 4 + 2 * i)).encode("latin-1")
        objects.append(page)

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += ("%d 0 obj\n" % num).encode("latin-1") + body + b"\nendobj\n"
    xref_pos = len(out)
    count = len(objects) + 1
    out += ("xref\n0 %d\n" % count).encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += ("%010d 00000 n \n" % off).encode("latin-1")
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (count, xref_pos)).encode("latin-1")

    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(out)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return len(out)


def render_pdf_from_docflow(spec: dict, output_path: str) -> Dict[str, Any]:
    """Render a validated DocFlow spec to a text-only PDF at output_path.

    Raises DocflowValidationError if the spec is invalid. Returns
    {path, bytes, pages}.
    """
    errors = docflow.validate_docflow(spec)
    if errors:
        raise DocflowValidationError(errors)
    pages = _paginate(flatten_docflow_to_lines(spec))
    size = _write_pdf(pages, output_path)
    return {"path": os.path.abspath(output_path), "bytes": size, "pages": len(pages)}


def validate_pdf(path: str) -> Dict[str, Any]:
    """Lightweight structural check: exists, non-empty, %PDF header, %%EOF trailer."""
    errors: List[str] = []
    if not os.path.exists(path):
        return {"ok": False, "errors": ["file_missing"], "bytes": 0}
    size = os.path.getsize(path)
    if size <= 0:
        errors.append("file_empty")
    with open(path, "rb") as fh:
        head = fh.read(8)
        fh.seek(max(0, size - 1024))
        tail = fh.read()
    if not head.startswith(b"%PDF-"):
        errors.append("missing_pdf_header")
    if b"%%EOF" not in tail:
        errors.append("missing_eof")
    return {"ok": not errors, "errors": errors, "bytes": size}
