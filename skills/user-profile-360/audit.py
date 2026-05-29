"""
audit.py — PII access audit trail for user-profile-360.

Every invocation of the skill writes exactly one row to
user_profile_access_log, including DENIED attempts (engineer reaching for
user data, unknown caller, wrong surface). Denied access is itself signal.

Also exposes read helpers for the weekly digest cron and anomaly detection.

Enum values are validated in Python before insert so a bad value fails with
a clear message here rather than as an opaque SQLite CHECK-constraint error.
Keep these in sync with migration 0003.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass

DEFAULT_DB_PATH = os.environ.get("ALASKA_DB_PATH", "/data/queue/alaska.db")

# Mirror of the CHECK constraints in migration 0003. Validated before insert.
VALID_AUTHORITY = {"admin", "founder", "engineer", "system", "unknown"}
VALID_OUTCOME = {
    "granted",
    "denied_authority",
    "denied_channel",
    "denied_unknown",
    "error",
}
VALID_CHANNEL_TYPE = {None, "dm", "channel", "cron", "agent_signal"}
VALID_REDACTION_TIER = {None, "full", "minimal", "medium"}


@dataclass
class AccessSummaryRow:
    requester_slack_id: str
    queries: int
    api_calls: int
    cache_hits: int
    response_bytes: int


def _connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def log_access(
    user_id: int,
    requester_slack_id: str,
    requester_authority: str,
    outcome: str,
    invoking_skill: str,
    channel_id: str | None = None,
    channel_type: str | None = None,
    sections_requested: list[str] | None = None,
    cache_hits: int = 0,
    api_calls: int = 0,
    response_bytes: int | None = None,
    intent_summary: str | None = None,
    redaction_tier: str | None = None,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """Append one access-log row. Returns the new row id.

    Validates enum fields up front. sections_requested is stored as a JSON
    array string. This must NEVER raise on a denied/error path — the whole
    point is to record those — so callers should wrap their own logic, but
    the validation here only guards against programmer error (bad enum), not
    runtime conditions.
    """
    if requester_authority not in VALID_AUTHORITY:
        raise ValueError(
            f"requester_authority {requester_authority!r} not in {sorted(VALID_AUTHORITY)}"
        )
    if outcome not in VALID_OUTCOME:
        raise ValueError(f"outcome {outcome!r} not in {sorted(VALID_OUTCOME)}")
    if channel_type not in VALID_CHANNEL_TYPE:
        raise ValueError(
            f"channel_type {channel_type!r} not in {sorted(x for x in VALID_CHANNEL_TYPE if x)}"
        )
    if redaction_tier not in VALID_REDACTION_TIER:
        raise ValueError(
            f"redaction_tier {redaction_tier!r} not in {sorted(x for x in VALID_REDACTION_TIER if x)}"
        )

    sections_json = (
        json.dumps(sections_requested, separators=(",", ":"))
        if sections_requested is not None
        else None
    )

    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO user_profile_access_log
                (user_id, requester_slack_id, requester_authority, outcome,
                 invoking_skill, channel_id, channel_type, sections_requested,
                 cache_hits, api_calls, response_bytes, intent_summary,
                 redaction_tier)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                requester_slack_id,
                requester_authority,
                outcome,
                invoking_skill,
                channel_id,
                channel_type,
                sections_json,
                cache_hits,
                api_calls,
                response_bytes,
                intent_summary,
                redaction_tier,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


# ============================================================
# Read helpers — weekly digest + anomaly detection
# ============================================================

def access_summary(
    days: int = 1,
    db_path: str = DEFAULT_DB_PATH,
) -> list[AccessSummaryRow]:
    """Per-requester rollup over the last N days (granted calls only)."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT requester_slack_id,
                   COUNT(*) AS queries,
                   COALESCE(SUM(api_calls), 0) AS api_calls,
                   COALESCE(SUM(cache_hits), 0) AS cache_hits,
                   COALESCE(SUM(response_bytes), 0) AS bytes
            FROM user_profile_access_log
            WHERE outcome = 'granted'
              AND accessed_at > datetime('now', ?)
            GROUP BY requester_slack_id
            ORDER BY queries DESC
            """,
            (f"-{int(days)} days",),
        ).fetchall()
    finally:
        conn.close()
    return [AccessSummaryRow(r[0], r[1], r[2], r[3], r[4]) for r in rows]


def cache_hit_rate(days: int = 7, db_path: str = DEFAULT_DB_PATH) -> float:
    """Fraction of section reads served from cache over the window.
    Returns 0.0 when there's no traffic (avoids div-by-zero)."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(cache_hits), 0), COALESCE(SUM(api_calls), 0)
            FROM user_profile_access_log
            WHERE accessed_at > datetime('now', ?)
            """,
            (f"-{int(days)} days",),
        ).fetchone()
    finally:
        conn.close()
    hits, calls = (row or (0, 0))
    total = (hits or 0) + (calls or 0)
    return (hits / total) if total else 0.0


def most_accessed_users(
    days: int = 7,
    limit: int = 10,
    db_path: str = DEFAULT_DB_PATH,
) -> list[tuple[int, int]]:
    """Most-looked-up users (user_id, access_count) over the window. A spike
    here can flag abuse or a hot debugging session worth a glance."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT user_id, COUNT(*) AS accesses
            FROM user_profile_access_log
            WHERE outcome = 'granted'
              AND accessed_at > datetime('now', ?)
            GROUP BY user_id
            ORDER BY accesses DESC
            LIMIT ?
            """,
            (f"-{int(days)} days", int(limit)),
        ).fetchall()
    finally:
        conn.close()
    return [(int(r[0]), int(r[1])) for r in rows]


def denied_attempts(
    days: int = 7,
    db_path: str = DEFAULT_DB_PATH,
) -> list[tuple[str, str, int]]:
    """Denied access attempts (requester_slack_id, outcome, count) over the
    window — for the digest's security section."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT requester_slack_id, outcome, COUNT(*) AS n
            FROM user_profile_access_log
            WHERE outcome LIKE 'denied_%'
              AND accessed_at > datetime('now', ?)
            GROUP BY requester_slack_id, outcome
            ORDER BY n DESC
            """,
            (f"-{int(days)} days",),
        ).fetchall()
    finally:
        conn.close()
    return [(r[0], r[1], int(r[2])) for r in rows]
