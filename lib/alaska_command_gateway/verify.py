"""Slack request verification — signing-secret HMAC + timestamp freshness.

Implements Slack's documented slash-command / Events API verification:

    base   = "v0:{timestamp}:{raw_body}"
    expect = "v0=" + hex(HMAC_SHA256(signing_secret, base))
    valid  = constant_time_eq(expect, X-Slack-Signature)  AND  |now - timestamp| <= 300

We never use the deprecated verification token. Verification fails closed: any
missing field, a malformed timestamp, or a stale request returns False.

    verify_slack_signature(signing_secret, timestamp, raw_body, signature) -> bool
    team_allowed(team_id, allowed=None) -> bool
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional, Sequence

MAX_SKEW_SECONDS = 300   # Slack's recommended replay window


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    raw_body: str,
    signature: str,
    *,
    now: Optional[float] = None,
    max_skew: int = MAX_SKEW_SECONDS,
) -> bool:
    """Return True only if `signature` is a valid Slack v0 signature for the
    exact `raw_body` and `timestamp`, and the timestamp is within `max_skew`
    seconds of `now` (defaults to wall-clock time). Never raises."""
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    if abs(current - ts) > max_skew:
        return False

    if isinstance(raw_body, bytes):
        raw_body = raw_body.decode("utf-8", "replace")
    base = ("v0:%s:%s" % (timestamp, raw_body)).encode("utf-8")
    digest = hmac.new(signing_secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    expected = "v0=" + digest
    return hmac.compare_digest(expected, signature)


def _configured_allowed(allowed: Optional[Sequence[str]]) -> Optional[set]:
    if allowed is not None:
        return {str(a).strip() for a in allowed if str(a).strip()}
    env = os.environ.get("SLACK_ALLOWED_TEAM_ID", "").strip()
    if not env:
        return None
    return {part.strip() for part in env.split(",") if part.strip()}


def team_allowed(team_id: Optional[str], allowed: Optional[Sequence[str]] = None) -> bool:
    """Return True if `team_id` is permitted.

    If no allowlist is configured (no `allowed` arg and no SLACK_ALLOWED_TEAM_ID
    env var), every team is allowed — matching the repo's current open posture.
    When an allowlist IS configured, only listed teams pass.
    """
    configured = _configured_allowed(allowed)
    if configured is None:
        return True
    return bool(team_id) and team_id in configured
