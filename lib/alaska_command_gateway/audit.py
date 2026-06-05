"""command_audit — the routing-decision log for the `!`-command layer (OM-4).

`log_command()` writes ONE row to the `command_audit` table (migration 0007) per
routing decision, so routing reliability can be MEASURED (model-mediated
recognition can't be unit-tested — it must be observed in production). It is
called deterministically from `execute.route()` for every executor invocation,
and from this module's CLI for the SKILL-emitted `fallthrough`/`unknown` rows.

Contract: logging must NEVER affect a command. `log_command` swallows every error
(missing DB, missing table, lock, bad value) and returns a bool — it never raises.
It is a fast no-op when the DB file doesn't exist (e.g. unit tests, or off-box),
so importing/using it carries no requirement that a database be present.

CLI (used by the routing SKILL when it answered a command-like message as chat):
    python3 -m alaska_command_gateway.audit --matched fallthrough \
        --raw-text "audit 1453" --invoker U07GKLVA9FE --channel C0ANKDD664A --channel-type channel
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
from typing import Any, Dict, Optional

logger = logging.getLogger("alaska_command_gateway.audit")

DEFAULT_DB_PATH = "/data/queue/alaska.db"

# Column order for the INSERT. `matched` is required (CHECK constraint in 0007);
# everything else is nullable.
_FIELDS = (
    "raw_text", "verb", "matched", "routed_target", "ok",
    "status", "invoker", "channel", "channel_type", "gateway_version",
)
_VALID_MATCHED = ("route", "unknown", "fallthrough")


def resolve_db_path(db_path: Optional[str] = None) -> str:
    """db_path arg → $ALASKA_DB_PATH → the /data default."""
    return db_path or os.environ.get("ALASKA_DB_PATH") or DEFAULT_DB_PATH


def log_command(record: Dict[str, Any], *, db_path: Optional[str] = None) -> bool:
    """Append one row to command_audit. Returns True if written, False otherwise.

    NEVER raises. No-ops (returns False) when the DB file is absent so that callers
    — including every `execute.route()` — carry no DB dependency. `record["matched"]`
    must be one of route|unknown|fallthrough; a bad/missing value is coerced safely.
    """
    db = resolve_db_path(db_path)
    if not os.path.exists(db):
        return False  # no database here (tests / off-box) — silent no-op
    matched = record.get("matched")
    if matched not in _VALID_MATCHED:
        return False  # never write a row that violates the CHECK constraint
    try:
        values = [record.get(f) for f in _FIELDS]
        placeholders = ", ".join("?" * len(_FIELDS))
        conn = sqlite3.connect(db, timeout=5)
        try:
            conn.execute(
                "INSERT INTO command_audit (%s) VALUES (%s)" % (", ".join(_FIELDS), placeholders),
                values,
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as exc:  # missing table, lock, disk — logging must not crash a command
        logger.debug("command_audit write skipped: %s", exc)
        return False


def main(argv: Optional[list] = None) -> int:
    """Write a single fallthrough/unknown row (the SKILL calls this when Alaska
    answered a command-like message conversationally instead of routing)."""
    ap = argparse.ArgumentParser(prog="alaska_command_gateway.audit",
                                 description="Append a command_audit row (fallthrough/unknown).")
    ap.add_argument("--matched", required=True, choices=["fallthrough", "unknown"])
    ap.add_argument("--raw-text", default=None)
    ap.add_argument("--verb", default=None)
    ap.add_argument("--invoker", default=None)
    ap.add_argument("--channel", default=None)
    ap.add_argument("--channel-type", default=None)
    args = ap.parse_args(argv)

    ok = log_command({
        "raw_text": args.raw_text,
        "verb": args.verb,
        "matched": args.matched,
        "invoker": args.invoker,
        "channel": args.channel,
        "channel_type": args.channel_type,
    })
    print(json.dumps({"logged": ok}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
