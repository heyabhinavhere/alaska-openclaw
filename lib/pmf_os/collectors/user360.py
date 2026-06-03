"""User 360 enrichment collector for PMF Cohort OS.

Resolves a cohort user's BON `user_id` and pulls their full profile from the BON
admin API — the same endpoints the user-profile-360 skill uses:
  GET /api/admin/users/search?email=|phone=|name=   (identity resolution)
  GET /api/admin/users/{user_id}/profile             (whole 360 payload)
auth via the `X-Admin-Key` header, base URL from `BON_API_BASE_URL`.

Derived funnel facts REUSE the skill's pure, tested `summarizer.summarize()`
(loaded by file path, no side effects) so we don't re-implement the gnarly bits:
Array-canonical MISMO credit-score parsing, Plaid `card_profile` aggregation, and
the proactive-vs-real chat-turn split. HTTP is injectable so tests use fixtures.

Architecture note: importing the skill's `summarizer.py` by file path is a
deliberate, documented coupling. The clean long-term move is to promote that pure
module into `lib/` shared and have both the skill and this collector import it —
deferred to avoid touching the V4 skill during the live test.
"""

from __future__ import annotations

import importlib.util
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ..funnel import is_meaningful_credgpt_message
from ..model import minimize_secrets

BON_API_BASE_URL = os.environ.get("BON_API_BASE_URL", "").rstrip("/")
BON_ADMIN_API_KEY = os.environ.get("BON_ADMIN_API_KEY", "")
HTTP_TIMEOUT_SECONDS = 25
HTTP_RETRIES = 1

# Value actions we can derive directly from the BON profile linking flags.
_VALUE_ACTION_FLAGS = {
    "is_card_added": "card_link_success",
    "is_bank_added": "bank_link_success",
    "is_paydown_schedule_created": "paydown_plan_created",
}

# (query_type, value) -> (status_code, body_bytes)
SearchFetcher = Callable[[str, str], "tuple[int, bytes]"]
# (user_id) -> (status_code, body_bytes)
ProfileFetcher = Callable[[int], "tuple[int, bytes]"]
# raw /profile payload -> derived summary dict
SummarizeFn = Callable[[dict], dict]


class User360ConfigError(RuntimeError):
    """Raised when BON admin API credentials are missing."""


def is_configured() -> bool:
    return bool(BON_API_BASE_URL and BON_ADMIN_API_KEY)


def _http_get(path: str, params: dict | None = None) -> "tuple[int, bytes]":
    if not is_configured():
        raise User360ConfigError("BON_API_BASE_URL and BON_ADMIN_API_KEY must be set")
    url = f"{BON_API_BASE_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last_exc: Exception | None = None
    for attempt in range(HTTP_RETRIES + 1):
        request = urllib.request.Request(url, headers={"X-Admin-Key": BON_ADMIN_API_KEY})
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            if exc.code >= 500 and attempt < HTTP_RETRIES:
                last_exc = exc
                time.sleep(0.5 * (attempt + 1))
                continue
            return exc.code, body
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt < HTTP_RETRIES:
                time.sleep(0.5 * (attempt + 1))
                continue
    return 0, str(last_exc or "transport error").encode("utf-8")


def _default_search_fetcher(query_type: str, value: str) -> "tuple[int, bytes]":
    return _http_get("/api/admin/users/search", {query_type: value})


def _default_profile_fetcher(user_id: int) -> "tuple[int, bytes]":
    return _http_get(f"/api/admin/users/{user_id}/profile")


def _load_summarize() -> SummarizeFn:
    """Load the user-profile-360 skill's pure summarizer by file path.

    No sys.path pollution and no intra-skill imports are triggered (summarizer.py
    is stdlib-only), so this reuses the derivation without dragging the skill's
    cache/audit/client side effects.
    """
    candidates = [
        os.environ.get("USER360_SKILL_DIR"),
        "/data/skills/user-profile-360",
        str(Path(__file__).resolve().parents[3] / "skills" / "user-profile-360"),
    ]
    for directory in candidates:
        if not directory:
            continue
        path = os.path.join(directory, "summarizer.py")
        if os.path.isfile(path):
            spec = importlib.util.spec_from_file_location("pmf_up360_summarizer", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            return module.summarize
    raise ImportError("user-profile-360 summarizer.py not found; set USER360_SKILL_DIR")


def resolve_bon_user_id(
    registry_row: dict[str, Any],
    *,
    search_fetcher: SearchFetcher | None = None,
) -> dict[str, Any]:
    """Resolve a registry row to a BON user_id.

    Precedence: an already-known bon_user_id, then a search by email, then phone.
    Returns {status, user_id, detail}. status is one of: resolved, multiple,
    not_found, unresolvable (no usable identifier), search_unavailable.
    """
    existing = registry_row.get("bon_user_id")
    if existing:
        try:
            return {"status": "resolved", "user_id": int(existing), "detail": "registry"}
        except (TypeError, ValueError):
            pass

    fetcher = search_fetcher or _default_search_fetcher
    for query_type in ("email", "phone"):
        value = registry_row.get(query_type) or registry_row.get(f"{query_type}_address")
        if query_type == "phone":
            value = registry_row.get("phone_number") or value
        if not value:
            continue
        status, body = fetcher(query_type, str(value))
        if status == 0 or status >= 500:
            return {"status": "search_unavailable", "user_id": None, "detail": f"{query_type} search status {status}"}
        if status != 200:
            continue
        try:
            matches = json.loads(body)
        except json.JSONDecodeError:
            continue
        if not isinstance(matches, list) or not matches:
            continue
        if len(matches) == 1:
            return {"status": "resolved", "user_id": int(matches[0]["user_id"]), "detail": query_type}
        return {"status": "multiple", "user_id": None, "detail": f"{len(matches)} {query_type} matches", "matches": matches}

    return {"status": "unresolvable", "user_id": None, "detail": "no bon_user_id / email / phone to resolve from"}


def fetch_profile(user_id: int, *, profile_fetcher: ProfileFetcher | None = None) -> dict[str, Any]:
    """Fetch the raw /profile payload. Returns {status, payload, detail}."""
    fetcher = profile_fetcher or _default_profile_fetcher
    status, body = fetcher(user_id)
    if status == 404:
        return {"status": "not_found", "payload": None, "detail": f"user {user_id} not found"}
    if status in (401, 403):
        return {"status": "auth_error", "payload": None, "detail": "BON API auth failed"}
    if status != 200:
        return {"status": "api_error", "payload": None, "detail": f"status {status}"}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "api_error", "payload": None, "detail": "non-JSON profile"}
    if payload.get("user_id") not in (None, user_id):
        return {"status": "identity_mismatch", "payload": None, "detail": f"requested {user_id}, got {payload.get('user_id')}"}
    return {"status": "ok", "payload": payload, "detail": "fetched"}


def _real_chat_turns(recent_turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Real user turns only (drop proactive briefings).

    Mirrors the user-profile-360 summarizer heuristic: a turn is a real user
    question if it has a non-empty answer OR its thread has more than one turn;
    single-turn + null-answer turns are system/proactive prompts the user never typed.
    """
    if not recent_turns:
        return []
    counts: dict[Any, int] = {}
    for turn in recent_turns:
        counts[turn.get("thread_id")] = counts.get(turn.get("thread_id"), 0) + 1
    real = []
    for turn in recent_turns:
        answer = turn.get("answer")
        if (answer not in (None, "")) or counts.get(turn.get("thread_id"), 0) > 1:
            real.append(turn)
    return real


def enrich_facts(payload: dict[str, Any], *, summarize_fn: SummarizeFn | None = None) -> dict[str, Any]:
    """Map a raw /profile payload into PMF profile_facts + daily_facts.

    Reuses the skill summarizer for derivation; applies minimize_secrets to the
    financial context so no SSN/routing/address is ever stored and account
    numbers are last-4 only.
    """
    summarize = summarize_fn or _load_summarize()
    summary = summarize(payload)

    credit_score = (summary.get("credit") or {}).get("score")
    linking = summary.get("linking") or {}
    profile = payload.get("profile") or {}
    real_turns = _real_chat_turns(((payload.get("chat") or {}).get("recent_turns")) or [])

    card_linked = bool(linking.get("card_linked"))
    bank_linked = bool(linking.get("bank_linked"))
    onboarding_complete = bool(linking.get("credit_activated")) or bool(credit_score and credit_score > 0)
    value_actions = [action for flag, action in _VALUE_ACTION_FLAGS.items() if profile.get(flag)]
    # Greeting-filtered: only real turns whose question is a substantive financial
    # message count toward activation (matches the funnel's meaningful definition).
    meaningful_messages = sum(1 for turn in real_turns if is_meaningful_credgpt_message(turn.get("question")))

    # Only the clearly-evidenced PMF metric is asserted here; the rest stay for
    # data-calibration (the six-metric mapping is still under review per the plan).
    pmf_success_metrics: dict[str, Any] = {}
    if card_linked or bank_linked:
        pmf_success_metrics["linked_financial_context"] = "confirmed"

    financial_context = minimize_secrets(
        {
            "credit": summary.get("credit"),
            "debt": summary.get("debt"),
            "liquidity": summary.get("liquidity"),
            "income": summary.get("income"),
            "spending": summary.get("spending"),
            "subscriptions": summary.get("subscriptions"),
        }
    )

    profile_facts = {
        "bon_user_id": payload.get("user_id"),
        "credit_score": credit_score,
        "onboarding_complete": onboarding_complete,
        "onboarding_status": "complete" if onboarding_complete else "in_progress",
        "is_card_added": card_linked,
        "is_bank_added": bank_linked,
        "source_ref": f"user360:{payload.get('user_id')}",
    }
    daily_facts = {
        "onboarding_complete": onboarding_complete,
        "credit_score": credit_score,
        "meaningful_credgpt_messages": meaningful_messages,
        "value_actions": value_actions,
        "pmf_success_metrics": pmf_success_metrics,
        "financial_context": financial_context,
        "profile_summary": {"identity": summary.get("identity"), "linking": linking},
    }
    return {"profile_facts": profile_facts, "daily_facts": daily_facts, "summary": summary, "chat_turns": real_turns}
