"""
client.py — HTTP client + cache-aware fetch for user-profile-360.

Talks to Sandeep's BON admin API:
  - GET /api/admin/users/search?email=|phone=|name=   -> identity resolution
  - GET /api/admin/users/{user_id}/profile             -> full 360 payload

Responsibilities:
  - resolve_user_id(): turn an email/phone/name into a user_id (search cache
    first, then the search endpoint; handles 0/1/many matches)
  - fetch_sections(): return the requested sections, cache-first. One API call
    returns the WHOLE profile, so on any miss we fetch once and refresh every
    catalog section's cache (we already paid for the bytes), then return the
    requested subset.

NOT this module's job:
  - Authority gating (who's allowed to look up users) — that lives in the
    redactor / SKILL layer. This module assumes the caller already authorized
    the request. It only *records* requester_authority in the audit log.
  - Redaction — raw section data is returned as-is; redactor.py transforms it
    before anything reaches Alaska's context or Slack.

Uses urllib (no `requests` dependency) to match the amplitude-analyst skill
and keep the Docker image lean.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import audit
import cache
import sections

# ---- Config (from Railway env) -------------------------------------------
BON_API_BASE_URL = os.environ.get("BON_API_BASE_URL", "").rstrip("/")
BON_ADMIN_API_KEY = os.environ.get("BON_ADMIN_API_KEY", "")

HTTP_TIMEOUT_SECONDS = 25
HTTP_RETRIES = 1  # one retry on timeout / 5xx

# Single per-user fetch lock — one /profile call refreshes the whole user,
# so the dedup unit is the user, not the section.
FETCH_LOCK = "__full_profile__"
INFLIGHT_WAIT_SECONDS = 8
INFLIGHT_POLL_INTERVAL = 0.2

VALID_QUERY_TYPES = {"user_id", "email", "phone", "name"}


# ---- Result types ---------------------------------------------------------

@dataclass
class ResolveResult:
    # status: resolved | not_found | multiple | search_unavailable | invalid | not_configured
    status: str
    user_id: int | None = None
    matches: list[dict] = field(default_factory=list)  # for 'multiple'
    message: str = ""


@dataclass
class FetchResult:
    # status: ok | not_found | auth_error | api_error | identity_mismatch | not_configured
    status: str
    sections: dict[str, Any] = field(default_factory=dict)  # parent_name -> raw data
    cache_hits: int = 0
    api_calls: int = 0
    response_bytes: int = 0
    served_stale: bool = False
    message: str = ""


# ---- Config + HTTP --------------------------------------------------------

def is_configured() -> bool:
    return bool(BON_API_BASE_URL and BON_ADMIN_API_KEY)


def _http_get(path: str, params: dict | None = None) -> tuple[int, bytes]:
    """GET with X-Admin-Key. Retries once on timeout / 5xx. Returns
    (status_code, body_bytes). status_code 0 means a transport-level failure
    (timeout / connection error) after retries."""
    url = f"{BON_API_BASE_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    last_exc: Exception | None = None
    for attempt in range(HTTP_RETRIES + 1):
        req = urllib.request.Request(url, headers={"X-Admin-Key": BON_ADMIN_API_KEY})
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            body = e.read() if hasattr(e, "read") else b""
            # Retry only on 5xx; 4xx is deterministic, return immediately.
            if e.code >= 500 and attempt < HTTP_RETRIES:
                last_exc = e
                time.sleep(0.5 * (attempt + 1))
                continue
            return e.code, body
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
            if attempt < HTTP_RETRIES:
                time.sleep(0.5 * (attempt + 1))
                continue
    # Transport failure after retries.
    return 0, str(last_exc or "transport error").encode()


# ---- Identity resolution --------------------------------------------------

def _normalize_phone(raw: str) -> str:
    """Strip to digits, drop a leading US country code so 11-digit '1XXXXXXXXXX'
    and 10-digit 'XXXXXXXXXX' resolve the same way."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def resolve_user_id(
    query: str,
    query_type: str,
    db_path: str = cache.DEFAULT_DB_PATH,
) -> ResolveResult:
    """Resolve an identifier to a user_id.

    query_type:
      user_id -> parse directly, no API call
      email   -> exact search
      phone   -> normalized search
      name    -> partial search (may return many; caller disambiguates)

    Search cache is consulted first (positive 24h / negative 10m). On a search
    API failure, returns status='search_unavailable' so the SKILL layer can
    fall back to Customer.io / Amplitude resolution.
    """
    if query_type not in VALID_QUERY_TYPES:
        return ResolveResult("invalid", message=f"bad query_type {query_type!r}")

    if query_type == "user_id":
        try:
            return ResolveResult("resolved", user_id=int(str(query).strip()))
        except (TypeError, ValueError):
            return ResolveResult("invalid", message=f"{query!r} is not an integer user_id")

    if not is_configured():
        return ResolveResult("not_configured", message="BON API env not set")

    value = _normalize_phone(query) if query_type == "phone" else query.strip()
    if not value:
        return ResolveResult("invalid", message="empty query")

    # Cache first (skip cache for name — name matches are fuzzy/ambiguous and
    # we don't cache multi-match results).
    if query_type in ("email", "phone"):
        hit = cache.get_cached_search(query_type, value, db_path=db_path)
        if hit is not None:
            if hit.user_id is not None:
                return ResolveResult("resolved", user_id=hit.user_id, message="cache")
            return ResolveResult("not_found", message="cache (negative)")

    status, body = _http_get("/api/admin/users/search", {query_type: value})

    if status == 400:
        return ResolveResult("invalid", message="search rejected the query")
    if status == 0 or status >= 500:
        return ResolveResult("search_unavailable", message=f"search API status {status}")
    if status != 200:
        return ResolveResult("search_unavailable", message=f"unexpected status {status}")

    try:
        results = json.loads(body)
    except json.JSONDecodeError:
        return ResolveResult("search_unavailable", message="search returned non-JSON")

    if not isinstance(results, list):
        return ResolveResult("search_unavailable", message="search returned non-array")

    if len(results) == 0:
        if query_type in ("email", "phone"):
            cache.put_cached_search(query_type, value, None, db_path=db_path)  # negative
        return ResolveResult("not_found", message="no match")

    if len(results) == 1:
        uid = int(results[0]["user_id"])
        if query_type in ("email", "phone"):
            cache.put_cached_search(query_type, value, uid, db_path=db_path)
        return ResolveResult("resolved", user_id=uid, message="search")

    # Multiple matches — return them for the caller to disambiguate (don't cache).
    return ResolveResult("multiple", matches=results, message=f"{len(results)} matches")


# ---- Section fetch --------------------------------------------------------

def _extract_and_cache_all(
    user_id: int,
    payload: dict,
    db_path: str,
) -> None:
    """Cache every catalog section from a fresh /profile payload. We fetched
    the whole thing, so populate the whole cache — a later request for a
    different section is then a hit."""
    api_uid = payload.get("user_id")
    for name in sections.all_sections():
        # Missing key -> None (cached as 'no data'); present -> stored faithfully
        # including {} / [] empties.
        cache.put_cached_section(
            user_id, name, payload.get(name), api_uid, db_path=db_path
        )


def fetch_sections(
    user_id: int,
    section_names: list[str],
    db_path: str = cache.DEFAULT_DB_PATH,
    *,
    force_refresh: bool = False,
    audit_ctx: dict | None = None,
) -> FetchResult:
    """Return the requested sections (cache-first).

    section_names may include sub-sections (e.g. 'chat.recent_turns'); they
    resolve to their parent for caching, and the parent's data is returned
    under the parent key (the caller/summarizer extracts sub-keys).

    audit_ctx, if provided, must carry: requester_slack_id, requester_authority,
    and optionally channel_id, channel_type, intent_summary, redaction_tier.
    A single audit row is written reflecting the outcome.
    """
    parents = sorted({sections.get_parent(s) for s in section_names})
    result = FetchResult(status="ok")

    def _finish(res: FetchResult) -> FetchResult:
        if audit_ctx is not None:
            outcome = "granted" if res.status == "ok" else "error"
            audit.log_access(
                user_id=user_id,
                requester_slack_id=audit_ctx.get("requester_slack_id", "unknown"),
                requester_authority=audit_ctx.get("requester_authority", "system"),
                outcome=outcome,
                invoking_skill=audit_ctx.get("invoking_skill", "user-profile-360"),
                channel_id=audit_ctx.get("channel_id"),
                channel_type=audit_ctx.get("channel_type"),
                sections_requested=section_names,
                cache_hits=res.cache_hits,
                api_calls=res.api_calls,
                response_bytes=res.response_bytes,
                intent_summary=audit_ctx.get("intent_summary"),
                redaction_tier=audit_ctx.get("redaction_tier"),
                db_path=db_path,
            )
        return res

    # 1. Cache check (unless forced)
    fresh: dict[str, Any] = {}
    if not force_refresh:
        for p in parents:
            hit = cache.get_cached_section(user_id, p, db_path=db_path)
            if hit is not None:  # fresh hit
                fresh[p] = hit.data
        if len(fresh) == len(parents):
            result.sections = fresh
            result.cache_hits = len(fresh)
            return _finish(result)

    # 2. Need an API call. Confirm config.
    if not is_configured():
        return _finish(FetchResult(status="not_configured",
                                   message="BON API env not set"))

    # 3. Per-user inflight lock to dedup concurrent fetches.
    claimed = cache.claim_inflight(user_id, FETCH_LOCK, f"client:{os.getpid()}", db_path=db_path)
    if not claimed:
        # Someone else is fetching this user. Poll cache briefly for the
        # sections we need; if they appear fresh, use them. Otherwise proceed
        # to fetch ourselves rather than deadlock.
        waited = 0.0
        while waited < INFLIGHT_WAIT_SECONDS:
            time.sleep(INFLIGHT_POLL_INTERVAL)
            waited += INFLIGHT_POLL_INTERVAL
            got = {}
            for p in parents:
                hit = cache.get_cached_section(user_id, p, db_path=db_path)
                if hit is not None:
                    got[p] = hit.data
            if len(got) == len(parents):
                result.sections = got
                result.cache_hits = len(got)
                return _finish(result)
        # Fell through — claim it ourselves (best-effort).
        claimed = cache.claim_inflight(user_id, FETCH_LOCK, f"client:{os.getpid()}", db_path=db_path)

    try:
        status, body = _http_get(f"/api/admin/users/{user_id}/profile")
        result.api_calls = 1
        result.response_bytes = len(body)

        if status == 404:
            return _finish(FetchResult(status="not_found", api_calls=1,
                                       response_bytes=len(body),
                                       message=f"user {user_id} not found"))
        if status in (401, 403):
            return _finish(FetchResult(status="auth_error", api_calls=1,
                                       response_bytes=len(body),
                                       message="BON API auth failed"))
        if status != 200:
            # Try stale cache as a fallback before giving up.
            stale = _gather_stale(user_id, parents, db_path)
            if stale:
                result.sections = stale
                result.served_stale = True
                result.message = f"API status {status}; served stale cache"
                return _finish(result)
            return _finish(FetchResult(status="api_error", api_calls=1,
                                       response_bytes=len(body),
                                       message=f"API status {status}"))

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return _finish(FetchResult(status="api_error", api_calls=1,
                                       response_bytes=len(body),
                                       message="profile returned non-JSON"))

        # Identity-mismatch defense: the payload's user_id must match.
        if payload.get("user_id") != user_id:
            return _finish(FetchResult(status="identity_mismatch", api_calls=1,
                                       response_bytes=len(body),
                                       message=(f"requested {user_id} but API "
                                                f"returned {payload.get('user_id')}")))

        # Cache everything we got, return the requested parents.
        _extract_and_cache_all(user_id, payload, db_path)
        result.sections = {p: payload.get(p) for p in parents}
        return _finish(result)
    finally:
        cache.release_inflight(user_id, FETCH_LOCK, db_path=db_path)


def _gather_stale(user_id: int, parents: list[str], db_path: str) -> dict[str, Any]:
    """Collect stale-but-present cache rows for the requested parents, for
    API-down degradation. Returns {} if we don't have all of them."""
    out: dict[str, Any] = {}
    for p in parents:
        hit = cache.get_cached_section(user_id, p, allow_stale=True, db_path=db_path)
        if hit is None:
            return {}  # incomplete — don't serve a partial stale picture
        out[p] = hit.data
    return out
