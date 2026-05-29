"""
Tests for cache.py + audit.py against a throwaway SQLite DB.

Runnable standalone (no pytest required):  python3 test_cache_audit.py
Also pytest-discoverable (functions named test_*).

Builds a temp DB with migration 0003's tables, then exercises:
  - section cache put/get, empty-section round-trip, TTL freshness, stale fallback
  - inflight claim/release/double-claim/orphan-reap
  - search cache positive/negative + TTL expiry
  - audit log granted/denied, enum validation, digest queries
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

# Make the skill modules importable when run from anywhere.
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

import audit  # noqa: E402
import cache  # noqa: E402


def _fresh_db() -> str:
    """Create a temp DB with just migration 0003's tables (the only ones
    cache.py / audit.py touch). Returns the path."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="up360_test_")
    os.close(fd)
    # Locate migration 0003 relative to this test file.
    repo_root = os.path.dirname(os.path.dirname(_SKILL_DIR))  # skills/.. -> repo
    migration = os.path.join(repo_root, "migrations", "0003_user_profile_360.sql")
    with open(migration, "r", encoding="utf-8") as f:
        sql = f.read()
    conn = sqlite3.connect(path)
    conn.executescript(sql)
    conn.commit()
    conn.close()
    return path


def _age_row(db: str, table: str, where: str, seconds: int) -> None:
    """Back-date a timestamp column to simulate age, for TTL tests."""
    col = {
        "user_profile_cache": "fetched_at",
        "user_profile_inflight": "claimed_at",
        "user_profile_search_cache": "cached_at",
    }[table]
    conn = sqlite3.connect(db)
    conn.execute(
        f"UPDATE {table} SET {col} = datetime('now', ?) WHERE {where}",
        (f"-{seconds} seconds",),
    )
    conn.commit()
    conn.close()


# ============================================================
# Section cache
# ============================================================

def test_section_put_get_fresh():
    db = _fresh_db()
    cache.put_cached_section(2762, "plaid_profiles", {"util": 0.61}, 2762, db_path=db)
    hit = cache.get_cached_section(2762, "plaid_profiles", db_path=db)
    assert hit is not None
    assert hit.data == {"util": 0.61}
    assert hit.is_fresh
    assert hit.api_response_user_id == 2762
    assert hit.payload_bytes > 0
    os.unlink(db)


def test_empty_section_roundtrip():
    db = _fresh_db()
    # API returned [] for an empty section — must round-trip as [] not None.
    cache.put_cached_section(2762, "plaid_liabilities", [], 2762, db_path=db)
    hit = cache.get_cached_section(2762, "plaid_liabilities", db_path=db)
    assert hit is not None and hit.data == []
    # And a None section (key absent) round-trips as None.
    cache.put_cached_section(2762, "persona", None, 2762, db_path=db)
    hit2 = cache.get_cached_section(2762, "persona", db_path=db)
    assert hit2 is not None and hit2.data is None
    os.unlink(db)


def test_section_ttl_expiry_and_stale_fallback():
    db = _fresh_db()
    # chat TTL is 900s. Back-date to 1000s -> stale.
    cache.put_cached_section(2762, "chat", {"threads": 1}, 2762, db_path=db)
    _age_row(db, "user_profile_cache", "user_id=2762 AND section='chat'", 1000)

    # Default read: stale -> miss.
    assert cache.get_cached_section(2762, "chat", db_path=db) is None
    # allow_stale: returns the row, flagged not-fresh.
    stale = cache.get_cached_section(2762, "chat", allow_stale=True, db_path=db)
    assert stale is not None and stale.is_fresh is False and stale.data == {"threads": 1}
    os.unlink(db)


def test_subsection_inherits_parent():
    db = _fresh_db()
    # Writing/reading a sub-section resolves to the parent 'chat' row.
    cache.put_cached_section(2762, "chat.recent_turns", {"x": 1}, 2762, db_path=db)
    hit = cache.get_cached_section(2762, "chat.recent_turns", db_path=db)
    assert hit is not None and hit.section == "chat"  # resolved to parent
    os.unlink(db)


def test_purge_expired():
    db = _fresh_db()
    cache.put_cached_section(2762, "chat", {"a": 1}, 2762, db_path=db)        # ttl 900
    cache.put_cached_section(2762, "tradeline_history", [1], 2762, db_path=db)  # ttl 21600
    _age_row(db, "user_profile_cache", "section='chat'", 1000)               # stale
    _age_row(db, "user_profile_cache", "section='tradeline_history'", 1000)  # still fresh
    deleted = cache.purge_expired(db_path=db)
    assert deleted == 1  # only chat purged
    assert cache.get_cached_section(2762, "tradeline_history", db_path=db) is not None
    os.unlink(db)


# ============================================================
# Inflight dedup
# ============================================================

def test_inflight_claim_release():
    db = _fresh_db()
    assert cache.claim_inflight(2762, "chat", "skillA:pid1", db_path=db) is True
    # Second claim by anyone fails while held.
    assert cache.claim_inflight(2762, "chat", "skillB:pid2", db_path=db) is False
    cache.release_inflight(2762, "chat", db_path=db)
    # After release, claimable again.
    assert cache.claim_inflight(2762, "chat", "skillB:pid2", db_path=db) is True
    os.unlink(db)


def test_inflight_orphan_reaped():
    db = _fresh_db()
    cache.claim_inflight(2762, "chat", "deadproc", db_path=db)
    _age_row(db, "user_profile_inflight", "user_id=2762 AND section='chat'", 120)
    # A fresh claim attempt reaps the 120s-old orphan first, then succeeds.
    assert cache.claim_inflight(2762, "chat", "liveproc", db_path=db) is True
    os.unlink(db)


# ============================================================
# Search cache
# ============================================================

def test_search_positive_and_negative():
    db = _fresh_db()
    cache.put_cached_search("email", "a@b.com", 2762, db_path=db)
    hit = cache.get_cached_search("email", "a@b.com", db_path=db)
    assert hit is not None and hit.user_id == 2762

    cache.put_cached_search("email", "ghost@b.com", None, db_path=db)
    neg = cache.get_cached_search("email", "ghost@b.com", db_path=db)
    assert neg is not None and neg.user_id is None  # cached negative
    os.unlink(db)


def test_search_negative_ttl_shorter():
    db = _fresh_db()
    # Negative TTL is 600s. Age a negative to 700s -> expired -> miss.
    cache.put_cached_search("email", "ghost@b.com", None, db_path=db)
    _age_row(db, "user_profile_search_cache", "query_value='ghost@b.com'", 700)
    assert cache.get_cached_search("email", "ghost@b.com", db_path=db) is None
    # A positive aged 700s is still fresh (positive TTL 24h).
    cache.put_cached_search("email", "real@b.com", 2762, db_path=db)
    _age_row(db, "user_profile_search_cache", "query_value='real@b.com'", 700)
    assert cache.get_cached_search("email", "real@b.com", db_path=db) is not None
    os.unlink(db)


# ============================================================
# Audit
# ============================================================

def test_audit_log_granted_and_queries():
    db = _fresh_db()
    audit.log_access(
        2762, "U07GKLVA9FE", "admin", "granted", "user-profile-360",
        channel_id="D123", channel_type="dm",
        sections_requested=["profile", "plaid_profiles"],
        cache_hits=1, api_calls=1, response_bytes=4096,
        intent_summary="debt situation", redaction_tier="minimal", db_path=db,
    )
    audit.log_access(
        2762, "U07GKLVA9FE", "admin", "granted", "user-profile-360",
        cache_hits=2, api_calls=0, db_path=db,
    )
    summ = audit.access_summary(days=1, db_path=db)
    assert len(summ) == 1 and summ[0].queries == 2 and summ[0].api_calls == 1
    # hit rate = 3 hits / (3 hits + 1 call) = 0.75
    assert abs(audit.cache_hit_rate(days=7, db_path=db) - 0.75) < 1e-9
    top = audit.most_accessed_users(days=7, db_path=db)
    assert top == [(2762, 2)]
    os.unlink(db)


def test_audit_log_denied():
    db = _fresh_db()
    audit.log_access(
        2762, "U0ENGINEER", "engineer", "denied_authority", "user-profile-360",
        channel_type="dm", db_path=db,
    )
    denied = audit.denied_attempts(days=7, db_path=db)
    assert denied == [("U0ENGINEER", "denied_authority", 1)]
    # denied calls don't count toward granted summary
    assert audit.access_summary(days=1, db_path=db) == []
    os.unlink(db)


def test_audit_enum_validation():
    db = _fresh_db()
    for bad in [
        dict(requester_authority="superuser"),
        dict(outcome="allowed"),
        dict(channel_type="telepathy"),
        dict(redaction_tier="none"),
    ]:
        kwargs = dict(
            user_id=1, requester_slack_id="U1", requester_authority="admin",
            outcome="granted", invoking_skill="x", db_path=db,
        )
        kwargs.update(bad)
        try:
            audit.log_access(**kwargs)
            assert False, f"expected ValueError for {bad}"
        except ValueError:
            pass
    os.unlink(db)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
