"""
Tests for summarizer.py — synthetic sections, deterministic, no real PII.

Runnable standalone:  python3 test_summarizer.py
"""
from __future__ import annotations

import os
import sys

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

import summarizer  # noqa: E402


def _full_sections() -> dict:
    return {
        "profile": {
            "first_name": "Jane", "age": 29, "city": "Austin", "state": "TX",
            "created_at": "2025-11-03T14:22:10+00:00", "bon_platform_mobile": "iOS",
            "is_card_added": True, "is_bank_added": True, "is_credit_activated": True,
        },
        "plaid_profiles": {
            "card_profile": {
                "total_cc_balance_exact": 4180.0, "total_cc_limit_exact": 6800.0,
                "overall_utilization_exact": 0.615, "weighted_avg_apr_exact": 24.99,
                "monthly_interest_exact": 87.0, "total_min_payment_exact": 142.0,
                "num_cards_active": 3, "any_card_overdue": False,
            },
            "bank_profile": {
                "total_cash_on_hand": 5200.0, "low_balance_risk": False,
                "monthly_income_exact": 4200.0, "monthly_spending_exact": 2310.5,
            },
        },
        "spinwheel_credit_report": {
            "profile_details": {"creditScore": 712},
            "credit_card_summary": {"currentOutstandingBalance": 4180.0,
                                    "creditUtilization": 0.61, "noOfCreditCards": 3},
        },
        "subscriptions": [
            {"monthly_cost_normalized": 15.99, "is_active": True},
            {"monthly_cost_normalized": 9.99, "is_active": True},
            {"monthly_cost_normalized": 50.0, "is_active": False},  # excluded
        ],
        "plaid_transactions": {
            "by_category_current_month": {
                "FOOD_AND_DRINK": 420.5, "SHOPPING": 210.0, "TRAVEL": 120.0,
                "INCOME": 4200.0, "TRANSFER_IN": 1000.0,  # excluded from spend
            },
        },
        "chat": {
            "total_threads": 3,
            "intent_breakdown": {"debt_repayment": 40, "budgeting": 25,
                                 "credit_report": 18, "proactive_briefing": 200},
            "feedback_summary": {"total": 5, "thumbs_up": 4, "thumbs_down": 1},
            "recent_turns": [
                # real multi-turn thread (T1)
                {"thread_id": "T1", "question": "q1", "answer": "a1", "created_at": "x"},
                {"thread_id": "T1", "question": "q2", "answer": "a2", "created_at": "x"},
                # proactive single-turn, null answer
                {"thread_id": "P1", "question": "briefing", "answer": None, "created_at": "x"},
                {"thread_id": "P2", "question": "briefing", "answer": None, "created_at": "x"},
            ],
        },
    }


def test_full_user_metrics():
    m = summarizer.summarize(_full_sections())
    assert m["identity"]["first_name"] == "Jane"
    assert m["identity"]["age"] == 29
    assert m["identity"]["location"] == "Austin, TX"
    assert m["identity"]["days_since_signup"] is not None
    assert m["linking"] == {"card_linked": True, "bank_linked": True, "credit_activated": True}
    assert m["credit"]["score"] == 712 and m["credit"]["score_band"] == "good"
    assert m["credit"]["source"] == "spinwheel"
    assert m["debt"]["total_cc_balance"] == 4180.0
    assert m["debt"]["source"] == "plaid"          # card_profile preferred
    assert m["debt"]["utilization"] == 0.615
    assert "high" in m["debt"]["utilization_band"]
    assert m["debt"]["weighted_avg_apr"] == 24.99
    assert m["liquidity"]["cash_on_hand"] == 5200.0
    assert m["income"]["monthly_income"] == 4200.0 and m["income"]["source"] == "plaid_bank"
    assert m["spending"]["current_month_total"] == 2310.5  # bank exact preferred
    # top categories exclude INCOME/TRANSFER
    cats = [c["category"] for c in m["spending"]["top_categories"]]
    assert cats == ["FOOD_AND_DRINK", "SHOPPING", "TRAVEL"]
    assert "INCOME" not in cats and "TRANSFER_IN" not in cats
    assert m["subscriptions"] == {"active_count": 2, "monthly_total": 25.98}
    # chat: 2 real turns (T1 multi), 2 proactive
    assert m["chat"]["real_turns"] == 2 and m["chat"]["proactive_turns"] == 2
    # dominant topics exclude proactive_briefing even though it has the highest count
    topics = [t["topic"] for t in m["chat"]["dominant_topics"]]
    assert topics == ["debt_repayment", "budgeting", "credit_report"]
    assert m["chat"]["thumbs_up"] == 4


def test_debt_falls_back_to_spinwheel():
    s = _full_sections()
    s["plaid_profiles"]["card_profile"] = {}  # no Plaid card data
    m = summarizer.summarize(s)
    assert m["debt"]["total_cc_balance"] == 4180.0
    assert m["debt"]["source"] == "spinwheel"
    assert m["debt"]["num_cards"] == 3  # from noOfCreditCards


def test_income_falls_back_to_signals():
    s = _full_sections()
    s["plaid_profiles"]["bank_profile"].pop("monthly_income_exact")
    s["plaid_income"] = {"income_signals": [
        {"net_monthly_income": 3000.0, "is_active": True, "variability": "low"},
        {"net_monthly_income": 500.0, "is_active": True, "variability": "high"},
        {"net_monthly_income": 9999.0, "is_active": False},  # inactive, excluded
    ]}
    m = summarizer.summarize(s)
    assert m["income"]["monthly_income"] == 3500.0  # sum of active
    assert m["income"]["source"] == "plaid_income_signals"
    assert m["income"]["stability"] == "low"  # from largest active source


def test_spending_falls_back_to_category_sum():
    s = _full_sections()
    s["plaid_profiles"]["bank_profile"].pop("monthly_spending_exact")
    m = summarizer.summarize(s)
    # sum of FOOD(420.5)+SHOPPING(210)+TRAVEL(120) = 750.5, INCOME/TRANSFER excluded
    assert m["spending"]["current_month_total"] == 750.5
    assert "approx" in m["spending"]["source"]


def test_partial_dormant_user_no_crash():
    # Only a sparse profile; everything else empty/missing.
    sparse = {"profile": {"first_name": "New", "age": 22,
                          "is_card_added": False, "is_bank_added": False,
                          "created_at": "2026-05-20T00:00:00+00:00"}}
    m = summarizer.summarize(sparse)
    assert m["credit"]["score"] is None
    assert m["debt"]["total_cc_balance"] is None and m["debt"]["source"] is None
    assert m["income"]["monthly_income"] is None
    assert m["spending"]["current_month_total"] is None
    assert m["subscriptions"]["active_count"] == 0
    assert m["chat"]["real_turns"] == 0
    assert m["linking"]["card_linked"] is False


def test_score_and_util_bands():
    assert summarizer._score_band(810) == "excellent"
    assert summarizer._score_band(710) == "good"
    assert summarizer._score_band(550) == "poor"
    assert summarizer._score_band(None) is None
    assert "good" in summarizer._util_band(0.25)
    # percent form normalizes the same as fraction form
    assert summarizer._util_band(62) == summarizer._util_band(0.62)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
