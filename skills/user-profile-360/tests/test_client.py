"""
Tests for client.py with mocked HTTP (no network, no real PII).

Runnable standalone:  python3 test_client.py
Also pytest-discoverable.

Monkeypatches client._http_get to return canned responses, and uses a
synthetic profile payload so the test is deterministic and carries no real
user data.
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

import audit  # noqa: E402
import cache  # noqa: E402
import client  # noqa: E402
import sections  # noqa: E402


def _fresh_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="up360_client_")
    os.close(fd)
    repo_root = os.path.dirname(os.path.dirname(_SKILL_DIR))
    migration = os.path.join(repo_root, "migrations", "0003_user_profile_360.sql")
    with open(migration, encoding="utf-8") as f:
        sql = f.read()
    conn = sqlite3.connect(path)
    conn.executescript(sql)
    conn.commit()
    conn.close()
    return path


# A synthetic profile — every catalog section present with trivial values, plus
# the dropped sections to prove they're ignored. No real PII.
def _synthetic_payload(user_id: int = 2762) -> dict:
    p = {"user_id": user_id, "fetched_at": "2026-05-29T00:00:00+00:00"}
    for name in sections.all_sections():
        p[name] = {"_marker": name}  # distinguishable per-section
    p["plaid_liabilities"] = []           # empty array section
    p["persona"] = {}                     # empty object section
    p["financial_profile_v2"] = {"dropped": True}  # not in catalog -> ignored
    p["amplitude_events"] = {"dropped": True}
    return p


class _Mock:
    """Swap in a fake _http_get; record call count."""
    def __init__(self, responder):
        self.responder = responder
        self.calls = 0
        self._orig = None

    def __enter__(self):
        self._orig = client._http_get
        def wrapped(path, params=None):
            self.calls += 1
            return self.responder(path, params)
        client._http_get = wrapped
        # Ensure "configured" so fetch path runs.
        client.BON_API_BASE_URL = "https://test.local"
        client.BON_ADMIN_API_KEY = "test-key"
        return self

    def __exit__(self, *a):
        client._http_get = self._orig


# ============================================================
# resolve_user_id
# ============================================================

def test_resolve_direct_user_id():
    db = _fresh_db()
    r = client.resolve_user_id("2762", "user_id", db_path=db)
    assert r.status == "resolved" and r.user_id == 2762
    # Non-integer user_id is invalid.
    assert client.resolve_user_id("abc", "user_id", db_path=db).status == "invalid"
    os.unlink(db)


def test_resolve_email_single_and_caches():
    db = _fresh_db()
    body = json.dumps([{"user_id": 2762, "email": "a@b.com", "name": "X",
                        "created_at": "2025-01-01T00:00:00Z"}]).encode()
    with _Mock(lambda path, params: (200, body)) as m:
        r = client.resolve_user_id("a@b.com", "email", db_path=db)
        assert r.status == "resolved" and r.user_id == 2762
        assert m.calls == 1
        # Second call served from cache — no extra HTTP call.
        r2 = client.resolve_user_id("a@b.com", "email", db_path=db)
        assert r2.status == "resolved" and r2.user_id == 2762
        assert m.calls == 1  # unchanged
    os.unlink(db)


def test_resolve_email_none_caches_negative():
    db = _fresh_db()
    with _Mock(lambda path, params: (200, b"[]")) as m:
        r = client.resolve_user_id("ghost@b.com", "email", db_path=db)
        assert r.status == "not_found"
        r2 = client.resolve_user_id("ghost@b.com", "email", db_path=db)
        assert r2.status == "not_found"
        assert m.calls == 1  # negative cached, no second HTTP call
    os.unlink(db)


def test_resolve_name_multiple():
    db = _fresh_db()
    body = json.dumps([
        {"user_id": 10, "email": "s1@b.com", "name": "Sultan A", "created_at": "x"},
        {"user_id": 11, "email": "s2@b.com", "name": "Sultan B", "created_at": "x"},
    ]).encode()
    with _Mock(lambda path, params: (200, body)):
        r = client.resolve_user_id("sultan", "name", db_path=db)
        assert r.status == "multiple" and len(r.matches) == 2
    os.unlink(db)


def test_resolve_search_400_invalid():
    db = _fresh_db()
    with _Mock(lambda path, params: (400, b'{"detail":"bad"}')):
        assert client.resolve_user_id("x", "email", db_path=db).status == "invalid"
    os.unlink(db)


def test_resolve_search_500_unavailable():
    db = _fresh_db()
    with _Mock(lambda path, params: (500, b"err")):
        assert client.resolve_user_id("x@b.com", "email", db_path=db).status == "search_unavailable"
    os.unlink(db)


def test_phone_normalization():
    db = _fresh_db()
    seen = {}
    def responder(path, params):
        seen["phone"] = params["phone"]
        return (200, json.dumps([{"user_id": 5, "email": "p@b.com", "name": "P",
                                  "created_at": "x"}]).encode())
    with _Mock(responder):
        client.resolve_user_id("+1 (415) 555-0100", "phone", db_path=db)
        assert seen["phone"] == "4155550100"  # stripped + de-countrycoded
    os.unlink(db)


# ============================================================
# fetch_sections
# ============================================================

def test_fetch_miss_then_hit_and_caches_all():
    db = _fresh_db()
    payload = json.dumps(_synthetic_payload(2762)).encode()
    with _Mock(lambda path, params: (200, payload)) as m:
        r = client.fetch_sections(2762, ["profile", "plaid_profiles"], db_path=db)
        assert r.status == "ok" and m.calls == 1
        assert r.api_calls == 1 and r.cache_hits == 0
        assert r.sections["profile"] == {"_marker": "profile"}

        # Second call for the SAME sections -> pure cache hit, no HTTP.
        r2 = client.fetch_sections(2762, ["profile", "plaid_profiles"], db_path=db)
        assert r2.status == "ok" and r2.api_calls == 0 and r2.cache_hits == 2
        assert m.calls == 1

        # A DIFFERENT section is also already cached (we cached the whole payload).
        r3 = client.fetch_sections(2762, ["subscriptions"], db_path=db)
        assert r3.api_calls == 0 and r3.cache_hits == 1
        assert m.calls == 1
    os.unlink(db)


def test_fetch_subsection_resolves_to_parent():
    db = _fresh_db()
    payload = json.dumps(_synthetic_payload(2762)).encode()
    with _Mock(lambda path, params: (200, payload)):
        r = client.fetch_sections(2762, ["chat.recent_turns"], db_path=db)
        assert r.status == "ok" and "chat" in r.sections  # returned under parent
    os.unlink(db)


def test_fetch_identity_mismatch():
    db = _fresh_db()
    # API returns a DIFFERENT user_id than requested.
    payload = json.dumps(_synthetic_payload(9999)).encode()
    with _Mock(lambda path, params: (200, payload)):
        r = client.fetch_sections(2762, ["profile"], db_path=db)
        assert r.status == "identity_mismatch"
    # Nothing should have been cached under 2762.
    assert cache.get_cached_section(2762, "profile", db_path=db) is None
    os.unlink(db)


def test_fetch_404_and_403():
    db = _fresh_db()
    with _Mock(lambda path, params: (404, b'{"detail":"Not Found"}')):
        assert client.fetch_sections(2762, ["profile"], db_path=db).status == "not_found"
    with _Mock(lambda path, params: (403, b'{"detail":"Forbidden"}')):
        assert client.fetch_sections(2762, ["profile"], db_path=db).status == "auth_error"
    os.unlink(db)


def test_fetch_5xx_serves_stale_when_available():
    db = _fresh_db()
    # Prime cache, then age it past TTL so it's stale-but-present.
    cache.put_cached_section(2762, "profile", {"_marker": "old"}, 2762, db_path=db)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE user_profile_cache SET fetched_at = datetime('now','-99999 seconds')")
    conn.commit(); conn.close()
    with _Mock(lambda path, params: (503, b"down")):
        r = client.fetch_sections(2762, ["profile"], db_path=db)
        assert r.status == "ok" and r.served_stale is True
        assert r.sections["profile"] == {"_marker": "old"}
    os.unlink(db)


def test_fetch_writes_audit_row():
    db = _fresh_db()
    payload = json.dumps(_synthetic_payload(2762)).encode()
    ctx = {"requester_slack_id": "U07GKLVA9FE", "requester_authority": "admin",
           "channel_type": "dm", "intent_summary": "debt", "redaction_tier": "minimal"}
    with _Mock(lambda path, params: (200, payload)):
        client.fetch_sections(2762, ["profile", "plaid_profiles"],
                              db_path=db, audit_ctx=ctx)
    summ = audit.access_summary(days=1, db_path=db)
    assert len(summ) == 1 and summ[0].requester_slack_id == "U07GKLVA9FE"
    assert summ[0].api_calls == 1
    os.unlink(db)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
