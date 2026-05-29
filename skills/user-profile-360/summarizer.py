"""
summarizer.py — derive a LEAN headline metric set from raw BON sections.

Scope (confirmed 2026-05-29): lean. ~25 headline metrics across identity,
linking, credit, debt, liquidity, income, spending, subscriptions, and chat —
not the full ~80-field dump. Alaska reasons over these; she does not do the
arithmetic herself.

Key principle: BON already pre-computes most of what we need
(plaid_profiles.card_profile / bank_profile, spinwheel *_summary blocks), so
this module mostly PLUCKS pre-computed fields, picks a primary source when
two exist, adds band labels, and filters chat. It does almost no arithmetic
of its own (LLMs are bad at it; pre-computed exacts are trustworthy).

Source-of-truth picks:
  - Credit card debt / utilization: plaid_profiles.card_profile (real-time
    Plaid) PRIMARY, spinwheel_credit_report.credit_card_summary fallback.
  - Credit score: spinwheel_credit_report.profile_details.creditScore (clean
    integer) PRIMARY, credit_report.credit_score fallback.
  - Income / spending: plaid_profiles.bank_profile exacts PRIMARY, then
    plaid_income signals / transaction-category sums as fallback.

Input is the {parent_name: raw_data} mapping from client.fetch_sections
(ideally already passed through redactor.redact_sections — the summarizer never
needs toxic PII anyway, since it reads profile.age not date_of_birth, etc.).
Every accessor is null-safe so partial/dormant users summarize cleanly.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

# Plaid category keys that are NOT discretionary spending — excluded from
# "spending" sums and top-category ranking.
_NON_SPEND_CATEGORIES = {"INCOME", "TRANSFER_IN", "TRANSFER_OUT", "LOAN_PAYMENTS"}


def _get(obj: Any, *path: str, default: Any = None) -> Any:
    """Safe nested lookup. _get(d, 'a', 'b') == d['a']['b'] or default."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def _num(value: Any) -> float | None:
    """Coerce to float if possible (handles MISMO string-typed numbers)."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_band(score: int | None) -> str | None:
    if score is None:
        return None
    if score >= 800:
        return "excellent"
    if score >= 740:
        return "very good"
    if score >= 670:
        return "good"
    if score >= 580:
        return "fair"
    return "poor"


def _util_band(util: float | None) -> str | None:
    if util is None:
        return None
    # util may be a fraction (0.62) or a percent (62). Normalize to fraction.
    u = util / 100.0 if util > 1.5 else util
    if u < 0.10:
        return "excellent (<10%)"
    if u < 0.30:
        return "good (<30%)"
    if u < 0.50:
        return "moderate (30-50%)"
    if u < 0.75:
        return "high (50-75%)"
    return "very high (>75%)"


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        # Handle trailing Z and offset forms.
        cleaned = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except (ValueError, TypeError):
        return None


def _split_chat_turns(recent_turns: list[dict]) -> tuple[list[dict], list[dict]]:
    """Partition turns into (real, proactive) using the heuristic from schema
    discovery: a turn is a REAL user question if it has a non-empty answer OR
    its thread has more than one turn. Single-turn + null-answer = proactive
    system prompt the user never typed."""
    if not recent_turns:
        return [], []
    thread_counts = Counter(t.get("thread_id") for t in recent_turns)
    real, proactive = [], []
    for t in recent_turns:
        ans = t.get("answer")
        is_multi = thread_counts.get(t.get("thread_id"), 0) > 1
        if (ans not in (None, "")) or is_multi:
            real.append(t)
        else:
            proactive.append(t)
    return real, proactive


def summarize(sections: dict[str, Any]) -> dict[str, Any]:
    """Produce the lean headline metric block. Missing/empty sections yield
    None metrics rather than errors."""
    profile = sections.get("profile") or {}
    card = _get(sections, "plaid_profiles", "card_profile", default={}) or {}
    bank = _get(sections, "plaid_profiles", "bank_profile", default={}) or {}
    sw_summary = _get(sections, "spinwheel_credit_report", "credit_card_summary",
                      default={}) or {}
    sw_profile = _get(sections, "spinwheel_credit_report", "profile_details",
                      default={}) or {}

    # ---- Identity ----
    city = profile.get("city")
    state = profile.get("state")
    location = ", ".join([p for p in (city, state) if p]) or None
    identity = {
        "first_name": profile.get("first_name"),
        "age": profile.get("age"),
        "location": location,
        "days_since_signup": _days_since(profile.get("created_at")),
        "platform": profile.get("bon_platform_mobile") or profile.get("bon_platform"),
    }

    # ---- Linking (flags live in profile) ----
    linking = {
        "card_linked": bool(profile.get("is_card_added")),
        "bank_linked": bool(profile.get("is_bank_added")),
        "credit_activated": bool(profile.get("is_credit_activated")),
    }

    # ---- Credit score (spinwheel primary, array fallback) ----
    score = sw_profile.get("creditScore")
    score_source = "spinwheel" if score is not None else None
    if score is None:
        # credit_report.credit_score is an object of unknown shape; try a
        # plain number if present, else leave None.
        cr_score = _get(sections, "credit_report", "credit_score")
        if isinstance(cr_score, (int, float)):
            score = cr_score
            score_source = "array"
    score = int(score) if isinstance(score, (int, float)) else None
    credit = {
        "score": score,
        "score_band": _score_band(score),
        "source": score_source,
    }

    # ---- Debt (Plaid card_profile primary, spinwheel fallback) ----
    debt_balance = _num(card.get("total_cc_balance_exact"))
    debt_source = "plaid" if debt_balance is not None else None
    util = _num(card.get("overall_utilization_exact"))
    limit = _num(card.get("total_cc_limit_exact"))
    num_cards = card.get("num_cards_active")
    if debt_balance is None:
        # Fall back to spinwheel credit_card_summary.
        debt_balance = _num(sw_summary.get("currentOutstandingBalance"))
        util = util if util is not None else _num(sw_summary.get("creditUtilization"))
        num_cards = num_cards if num_cards is not None else sw_summary.get("noOfCreditCards")
        if debt_balance is not None:
            debt_source = "spinwheel"
    debt = {
        "total_cc_balance": debt_balance,
        "total_cc_limit": limit,
        "utilization": util,
        "utilization_band": _util_band(util),
        "weighted_avg_apr": _num(card.get("weighted_avg_apr_exact")),
        "monthly_interest": _num(card.get("monthly_interest_exact")),
        "total_min_payment": _num(card.get("total_min_payment_exact")),
        "num_cards": num_cards,
        "any_overdue": card.get("any_card_overdue"),
        "source": debt_source,
    }

    # ---- Liquidity ----
    cash = _num(bank.get("total_cash_on_hand"))
    if cash is None:
        chk = _num(bank.get("total_checking_balance")) or 0.0
        sav = _num(bank.get("total_savings_balance")) or 0.0
        cash = (chk + sav) if (bank.get("total_checking_balance") is not None
                               or bank.get("total_savings_balance") is not None) else None
    liquidity = {
        "cash_on_hand": cash,
        "low_balance_risk": bank.get("low_balance_risk"),
    }

    # ---- Income (bank_profile exact primary, income_signals fallback) ----
    monthly_income = _num(bank.get("monthly_income_exact"))
    income_source = "plaid_bank" if monthly_income is not None else None
    stability = None
    signals = _get(sections, "plaid_income", "income_signals", default=[]) or []
    active_signals = [s for s in signals if s.get("is_active")]
    if monthly_income is None and active_signals:
        # Sum active sources' net monthly; stability from the largest source.
        nets = [(_num(s.get("net_monthly_income")) or 0.0, s) for s in active_signals]
        monthly_income = sum(n for n, _ in nets) or None
        if monthly_income is not None:
            income_source = "plaid_income_signals"
            _, top = max(nets, key=lambda x: x[0])
            stability = top.get("variability")
    income = {
        "monthly_income": monthly_income,
        "stability": stability,
        "source": income_source,
    }

    # ---- Spending (bank_profile exact primary, category-sum fallback) ----
    by_cat = _get(sections, "plaid_transactions", "by_category_current_month",
                  default={}) or {}
    spend_total = _num(bank.get("monthly_spending_exact"))
    spend_source = "plaid_bank" if spend_total is not None else None
    if spend_total is None and by_cat:
        spend_total = sum(
            (_num(v) or 0.0)
            for k, v in by_cat.items()
            if k not in _NON_SPEND_CATEGORIES and (_num(v) or 0.0) > 0
        )
        spend_source = "category_sum (approx)"
    top_categories = sorted(
        (
            {"category": k, "amount": round(_num(v) or 0.0, 2)}
            for k, v in by_cat.items()
            if k not in _NON_SPEND_CATEGORIES and (_num(v) or 0.0) > 0
        ),
        key=lambda x: x["amount"],
        reverse=True,
    )[:3]
    spending = {
        "current_month_total": round(spend_total, 2) if spend_total is not None else None,
        "top_categories": top_categories,
        "source": spend_source,
    }

    # ---- Subscriptions ----
    subs = sections.get("subscriptions") or []
    active_subs = [s for s in subs if s.get("is_active")]
    subscriptions = {
        "active_count": len(active_subs),
        "monthly_total": round(
            sum(_num(s.get("monthly_cost_normalized")) or 0.0 for s in active_subs), 2
        ),
    }

    # ---- Chat ----
    chat = sections.get("chat") or {}
    recent_turns = chat.get("recent_turns") or []
    real_turns, proactive_turns = _split_chat_turns(recent_turns)
    intent_breakdown = chat.get("intent_breakdown") or {}
    dominant_topics = sorted(
        ((intent, cnt) for intent, cnt in intent_breakdown.items()
         if intent != "proactive_briefing" and isinstance(cnt, (int, float)) and cnt > 0),
        key=lambda x: x[1],
        reverse=True,
    )[:3]
    feedback = chat.get("feedback_summary") or {}
    chat_metrics = {
        "total_threads": chat.get("total_threads"),
        "real_turns": len(real_turns),
        "proactive_turns": len(proactive_turns),
        "dominant_topics": [{"topic": t, "count": c} for t, c in dominant_topics],
        "thumbs_up": feedback.get("thumbs_up"),
        "thumbs_down": feedback.get("thumbs_down"),
    }

    # ---- Meta: which sections had data ----
    present, empty = [], []
    for name, data in sections.items():
        (present if data else empty).append(name)

    return {
        "identity": identity,
        "linking": linking,
        "credit": credit,
        "debt": debt,
        "liquidity": liquidity,
        "income": income,
        "spending": spending,
        "subscriptions": subscriptions,
        "chat": chat_metrics,
        "_meta": {"sections_present": sorted(present), "sections_empty": sorted(empty)},
    }
