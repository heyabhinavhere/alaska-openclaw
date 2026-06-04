"""Built-in `/alaska` subcommand handlers for P0.

    help   — list available subcommands (always safe)
    ping   — liveness check ("pong" + gateway version)
    audit  — parse `/alaska audit <user_id>` and return an ASYNC job spec, but
             DRY-RUN only: the job posts a "would run" message. Live audit
             execution is intentionally NOT wired here — it is connected to the
             bon-internal-audit skill in a later, approved PR (#4), only after
             Audit Agent v1 is merged and stable.

Handlers are registered into core's registry at import time. Adding a new
subcommand is a one-liner here + a register_handler() call — no changes to the
shared intent-classifier / alaska-core routing.
"""
from __future__ import annotations

from typing import Any, Dict

from .core import (
    GATEWAY_VERSION,
    FUTURE_SUBCOMMANDS,
    ParsedCommand,
    ephemeral,
    register_handler,
)
from .jobs import register_finalizer

HELP_TEXT = (
    "*Alaska command gateway* (v%s)\n"
    "`/alaska help` — show this help\n"
    "`/alaska ping` — check that the gateway is alive\n"
    "`/alaska audit <user_id>` — generate an internal audit report (e.g. `/alaska audit 1414`)\n"
    "\n_Coming soon:_ %s"
) % (GATEWAY_VERSION, ", ".join("`/alaska %s`" % s for s in sorted(FUTURE_SUBCOMMANDS)))


def help_handler(parsed: ParsedCommand, context: Dict[str, Any]) -> Dict[str, Any]:
    return ephemeral(HELP_TEXT)


def ping_handler(parsed: ParsedCommand, context: Dict[str, Any]) -> Dict[str, Any]:
    return ephemeral("pong — Alaska command gateway v%s is alive." % GATEWAY_VERSION)


def audit_handler(parsed: ParsedCommand, context: Dict[str, Any]) -> Dict[str, Any]:
    """Parse `/alaska audit <user_id>` safely and return an async (dry-run) job.

    Validates arguments and returns a helpful error for missing/invalid input.
    On valid input it returns an ephemeral "started" ack plus an async job spec;
    it NEVER triggers a live audit in P0.
    """
    if not parsed.args:
        return ephemeral("Usage: `/alaska audit <user_id>` — e.g. `/alaska audit 1414`.")
    user_id = parsed.args[0]
    if not user_id.isdigit():
        return ephemeral(
            "`%s` doesn't look like a user id. Usage: `/alaska audit <user_id>` "
            "(numeric), e.g. `/alaska audit 1414`." % user_id)
    return ephemeral(
        ":hammer_and_wrench: Audit for user %s started — I'll post the report here when it's ready."
        % user_id,
        **{"async": {"command": "audit", "params": {"user_id": user_id}}},
    )


def audit_finalizer(job: Dict[str, Any]) -> Dict[str, Any]:
    """DRY RUN. The deferred work for `/alaska audit <user_id>` in P0.

    It performs NO live audit. When Audit Agent v1 is wired in (platform PR #4),
    this finalizer is replaced by a call into the bon-internal-audit skill +
    the Artifact Service, and the resulting DOCX is uploaded to the channel.
    """
    user_id = (job.get("params") or {}).get("user_id", "?")
    return {
        "response_type": "ephemeral",
        "text": (
            ":information_source: Dry run — would generate an internal audit report for "
            "user %s and upload it here. Live audit execution is pending Audit Agent v1 "
            "integration (platform PR #4); no report was generated." % user_id
        ),
    }


def register_builtin_handlers() -> None:
    register_handler("help", help_handler)
    register_handler("ping", ping_handler)
    register_handler("audit", audit_handler)
    register_finalizer("audit", audit_finalizer)
