"""
Tests for lookup.py orchestration with mocked HTTP. No network, no real PII.

Runnable standalone:  python3 test_lookup.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

import client  # noqa: E402
import lookup  # noqa: E402
import sections  # noqa: E402


def _fresh_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="up360_lookup_")
    os.close(fd)
    repo_root = os.path.dirname(os.path.dirname(_SKILL_DIR))
    with open(os.path.join(repo_root, "migrations", "0003_user_profile_360.sql"),
              encoding="utf-8") as f:
        sql = f.read()
    conn = sqlite3.connect(path)
    conn.executescript(sql)
    conn.commit()
    conn.close()
    return path


def _payload(user_id=2762) -> bytes:
    p = {"user_id": user_id, "fetched_at": "2026-05-29T00:00:00+00:00"}
    for name in sections.all_sections():
        p[name] = {"_marker": name}
    p["profile"] = {"first_name": "Jane", "age": 30, "city": "Reno", "state": "NV",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "is_card_added": True, "is_bank_added": False,
                    "date_of_birth": "1996-01-01", "mobile_no": "4155550100"}
    p["chat"] = {
        "total_threads": 2,
        "intent_breakdown": {"budgeting": 5, "proactive_briefing": 10},
        "feedback_summary": {"thumbs_up": 2, "thumbs_down": 0},
        "recent_turns": [
            {"thread_id": "T1", "question": "q1", "answer": "a1", "created_at": "2026-05-28T10:00:00Z"},
            {"thread_id": "T1", "question": "q2", "answer": "a2", "created_at": "2026-05-28T10:05:00Z"},
            {"thread_id": "P1", "question": "briefing", "answer": None, "created_at": "2026-05-28T09:00:00Z"},
        ],
    }
    return json.dumps(p).encode()


class _Mock:
    def __init__(self, responder):
        self.responder = responder
        self._orig = None

    def __enter__(self):
        self._orig = client._http_get
        client._http_get = self.responder
        client.BON_API_BASE_URL = "https://test.local"
        client.BON_ADMIN_API_KEY = "k"
        return self

    def __exit__(self, *a):
        client._http_get = self._orig


def test_headline_mode():
    db = _fresh_db()
    with _Mock(lambda path, params=None: (200, _payload())):
        out = lookup.lookup("2762", "user_id", "user_summary",
                            "U07GKLVA9FE", "admin", "dm", db_path=db)
    assert out["status"] == "ok" and out["mode"] == "headline"
    assert out["summary"]["identity"]["first_name"] == "Jane"
    # toxic PII stripped even though summary doesn't use it: confirm redaction ran
    assert out["user_id"] == 2762
    os.unlink(db)


def test_deep_dive_mode_returns_real_turns():
    db = _fresh_db()
    with _Mock(lambda path, params=None: (200, _payload())):
        out = lookup.lookup("2762", "user_id", "chat_deep_dive",
                            "U07GKLVA9FE", "admin", "dm", db_path=db)
    assert out["status"] == "ok" and out["mode"] == "deep_dive"
    # 2 real turns (T1 multi-turn), proactive P1 excluded
    assert len(out["chat_turns"]) == 2
    assert all(t["thread_id"] == "T1" for t in out["chat_turns"])
    os.unlink(db)


def test_resolve_not_found_passthrough():
    db = _fresh_db()
    with _Mock(lambda path, params=None: (200, b"[]")):
        out = lookup.lookup("ghost@b.com", "email", "user_summary",
                            "U1", "admin", "dm", db_path=db)
    assert out["status"] == "not_found" and out["user_id"] is None
    os.unlink(db)


def test_resolve_multiple_passthrough():
    db = _fresh_db()
    body = json.dumps([{"user_id": 1, "email": "a@b.com", "name": "A", "created_at": "x"},
                       {"user_id": 2, "email": "b@b.com", "name": "B", "created_at": "x"}]).encode()
    with _Mock(lambda path, params=None: (200, body)):
        out = lookup.lookup("sultan", "name", "user_summary",
                            "U1", "admin", "dm", db_path=db)
    assert out["status"] == "multiple" and len(out["matches"]) == 2
    os.unlink(db)


def test_invalid_intent():
    db = _fresh_db()
    out = lookup.lookup("2762", "user_id", "not_a_real_intent",
                        "U1", "admin", "dm", db_path=db)
    assert out["status"] == "invalid"
    os.unlink(db)


def test_identity_mismatch_passthrough():
    db = _fresh_db()
    with _Mock(lambda path, params=None: (200, _payload(user_id=9999))):
        out = lookup.lookup("2762", "user_id", "user_summary",
                            "U1", "admin", "dm", db_path=db)
    assert out["status"] == "identity_mismatch"
    os.unlink(db)


def test_no_data_empty_profile():
    # Nonexistent user_id: API returns 200 and echoes the id (so identity check
    # passes) but the profile is empty. Must surface as no_data, not a blank
    # "real" user.
    db = _fresh_db()
    p = {"user_id": 999999, "fetched_at": "2026-05-29T00:00:00+00:00", "profile": {}}
    with _Mock(lambda path, params=None: (200, json.dumps(p).encode())):
        out = lookup.lookup("999999", "user_id", "user_summary",
                            "U1", "admin", "dm", db_path=db)
    assert out["status"] == "no_data", out["status"]
    assert out["mode"] is None
    os.unlink(db)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
