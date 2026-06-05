"""DocFlow — Alaska's structured document model and its WordprocessingML renderer.

A DocFlow spec is a plain dict (JSON-friendly) describing a document as an
ordered list of typed blocks. It is the single content contract every Alaska
capability uses to produce a beautiful DOCX (and, via lib/alaska_artifacts/pdf,
a text PDF) — audit reports, PMF memos, user case files, weekly digests,
internal docs.

This module is Alaska-owned and stdlib-only. It re-implements (does NOT import)
the hand-built-OOXML technique proven in the V5 PMF artifact code and the audit
renderer: a .docx is a zip of XML, so we emit WordprocessingML directly with
string templates — no python-docx, no LibreOffice, zero heavy dependencies.

Spec shape (mirrors Artifacts and docx/docflow-agent/schema/document-spec.schema.json):

    {
      "meta":   {"title": str (required), "subtitle"?: str,
                 "author"?: str, "date"?: str, "format"?: "letter"|"a4"},
      "options":{"accent_color"?: "RRGGBB", "font"?: str, "page_numbers"?: bool},
      "blocks": [ {"type": ...}, ... ]
    }

Block types:
    heading    {level: 1|2|3, text}
    paragraph  {text}
    bullets    {items: [str, ...]}
    numbered   {items: [str, ...]}
    table      {columns: [str], rows: [[str]], title?, widths?: [float], align?: [str]}
    callout    {text, style: "info"|"warning"|"success"|"muted"}
    spacer     {}
    pagebreak  {}

Public API:
    validate_docflow(spec) -> list[str]          # [] means valid
    build_docx_body_xml(spec) -> str             # inner <w:body> content (no sectPr)
    build_styles_xml(spec) -> str                # word/styles.xml (default font)
"""
from __future__ import annotations

import html
from typing import Any, List

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

DEFAULT_ACCENT = "1F4E79"   # dark slate blue; matches the docflow schema default
DEFAULT_FONT = "Calibri"

ALLOWED_BLOCKS = {
    "heading", "paragraph", "bullets", "numbered",
    "table", "callout", "spacer", "pagebreak",
}
CALLOUT_STYLES = {"info", "warning", "success", "muted"}

# Callout fill / label per style (background shading, twip-free).
_CALLOUT = {
    "info":    ("DDEBF7", "2E74B5", "INFO"),
    "warning": ("FCE4D6", "C55A11", "WARNING"),
    "success": ("E2EFDA", "548235", "OK"),
    "muted":   ("F2F2F2", "808080", "NOTE"),
}

# Page geometry in twips (1 inch = 1440). Usable width = page - 2 * 1in margin.
_PAGE = {
    "letter": (12240, 15840),
    "a4":     (11906, 16838),
}
_MARGIN = 1440
_HEADING_SIZE = {1: 36, 2: 30, 3: 26}   # half-points (so 36 -> 18pt)


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate_docflow(spec: Any) -> List[str]:
    """Return a list of human-readable error strings; empty list means valid.

    Validation is structural only — it never raises, so callers can surface all
    problems at once. render_docx_from_docflow turns a non-empty list into a
    DocflowValidationError before any file is written.
    """
    errors: List[str] = []
    if not isinstance(spec, dict):
        return ["spec must be a dict"]

    meta = spec.get("meta")
    if not isinstance(meta, dict):
        errors.append("meta must be a dict")
    elif not str(meta.get("title", "")).strip():
        errors.append("meta.title is required")
    else:
        fmt = meta.get("format", "letter")
        if fmt not in _PAGE:
            errors.append("meta.format must be one of %s" % sorted(_PAGE))

    blocks = spec.get("blocks")
    if not isinstance(blocks, list):
        errors.append("blocks must be a list")
        return errors

    for i, block in enumerate(blocks):
        where = "blocks[%d]" % i
        if not isinstance(block, dict):
            errors.append("%s must be a dict" % where)
            continue
        btype = block.get("type")
        if btype not in ALLOWED_BLOCKS:
            errors.append("%s.type %r not in %s" % (where, btype, sorted(ALLOWED_BLOCKS)))
            continue
        if btype == "heading":
            if not str(block.get("text", "")).strip():
                errors.append("%s heading needs non-empty text" % where)
            if block.get("level", 1) not in (1, 2, 3):
                errors.append("%s heading.level must be 1, 2 or 3" % where)
        elif btype == "paragraph":
            if "text" not in block:
                errors.append("%s paragraph needs text" % where)
        elif btype in ("bullets", "numbered"):
            items = block.get("items")
            if not isinstance(items, list) or not items:
                errors.append("%s %s needs a non-empty items list" % (where, btype))
        elif btype == "table":
            cols = block.get("columns")
            rows = block.get("rows")
            if not isinstance(cols, list) or not cols:
                errors.append("%s table needs a non-empty columns list" % where)
                cols = []
            if not isinstance(rows, list):
                errors.append("%s table.rows must be a list" % where)
                rows = []
            for r, row in enumerate(rows):
                if not isinstance(row, list):
                    errors.append("%s table.rows[%d] must be a list" % (where, r))
                elif cols and len(row) != len(cols):
                    errors.append("%s table.rows[%d] has %d cells, expected %d"
                                  % (where, r, len(row), len(cols)))
            widths = block.get("widths")
            if widths is not None:
                if not isinstance(widths, list) or (cols and len(widths) != len(cols)):
                    errors.append("%s table.widths must match the column count" % where)
        elif btype == "callout":
            if not str(block.get("text", "")).strip():
                errors.append("%s callout needs non-empty text" % where)
            style = block.get("style", "info")
            if style not in CALLOUT_STYLES:
                errors.append("%s callout.style must be one of %s" % (where, sorted(CALLOUT_STYLES)))
        # spacer / pagebreak carry no fields
    return errors


# --------------------------------------------------------------------------
# small XML helpers
# --------------------------------------------------------------------------

def _esc(value: Any) -> str:
    """XML-escape text content (& < > and quotes); None -> ''."""
    return html.escape("" if value is None else str(value), quote=True)


def _run(text: Any, *, bold: bool = False, italic: bool = False,
         color: str = "", size: int = 0) -> str:
    rpr = []
    if bold:
        rpr.append("<w:b/>")
    if italic:
        rpr.append("<w:i/>")
    if color:
        rpr.append('<w:color w:val="%s"/>' % color)
    if size:
        rpr.append('<w:sz w:val="%d"/>' % size)
        rpr.append('<w:szCs w:val="%d"/>' % size)
    rpr_xml = "<w:rPr>%s</w:rPr>" % "".join(rpr) if rpr else ""
    return '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr_xml, _esc(text))


def _para(runs: str, *, ppr: str = "") -> str:
    return "<w:p>%s%s</w:p>" % (ppr, runs)


def _spacing(before: int = 0, after: int = 120) -> str:
    return '<w:spacing w:before="%d" w:after="%d"/>' % (before, after)


# --------------------------------------------------------------------------
# block renderers
# --------------------------------------------------------------------------

def _heading(block: dict, accent: str) -> str:
    level = block.get("level", 1)
    size = _HEADING_SIZE.get(level, 26)
    ppr = "<w:pPr>%s</w:pPr>" % _spacing(before=240 if level == 1 else 160, after=80)
    return _para(_run(block.get("text", ""), bold=True, color=accent, size=size), ppr=ppr)


def _paragraph(block: dict) -> str:
    ppr = "<w:pPr>%s</w:pPr>" % _spacing(after=120)
    return _para(_run(block.get("text", "")), ppr=ppr)


def _list(block: dict, numbered: bool) -> str:
    out = []
    ppr = '<w:pPr><w:ind w:left="360" w:hanging="360"/>%s</w:pPr>' % _spacing(after=40)
    for idx, item in enumerate(block.get("items", []), start=1):
        marker = ("%d. " % idx) if numbered else "• "
        out.append(_para(_run(marker + str(item)), ppr=ppr))
    return "".join(out)


def _usable_width(spec: dict) -> int:
    fmt = (spec.get("meta") or {}).get("format", "letter")
    page_w = _PAGE.get(fmt, _PAGE["letter"])[0]
    return page_w - 2 * _MARGIN


def _col_widths(block: dict, total: int) -> List[int]:
    cols = block.get("columns", [])
    n = len(cols)
    if n == 0:
        return []
    widths = block.get("widths")
    if isinstance(widths, list) and len(widths) == n:
        total_frac = sum(float(w) for w in widths) or 1.0
        return [max(1, int(total * float(w) / total_frac)) for w in widths]
    return [max(1, total // n)] * n


def _cell(text: Any, width: int, *, fill: str = "", bold: bool = False,
          color: str = "", align: str = "left") -> str:
    shd = '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>' % fill if fill else ""
    jc = '<w:jc w:val="%s"/>' % align if align in ("center", "right") else ""
    ppr = "<w:pPr>%s%s</w:pPr>" % (jc, _spacing(before=20, after=20))
    tcpr = '<w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s</w:tcPr>' % (width, shd)
    return "<w:tc>%s%s</w:tc>" % (tcpr, _para(_run(text, bold=bold, color=color), ppr=ppr))


_BORDER = (
    "<w:tblBorders>"
    + "".join('<w:%s w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>' % e
              for e in ("top", "left", "bottom", "right", "insideH", "insideV"))
    + "</w:tblBorders>"
)


def _table(block: dict, accent: str, total: int) -> str:
    cols = [str(c) for c in block.get("columns", [])]
    rows = block.get("rows", [])
    aligns = block.get("align") or ["left"] * len(cols)
    widths = _col_widths(block, total)

    grid = "".join('<w:gridCol w:w="%d"/>' % w for w in widths)
    header = "<w:tr>%s</w:tr>" % "".join(
        _cell(c, widths[i], fill=accent, bold=True, color="FFFFFF",
              align=aligns[i] if i < len(aligns) else "left")
        for i, c in enumerate(cols))
    body_rows = []
    for r, row in enumerate(rows):
        fill = "F2F6FB" if r % 2 else ""   # subtle zebra striping
        cells = "".join(
            _cell(val, widths[i], fill=fill, align=aligns[i] if i < len(aligns) else "left")
            for i, val in enumerate(row))
        body_rows.append("<w:tr>%s</w:tr>" % cells)

    tblpr = ('<w:tblPr><w:tblW w:w="%d" w:type="dxa"/>%s'
             '<w:tblLayout w:type="fixed"/></w:tblPr>' % (sum(widths), _BORDER))
    caption = ""
    if block.get("title"):
        caption = _para(_run(block["title"], bold=True, color=accent, size=24),
                        ppr="<w:pPr>%s</w:pPr>" % _spacing(before=160, after=40))
    spacer = _para("")  # breathing room after a table
    return caption + "<w:tbl>%s<w:tblGrid>%s</w:tblGrid>%s%s</w:tbl>" % (
        tblpr, grid, header, "".join(body_rows)) + spacer


def _callout(block: dict, total: int) -> str:
    style = block.get("style", "info")
    fill, accent, label = _CALLOUT.get(style, _CALLOUT["info"])
    text = "%s: %s" % (label, block.get("text", ""))
    tcpr = ('<w:tcPr><w:tcW w:w="%d" w:type="dxa"/>'
            '<w:shd w:val="clear" w:color="auto" w:fill="%s"/>'
            '<w:tcMar><w:top w:w="80" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/>'
            '<w:left w:w="120" w:type="dxa"/><w:right w:w="120" w:type="dxa"/></w:tcMar>'
            '</w:tcPr>' % (total, fill))
    cell = "<w:tc>%s%s</w:tc>" % (tcpr, _para(_run(text, bold=True, color=accent)))
    tblpr = ('<w:tblPr><w:tblW w:w="%d" w:type="dxa"/>'
             '<w:tblLayout w:type="fixed"/></w:tblPr>' % total)
    return ("<w:tbl>%s<w:tblGrid><w:gridCol w:w=\"%d\"/></w:tblGrid>"
            "<w:tr>%s</w:tr></w:tbl>" % (tblpr, total, cell)) + _para("")


def _pagebreak() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def _title_block(spec: dict, accent: str) -> str:
    meta = spec.get("meta") or {}
    out = [_para(_run(meta.get("title", ""), bold=True, color=accent, size=48),
                 ppr="<w:pPr>%s</w:pPr>" % _spacing(after=60))]
    if meta.get("subtitle"):
        out.append(_para(_run(meta["subtitle"], color="595959", size=28),
                         ppr="<w:pPr>%s</w:pPr>" % _spacing(after=40)))
    byline = " · ".join(str(meta[k]) for k in ("author", "date") if meta.get(k))
    if byline:
        out.append(_para(_run(byline, italic=True, color="808080", size=20),
                         ppr="<w:pPr>%s</w:pPr>" % _spacing(after=200)))
    return "".join(out)


# --------------------------------------------------------------------------
# public builders
# --------------------------------------------------------------------------

def build_docx_body_xml(spec: dict) -> str:
    """Render the inner content of <w:body> for a (validated) DocFlow spec.

    The document envelope and <w:sectPr> are added by lib/alaska_artifacts/docx.
    """
    options = spec.get("options") or {}
    accent = str(options.get("accent_color") or DEFAULT_ACCENT).lstrip("#")
    total = _usable_width(spec)

    parts = [_title_block(spec, accent)]
    for block in spec.get("blocks", []):
        btype = block.get("type")
        if btype == "heading":
            parts.append(_heading(block, accent))
        elif btype == "paragraph":
            parts.append(_paragraph(block))
        elif btype == "bullets":
            parts.append(_list(block, numbered=False))
        elif btype == "numbered":
            parts.append(_list(block, numbered=True))
        elif btype == "table":
            parts.append(_table(block, accent, total))
        elif btype == "callout":
            parts.append(_callout(block, total))
        elif btype == "spacer":
            parts.append(_para(""))
        elif btype == "pagebreak":
            parts.append(_pagebreak())
    return "".join(parts)


def build_styles_xml(spec: dict) -> str:
    """Minimal word/styles.xml setting the document default font + size."""
    options = spec.get("options") or {}
    font = _esc(options.get("font") or DEFAULT_FONT)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:styles xmlns:w="%s"><w:docDefaults><w:rPrDefault><w:rPr>'
        '<w:rFonts w:ascii="%s" w:hAnsi="%s" w:cs="%s"/>'
        '<w:sz w:val="22"/><w:szCs w:val="22"/>'
        '</w:rPr></w:rPrDefault></w:docDefaults></w:styles>' % (W_NS, font, font, font)
    )


def sect_pr(spec: dict) -> str:
    """The trailing <w:sectPr> (page size + margins) for the body."""
    fmt = (spec.get("meta") or {}).get("format", "letter")
    page_w, page_h = _PAGE.get(fmt, _PAGE["letter"])
    return ('<w:sectPr><w:pgSz w:w="%d" w:h="%d"/>'
            '<w:pgMar w:top="%d" w:right="%d" w:bottom="%d" w:left="%d" '
            'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
            % (page_w, page_h, _MARGIN, _MARGIN, _MARGIN, _MARGIN))
