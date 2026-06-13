"""Tests for lib/ingest_messages.py — the committed Slack→intent_inbox parser.

Exercises every failure mode the ingestion-corruption audit surfaced: SQL
injection via raw interpolation, column shift from tab/newline-laden text,
mid-word truncation from a NUL byte, JSON-null text, system/bot messages, and
the (channel_id, message_ts) dedup contract.

Stdlib only. Runnable directly:
    python3 tests/test_ingest_messages.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

import ingest_messages  # noqa: E402

# intent_inbox schema mirrors migrations/0001_v2_task_model.sql:191-205.
_SCHEMA = """
CREATE TABLE intent_inbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_ts TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  author_slack_id TEXT NOT NULL,
  message_text TEXT NOT NULL,
  thread_ts TEXT,
  processed BOOLEAN NOT NULL DEFAULT 0,
  intent TEXT,
  confidence REAL,
  classifier_output TEXT,
  processed_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (channel_id, message_ts)
);
"""


def _make_db():
    path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    con = sqlite3.connect(path)
    con.executescript(_SCHEMA)
    con.commit()
    con.close()
    return path


def _body(*messages):
    return json.dumps({"ok": True, "messages": list(messages)})


def _rows(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    out = [dict(r) for r in con.execute("SELECT * FROM intent_inbox ORDER BY id")]
    con.close()
    return out


def test_basic_ingest():
    db = _make_db()
    ingest_messages.ingest(
        _body({"ts": "1700000000.000100", "user": "U123", "text": "shipped to staging"}),
        "C0AAA", db,
    )
    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0]["message_text"] == "shipped to staging"
    assert rows[0]["channel_id"] == "C0AAA"
    assert rows[0]["author_slack_id"] == "U123"
    assert rows[0]["thread_ts"] is None
    assert rows[0]["processed"] == 0


def test_apostrophes_and_quotes_stored_verbatim():
    db = _make_db()
    text = "let's ship it — O'Brien said \"do it\""
    ingest_messages.ingest(
        _body({"ts": "1.1", "user": "U1", "text": text}), "C0AAA", db,
    )
    assert _rows(db)[0]["message_text"] == text


def test_sql_injection_payload_is_inert():
    db = _make_db()
    payload = "'); DROP TABLE intent_inbox; -- and '||(SELECT author_slack_id FROM intent_inbox)||'"
    ingest_messages.ingest(
        _body({"ts": "1.1", "user": "U1", "text": payload}), "C0AAA", db,
    )
    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0]["message_text"] == payload  # stored as literal data
    # Table still exists and is queryable -> DROP did not execute.
    con = sqlite3.connect(db)
    assert con.execute("SELECT count(*) FROM intent_inbox").fetchone()[0] == 1
    con.close()


def test_embedded_tab_and_newline_no_column_shift():
    db = _make_db()
    text = "line1\tcol2\nline2 with\ttabs"
    ingest_messages.ingest(
        _body({"ts": "1.1", "user": "U1", "text": text, "thread_ts": "1.0"}),
        "C0AAA", db,
    )
    row = _rows(db)[0]
    assert row["message_text"] == text  # tabs/newlines preserved, not split into columns
    assert row["message_ts"] == "1.1"   # nothing spilled into message_ts
    assert row["thread_ts"] == "1.0"


def test_nul_byte_stripped_not_truncated():
    db = _make_db()
    # The NUL must NOT truncate — the verb after it must survive (this was the
    # production "cut mid-word" symptom).
    ingest_messages.ingest(
        _body({"ts": "1.1", "user": "U1", "text": "status: \x00deployed to staging"}),
        "C0AAA", db,
    )
    stored = _rows(db)[0]["message_text"]
    assert stored == "status: deployed to staging"
    assert "deployed" in stored


def test_json_null_text_ingested_as_empty():
    db = _make_db()
    ingest_messages.ingest(
        _body({"ts": "1.1", "user": "U1", "text": None}), "C0AAA", db,
    )
    rows = _rows(db)
    assert len(rows) == 1  # contract: still ingested, not dropped
    assert rows[0]["message_text"] == ""


def test_system_and_bot_messages_ingested():
    db = _make_db()
    ingest_messages.ingest(
        _body(
            {"ts": "1.1", "subtype": "channel_join", "user": "U1", "text": "U1 has joined"},
            {"ts": "1.2", "bot_id": "B999", "text": "deploy finished"},  # no .user
        ),
        "C0AAA", db,
    )
    rows = _rows(db)
    assert len(rows) == 2  # system + bot both ingested per the contract
    assert rows[1]["author_slack_id"] == "B999"


def test_thread_parent_self_reference_becomes_top_level():
    db = _make_db()
    ingest_messages.ingest(
        _body({"ts": "1.1", "user": "U1", "text": "parent", "thread_ts": "1.1"}),
        "C0AAA", db,
    )
    assert _rows(db)[0]["thread_ts"] is None


def test_message_without_ts_skipped_others_kept():
    db = _make_db()
    ingest_messages.ingest(
        _body(
            {"user": "U1", "text": "no ts here"},
            {"ts": "1.2", "user": "U2", "text": "keep me"},
        ),
        "C0AAA", db,
    )
    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0]["message_text"] == "keep me"


def test_dedup_on_channel_and_ts():
    db = _make_db()
    msg = {"ts": "1.1", "user": "U1", "text": "once"}
    attempted1, inserted1 = ingest_messages.ingest(_body(msg), "C0AAA", db)
    attempted2, inserted2 = ingest_messages.ingest(_body(msg), "C0AAA", db)
    assert (attempted1, inserted1) == (1, 1)
    assert (attempted2, inserted2) == (1, 0)  # INSERT OR IGNORE dedups
    assert len(_rows(db)) == 1


def test_bad_json_raises():
    db = _make_db()
    try:
        ingest_messages.ingest("{not valid json", "C0AAA", db)
    except json.JSONDecodeError:
        return
    raise AssertionError("expected JSONDecodeError on malformed body")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
