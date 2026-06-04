"""audit_compute — the fixed financial formulas for the BON Internal Audit.

Every formula here is taken verbatim from the bon-internal-audit skill
("Step 2. Run the math"). They are deterministic and pure so they can be
unit-tested and so the rendered numbers are traceable, not invented.

Python 3.9 compatible (the deployed image and local dev both run 3.9+).
"""
from __future__ import annotations

from typing import List, Optional

# Score-band -> estimated APR midpoint (skill table). Ordered high score first.
_APR_BANDS = [
    (750, 16.0),
    (700, 18.0),
    (660, 20.0),
    (620, 24.0),
    (580, 27.5),
    (0, 29.5),  # 300-579 and any lower/invalid score floors here (worst band)
]

# Confidence tag -> multiplier used in the priority score (skill).
_CONFIDENCE_MULTIPLIERS = {
    "EXACT": 1.0,
    "COMPUTED": 1.0,   # derived from EXACT inputs via a known formula
    "INFERENCE": 0.7,
    "ASSUMPTION": 0.5,
}

_REVOLVING_TYPES = {"CC", "BNPL"}  # accounts that carry a credit limit / utilization


def estimate_apr_from_score_band(score: Optional[int]) -> float:
    """Estimated APR midpoint for a credit score. Floors to the worst band for
    missing or sub-table scores so we never fabricate a flattering rate."""
    if score is None:
        return 29.5
    for floor, apr in _APR_BANDS:
        if score >= floor:
            return apr
    return 29.5


def monthly_interest(balance: float, apr_pct: float) -> float:
    """balance * APR / 12."""
    return round(balance * (apr_pct / 100.0) / 12.0, 2)


def utilization_pct(balance: float, limit: Optional[float]) -> Optional[float]:
    """balance / limit * 100. Returns None when the limit is missing or zero
    (skill: 'limit not reported' -> skip per-card utilization, never invent)."""
    if not limit:  # None or 0
        return None
    return round(balance / limit * 100.0, 2)


def utilization_severity(util_pct: float) -> str:
    """skill: <30 good, 30-49 moderate, 50-74 significant, 75+ severe."""
    if util_pct < 30:
        return "good"
    if util_pct < 50:
        return "moderate"
    if util_pct < 75:
        return "significant"
    return "severe"


def _is_revolving(account: dict) -> bool:
    return account.get("type") in _REVOLVING_TYPES and account.get("limit")


def overall_utilization(accounts: List[dict]) -> dict:
    """Two views (skill reports both):
    - overall_pct: sum(balances) / sum(limits) across all open revolving accounts.
    - cards_with_balance_pct: same but only over cards that carry a balance.
    Accounts without a limit are excluded (cannot compute), never invented."""
    rev = [a for a in accounts if _is_revolving(a)]
    total_bal = sum(a.get("balance", 0) for a in rev)
    total_lim = sum(a.get("limit", 0) for a in rev)
    with_bal = [a for a in rev if a.get("balance", 0) > 0]
    wb_bal = sum(a.get("balance", 0) for a in with_bal)
    wb_lim = sum(a.get("limit", 0) for a in with_bal)
    return {
        "overall_pct": round(total_bal / total_lim * 100.0, 2) if total_lim else None,
        "cards_with_balance_pct": round(wb_bal / wb_lim * 100.0, 2) if wb_lim else None,
    }


def confidence_multiplier_for(tag: str) -> float:
    """Map a confidence tag to its priority multiplier. Unknown -> 0.5 (most
    conservative), so an untagged claim can never inflate a priority score."""
    return _CONFIDENCE_MULTIPLIERS.get(str(tag).upper(), 0.5)


def priority_score(yearly_savings: float, confidence_multiplier: float, effort_score: int) -> float:
    """(yearly_savings * confidence_multiplier) / effort_score (skill)."""
    if not effort_score:
        raise ValueError("effort_score must be 1, 2, or 3 (never zero)")
    return round(yearly_savings * confidence_multiplier / effort_score, 2)


def rank_opportunities(opportunities: List[dict]) -> List[dict]:
    """Compute priority_score for each opportunity, sort descending, assign 1-based
    rank. Lead with the highest priority score, NOT the biggest yearly dollar
    (skill overrides the template here). Returns new dicts; inputs untouched."""
    out = []
    for opp in opportunities:
        o = dict(opp)
        o["priority_score"] = priority_score(
            o.get("yearly_savings", 0),
            o.get("confidence_multiplier", 0.5),
            o.get("effort_score", 1),
        )
        out.append(o)
    out.sort(key=lambda o: o["priority_score"], reverse=True)
    for i, o in enumerate(out, start=1):
        o["rank"] = i
    return out


def collections_monthly_cost(total_cc_debt: float, apr_delta_pct: float) -> float:
    """Monthly cost of carrying a collection: total CC debt * APR delta / 12
    (skill: each active collection raises revolving APR ~2-5pp)."""
    return round(total_cc_debt * (apr_delta_pct / 100.0) / 12.0, 2)
