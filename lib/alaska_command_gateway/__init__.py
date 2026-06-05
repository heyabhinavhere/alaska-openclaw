"""Alaska Command Gateway — the native `/alaska` slash command (P0).

A single Slack command, `/alaska`, with subcommands routed internally
(`help`, `ping`, `audit <user_id>`, and — later — `pmf`, `user`, `brief`). This
package is the runtime-agnostic brain: Slack request verification, command
parsing, a 3-second ack, and an async job pattern that finishes work off the
request path and posts the result to the command's response_url.

P0 ships the tested core + a reference HTTP receiver but does NOT wire `/alaska`
live in production — see docs/platform/command-gateway.md and receiver.py.

    from alaska_command_gateway import handle_slash_command, verify_slack_signature
    result = handle_slash_command(raw_body, headers, signing_secret=...)
"""
from __future__ import annotations

from .core import (
    GATEWAY_VERSION,
    FUTURE_SUBCOMMANDS,
    ParsedCommand,
    dispatch_ack,
    ephemeral,
    get_handler,
    in_channel,
    known_subcommands,
    parse_command,
    register_handler,
)
from .handlers import register_builtin_handlers
from .jobs import (
    FINALIZERS,
    create_job,
    get_job,
    post_to_response_url,
    register_finalizer,
    run_job,
    update_job,
)
from .receiver import build_context, handle_slash_command, make_server, parse_form
from .verify import team_allowed, verify_slack_signature

# Register help/ping/audit (+ the audit dry-run finalizer) exactly once on import.
register_builtin_handlers()

__version__ = GATEWAY_VERSION

__all__ = [
    "GATEWAY_VERSION",
    "FUTURE_SUBCOMMANDS",
    "ParsedCommand",
    "parse_command",
    "dispatch_ack",
    "register_handler",
    "get_handler",
    "known_subcommands",
    "ephemeral",
    "in_channel",
    "verify_slack_signature",
    "team_allowed",
    "handle_slash_command",
    "parse_form",
    "build_context",
    "make_server",
    "create_job",
    "run_job",
    "get_job",
    "update_job",
    "post_to_response_url",
    "register_finalizer",
    "FINALIZERS",
    "register_builtin_handlers",
    "__version__",
]
