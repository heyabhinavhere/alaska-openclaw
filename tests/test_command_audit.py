"""command_audit — test suite for the routing-decision log (OM-4 PR-1).

Covers: migration 0007 applies (and is idempotent); log_command writes a row,
no-ops safely when the DB or table is absent, and rejects an invalid `matched`;
and execute.route() logs a deterministic 'route' / 'unknown' row without affecting
the command result. No live DB required — everything uses a tempdir.

Run: python3 -m pytest tests/test_command_audit.py -q
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from alaska_command_gateway import audit, execute as E  # noqa: E402

MIGRATION = REPO_ROOT / "migrations" / "0007_command_audit.sql"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _db_with_table() -> str:
    """A temp alaska.db with command_audit created by applying migration 0007."""
    db = os.path.join(tempfile.mkdtemp(), "alaska.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.close()
    return db


def _rows(db: str):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM command_audit ORDER BY id")]
    finally:
        conn.close()


# --------------------------------------------------------------------------
# migration 0007
# --------------------------------------------------------------------------

def test_migration_creates_table_and_is_idempotent():
    db = _db_with_table()
    conn = sqlite3.connect(db)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "command_audit" in names
        idx = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_command_audit_matched" in idx
    finally:
        conn.close()
    # Re-applying the migration SQL must not error (CREATE IF NOT EXISTS).
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.close()


# --------------------------------------------------------------------------
# log_command
# --------------------------------------------------------------------------

def test_log_command_writes_a_row():
    db = _db_with_table()
    ok = audit.log_command({
        "raw_text": "case 2762", "verb": "case", "matched": "route",
        "routed_target": "user-casefile", "ok": 1, "status": "ok",
        "invoker": "U07GKLVA9FE", "channel": "C0ANKDD664A", "channel_type": "channel",
        "gateway_version": "0.1.0",
    }, db_path=db)
    assert ok is True
    rows = _rows(db)
    assert len(rows) == 1
    r = rows[0]
    assert r["verb"] == "case" and r["matched"] == "route" and r["ok"] == 1
    assert r["routed_target"] == "user-casefile" and r["invoker"] == "U07GKLVA9FE"
    assert r["created_at"]  # default timestamp populated


def test_log_command_noop_when_db_absent():
    assert audit.log_command({"matched": "route"}, db_path="/no/such/dir/alaska.db") is False


def test_log_command_noop_when_table_missing():
    empty = os.path.join(tempfile.mkdtemp(), "alaska.db")
    sqlite3.connect(empty).close()  # exists, but no command_audit table
    assert audit.log_command({"matched": "route", "verb": "case"}, db_path=empty) is False


def test_log_command_rejects_invalid_matched():
    db = _db_with_table()
    assert audit.log_command({"matched": "bogus"}, db_path=db) is False
    assert _rows(db) == []  # nothing written (would violate the CHECK constraint)


# --------------------------------------------------------------------------
# execute.route() logs every decision, without affecting the result
# --------------------------------------------------------------------------

def test_route_logs_route_decision():
    db = _db_with_table()

    def fake(user_id, invoker, **kw):
        return {"ok": True, "status": "ok", "user_id": 2762, "delivered": True}

    ctx = E.build_context(invoker="U07GKLVA9FE", channel="C0ANKDD664A",
                          generate_fn=fake, audit_db_path=db)
    res = E.route("user 2762", ctx)
    assert res["ok"] is True                       # result is unchanged by auditing
    rows = _rows(db)
    assert len(rows) == 1
    assert rows[0]["matched"] == "route" and rows[0]["verb"] == "user"
    assert rows[0]["routed_target"] == "user-casefile" and rows[0]["ok"] == 1
    assert rows[0]["channel"] == "C0ANKDD664A" and rows[0]["gateway_version"]


def test_route_logs_unknown_decision():
    db = _db_with_table()
    res = E.route("frobnicate now", E.build_context(invoker="U1", channel="C1", audit_db_path=db))
    assert res["ok"] is False and res["status"] == "unknown_subcommand"
    rows = _rows(db)
    assert len(rows) == 1 and rows[0]["matched"] == "unknown"
    assert rows[0]["verb"] == "frobnicate" and rows[0]["routed_target"] is None and rows[0]["ok"] == 0


def test_route_without_audit_db_is_a_silent_noop():
    # No audit_db_path + default /data path absent locally → no write, no error.
    res = E.route("help", E.build_context(invoker="U1", channel="C1"))
    assert res["ok"] is True  # routing still works with logging disabled


# --------------------------------------------------------------------------
# the CLI (SKILL-emitted fallthrough/unknown rows)
# --------------------------------------------------------------------------

def test_cli_writes_fallthrough_row(monkeypatch):
    db = _db_with_table()
    monkeypatch.setenv("ALASKA_DB_PATH", db)
    rc = audit.main(["--matched", "fallthrough", "--raw-text", "audit 1453",
                     "--verb", "audit", "--invoker", "U1", "--channel", "C1", "--channel-type", "channel"])
    assert rc == 0
    rows = _rows(db)
    assert len(rows) == 1 and rows[0]["matched"] == "fallthrough" and rows[0]["verb"] == "audit"
    assert rows[0]["raw_text"] == "audit 1453"
