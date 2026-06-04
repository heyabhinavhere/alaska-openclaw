"""Deterministic PMF Funnel rules for Alaska V5."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .model import (
    ACTIVATED_SAVER_CANDIDATE,
    ACTIVATED_SAVER_COMPUTED,
    Evidence,
    FunnelResult,
    LOW_VALUE_CHAT_PATTERNS,
    MEANINGFUL_CHAT_INTENTS,
    PMF_SUCCESS_METRICS,
    VALUE_ACTION_TYPES,
    higher_stage,
)
from .thresholds import DEFAULT_THRESHOLDS


def is_meaningful_credgpt_message(text: str | None, intent: str | None = None) -> bool:
    """Classify whether a user message should count toward activation.

    This deliberately excludes greetings/logistics and requires either a known
    financial intent or enough substantive language to likely represent a real
    user question.
    """
    if not text:
        return False
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    if normalized in LOW_VALUE_CHAT_PATTERNS:
        return False
    if intent and intent in MEANINGFUL_CHAT_INTENTS:
        return True
    tokens = re.findall(r"[a-z0-9$%]+", normalized)
    financial_terms = {
        "credit",
        "score",
        "card",
        "bank",
        "debt",
        "apr",
        "interest",
        "pay",
        "payment",
        "budget",
        "save",
        "saving",
        "autopay",
        "utilization",
        "balance",
        "income",
        "subscription",
    }
    return len(tokens) >= 5 and bool(financial_terms.intersection(tokens))


def _truthy_count(values: dict[str, Any], wanted_state: str) -> int:
    count = 0
    for key in PMF_SUCCESS_METRICS:
        value = values.get(key)
        if value == wanted_state or (wanted_state == "confirmed" and value is True):
            count += 1
    return count


def compute_pmf_success_metrics(facts: dict[str, Any], *, thresholds: dict[str, int] | None = None) -> dict[str, str]:
    """Map raw signal facts to confirmed/candidate PMF success-metric states.

    Reads ONLY raw signals (greeting-filtered chat exchanges, active days, raw
    user product actions, link flags) — never CredGPT's interpreted layer — so
    Alaska's funnel stays an independent judge of CredGPT. Two metrics have no
    usable data source yet and are intentionally left uncomputed:
      - qualitative_positive_signal: chat thumbs are effectively dead (~1 across
        hundreds of turns) and the API exposes no sentiment field — deferred to
        the P4.1 LLM judge on turn text.
      - retained_value: time-gated; computed later from Alaska's own raw credit/
        savings snapshots over the cohort, not BON's precomputed deltas.

    Expected fact keys: meaningful_credgpt_messages (int), meaningful_threads
    (int), active_days (int|list[YYYY-MM-DD]), financial_actions
    (list[{type, level}]), card_linked/bank_linked (bool).
    """
    t = thresholds or DEFAULT_THRESHOLDS
    metrics: dict[str, str] = {}

    # 1. activation_depth — deep CredGPT use, strictly ABOVE the activated_user
    #    gate. Confirmed-only: a candidate band at the gate would collapse the
    #    activated_user / activated_saver tiers.
    msgs = _as_int(facts.get("meaningful_credgpt_messages")) or 0
    threads = _as_int(facts.get("meaningful_threads")) or 0
    if threads >= t["activation_depth_threads"] or msgs >= t["activation_depth_messages"]:
        metrics["activation_depth"] = "confirmed"

    # 2. repeat_engagement — returned across distinct days.
    active = _active_day_count(facts.get("active_days"))
    if active >= t["repeat_engagement_confirmed_days"]:
        metrics["repeat_engagement"] = "confirmed"
    elif active >= t["repeat_engagement_candidate_days"]:
        metrics["repeat_engagement"] = "candidate"

    # 3. financial_action — a real money/plan action beyond linking.
    financial_actions = facts.get("financial_actions") or []
    if any((action or {}).get("level") == "confirmed" for action in financial_actions):
        metrics["financial_action"] = "confirmed"
    elif financial_actions:
        metrics["financial_action"] = "candidate"

    # 4. linked_financial_context — connected a card or bank.
    if facts.get("card_linked") or facts.get("bank_linked"):
        metrics["linked_financial_context"] = "confirmed"

    return metrics


def evaluate_funnel(
    facts: dict[str, Any],
    *,
    previous_highest_stage: str | None = None,
    thresholds: dict[str, int] | None = None,
) -> FunnelResult:
    """Evaluate one user's current PMF stage, flags, queues, and evidence.

    Expected fact keys are intentionally plain JSON-compatible structures so
    this engine can consume Amplitude/User 360/Customer.io-derived snapshots:

    - onboarding_complete: bool
    - credit_score: int
    - meaningful_credgpt_messages: int
    - high_intent_usable_qas: int
    - value_actions: list[str]
    - failed_link_attempts: list[str]
    - pmf_success_metrics: dict[str, bool|"confirmed"|"candidate"]
    - active_days: int or list[YYYY-MM-DD]
    - inactive_days: int
    - explicit_love_proof: bool
    - negative_signals: list[str]
    """
    t = thresholds or DEFAULT_THRESHOLDS
    evidence: list[Evidence] = []
    flags: list[str] = []
    queues: list[dict[str, Any]] = []

    stage = "signed_up"
    activated_saver_state: str | None = None
    health = "unknown"

    credit_score = _as_int(facts.get("credit_score"))
    onboarding_complete = bool(facts.get("onboarding_complete"))
    is_real_user = onboarding_complete and credit_score is not None and credit_score > 0
    evidence.append(
        Evidence(
            "real_user",
            state="confirmed" if is_real_user else "false",
            confidence=1.0,
            source_system="alaska",
            value={"onboarding_complete": onboarding_complete, "credit_score": credit_score},
        )
    )
    if is_real_user:
        stage = "onboarded_real_user"

    meaningful_messages = _as_int(facts.get("meaningful_credgpt_messages")) or 0
    high_intent_usable_qas = _as_int(facts.get("high_intent_usable_qas")) or 0
    value_actions = set(facts.get("value_actions") or [])
    qualifying_value_actions = sorted(value_actions.intersection(VALUE_ACTION_TYPES))
    activated = is_real_user and (
        meaningful_messages >= t["activation_meaningful_messages"]
        or high_intent_usable_qas >= t["activation_high_intent_qas"]
        or bool(qualifying_value_actions)
    )
    evidence.append(
        Evidence(
            "activated_user",
            state="confirmed" if activated else "false",
            confidence=1.0,
            source_system="alaska",
            value={
                "meaningful_credgpt_messages": meaningful_messages,
                "high_intent_usable_qas": high_intent_usable_qas,
                "qualifying_value_actions": qualifying_value_actions,
            },
        )
    )
    if activated:
        stage = "activated_user"

    failed_link_attempts = list(facts.get("failed_link_attempts") or [])
    if failed_link_attempts:
        flags.append("high_intent")
        queues.append(
            _queue(
                "high_intent",
                "High-intent user hit a linking failure",
                "Failed linking is intent evidence, not activation evidence.",
                "P1",
                {"failed_link_attempts": failed_link_attempts},
            )
        )
        queues.append(
            _queue(
                "plaid_failed",
                "Plaid linking failed",
                "User attempted to link but did not complete successfully.",
                "P1",
                {"failed_link_attempts": failed_link_attempts},
            )
        )

    pmf_metrics = facts.get("pmf_success_metrics") or {}
    computed_metric_count = _truthy_count(pmf_metrics, "confirmed")
    candidate_metric_count = computed_metric_count + _truthy_count(pmf_metrics, "candidate")
    if activated and computed_metric_count >= t["activated_saver_confirmed_metrics"]:
        stage = "activated_saver"
        activated_saver_state = ACTIVATED_SAVER_COMPUTED
    elif activated and candidate_metric_count >= t["activated_saver_candidate_metrics"]:
        stage = "activated_saver"
        activated_saver_state = ACTIVATED_SAVER_CANDIDATE
        flags.append("activated_saver_candidate")
        queues.append(
            _queue(
                "needs_human_review",
                "Activated Saver candidate needs evidence review",
                "Promising PMF metric evidence exists, but instrumentation or review is incomplete.",
                "P2",
                {"pmf_success_metrics": pmf_metrics},
            )
        )
    evidence.append(
        Evidence(
            "activated_saver",
            state="confirmed" if activated_saver_state in {ACTIVATED_SAVER_COMPUTED, ACTIVATED_SAVER_CANDIDATE} else "false",
            confidence=1.0 if activated_saver_state == ACTIVATED_SAVER_COMPUTED else 0.65 if activated_saver_state == ACTIVATED_SAVER_CANDIDATE else 1.0,
            source_system="alaska",
            value={
                "computed_metric_count": computed_metric_count,
                "candidate_metric_count": candidate_metric_count,
                "activated_saver_state": activated_saver_state,
            },
        )
    )

    active_days = _active_day_count(facts.get("active_days"))
    negative_signals = list(facts.get("negative_signals") or [])
    likely_lover = (
        stage == "activated_saver"
        and active_days >= t["likely_lover_active_days"]
        and not negative_signals
    )
    if likely_lover:
        stage = "likely_lover"
        flags.append("potential_lover")
        queues.append(
            _queue(
                "potential_lover",
                "Potential lover needs qualitative follow-up",
                "User has value evidence plus repeated engagement and no strong negative signal.",
                "P1",
                {"active_days": active_days, "activated_saver_state": activated_saver_state},
            )
        )
    evidence.append(
        Evidence(
            "likely_lover",
            state="confirmed" if likely_lover else "false",
            confidence=0.9 if likely_lover else 1.0,
            source_system="alaska",
            value={"active_days": active_days, "negative_signals": negative_signals},
        )
    )

    if bool(facts.get("explicit_love_proof")):
        stage = "confirmed_lover"
        flags.append("confirmed_lover")
        evidence.append(
            Evidence(
                "confirmed_lover",
                state="confirmed",
                confidence=1.0,
                source_system=facts.get("love_proof_source_system") or "manual",
                source_ref=facts.get("love_proof_source_ref"),
                value=facts.get("love_proof"),
            )
        )
    else:
        evidence.append(Evidence("confirmed_lover", state="false", confidence=1.0))

    if facts.get("weak_credgpt_response_count", 0):
        flags.append("weak_credgpt_response")
        queues.append(
            _queue(
                "weak_credgpt_response",
                "Weak CredGPT response needs product/model review",
                "CredGPT quality findings are internal product/model work in Phase 1.",
                "P1",
                {"weak_credgpt_response_count": facts.get("weak_credgpt_response_count")},
            )
        )

    if facts.get("intake_period") and not onboarding_complete:
        flags.append("stuck_onboarding")
        queues.append(
            _queue(
                "stuck_onboarding",
                "Signup user is stuck before onboarding completion",
                "Intake-only queue for signup window and immediate post-signup period.",
                "P1",
                {"furthest_onboarding_step": facts.get("furthest_onboarding_step")},
                intake_only=True,
            )
        )
        furthest = str(facts.get("furthest_onboarding_step") or "").lower()
        if "spin" in furthest or facts.get("spinwheel_failed"):
            queues.append(
                _queue(
                    "spinwheel_stuck",
                    "User appears stuck around Spinwheel",
                    "Spinwheel stuck is intake-only and should be handled during signup/post-signup.",
                    "P1",
                    {"furthest_onboarding_step": facts.get("furthest_onboarding_step")},
                    intake_only=True,
                )
            )

    inactive_days = _as_int(facts.get("inactive_days")) or 0
    if is_real_user and inactive_days >= t["at_risk_inactive_days"] and stage not in {"confirmed_lover", "likely_lover"}:
        health = "at_risk"
        flags.append("at_risk")
        queues.append(
            _queue(
                "at_risk",
                "Real user has gone quiet",
                "User is onboarded but has no recent activity.",
                "P2",
                {"inactive_days": inactive_days},
            )
        )
    elif facts.get("intake_period") and not onboarding_complete:
        health = "stuck"
    elif is_real_user:
        health = "healthy" if stage in {"likely_lover", "confirmed_lover"} else "watch"

    highest_stage = higher_stage(previous_highest_stage, stage)
    confidence = min((item.confidence for item in evidence), default=1.0)
    return FunnelResult(
        stage=stage,
        highest_stage=highest_stage,
        activated_saver_state=activated_saver_state,
        health=health,
        flags=_dedupe(flags),
        queues=queues,
        evidence=evidence,
        confidence=confidence,
    )


def _queue(
    queue_type: str,
    title: str,
    reason: str,
    severity: str,
    evidence: dict[str, Any],
    *,
    intake_only: bool = False,
) -> dict[str, Any]:
    return {
        "queue_type": queue_type,
        "title": title,
        "reason": reason,
        "severity": severity,
        "intake_only": intake_only,
        "evidence": evidence,
    }


def _active_day_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple, set)):
        unique_days = set()
        for item in value:
            if isinstance(item, date):
                unique_days.add(item.isoformat())
            elif isinstance(item, datetime):
                unique_days.add(item.date().isoformat())
            elif isinstance(item, str):
                unique_days.add(item[:10])
        return len(unique_days)
    return 0


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out
