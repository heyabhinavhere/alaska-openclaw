#!/usr/bin/env python3
"""audit_agent — the BON Internal Audit CLI + orchestration.

This is the single entrypoint the bon-internal-audit SKILL.md drives. It glues
together the pure helpers:
  audit_fetch    -> get + redact the 360 profile (live only behind --live)
  audit_validate -> gate the audit JSON the LLM produced
  audit_render   -> fill the Internal Report DOCX template
  audit_slack    -> build the summary, post + upload (live only behind --live)
and logs every run to its OWN sqlite file (alaska_audit.db), never the V4 task
graph or the V5 PMF store.

Subcommands: parse | fetch-profile | validate | render | run | deliver | log
The LLM typically calls fetch-profile, then (after reasoning) run/validate/render
/deliver with the audit JSON it wrote.

Safety defaults: no network call happens without --live AND the required env
vars. --dry-run renders + logs from a supplied audit JSON and never delivers.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sqlite3
import sys

import audit_fetch
import audit_render
import audit_slack
import audit_validate

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(_HERE, "references", "Internal_Report_Template.docx")
DEFAULT_DB = os.environ.get("ALASKA_AUDIT_DB_PATH", "/data/queue/alaska_audit.db")
DEFAULT_ARTIFACT_ROOT = os.environ.get("AUDIT_ARTIFACT_ROOT", "/data/workspace/audit_artifacts")


# --------------------------------------------------------------------------
# command parsing
# --------------------------------------------------------------------------

# Explicit markers (!audit / /audit) are unambiguous and may appear anywhere
# (e.g. "hey @alaska !audit 1414"). A BARE "audit" is only a command at the start
# of the message (after an optional @mention) — so conversational use like
# "can you audit this later" is NOT misread as a command.
_AUDIT_EXPLICIT_RE = re.compile(r"[!/]audit\b[\s:]*(\S+)?", re.IGNORECASE)
_AUDIT_BARE_RE = re.compile(r"^\s*(?:<@[A-Za-z0-9]+>\s*)?audit\b[\s:]*(\S+)?", re.IGNORECASE)


def parse_command(text):
    """Parse a Slack message like 'hey @alaska !audit 1414' into a user_id.
    Accepts the canonical `!audit`, the legacy `/audit` alias (both anywhere),
    and a bare `audit` only at command position (message start / after a mention).
    Returns (ok, user_id:int|None, error:str|None). Fails safely on anything
    that is not a well-formed audit command."""
    if not text:
        return False, None, "not an audit command"
    m = _AUDIT_EXPLICIT_RE.search(text) or _AUDIT_BARE_RE.match(text)
    if not m:
        return False, None, "not an audit command"
    token = m.group(1)
    if not token:
        return False, None, "missing user_id (usage: !audit <user_id>)"
    ok, uid, err = audit_fetch.validate_user_id(token)
    if not ok:
        return False, None, err
    return True, uid, None


def _make_audit_id(user_id, now=None):
    now = now or _dt.datetime.utcnow()
    return "audit-%s-%s" % (now.strftime("%Y%m%d-%H%M%S"), user_id)


# --------------------------------------------------------------------------
# run-log database (own file; idempotent schema)
# --------------------------------------------------------------------------

def init_db(db_path):
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(os.path.join(_HERE, "schema.sql"), encoding="utf-8") as fh:
        schema = fh.read()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()


def record_run(db_path, run):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO audit_runs "
            "(audit_id, user_id, status, persona, lead_opportunity, data_available, "
            " artifact_path, error_reason, invoked_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (run["audit_id"], run["user_id"], run["status"], run.get("persona"),
             run.get("lead_opportunity"), run.get("data_available"),
             run.get("artifact_path"), run.get("error_reason"), run.get("invoked_by")),
        )
        conn.commit()
    finally:
        conn.close()


def get_run(db_path, audit_id):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM audit_runs WHERE audit_id=?", (audit_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------

def run_audit(audit, *, template_path=None, artifact_root=None, db_path=None,
              now=None, audit_id=None, invoked_by=None):
    """Validate -> render DOCX -> log. Returns a result dict (always; never
    raises for the expected failure modes). The audit JSON is produced by the
    Alaska LLM per the skill; this function makes the deterministic part safe."""
    template_path = template_path or DEFAULT_TEMPLATE
    artifact_root = artifact_root or DEFAULT_ARTIFACT_ROOT
    meta = audit.get("audit_meta", {}) or {}
    user = audit.get("user", {}) or {}
    raw_uid = meta.get("user_id")
    user_id = int(raw_uid) if str(raw_uid).isdigit() else raw_uid
    audit_id = audit_id or _make_audit_id(raw_uid, now)
    opps = audit.get("opportunities", []) or []

    base = {
        "audit_id": audit_id,
        "user_id": user_id,
        "persona": user.get("persona_pattern"),
        "lead_opportunity": opps[0].get("type") if opps else None,
        "data_available": meta.get("data_available"),
        "invoked_by": invoked_by,
    }

    def finish(status, artifact_path=None, error_reason=None, **extra):
        rec = dict(base, status=status, artifact_path=artifact_path, error_reason=error_reason)
        if db_path:
            record_run(db_path, rec)
        return dict(rec, **extra)

    validation = audit_validate.validate_audit(audit)
    if not validation["ok"]:
        return finish("validation_failed",
                      error_reason=json.dumps(validation["failures"])[:1500],
                      failures=validation["failures"], summary=None)

    out_path = os.path.join(artifact_root, str(raw_uid), audit_id + ".docx")
    try:
        audit_render.render_docx(audit, template_path, out_path)
    except audit_render.AuditValidationError as e:
        return finish("validation_failed", error_reason=str(e)[:1500], summary=None)
    except Exception as e:  # bad template, disk error, etc.
        return finish("render_error", error_reason="%s: %s" % (type(e).__name__, e), summary=None)

    return finish("success", artifact_path=out_path,
                  summary=audit_slack.build_summary(audit))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _load_json_arg(value):
    if value == "-":
        return json.loads(sys.stdin.read())
    with open(value, encoding="utf-8") as fh:
        return json.load(fh)


def _cmd_parse(args):
    ok, uid, err = parse_command(args.text)
    print(json.dumps({"ok": ok, "user_id": uid, "error": err}))
    return 0 if ok else 1


def _cmd_fetch_profile(args):
    if not args.live:
        print(json.dumps({"status": "refused",
                          "detail": "live profile fetch requires --live (default-safe)"}))
        return 2
    res = audit_fetch.fetch_profile(args.user_id, base_url=args.base_url, api_key=args.api_key)
    if res["status"] != "ok":
        print(json.dumps({"status": res["status"], "detail": res.get("detail")}))
        return 1
    out = {"status": "ok",
           "summary": audit_fetch.summarize_for_audit(res["payload"]),
           "profile": audit_fetch.redact(res["payload"])}
    print(json.dumps(out))
    return 0


def _cmd_validate(args):
    result = audit_validate.validate_audit(_load_json_arg(args.audit_json))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def _cmd_render(args):
    out = args.out or os.path.join(
        args.artifact_root, "manual", "render-output.docx")
    try:
        path = audit_render.render_docx(_load_json_arg(args.audit_json), args.template, out)
    except audit_render.AuditValidationError as e:
        print(json.dumps({"status": "validation_failed", "failures": e.failures}))
        return 1
    print(json.dumps({"status": "ok", "artifact_path": path}))
    return 0


def _cmd_run(args):
    audit = _load_json_arg(args.audit_json)
    result = run_audit(audit, template_path=args.template, artifact_root=args.artifact_root,
                       db_path=args.db, invoked_by=args.invoked_by)
    if result["status"] == "success" and args.deliver and not args.dry_run:
        result["delivery"] = audit_slack.deliver(
            args.channel, result["summary"], result["artifact_path"], thread_ts=args.thread_ts)
    print(json.dumps(result))
    return 0 if result["status"] == "success" else 1


def _cmd_deliver(args):
    if not args.live:
        print(json.dumps({"status": "refused", "detail": "delivery requires --live"}))
        return 2
    audit = _load_json_arg(args.audit_json)
    summary = audit_slack.build_summary(audit)
    res = audit_slack.deliver(args.channel, summary, args.docx, thread_ts=args.thread_ts)
    print(json.dumps(res))
    return 0 if res["ok"] else 1


def _cmd_log(args):
    record_run(args.db, {
        "audit_id": args.audit_id, "user_id": args.user_id, "status": args.status,
        "persona": args.persona, "lead_opportunity": args.lead, "data_available": args.data_available,
        "artifact_path": args.artifact, "error_reason": args.error, "invoked_by": args.invoked_by,
    })
    print(json.dumps({"status": "logged", "audit_id": args.audit_id}))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="audit_agent", description="BON Internal Audit Agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("parse"); sp.add_argument("text"); sp.set_defaults(fn=_cmd_parse)

    sp = sub.add_parser("fetch-profile")
    sp.add_argument("--user-id", type=int, required=True)
    sp.add_argument("--live", action="store_true")
    sp.add_argument("--base-url", default=None)
    sp.add_argument("--api-key", default=None)
    sp.set_defaults(fn=_cmd_fetch_profile)

    sp = sub.add_parser("validate")
    sp.add_argument("--audit-json", required=True)
    sp.set_defaults(fn=_cmd_validate)

    sp = sub.add_parser("render")
    sp.add_argument("--audit-json", required=True)
    sp.add_argument("--out", default=None)
    sp.add_argument("--template", default=DEFAULT_TEMPLATE)
    sp.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT)
    sp.set_defaults(fn=_cmd_render)

    sp = sub.add_parser("run")
    sp.add_argument("--audit-json", required=True)
    sp.add_argument("--db", default=DEFAULT_DB)
    sp.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT)
    sp.add_argument("--template", default=DEFAULT_TEMPLATE)
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--deliver", action="store_true")
    sp.add_argument("--channel", default=None)
    sp.add_argument("--thread-ts", default=None)
    sp.add_argument("--invoked-by", default=None)
    sp.set_defaults(fn=_cmd_run)

    sp = sub.add_parser("deliver")
    sp.add_argument("--audit-json", required=True)
    sp.add_argument("--docx", required=True)
    sp.add_argument("--channel", required=True)
    sp.add_argument("--thread-ts", default=None)
    sp.add_argument("--live", action="store_true")
    sp.set_defaults(fn=_cmd_deliver)

    sp = sub.add_parser("log")
    sp.add_argument("--db", default=DEFAULT_DB)
    sp.add_argument("--audit-id", required=True)
    sp.add_argument("--user-id", type=int, required=True)
    sp.add_argument("--status", required=True)
    sp.add_argument("--persona", default=None)
    sp.add_argument("--lead", default=None)
    sp.add_argument("--data-available", default=None)
    sp.add_argument("--artifact", default=None)
    sp.add_argument("--error", default=None)
    sp.add_argument("--invoked-by", default=None)
    sp.set_defaults(fn=_cmd_log)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
