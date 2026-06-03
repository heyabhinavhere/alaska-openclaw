"""Tests for the six PMF success-metric computation (lean scope) and the chat
meaningful-message over-count fix. Pure functions — no live API, no DB."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.collectors import user360  # noqa: E402
from pmf_os.collectors.user360 import (  # noqa: E402
    _active_days,
    _financial_actions,
    _meaningful_chat_stats,
    _real_chat_turns,
)
from pmf_os.funnel import compute_pmf_success_metrics, evaluate_funnel  # noqa: E402


# ---- compute_pmf_success_metrics -------------------------------------------

def test_activation_depth_confirmed_paths_and_no_candidate_tier():
    # >=2 meaningful threads -> confirmed
    assert compute_pmf_success_metrics(
        {"meaningful_threads": 2, "meaningful_credgpt_messages": 2}
    ).get("activation_depth") == "confirmed"
    # >=5 meaningful messages -> confirmed
    assert compute_pmf_success_metrics(
        {"meaningful_threads": 1, "meaningful_credgpt_messages": 5}
    ).get("activation_depth") == "confirmed"
    # exactly the activated_user gate (3 msgs, 1 thread) -> NOT set: no candidate
    # tier, so activation_depth can't collapse activated_user into activated_saver.
    assert "activation_depth" not in compute_pmf_success_metrics(
        {"meaningful_threads": 1, "meaningful_credgpt_messages": 3}
    )


def test_repeat_engagement_thresholds():
    assert compute_pmf_success_metrics(
        {"active_days": ["2026-06-11", "2026-06-12", "2026-06-13"]}
    ).get("repeat_engagement") == "confirmed"
    assert compute_pmf_success_metrics(
        {"active_days": ["2026-06-11", "2026-06-12"]}
    ).get("repeat_engagement") == "candidate"
    assert "repeat_engagement" not in compute_pmf_success_metrics({"active_days": ["2026-06-11"]})
    # int form is also accepted
    assert compute_pmf_success_metrics({"active_days": 3}).get("repeat_engagement") == "confirmed"


def test_financial_action_confirmed_beats_candidate():
    mixed = [
        {"type": "budget_plan:plaid_prefill", "level": "candidate"},
        {"type": "task_completed:call_creditor", "level": "confirmed"},
    ]
    assert compute_pmf_success_metrics({"financial_actions": mixed}).get("financial_action") == "confirmed"
    only_candidate = [{"type": "active_budget", "level": "candidate"}]
    assert compute_pmf_success_metrics({"financial_actions": only_candidate}).get("financial_action") == "candidate"
    assert "financial_action" not in compute_pmf_success_metrics({"financial_actions": []})


def test_linked_and_deferred_metrics():
    assert compute_pmf_success_metrics({"card_linked": True}).get("linked_financial_context") == "confirmed"
    assert compute_pmf_success_metrics({"bank_linked": True}).get("linked_financial_context") == "confirmed"
    # the two un-sourced metrics are NEVER asserted, even with strong other signals
    m = compute_pmf_success_metrics(
        {"card_linked": True, "meaningful_threads": 3, "active_days": 5,
         "financial_actions": [{"level": "confirmed"}]}
    )
    assert "qualitative_positive_signal" not in m
    assert "retained_value" not in m


# ---- chat meaningful-message over-count fix --------------------------------

def test_null_answer_mega_thread_does_not_inflate_activation():
    # Mirrors user 2762: one huge thread of substantive questions but ALL answers
    # null (proactive / pre-backfill). _real_chat_turns keeps them (multi-turn),
    # but the meaningful count must be 0 — none is a real two-way exchange.
    mega = [
        {"thread_id": "t1", "question": "how do i lower my credit card utilization",
         "answer": None, "created_at": "2026-06-11T10:00:00Z"}
        for _ in range(80)
    ]
    real = _real_chat_turns(mega)
    assert len(real) == 80  # still "real" for observatory ingestion
    count, threads = _meaningful_chat_stats(real)
    assert count == 0 and threads == 0
    assert "activation_depth" not in compute_pmf_success_metrics(
        {"meaningful_credgpt_messages": count, "meaningful_threads": threads}
    )


def test_answered_substantive_turns_count_across_threads():
    turns = [
        {"thread_id": "t1", "question": "how should i pay down my credit card debt",
         "answer": "a", "created_at": "2026-06-11T10:00:00Z"},
        {"thread_id": "t1", "question": "hi", "answer": "hello",
         "created_at": "2026-06-11T10:01:00Z"},  # greeting -> filtered out
        {"thread_id": "t2", "question": "what is my apr on my card balance",
         "answer": "b", "created_at": "2026-06-12T09:00:00Z"},
    ]
    count, threads = _meaningful_chat_stats(turns)
    assert count == 2 and threads == 2  # two substantive answered turns, two threads
    assert compute_pmf_success_metrics(
        {"meaningful_credgpt_messages": count, "meaningful_threads": threads}
    ).get("activation_depth") == "confirmed"  # >=2 threads


def test_active_days_distinct_calendar_days():
    turns = [
        {"created_at": "2026-06-11T10:00:00Z"},
        {"created_at": "2026-06-11T22:00:00Z"},
        {"created_at": "2026-06-13T09:00:00Z"},
    ]
    assert _active_days(turns) == ["2026-06-11", "2026-06-13"]


# ---- financial_actions extraction ------------------------------------------

def test_financial_actions_money_task_vs_general_and_incomplete():
    payload = {"tasks": {"completed": [
        {"task_type": "call_creditor", "completed_at": "2026-06-12T00:00:00Z"},
        {"task_type": "general", "completed_at": "2026-06-12T00:00:00Z"},
        {"task_type": "cancel_subscription", "completed_at": None},  # not completed -> ignored
    ]}}
    levels = {a["type"]: a["level"] for a in _financial_actions(payload)}
    assert levels.get("task_completed:call_creditor") == "confirmed"
    assert levels.get("task_completed:general") == "candidate"
    assert "task_completed:cancel_subscription" not in levels


def test_financial_actions_budget_source_and_checkin():
    assert any(a["type"] == "budget_plan:manual" and a["level"] == "confirmed"
               for a in _financial_actions({"budgeting": {"budget_plan": {"source": "manual"}}}))
    assert any(a["type"] == "budget_plan:credgpt" and a["level"] == "confirmed"
               for a in _financial_actions({"budgeting": {"budget_plan": {"source": "credgpt"}}}))
    # system auto-seed -> candidate (not a user action)
    assert _financial_actions({"budgeting": {"budget_plan": {"source": "plaid_prefill"}}})[0]["level"] == "candidate"
    # a check-in is a user action -> confirmed
    assert any(a["type"] == "budget_checkin" and a["level"] == "confirmed"
               for a in _financial_actions({"budgeting": {"checkin_history": [{"checkin_week": "2026-06-08"}]}}))
    # active_budget only (no plan, no checkin) -> candidate
    assert _financial_actions({"budgeting": {"active_budget": {"id": 1}}})[0]["type"] == "active_budget"


# ---- end-to-end: enrich -> funnel reaches activated_saver ------------------

def _fake_summary(payload):
    profile = payload.get("profile") or {}
    return {
        "credit": {"score": 700},
        "linking": {
            "card_linked": bool(profile.get("is_card_added")),
            "bank_linked": bool(profile.get("is_bank_added")),
            "credit_activated": bool(profile.get("is_credit_activated")),
        },
        "identity": {}, "debt": {}, "liquidity": {}, "income": {}, "spending": {}, "subscriptions": {},
    }


def test_enrich_to_funnel_activated_saver_computed():
    # Same-day turns so repeat_engagement / likely_lover don't trigger — we want
    # the run to land exactly on activated_saver (computed) via 3 confirmed metrics.
    payload = {
        "user_id": 4242,
        "profile": {"is_card_added": True, "is_bank_added": False, "is_credit_activated": True},
        "chat": {"recent_turns": [
            {"thread_id": "t1", "question": "how should i pay down my credit card debt",
             "answer": "x", "created_at": "2026-06-11T10:00:00Z"},
            {"thread_id": "t2", "question": "what apr am i paying on my card balance",
             "answer": "y", "created_at": "2026-06-11T12:00:00Z"},
        ]},
        "tasks": {"completed": [{"task_type": "call_creditor", "completed_at": "2026-06-11T13:00:00Z"}]},
    }
    enriched = user360.enrich_facts(payload, summarize_fn=_fake_summary)
    metrics = enriched["daily_facts"]["pmf_success_metrics"]
    assert metrics.get("activation_depth") == "confirmed"        # 2 meaningful threads
    assert metrics.get("linked_financial_context") == "confirmed"  # card linked
    assert metrics.get("financial_action") == "confirmed"        # completed money task
    assert "repeat_engagement" not in metrics                    # single day

    result = evaluate_funnel(enriched["daily_facts"])
    assert result.stage == "activated_saver"
    assert result.activated_saver_state == "computed"


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
