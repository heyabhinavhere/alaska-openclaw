"""Socket-Mode executor for `/alaska` — the LIVE command router.

This is the path that actually runs in production. In Socket Mode an `/alaska …`
slash command becomes an *agent turn*; the always-on routing skill
(skills/command-gateway/SKILL.md) shells exactly one command:

    python3 -m alaska_command_gateway.execute \
        --text "user 2762" --invoker U07GKLVA9FE --channel C0ANKDD664A --channel-type channel

and relays the printed `text` back to Slack. All parsing + routing + execution is
deterministic Python here — the LLM only relays — so behavior is predictable and
testable. (The HTTP receiver in receiver.py/verify.py is the OTHER architecture,
for a webhook deployment; it is NOT used in Socket Mode.)

────────────────────────────────────────────────────────────────────────────
THE ROUTING TABLE — this is the one place to tune what `/alaska <x>` does.
Each row is  subcommand -> executor(parsed, ctx) -> {ok, text, ...}.  Add a
command = add a row + a small function. Change a command = edit its row.
────────────────────────────────────────────────────────────────────────────

Delivery policy (decided 2026-06-05): a generated document is posted to the
SAME channel the command was run in (ctx["channel"]). The user profile contains
no SSN/DOB/full address (user-profile-360's redactor strips them upstream), and
the team treats the rest as shared — so channel delivery is the clear, simple
default rather than a private DM.
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Callable, Dict, Optional

from .audit import log_command
from .core import ParsedCommand, parse_command

GATEWAY_VERSION = "0.1.0"

# Slack user id -> requester_authority. LOG-ONLY: user-profile-360/lookup.py
# records this in its audit trail and never gates on it (access is flat for the
# whole team), so an unmapped id simply logs "unknown" — it is never denied.
AUTHORITY_BY_SLACK_ID = {
    "U07GKLVA9FE": "admin",     # Abhinav (Head of Product & Design)
    "U0APEUXD9DH": "founder",   # Samder (CEO)
    "U0APK8VTT62": "founder",   # Darwin (COO/CMO)
    "U0AQ0817FJM": "engineer",  # Pankaj
    "U0AQFJV9B32": "engineer",  # Sandeep
    "U0AQ1UZHZ8D": "engineer",  # Shailesh
    "U0AS70U9KM5": "engineer",  # Tarun
    "U0B17Q59J75": "engineer",  # Nilesh
}


def authority_for(slack_id: Optional[str]) -> str:
    return AUTHORITY_BY_SLACK_ID.get(slack_id or "", "unknown")


# --------------------------------------------------------------------------
# result + context helpers
# --------------------------------------------------------------------------

def _result(ok: bool, text: str, **extra: Any) -> Dict[str, Any]:
    out = {"ok": ok, "text": text}
    out.update(extra)
    return out


def build_context(invoker: Optional[str] = None, channel: Optional[str] = None,
                  channel_type: str = "channel", thread_ts: Optional[str] = None,
                  channel_label: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {
        "invoker": invoker,
        "channel": channel,
        "channel_type": channel_type,
        "thread_ts": thread_ts,
        "channel_label": channel_label,  # human label for the success message (e.g. "#user-audit")
        "authority": extra.pop("authority", None) or authority_for(invoker),
    }
    ctx.update(extra)
    return ctx


# --------------------------------------------------------------------------
# subcommand executors  (each: (parsed, ctx) -> result dict)
# --------------------------------------------------------------------------

def _cmd_help(parsed: ParsedCommand, ctx: Dict[str, Any]) -> Dict[str, Any]:
    lines = ["*Alaska* (`/alaska`) — v%s" % GATEWAY_VERSION]
    for name in sorted(ROUTES):
        lines.append("• `/alaska %s` — %s" % (name, ROUTES[name]["help"]))
    return _result(True, "\n".join(lines))


def _cmd_ping(parsed: ParsedCommand, ctx: Dict[str, Any]) -> Dict[str, Any]:
    return _result(True, "pong — Alaska command gateway v%s is alive." % GATEWAY_VERSION)


def _cmd_user(parsed: ParsedCommand, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """`/alaska user <id>` — build a User Case File and post it to this channel."""
    if not parsed.args:
        return _result(False, "Usage: `/alaska user <id>` — e.g. `/alaska user 2762`.")
    user_id = parsed.args[0]
    if not str(user_id).isdigit():
        return _result(False,
                       "`%s` doesn't look like a BON user id (it's a number, e.g. `2762`)." % user_id)

    # Injectable for tests; the real generator is imported lazily so the routing
    # layer carries no import-time dependency on the capabilities package.
    generate = ctx.get("generate_fn")
    if generate is None:
        from alaska_capabilities.user_casefile import generate as generate  # noqa: PLC0415

    res = generate(
        user_id, ctx.get("invoker") or "slash-command",
        requester_authority=ctx.get("authority") or "unknown",
        channel_id=ctx.get("channel"),
        channel_type=ctx.get("channel_type") or "channel",
        thread_ts=ctx.get("thread_ts"),
        deliver=bool(ctx.get("channel")),
    )

    if not res.get("ok"):
        status = res.get("status")
        if status == "multiple":
            return _result(False, "More than one user matches `%s`. %s"
                           % (user_id, res.get("message") or ""), status=status)
        if status == "not_found":
            return _result(False, "No BON user matches `%s`." % user_id, status=status)
        return _result(False, "Couldn't build the case file for `%s`: %s"
                       % (user_id, res.get("message") or status), status=status)

    uid = res.get("user_id", user_id)
    where = ctx.get("channel_label") or "the channel"
    if res.get("delivered"):
        note = " _(served from a stale cache — BON API was unreachable)_" if res.get("served_stale") else ""
        return _result(True, ":card_index_dividers: User case file for *#%s* posted to %s.%s" % (uid, where, note),
                       artifact_id=res.get("artifact_id"), delivered=True)
    # Generated but not delivered (no channel, or Slack upload failed).
    slack_err = (res.get("slack") or {}).get("error")
    if slack_err:
        return _result(False, ":warning: Built the case file for #%s but couldn't post it (Slack: %s). "
                              "The file is saved server-side." % (uid, slack_err),
                       artifact_id=res.get("artifact_id"), delivered=False)
    return _result(True, ":card_index_dividers: User case file for #%s generated." % uid,
                   artifact_id=res.get("artifact_id"), delivered=False)


def _coming_soon(label: str, when: str) -> Callable[[ParsedCommand, Dict[str, Any]], Dict[str, Any]]:
    def _h(parsed: ParsedCommand, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return _result(True, ":construction: `/alaska %s` is coming %s. Not wired yet." % (label, when))
    return _h


# --------------------------------------------------------------------------
# THE ROUTING TABLE
# --------------------------------------------------------------------------

ROUTES: Dict[str, Dict[str, Any]] = {
    "help": {"fn": _cmd_help, "help": "show this help", "target": "command-gateway"},
    "ping": {"fn": _cmd_ping, "help": "liveness check", "target": "command-gateway"},
    "user": {"fn": _cmd_user, "help": "post a 360° user case file (e.g. `/alaska user 2762`)",
             "target": "user-casefile"},
    # Wired in later, approved phases (kept as honest stubs so they never 500):
    "audit": {"fn": _coming_soon("audit", "in P1 (runs via the bon-internal-audit skill)"),
              "help": "internal audit report — P1", "target": "bon-internal-audit"},
    "brief": {"fn": _coming_soon("brief", "in P1"), "help": "daily brief / standup sheet — P1",
              "target": "command-gateway"},
    "pmf":   {"fn": _coming_soon("pmf", "in P2 (routes to pmf-cohort-os)"),
              "help": "PMF cohort status — P2", "target": "pmf-cohort-os"},
}


def _unknown(parsed: ParsedCommand) -> Dict[str, Any]:
    known = ", ".join("`%s`" % k for k in sorted(ROUTES))
    return _result(False, "Unknown command `%s`. Try one of: %s. Run `/alaska help`."
                   % (parsed.subcommand, known), status="unknown_subcommand")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

def _audit(parsed: ParsedCommand, ctx: Dict[str, Any], result: Dict[str, Any],
           *, matched: str, target: Optional[str]) -> None:
    """Best-effort routing-decision log (command_audit, migration 0007). Never
    raises and never affects the command — see alaska_command_gateway.audit."""
    try:
        log_command({
            "raw_text": " ".join([parsed.subcommand] + list(parsed.args)).strip() or None,
            "verb": parsed.subcommand or None,
            "matched": matched,
            "routed_target": target,
            "ok": 1 if result.get("ok") else 0,
            "status": result.get("status"),
            "invoker": ctx.get("invoker"),
            "channel": ctx.get("channel"),
            "channel_type": ctx.get("channel_type"),
            "gateway_version": GATEWAY_VERSION,
        }, db_path=ctx.get("audit_db_path"))
    except Exception:  # belt-and-suspenders; log_command already swallows
        pass


def route(text: Optional[str], ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Parse `/alaska` TEXT and run its executor. Never raises — any executor
    fault is caught and returned as a friendly, non-500 result. Every decision is
    logged to command_audit (best-effort; never affects the result)."""
    ctx = ctx if ctx is not None else build_context()
    parsed = parse_command(text)
    row = ROUTES.get(parsed.subcommand)
    if row is None:
        result = _unknown(parsed)
        _audit(parsed, ctx, result, matched="unknown", target=None)
        return result
    try:
        result = row["fn"](parsed, ctx)
    except Exception as exc:  # a handler bug must not crash the slash command
        result = _result(False, ":x: `/alaska %s` hit an internal error: %s" % (parsed.subcommand, exc),
                         status="handler_error")
    _audit(parsed, ctx, result, matched="route", target=row.get("target"))
    return result


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="alaska_command_gateway.execute",
                                 description="Execute one /alaska command (Socket Mode).")
    ap.add_argument("--text", required=True, help='subcommand + args, e.g. "user 2762"')
    ap.add_argument("--invoker", default=None, help="Slack user id who ran the command")
    ap.add_argument("--channel", default=None, help="Slack channel id the command was run in")
    ap.add_argument("--channel-type", default="channel", help="channel|dm|group")
    ap.add_argument("--thread-ts", default=None, help="post into this Slack thread, if the command was threaded")
    ap.add_argument("--channel-label", default=None, help="human label for the success message, e.g. #user-audit")
    args = ap.parse_args(argv)

    ctx = build_context(invoker=args.invoker, channel=args.channel,
                        channel_type=args.channel_type, thread_ts=args.thread_ts,
                        channel_label=args.channel_label)
    result = route(args.text, ctx)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
