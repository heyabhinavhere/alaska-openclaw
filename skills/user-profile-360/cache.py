"""
cache.py — SQLite-backed cache + concurrency control for user-profile-360.

Backs three of the four migration-0003 tables:
  - user_profile_cache         (per-section TTL cache)
  - user_profile_inflight      (concurrent-fetch dedup)
  - user_profile_search_cache  (email/phone/name -> user_id resolution cache)

Design notes:
  - Freshness is decided at READ time using each section's TTL from
    sections.py. A stale row is harmless until read, so the daily purge cron
    is just disk housekeeping, not a correctness mechanism.
  - A stale row can still be served as a fallback when the API is down
    (get_cached_section(..., allow_stale=True)). The returned object always
    carries is_fresh so the caller can decide.
  - Age + freshness are computed in SQLite (strftime) to avoid Python/UTC
    timezone parsing pitfalls — SQLite CURRENT_TIMESTAMP is UTC and so is
    strftime('%s','now').
  - All connections set PRAGMA foreign_keys=ON per shared-toolkit Section 1.5.
    These tables have no outgoing FKs, so it's a harmless no-op kept for
    consistency with the rest of the codebase.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Any

import sections

# Default DB path matches the rest of Alaska (see shared-toolkit). Overridable
# via env for local testing against a throwaway DB.
DEFAULT_DB_PATH = os.environ.get("ALASKA_DB_PATH", "/data/queue/alaska.db")

# Search-cache TTLs (seconds). Positive results are stable for a day; negative
# results ("no user with this email") expire fast so a typo'd lookup that's
# later corrected upstream isn't stuck.
SEARCH_POSITIVE_TTL = 24 * 3600
SEARCH_NEGATIVE_TTL = 10 * 60

# Inflight claims older than this are considered orphaned (process died
# mid-fetch) and reaped on the next claim attempt.
INFLIGHT_ORPHAN_SECONDS = 60


@dataclass
class CachedSection:
    user_id: int
    section: str
    data: Any          # parsed JSON; may be None / {} / [] for empty sections
    age_seconds: int
    is_fresh: bool
    payload_bytes: int
    api_response_user_id: int | None


@dataclass
class SearchHit:
    query_type: str
    query_value: str
    user_id: int | None  # None == cached negative result ("no match")
    age_seconds: int
    is_fresh: bool


def _connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ============================================================
# Section cache
# ============================================================

def get_cached_section(
    user_id: int,
    section: str,
    allow_stale: bool = False,
    db_path: str = DEFAULT_DB_PATH,
) -> CachedSection | None:
    """Return the cached section if present.

    By default returns it only when fresh (age <= the section's TTL). With
    allow_stale=True, returns a present-but-stale row too (for serving when
    the API is unreachable) — inspect .is_fresh to tell which you got.

    Returns None on a true cache miss (no row at all), or on a stale row
    when allow_stale is False.
    """
    parent = sections.get_parent(section)
    ttl = sections.get_ttl(section)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT data_json, payload_bytes, api_response_user_id,
                   CAST(strftime('%s','now') - strftime('%s', fetched_at) AS INTEGER)
                     AS age_seconds
            FROM user_profile_cache
            WHERE user_id = ? AND section = ?
            """,
            (user_id, parent),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    data_json, payload_bytes, api_uid, age_seconds = row
    age_seconds = int(age_seconds if age_seconds is not None else 0)
    is_fresh = age_seconds <= ttl
    if not is_fresh and not allow_stale:
        return None

    data = json.loads(data_json) if data_json is not None else None
    return CachedSection(
        user_id=user_id,
        section=parent,
        data=data,
        age_seconds=age_seconds,
        is_fresh=is_fresh,
        payload_bytes=int(payload_bytes or 0),
        api_response_user_id=api_uid,
    )


def put_cached_section(
    user_id: int,
    section: str,
    data: Any,
    api_response_user_id: int | None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Upsert a section's data into the cache. `data` may be None / {} / []
    for an empty section — stored faithfully so the summarizer can tell
    'no data' apart from 'not fetched'. fetched_at resets to now."""
    parent = sections.get_parent(section)
    data_json = json.dumps(data, separators=(",", ":")) if data is not None else None
    payload_bytes = len(data_json.encode("utf-8")) if data_json is not None else 0
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO user_profile_cache
                (user_id, section, data_json, fetched_at, payload_bytes,
                 api_response_user_id)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            ON CONFLICT(user_id, section) DO UPDATE SET
                data_json = excluded.data_json,
                fetched_at = excluded.fetched_at,
                payload_bytes = excluded.payload_bytes,
                api_response_user_id = excluded.api_response_user_id
            """,
            (user_id, parent, data_json, payload_bytes, api_response_user_id),
        )
        conn.commit()
    finally:
        conn.close()


def purge_expired(db_path: str = DEFAULT_DB_PATH) -> int:
    """Delete cache rows older than their section's TTL. Pure housekeeping —
    correctness comes from the read-time freshness check. Returns rows deleted.

    Runs one DELETE per distinct TTL bucket so each section is judged by its
    own TTL (chat at 15m, history at 6h, etc.)."""
    # Map ttl -> [sections with that ttl]
    ttl_buckets: dict[int, list[str]] = {}
    for name in sections.all_sections():
        ttl_buckets.setdefault(sections.SECTIONS[name].ttl_seconds, []).append(name)

    deleted = 0
    conn = _connect(db_path)
    try:
        for ttl, names in ttl_buckets.items():
            placeholders = ",".join("?" * len(names))
            cur = conn.execute(
                f"""
                DELETE FROM user_profile_cache
                WHERE section IN ({placeholders})
                  AND CAST(strftime('%s','now') - strftime('%s', fetched_at)
                       AS INTEGER) > ?
                """,
                (*names, ttl),
            )
            deleted += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return deleted


# ============================================================
# Inflight dedup
# ============================================================

def reap_orphan_inflight(
    db_path: str = DEFAULT_DB_PATH,
    older_than_seconds: int = INFLIGHT_ORPHAN_SECONDS,
) -> int:
    """Delete inflight claims older than the orphan threshold (process died
    mid-fetch). Returns rows reaped."""
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            DELETE FROM user_profile_inflight
            WHERE CAST(strftime('%s','now') - strftime('%s', claimed_at)
                  AS INTEGER) > ?
            """,
            (older_than_seconds,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def claim_inflight(
    user_id: int,
    lock_key: str,
    claimed_by: str,
    db_path: str = DEFAULT_DB_PATH,
) -> bool:
    """Try to claim a fetch lock for (user_id, lock_key). Returns True if this
    caller now holds the claim, False if someone else already does. Reaps
    orphans first so a dead claim never blocks forever.

    lock_key is opaque — the caller decides granularity. client.py uses a
    single per-user lock (one API call returns the whole profile, so the dedup
    unit is the user, not the individual section)."""
    reap_orphan_inflight(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO user_profile_inflight (user_id, section, claimed_by)
            VALUES (?, ?, ?)
            """,
            (user_id, lock_key, claimed_by),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # PK conflict — another caller holds the claim.
        return False
    finally:
        conn.close()


def release_inflight(
    user_id: int,
    lock_key: str,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Release a fetch lock (call after the cache write, in a finally block)."""
    conn = _connect(db_path)
    try:
        conn.execute(
            "DELETE FROM user_profile_inflight WHERE user_id = ? AND section = ?",
            (user_id, lock_key),
        )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# Search (identity-resolution) cache
# ============================================================

def get_cached_search(
    query_type: str,
    query_value: str,
    db_path: str = DEFAULT_DB_PATH,
) -> SearchHit | None:
    """Look up a cached email/phone/name -> user_id resolution. Honors a
    longer TTL for positive hits and a shorter one for cached negatives.
    Returns None on miss or when the cached entry has expired."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT user_id,
                   CAST(strftime('%s','now') - strftime('%s', cached_at)
                        AS INTEGER) AS age_seconds
            FROM user_profile_search_cache
            WHERE query_type = ? AND query_value = ?
            """,
            (query_type, query_value),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    user_id, age_seconds = row
    age_seconds = int(age_seconds if age_seconds is not None else 0)
    ttl = SEARCH_POSITIVE_TTL if user_id is not None else SEARCH_NEGATIVE_TTL
    is_fresh = age_seconds <= ttl
    if not is_fresh:
        return None
    return SearchHit(
        query_type=query_type,
        query_value=query_value,
        user_id=user_id,
        age_seconds=age_seconds,
        is_fresh=is_fresh,
    )


def put_cached_search(
    query_type: str,
    query_value: str,
    user_id: int | None,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    """Cache a resolution. Pass user_id=None to cache a negative ('no match')."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO user_profile_search_cache
                (query_type, query_value, user_id, cached_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(query_type, query_value) DO UPDATE SET
                user_id = excluded.user_id,
                cached_at = excluded.cached_at
            """,
            (query_type, query_value, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def purge_expired_search(db_path: str = DEFAULT_DB_PATH) -> int:
    """Delete search-cache rows past their (positive/negative) TTL. Housekeeping.
    Returns rows deleted."""
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            DELETE FROM user_profile_search_cache
            WHERE (user_id IS NOT NULL
                   AND CAST(strftime('%s','now') - strftime('%s', cached_at)
                        AS INTEGER) > ?)
               OR (user_id IS NULL
                   AND CAST(strftime('%s','now') - strftime('%s', cached_at)
                        AS INTEGER) > ?)
            """,
            (SEARCH_POSITIVE_TTL, SEARCH_NEGATIVE_TTL),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
