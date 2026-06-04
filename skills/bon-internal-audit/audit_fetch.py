"""audit_fetch — get one user's 360 profile, redact toxic PII, surface the
reliable flat aggregates the audit reasoning starts from.

This is a THIN, VENDORED client. It deliberately does NOT import the V4
user-profile-360 skill or the V5 lib/pmf_os collector, so the audit cannot be
broken by changes those parallel workstreams make. It reuses only their
*knowledge*: the endpoint shape, the X-Admin-Key auth, and the redaction
contract from skills/user-profile-360/redactor.py.

Live fetch only happens when BON_API_BASE_URL + BON_ADMIN_API_KEY are present
AND the caller passes a real http_request (the CLI gates this behind --live).
Tests inject a fake http_request and never touch the network.
"""
from __future__ import annotations

import json
import os
from typing import Callable, Optional, Tuple

import audit_compute as C

# --- redaction contract (mirrors skills/user-profile-360/redactor.py) --------
_ALWAYS_DROP_KEYS = {
    "@_SSN", "ssn", "SSN", "social_security_number", "ssn_last4",
    "@_BirthDate", "date_of_birth", "dateOfBirth", "dob", "birth_date",
}
# Street-address blocks: drop entirely (coarse city/state live elsewhere on profile).
_ADDRESS_DROP_KEYS = {"_RESIDENCE", "addresses", "address"}
# Account identifiers: mask to last-4 (keep useful context, drop the full PAN).
_ACCOUNT_ID_KEYS = {"@_AccountIdentifier", "account_number", "accountNumber"}
_PHONE_KEYS = {"mobile_no", "phone_number", "phone"}

HTTP_TIMEOUT_SECONDS = 25


def validate_user_id(raw) -> Tuple[bool, Optional[int], Optional[str]]:
    """BON user_ids are positive integers (the admin API resolves them as int).
    Returns (ok, user_id_int, error_message)."""
    if raw is None:
        return False, None, "user_id is required"
    s = str(raw).strip()
    if not s:
        return False, None, "user_id is empty"
    if not s.isdigit():
        return False, None, "user_id must be a positive integer, got %r" % (raw,)
    val = int(s)
    if val <= 0:
        return False, None, "user_id must be greater than zero"
    return True, val, None


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _live_http(method: str, url: str, headers=None, timeout: int = HTTP_TIMEOUT_SECONDS):
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:  # 4xx/5xx with a body
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b""
    except Exception as e:  # URLError, timeout, DNS, etc. -> transport failure
        return 0, str(e).encode("utf-8", "replace")


def fetch_profile(
    user_id,
    *,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    http_request: Optional[Callable] = None,
    timeout: int = HTTP_TIMEOUT_SECONDS,
    max_retries: int = 1,
) -> dict:
    """GET {base}/api/admin/users/{id}/profile with X-Admin-Key.

    Returns {"status": ..., "payload": dict|None, "detail": str, "http_status": int}
    status in: ok | not_found | auth_error | api_error | identity_mismatch | invalid
    """
    base_url = base_url if base_url is not None else os.environ.get("BON_API_BASE_URL")
    api_key = api_key if api_key is not None else os.environ.get("BON_ADMIN_API_KEY")
    http_request = http_request or _live_http

    if not base_url or not api_key:
        return {"status": "invalid", "payload": None,
                "detail": "BON_API_BASE_URL and BON_ADMIN_API_KEY must be set", "http_status": 0}

    ok, uid, err = validate_user_id(user_id)
    if not ok:
        return {"status": "invalid", "payload": None, "detail": err, "http_status": 0}

    url = base_url.rstrip("/") + "/api/admin/users/%d/profile" % uid
    headers = {"X-Admin-Key": api_key, "Accept": "application/json"}

    attempt = 0
    while True:
        status, body = http_request("GET", url, headers, timeout)
        retryable = status == 0 or 500 <= status <= 599
        if retryable and attempt < max_retries:
            attempt += 1
            continue
        break

    if status == 200:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return {"status": "api_error", "payload": None,
                    "detail": "profile returned non-JSON", "http_status": 200}
        resp_id = payload.get("user_id")
        if resp_id is not None and str(resp_id) != str(uid):
            return {"status": "identity_mismatch", "payload": None,
                    "detail": "requested %d but got %r" % (uid, resp_id), "http_status": 200}
        return {"status": "ok", "payload": payload, "detail": "", "http_status": 200}
    if status == 404:
        return {"status": "not_found", "payload": None,
                "detail": "user %d not found" % uid, "http_status": 404}
    if status in (401, 403):
        return {"status": "auth_error", "payload": None,
                "detail": "BON API auth failed (status %d)" % status, "http_status": status}
    return {"status": "api_error", "payload": None,
            "detail": "BON API error (status %d)" % status, "http_status": status}


# --------------------------------------------------------------------------
# Redaction (non-destructive; returns a new structure)
# --------------------------------------------------------------------------

def _mask_tail(value) -> str:
    s = str(value)
    return "****" + s[-4:] if len(s) >= 4 else "****"


def redact(obj):
    """Deep-strip SSN + full DOB + street address; mask account numbers and
    phones to last-4. Defense-in-depth: applies wherever the keys appear, so a
    schema change that moves SSN somewhere new is still caught. Input untouched."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _ALWAYS_DROP_KEYS or k in _ADDRESS_DROP_KEYS:
                continue
            if k in _ACCOUNT_ID_KEYS:
                out[k] = _mask_tail(v)
            elif k in _PHONE_KEYS:
                out[k] = _mask_tail(v)
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


# --------------------------------------------------------------------------
# Light, reliable derivation (the deterministic backbone; deep analysis is
# the LLM's job per the skill)
# --------------------------------------------------------------------------

def score_band_for(score: Optional[int]) -> str:
    if score is None:
        return "Poor"
    if score < 620:
        return "Poor"
    if score < 700:
        return "Fair"
    if score < 760:
        return "Good"
    return "Excellent"


def _credit_score(payload: dict) -> Optional[int]:
    hist = payload.get("credit_report_history") or []
    if hist:
        raw = (hist[0].get("credit_score") or {}).get("@_Value")
        try:
            return int(str(raw))
        except (TypeError, ValueError):
            pass
    spin = ((payload.get("spinwheel_credit_report") or {}).get("profile_details") or {})
    sc = spin.get("creditScore")
    try:
        return int(sc) if sc is not None else None
    except (TypeError, ValueError):
        return None


def _nonempty_dict(d) -> bool:
    return isinstance(d, dict) and len(d) > 0


def classify_data_available(payload: dict) -> str:
    profile = payload.get("profile") or {}
    plaid = payload.get("plaid_profiles") or {}
    has_card = bool(profile.get("is_card_added")) or _nonempty_dict(plaid.get("card_profile"))
    has_bank = bool(profile.get("is_bank_added")) or _nonempty_dict(plaid.get("bank_profile"))
    if has_card and has_bank:
        return "CR + Card + Bank"
    if has_card:
        return "CR + Card"
    if has_bank:
        return "CR + Bank"
    return "CR Only"


def summarize_for_audit(payload: dict) -> dict:
    """The clean, redaction-safe starting point Alaska reasons from: identity,
    score, data_available, and the EXACT Plaid aggregates when present. When
    Plaid is absent, APR is estimated from the score band and flagged INFERENCE
    so nothing exact is ever invented."""
    profile = payload.get("profile") or {}
    plaid = payload.get("plaid_profiles") or {}
    card = plaid.get("card_profile") if _nonempty_dict(plaid.get("card_profile")) else None
    bank = plaid.get("bank_profile") if _nonempty_dict(plaid.get("bank_profile")) else None
    score = _credit_score(payload)

    if card and card.get("weighted_avg_apr_exact") is not None:
        apr_confidence = "EXACT"
        estimated_apr_pct = card.get("weighted_avg_apr_exact")
    else:
        apr_confidence = "INFERENCE"
        estimated_apr_pct = C.estimate_apr_from_score_band(score)

    return {
        "first_name": profile.get("first_name"),
        "age": profile.get("age"),
        "city": profile.get("city"),
        "state": profile.get("state"),
        "credit_score": score,
        "score_band": score_band_for(score),
        "data_available": classify_data_available(payload),
        "plaid_card": card,
        "plaid_bank": bank,
        "apr_confidence": apr_confidence,
        "estimated_apr_pct": estimated_apr_pct,
        "income_signals": (payload.get("plaid_income") or {}).get("income_signals") or [],
        "subscriptions": payload.get("subscriptions") or [],
    }
