"""Command parsing + dispatch for the single `/alaska` namespace.

One native Slack command, many internal subcommands:

    /alaska help
    /alaska ping
    /alaska audit 1414
    (later: /alaska pmf status   /alaska user 1414   /alaska brief today)

A `/alaska` slash command arrives with command="/alaska" and text="audit 1414".
parse_command() turns the TEXT into a ParsedCommand; dispatch_ack() routes it to
a registered handler and returns the immediate (<3s) Slack response. Handlers
either answer synchronously (help/ping) or return an async job spec (audit) so
the receiver can ack now and finish the work off the request path.

Handlers are plain callables (ParsedCommand, context) -> response dict. Register
new subcommands with register_handler() — no edits to the shared intent-classifier.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

GATEWAY_VERSION = "0.1.0"

# Subcommands documented as coming later (routed to existing skills once wired).
FUTURE_SUBCOMMANDS = {
    "pmf": "PMF cohort status and queries (migrates the current /pmf path)",
    "user": "360° user lookup (user-profile-360)",
    "brief": "daily brief / pre-call standup sheet",
}

# response dict shape: {"response_type": "ephemeral"|"in_channel", "text": str,
#                       optional "async": {"command": str, "params": dict}}
Handler = Callable[["ParsedCommand", Dict[str, Any]], Dict[str, Any]]

_HANDLERS: Dict[str, Handler] = {}


@dataclass
class ParsedCommand:
    subcommand: str
    args: List[str] = field(default_factory=list)
    raw: str = ""


def parse_command(text: Optional[str]) -> ParsedCommand:
    """Parse the slash-command TEXT into a subcommand + args.

    Empty text defaults to the `help` subcommand. A leading slash (if a caller
    passes the whole '/alaska audit 1414') is tolerated and stripped.
    """
    raw = (text or "").strip()
    cleaned = raw
    if cleaned.startswith("/"):
        # tolerate "/alaska audit 1414" or "/audit 1414" being passed as text
        parts = cleaned.split()
        cleaned = " ".join(parts[1:]) if parts and parts[0].lower() in ("/alaska", "/audit") else cleaned.lstrip("/")
    tokens = cleaned.split()
    if not tokens:
        return ParsedCommand(subcommand="help", args=[], raw=raw)
    return ParsedCommand(subcommand=tokens[0].lower(), args=tokens[1:], raw=raw)


def register_handler(name: str, handler: Handler) -> None:
    _HANDLERS[name.lower()] = handler


def get_handler(name: str) -> Optional[Handler]:
    return _HANDLERS.get(name.lower())


def known_subcommands() -> List[str]:
    return sorted(_HANDLERS)


# --------------------------------------------------------------------------
# response helpers
# --------------------------------------------------------------------------

def ephemeral(text: str, **extra: Any) -> Dict[str, Any]:
    out = {"response_type": "ephemeral", "text": text}
    out.update(extra)
    return out


def in_channel(text: str, **extra: Any) -> Dict[str, Any]:
    out = {"response_type": "in_channel", "text": text}
    out.update(extra)
    return out


def unknown_subcommand(parsed: ParsedCommand) -> Dict[str, Any]:
    known = ", ".join(known_subcommands())
    return ephemeral(
        "Unknown subcommand `%s`. Try one of: %s. Run `/alaska help` for details."
        % (parsed.subcommand, known))


def dispatch_ack(parsed: ParsedCommand, context: Dict[str, Any]) -> Dict[str, Any]:
    """Route a parsed command to its handler and return the immediate response.

    For sync subcommands this IS the answer. For async subcommands the response
    carries an "async" job spec and a friendly "started" message; the receiver
    enqueues the job and posts the final result to response_url afterwards.
    Never runs long work inline.
    """
    handler = get_handler(parsed.subcommand)
    if handler is None:
        return unknown_subcommand(parsed)
    return handler(parsed, context)
