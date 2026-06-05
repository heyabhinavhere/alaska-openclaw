"""Thin CLI for the Alaska Artifact Service.

Lets skills and cron jobs invoke the service as a subprocess, mirroring how
lib/pmf_cohort_os.py is run. Every command prints a JSON result to stdout and
exits non-zero on failure.

    python3 -m alaska_artifacts.cli render-docflow spec.json out.docx
    python3 -m alaska_artifacts.cli render-pdf      spec.json out.pdf
    python3 -m alaska_artifacts.cli fill-template   tpl.docx repl.json out.docx [--table-fills tf.json]
    python3 -m alaska_artifacts.cli validate        out.docx
    python3 -m alaska_artifacts.cli store           out.docx --type docx --owner audit --run 1414
    python3 -m alaska_artifacts.cli upload          out.docx --channel C123 [--thread TS] [--comment "..."]
    python3 -m alaska_artifacts.cli metadata        audit/1414/report.docx
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Work both as `python3 -m alaska_artifacts.cli` and `python3 lib/alaska_artifacts/cli.py`.
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from alaska_artifacts import docflow, docx, pdf, slack_upload, store  # type: ignore
else:
    from . import docflow, docx, pdf, slack_upload, store


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _emit(result) -> int:
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="alaska_artifacts", description="Alaska Artifact Service")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("render-docflow"); p.add_argument("spec"); p.add_argument("out")
    p = sub.add_parser("render-pdf"); p.add_argument("spec"); p.add_argument("out")
    p = sub.add_parser("fill-template")
    p.add_argument("template"); p.add_argument("replacements"); p.add_argument("out")
    p.add_argument("--table-fills", default=None)
    p = sub.add_parser("validate"); p.add_argument("path")
    p = sub.add_parser("store")
    p.add_argument("path"); p.add_argument("--type", required=True)
    p.add_argument("--owner", required=True); p.add_argument("--run", required=True)
    p.add_argument("--overwrite", action="store_true")
    p = sub.add_parser("upload")
    p.add_argument("path"); p.add_argument("--channel", required=True)
    p.add_argument("--thread", default=None); p.add_argument("--title", default=None)
    p.add_argument("--comment", default=None)
    p = sub.add_parser("metadata"); p.add_argument("artifact_id")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "render-docflow":
            return _emit(docx.render_docx_from_docflow(_load_json(args.spec), args.out))
        if args.cmd == "render-pdf":
            return _emit(pdf.render_pdf_from_docflow(_load_json(args.spec), args.out))
        if args.cmd == "fill-template":
            table_fills = _load_json(args.table_fills) if args.table_fills else None
            return _emit(docx.render_docx_from_template(
                args.template, _load_json(args.replacements), args.out, table_fills=table_fills))
        if args.cmd == "validate":
            if args.path.lower().endswith(".pdf"):
                return _emit(pdf.validate_pdf(args.path))
            return _emit(docx.validate_docx(args.path))
        if args.cmd == "store":
            return _emit(store.store_artifact(
                args.path, args.type, args.owner, args.run, overwrite=args.overwrite))
        if args.cmd == "upload":
            return _emit(slack_upload.upload_artifact_to_slack(
                args.path, args.channel, thread_ts=args.thread,
                title=args.title, initial_comment=args.comment))
        if args.cmd == "metadata":
            meta = store.get_artifact_metadata(args.artifact_id)
            if meta is None:
                print(json.dumps({"error": "not_found", "artifact_id": args.artifact_id}))
                return 1
            return _emit(meta)
    except (docx.DocflowValidationError, docx.TemplateRenderError,
            store.ArtifactExistsError, FileNotFoundError, ValueError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}))
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
