#!/usr/bin/env python3
"""Ingest a Slack ``conversations.history`` response into ``intent_inbox``.

WHY THIS EXISTS
---------------
Before this script there was *no committed parser* for Slack → intent_inbox.
``skills/thinker`` and ``skills/shared-toolkit`` told the model to "fetch each
message" then used ``$message_text`` / ``$message_ts`` / ``$author_slack_id``
shell variables that were **never assigned** — so the model improvised the
per-message parse at runtime by splitting multi-line, tab/pipe-laden Slack text.
A tab or newline inside ``message_text`` shifted later fields rightward (Slack
metadata spilled into ``message_ts``) and truncated fields mid-word. The old
INSERT also string-interpolated three of the five values raw into SQL — an
injection vector. This script kills both: it parses the response **structurally**
with ``json.loads`` (field boundaries come from JSON keys, never positional
splitting) and INSERTs via SQLite **bound parameters** (no escaping, no
injection, no column shift).

CONTRACT (shared-toolkit Section 1.6): bot, empty, and system messages are all
ingested — the intent-classifier's pre-filter decides what to skip, not the
ingester. The only message dropped here is one with no ``ts`` (unkeyable).

USAGE
-----
    printf '%s' "$CH_JSON" | python3 /opt/lib/ingest_messages.py <channel_id> [db_path]

``$CH_JSON`` is the raw ``conversations.history`` response body for ONE channel.
Reads the body on stdin; prints ``ingest_messages: inserted N of M`` on success.
"""
import sys
import os
import re
import json
import sqlite3

DEFAULT_DB = "/data/queue/alaska.db"

# Strip C0 control bytes that have no place in chat text. NUL (\x00) is the
# critical one: SQLite's TEXT bind is C-string based and truncates the value at
# the first NUL, so a message like "deploy blocked\x00<rest>" would silently
# lose everything after the NUL. \t (09), \n (0a), \r (0d) are real in Slack
# text and are preserved.
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean(value):
    """Strip control bytes from a text field; pass ``None`` through untouched."""
    return value if value is None else _CTRL.sub("", value)


def ingest(body, channel_id, db_path=DEFAULT_DB):
    """Parse a conversations.history body and INSERT OR IGNORE each message.

    Returns ``(attempted, inserted)`` — ``inserted`` excludes rows the
    ``(channel_id, message_ts)`` unique constraint deduplicated away.
    """
    resp = json.loads(body)  # structural parse: newlines/tabs/pipes stay INSIDE each field
    attempted = 0
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        for message in resp.get("messages", []):
            ts = message.get("ts")
            if not ts:
                # No key -> can't dedup or store meaningfully; skip only this one.
                continue
            uid = message.get("user") or message.get("bot_id") or "unknown"  # bot/app msgs have no .user
            text = message.get("text") or ""  # None-safe: JSON null -> "" (contract: still ingest)
            thread_ts = message.get("thread_ts")
            if thread_ts == ts:
                # A thread parent lists its own ts as thread_ts -> it's top-level.
                thread_ts = None
            con.execute(
                "INSERT OR IGNORE INTO intent_inbox "
                "(message_ts, channel_id, author_slack_id, message_text, thread_ts) "
                "VALUES (?,?,?,?,?)",
                (clean(ts), clean(channel_id), clean(uid), clean(text), clean(thread_ts)),
            )
            attempted += 1
        inserted = con.total_changes
        con.commit()
    finally:
        con.close()
    return attempted, inserted


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(
            "usage: ingest_messages.py <channel_id> [db_path]  (JSON body on stdin)\n"
        )
        return 2
    channel_id = argv[1]
    db_path = argv[2] if len(argv) > 2 else DEFAULT_DB
    body = sys.stdin.read()
    try:
        attempted, inserted = ingest(body, channel_id, db_path)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"ingest_messages: bad JSON body for {channel_id}: {exc}\n")
        return 1
    print(f"ingest_messages: inserted {inserted} of {attempted} for {channel_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
