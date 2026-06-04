"""DOCX rendering, template-fill and validation — stdlib only.

Three entry points power every Alaska document workflow:

    render_docx_from_docflow(spec, output_path)
        Build a brand-new .docx from a DocFlow spec (see docflow.py). Hand-built
        OOXML zip; no python-docx, no LibreOffice.

    render_docx_from_template(template_path, replacements, output_path, ...)
        Fill an existing .docx template by token replacement (+ optional table
        row expansion). Rewrites word/document.xml in place and copies every
        other part untouched, so the template's exact styling is preserved.
        This is a generic, dependency-decoupled re-implementation of the proven
        technique in skills/bon-internal-audit/audit_render.py (which we study,
        never import — it is audit-owned and bound to audit_validate).

    validate_docx(path, ...) / validate_docx_no_placeholders(path, ...)
        The delivery gate: valid zip, non-empty, required parts present,
        well-formed XML, and no unresolved placeholders / forbidden substrings.

A .docx is a zip of XML. We rely only on zipfile + xml.etree from the stdlib,
which the slim OpenClaw/Railway image ships (Python 3.9).
"""
from __future__ import annotations

import copy
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional, Sequence

from . import docflow

W = "{%s}" % docflow.W_NS
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

# Default "this looks like an unfilled placeholder" patterns. Override with ()
# to disable (templates that legitimately contain square brackets).
DEFAULT_PLACEHOLDER_PATTERNS = (r"\[[^\]\n]{1,60}\]", r"\{\{[^}\n]{1,60}\}\}")

DOCX_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '</Types>'
)
DOCX_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    '</Relationships>'
)
DOCX_DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    '</Relationships>'
)
REQUIRED_PARTS = ("[Content_Types].xml", "word/document.xml")


class DocflowValidationError(ValueError):
    """The DocFlow spec failed structural validation."""
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("invalid docflow spec: %s" % "; ".join(errors))


class TemplateRenderError(RuntimeError):
    """Template fill left a placeholder behind, or a forbidden substring."""


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------

def _write_zip(output_path: str, members: "list[tuple[str, Any]]") -> int:
    """Write an ordered list of (name, str|bytes) members as a deflated zip.
    Creates parent dirs, chmod 0600. Returns the byte size of the result."""
    parent = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(parent, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)
    try:
        os.chmod(output_path, 0o600)
    except OSError:
        pass
    return os.path.getsize(output_path)


def _document_xml(spec: dict) -> str:
    body = docflow.build_docx_body_xml(spec)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document xmlns:w="%s"><w:body>%s%s</w:body></w:document>'
            % (docflow.W_NS, body, docflow.sect_pr(spec)))


def _register_namespaces(xml_bytes: bytes) -> None:
    head = xml_bytes[:4000].decode("utf-8", "replace")
    for prefix, uri in re.findall(r'xmlns:([A-Za-z0-9]+)="([^"]+)"', head):
        ET.register_namespace(prefix, uri)
    m = re.search(r'xmlns="([^"]+)"', head)
    if m:
        ET.register_namespace("", m.group(1))


def _all_text(root: ET.Element) -> str:
    return "\n".join(t.text or "" for t in root.iter(W + "t"))


def _rows(tbl: ET.Element) -> List[ET.Element]:
    return tbl.findall(W + "tr")


def _cells(tr: ET.Element) -> List[ET.Element]:
    return tr.findall(W + "tc")


def _row_text(tr: ET.Element) -> str:
    return " ".join(t.text or "" for t in tr.iter(W + "t"))


def _set_cell_text(tc: ET.Element, text: str) -> None:
    ts = list(tc.iter(W + "t"))
    if ts:
        ts[0].text = text
        ts[0].set(XML_SPACE, "preserve")
        for extra in ts[1:]:
            extra.text = ""
    else:
        p = tc.find(W + "p")
        if p is None:
            p = ET.SubElement(tc, W + "p")
        r = ET.SubElement(p, W + "r")
        t = ET.SubElement(r, W + "t")
        t.set(XML_SPACE, "preserve")
        t.text = text


# --------------------------------------------------------------------------
# render from a DocFlow spec
# --------------------------------------------------------------------------

def render_docx_from_docflow(spec: dict, output_path: str) -> Dict[str, Any]:
    """Render a validated DocFlow spec to a .docx at output_path.

    Raises DocflowValidationError if the spec is invalid (no file is written).
    Returns {path, bytes, parts, blocks}.
    """
    errors = docflow.validate_docflow(spec)
    if errors:
        raise DocflowValidationError(errors)

    members = [
        ("[Content_Types].xml", DOCX_CONTENT_TYPES),
        ("_rels/.rels", DOCX_ROOT_RELS),
        ("word/_rels/document.xml.rels", DOCX_DOC_RELS),
        ("word/styles.xml", docflow.build_styles_xml(spec)),
        ("word/document.xml", _document_xml(spec)),
    ]
    size = _write_zip(output_path, members)
    return {
        "path": os.path.abspath(output_path),
        "bytes": size,
        "parts": [name for name, _ in members],
        "blocks": len(spec.get("blocks", [])),
    }


# --------------------------------------------------------------------------
# fill an existing template
# --------------------------------------------------------------------------

def _apply_scalar_replacements(root: ET.Element, replacements: Dict[str, Any]) -> None:
    """Substring-replace every replacement key inside each <w:t> run.

    Clean single-run tokens (the recommended template style, e.g. '[User ID]' or
    '{{name}}') are replaced reliably. A token Word split across runs will not be
    caught — render_docx_from_template's post-fill guard turns that into a loud
    TemplateRenderError rather than a silently half-filled document.
    """
    items = [(k, "" if v is None else str(v)) for k, v in replacements.items()]
    for t in root.iter(W + "t"):
        text = t.text or ""
        if not text:
            continue
        changed = False
        for key, val in items:
            if key and key in text:
                text = text.replace(key, val)
                changed = True
        if changed:
            t.text = text
            t.set(XML_SPACE, "preserve")


def _apply_table_fills(root: ET.Element, table_fills: Sequence[dict]) -> None:
    """Expand data tables by cloning a prototype row.

    Each fill is {"locate": <header substring>, "rows": [[cell, ...], ...]}.
    The table whose header (first row) contains `locate` keeps its header + a
    prototype data row (row index 1); the prototype is deep-copied once per data
    row (preserving cell styling) and filled positionally.
    """
    tables = list(root.iter(W + "tbl"))
    for fill in table_fills:
        locate = str(fill.get("locate", "")).lower()
        data_rows = fill.get("rows", [])
        target = None
        for tbl in tables:
            trs = _rows(tbl)
            if trs and locate and locate in _row_text(trs[0]).lower():
                target = tbl
                break
        if target is None:
            raise TemplateRenderError("table_fill: no table header matches %r" % fill.get("locate"))
        trs = _rows(target)
        if len(trs) < 2:
            raise TemplateRenderError(
                "table_fill: table %r needs a prototype data row to clone" % fill.get("locate"))
        header, prototype = trs[0], trs[1]
        for tr in trs[1:]:
            target.remove(tr)
        pos = list(target).index(header) + 1
        for i, row in enumerate(data_rows):
            clone = copy.deepcopy(prototype)
            for cell, value in zip(_cells(clone), row):
                _set_cell_text(cell, "" if value is None else str(value))
            target.insert(pos + i, clone)


def render_docx_from_template(
    template_path: str,
    replacements: Dict[str, Any],
    output_path: str,
    *,
    table_fills: Optional[Sequence[dict]] = None,
    forbid_placeholder_patterns: Sequence[str] = DEFAULT_PLACEHOLDER_PATTERNS,
    forbid_substrings: Sequence[str] = (),
) -> Dict[str, Any]:
    """Fill `template_path` with `replacements`, writing `output_path`.

    Guarantees (each a loud TemplateRenderError, never a silent half-fill):
      * every key in `replacements` is absent from the rendered text;
      * no `forbid_placeholder_patterns` match remains (default: '[...]'/'{{...}}'
        — pass () to allow templates that use square brackets legitimately);
      * no `forbid_substrings` remain (e.g. pass ('\\u2014',) to forbid em dashes).

    Every part other than word/document.xml is copied byte-for-byte, so the
    template's styles/header/footer/fonts are preserved exactly.
    Returns {path, bytes, replaced_keys, table_fills}.
    """
    with zipfile.ZipFile(template_path) as zin:
        names = zin.namelist()
        members = {n: zin.read(n) for n in names}
    if "word/document.xml" not in members:
        raise TemplateRenderError("template is not a valid .docx (no word/document.xml)")

    doc_xml = members["word/document.xml"]
    _register_namespaces(doc_xml)
    root = ET.fromstring(doc_xml)

    if table_fills:
        _apply_table_fills(root, table_fills)
    _apply_scalar_replacements(root, replacements)

    new_doc = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
               + ET.tostring(root, encoding="unicode").encode("utf-8"))

    rendered = _all_text(root)
    leftover_keys = sorted(k for k in replacements if k and k in rendered)
    if leftover_keys:
        raise TemplateRenderError("replacement keys still present after fill: %s" % leftover_keys)
    leftover_ph = _scan_placeholders(rendered, forbid_placeholder_patterns, ())
    if leftover_ph:
        raise TemplateRenderError("unresolved placeholders remain: %s" % leftover_ph)
    present_forbidden = [s for s in forbid_substrings if s and s in rendered]
    if present_forbidden:
        raise TemplateRenderError("forbidden substrings present: %r" % present_forbidden)

    ordered = [(n, new_doc if n == "word/document.xml" else members[n]) for n in names]
    size = _write_zip(output_path, ordered)
    return {
        "path": os.path.abspath(output_path),
        "bytes": size,
        "replaced_keys": sorted(replacements),
        "table_fills": [f.get("locate") for f in (table_fills or [])],
    }


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def _scan_placeholders(text: str, patterns: Sequence[str], extra_tokens: Sequence[str]) -> List[str]:
    found: "set[str]" = set()
    for pat in patterns:
        for m in re.findall(pat, text):
            found.add(m if isinstance(m, str) else m[0])
    for tok in extra_tokens:
        if tok and tok in text:
            found.add(tok)
    return sorted(found)


def validate_docx_no_placeholders(
    path: str,
    *,
    patterns: Sequence[str] = DEFAULT_PLACEHOLDER_PATTERNS,
    extra_tokens: Sequence[str] = (),
) -> List[str]:
    """Return the list of unresolved placeholder strings found in the document
    text (empty list == clean). `extra_tokens` are literal substrings to also
    treat as placeholders (e.g. the exact tokens a template shipped with)."""
    try:
        with zipfile.ZipFile(path) as zf:
            doc = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError):
        return ["<could-not-read-document.xml>"]
    try:
        root = ET.fromstring(doc)
    except ET.ParseError:
        return ["<malformed-document.xml>"]
    return _scan_placeholders(_all_text(root), patterns, extra_tokens)


def validate_docx(
    path: str,
    *,
    required_parts: Sequence[str] = REQUIRED_PARTS,
    placeholder_patterns: Sequence[str] = DEFAULT_PLACEHOLDER_PATTERNS,
    forbid_substrings: Sequence[str] = (),
    check_placeholders: bool = True,
) -> Dict[str, Any]:
    """Comprehensive delivery gate for a .docx. Never raises; returns
    {ok, errors, bytes, parts}. ok is True only when every check passes."""
    errors: List[str] = []
    if not os.path.exists(path):
        return {"ok": False, "errors": ["file_missing"], "bytes": 0, "parts": []}
    size = os.path.getsize(path)
    if size <= 0:
        errors.append("file_empty")

    parts: List[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            parts = zf.namelist()
            missing = [p for p in required_parts if p not in parts]
            if missing:
                errors.append("missing_parts:%s" % ",".join(missing))
            if "word/document.xml" in parts:
                try:
                    root = ET.fromstring(zf.read("word/document.xml"))
                    text = _all_text(root)
                    if check_placeholders:
                        leftover = _scan_placeholders(text, placeholder_patterns, ())
                        if leftover:
                            errors.append("placeholders:%s" % leftover)
                    bad = [s for s in forbid_substrings if s and s in text]
                    if bad:
                        errors.append("forbidden_substrings:%r" % bad)
                except ET.ParseError as exc:
                    errors.append("malformed_xml:%s" % exc)
    except zipfile.BadZipFile:
        errors.append("bad_zip")
    return {"ok": not errors, "errors": errors, "bytes": size, "parts": parts}
