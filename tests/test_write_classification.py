"""Tests for lib/write_classification.py — the bound-param classifier write-back.

The old inline ``classifier_output='<json>'`` form broke/injected on apostrophes
(≈ every other Slack message). These tests confirm the bound-param binder stores
apostrophes/quotes/injection payloads verbatim, marks the row processed, and
writes a faithful audit record across intent_inbox + classifier_audit.

Stdlib only. Runnable directly:
    python3 tests/test_write_classification.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

import write_classification  # noqa: E402

# intent_inbox + classifier_audit (incl. the 0002 secondary_intents column).
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
CREATE TABLE classifier_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inbox_id INTEGER REFERENCES intent_inbox(id),
  classified_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  intent TEXT NOT NULL,
  confidence REAL NOT NULL,
  entities TEXT,
  reasoning TEXT,
  would_have_done TEXT,
  abhinav_reviewed BOOLEAN NOT NULL DEFAULT 0,
  abhinav_verdict TEXT,
  secondary_intents TEXT DEFAULT '[]'
);
"""


def _make_db(seed=1):
    path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    con = sqlite3.connect(path)
    con.executescript(_SCHEMA)
    for i in range(1, seed + 1):
        con.execute(
            "INSERT INTO intent_inbox (message_ts, channel_id, author_slack_id, message_text) "
            "VALUES (?,?,?,?)",
            (f"1.{i}", "C0AAA", "U1", f"msg {i}"),
        )
    con.commit()
    con.close()
    return path


def _inbox(db, rid):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    row = dict(con.execute("SELECT * FROM intent_inbox WHERE id=?", (rid,)).fetchone())
    con.close()
    return row


def _audit(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    out = [dict(r) for r in con.execute("SELECT * FROM classifier_audit ORDER BY id")]
    con.close()
    return out


def test_basic_write_marks_processed_and_audits():
    db = _make_db()
    write_classification.write_rows(
        [{
            "id": 1, "intent": "TASK_CREATE", "confidence": 0.9,
            "classifier_output": {"intent": "TASK_CREATE", "x": 1},
            "secondary_intents": ["TASK_UPDATE"], "entities": {"task_ids": ["T-1"]},
            "reasoning": "explicit directive", "would_have_done": "create task",
        }],
        db,
    )
    inbox = _inbox(db, 1)
    assert inbox["processed"] == 1
    assert inbox["intent"] == "TASK_CREATE"
    assert inbox["confidence"] == 0.9
    assert json.loads(inbox["classifier_output"])["x"] == 1
    audit = _audit(db)
    assert len(audit) == 1
    assert json.loads(audit[0]["secondary_intents"]) == ["TASK_UPDATE"]
    assert json.loads(audit[0]["entities"])["task_ids"] == ["T-1"]


def test_apostrophes_stored_verbatim():
    db = _make_db()
    write_classification.write_rows(
        [{
            "id": 1, "intent": "STATUS_QUERY", "confidence": 0.8,
            "classifier_output": {"note": "what's left on Pankaj's plate?"},
            "reasoning": "user asked what's pending", "would_have_done": "n/a",
        }],
        db,
    )
    assert _inbox(db, 1)["processed"] == 1
    assert "what's left" in _inbox(db, 1)["classifier_output"]
    assert _audit(db)[0]["reasoning"] == "user asked what's pending"


def test_injection_payload_inert():
    db = _make_db()
    nasty = "'); DROP TABLE classifier_audit; --"
    write_classification.write_rows(
        [{"id": 1, "intent": "AMBIGUOUS", "confidence": 0.2, "reasoning": nasty}],
        db,
    )
    audit = _audit(db)
    assert len(audit) == 1
    assert audit[0]["reasoning"] == nasty  # stored as data, table intact


def test_classifier_output_string_passthrough():
    db = _make_db()
    write_classification.write_rows(
        [{"id": 1, "intent": "NON_WORK_CHAT", "confidence": 0.1,
          "classifier_output": '{"already":"json string"}'}],
        db,
    )
    assert _inbox(db, 1)["classifier_output"] == '{"already":"json string"}'


def test_nul_byte_stripped_in_reasoning():
    db = _make_db()
    write_classification.write_rows(
        [{"id": 1, "intent": "AMBIGUOUS", "confidence": 0.2,
          "reasoning": "garbled\x00 but recovered"}],
        db,
    )
    assert _audit(db)[0]["reasoning"] == "garbled but recovered"


def test_defaults_for_missing_optional_fields():
    db = _make_db()
    write_classification.write_rows([{"id": 1, "intent": "NON_WORK_CHAT", "confidence": 0.1}], db)
    audit = _audit(db)[0]
    assert json.loads(audit["secondary_intents"]) == []
    assert json.loads(audit["entities"]) == {}
    assert audit["reasoning"] == ""


def test_multiple_rows():
    db = _make_db(seed=3)
    written = write_classification.write_rows(
        [
            {"id": 1, "intent": "TASK_CREATE", "confidence": 0.9},
            {"id": 2, "intent": "STATUS_QUERY", "confidence": 0.7},
            {"id": 3, "intent": "NON_WORK_CHAT", "confidence": 0.1},
        ],
        db,
    )
    assert written == 3
    assert all(_inbox(db, i)["processed"] == 1 for i in (1, 2, 3))
    assert len(_audit(db)) == 3


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
