"""CredGPT Quality Observatory deterministic layer.

Phase 1 does not auto-message users from quality findings. It produces
case-file annotations, internal recommendations, and selected LLM review
requests for high-risk or high-value turns.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .funnel import is_meaningful_credgpt_message


HIGH_INTENT_PATTERNS = [
    r"\bpay\s*(off|down)\b",
    r"\bdebt\b",
    r"\bcredit\s*score\b",
    r"\bapr\b",
    r"\binterest\b",
    r"\bbudget\b",
    r"\bautopay\b",
    r"\bcard\b",
    r"\bbank\b",
    r"\bloan\b",
    r"\bmortgage\b",
    r"\brent\b",
]

UNSAFE_PATTERNS = [
    r"\bguarantee(d)?\b.*\b(score|approval|loan|credit)\b",
    r"\bignore\b.*\bpayment\b",
    r"\bhide\b.*\bdebt\b",
    r"\bfake\b.*\b(income|statement|document)\b",
    r"\bnot\s+legal\s+advice\b",
]

GROUNDING_TERMS = {
    "score",
    "balance",
    "utilization",
    "apr",
    "minimum",
    "payment",
    "income",
    "spend",
    "card",
    "bank",
    "account",
}


@dataclass
class QualityReview:
    review_id: str
    quality_state: str
    deterministic_flags: list[str]
    rubric_scores: dict[str, float]
    needs_llm_review: bool
    llm_review_status: str
    pmf_usefulness_score: float
    internal_recommendations: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "quality_state": self.quality_state,
            "deterministic_flags": self.deterministic_flags,
            "rubric_scores": self.rubric_scores,
            "needs_llm_review": self.needs_llm_review,
            "llm_review_status": self.llm_review_status,
            "pmf_usefulness_score": self.pmf_usefulness_score,
            "internal_recommendations": self.internal_recommendations,
        }


def review_turn(turn: dict[str, Any]) -> QualityReview:
    """Run deterministic review for one CredGPT turn.

    turn keys: cohort_id, user_key, thread_id, turn_id, question, answer,
    feedback ("good"|"bad"|None), chat_stopped_by_user, dropoff_adjacent,
    post_response_action, user_context_present.
    """
    question = str(turn.get("question") or "")
    answer = str(turn.get("answer") or "")
    feedback = turn.get("feedback")
    stopped = bool(turn.get("chat_stopped_by_user"))
    dropoff = bool(turn.get("dropoff_adjacent"))
    user_context_present = bool(turn.get("user_context_present", True))
    high_intent = _matches_any(question, HIGH_INTENT_PATTERNS) or is_meaningful_credgpt_message(question)

    flags: list[str] = []
    if not answer.strip():
        flags.append("missing_answer")
    if answer and len(answer.strip()) < 80 and high_intent:
        flags.append("thin_answer_for_high_intent_question")
    if stopped:
        flags.append("interrupted_by_user")
    if dropoff:
        flags.append("dropoff_adjacent")
    if feedback == "bad":
        flags.append("bad_feedback")
    if _matches_any(answer, UNSAFE_PATTERNS):
        flags.append("unsafe_or_overconfident_language")
    if high_intent and user_context_present and not _has_grounding(answer):
        flags.append("low_data_grounding_for_personal_finance")
    if high_intent and not _has_next_step(answer):
        flags.append("missing_clear_next_step")

    scores = _rubric_scores(question, answer, flags, high_intent, user_context_present)
    pmf_usefulness = round(
        (
            scores["usefulness_actionability"]
            + scores["personalization"]
            + scores["data_grounding"]
            + scores["next_step_quality"]
        )
        / 4,
        3,
    )
    quality_state = "ok"
    if "unsafe_or_overconfident_language" in flags:
        quality_state = "unsafe"
    elif "low_data_grounding_for_personal_finance" in flags:
        quality_state = "hallucination_risk"
    elif flags:
        quality_state = "weak"
    if not answer.strip():
        quality_state = "unavailable"

    needs_llm_review = bool(
        flags
        or high_intent
        or feedback == "bad"
        or stopped
        or dropoff
    )
    recommendations = _recommendations(flags, quality_state)
    return QualityReview(
        review_id=_review_id(turn),
        quality_state=quality_state,
        deterministic_flags=flags,
        rubric_scores=scores,
        needs_llm_review=needs_llm_review,
        llm_review_status="pending" if needs_llm_review else "not_needed",
        pmf_usefulness_score=pmf_usefulness,
        internal_recommendations=recommendations,
    )


def cluster_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create lightweight recurring issue clusters from review rows/dicts."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for review in reviews:
        flags = review.get("deterministic_flags") or review.get("deterministic_flags_json") or []
        if isinstance(flags, str):
            continue
        for flag in flags:
            buckets.setdefault(_cluster_type(flag), []).append(review)

    clusters: list[dict[str, Any]] = []
    for cluster_type, items in sorted(buckets.items()):
        if not items:
            continue
        severity = "P1" if cluster_type in {"unsafe_advice", "hallucination_risk"} else "P2"
        review_ids = [item.get("review_id") for item in items if item.get("review_id")]
        title = _cluster_title(cluster_type)
        clusters.append(
            {
                "cluster_id": _stable_id("cqcl", cluster_type, ",".join(sorted(review_ids))),
                "cluster_type": cluster_type,
                "title": title,
                "description": f"{len(items)} CredGPT turn(s) share this issue.",
                "severity": severity,
                "review_ids": review_ids,
                "evidence": {"count": len(items), "sample_review_ids": review_ids[:5]},
            }
        )
    return clusters


def _rubric_scores(
    question: str,
    answer: str,
    flags: list[str],
    high_intent: bool,
    user_context_present: bool,
) -> dict[str, float]:
    base = {
        "correctness": 0.8,
        "data_grounding": 0.8,
        "personalization": 0.75,
        "usefulness_actionability": 0.8,
        "clarity": 0.8,
        "empathy_trust": 0.75,
        "next_step_quality": 0.8,
        "hallucination_unsafe_advice_risk": 0.9,
        "pmf_usefulness": 0.8,
    }
    if not answer.strip():
        return {key: 0.0 for key in base}
    if "thin_answer_for_high_intent_question" in flags:
        base["usefulness_actionability"] = 0.45
        base["pmf_usefulness"] = 0.45
    if "low_data_grounding_for_personal_finance" in flags:
        base["data_grounding"] = 0.35
        base["personalization"] = 0.35
        base["hallucination_unsafe_advice_risk"] = 0.45
    if "missing_clear_next_step" in flags:
        base["next_step_quality"] = 0.35
        base["usefulness_actionability"] = min(base["usefulness_actionability"], 0.5)
    if "unsafe_or_overconfident_language" in flags:
        base["correctness"] = 0.2
        base["hallucination_unsafe_advice_risk"] = 0.1
    if high_intent and user_context_present and _has_grounding(answer):
        base["data_grounding"] = max(base["data_grounding"], 0.85)
        base["personalization"] = max(base["personalization"], 0.8)
    if not question.strip():
        base["clarity"] = min(base["clarity"], 0.6)
    return {key: round(value, 3) for key, value in base.items()}


def _recommendations(flags: list[str], quality_state: str) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    if not flags and quality_state == "ok":
        return recommendations
    if "low_data_grounding_for_personal_finance" in flags:
        recommendations.append(
            {
                "type": "model_prompt",
                "title": "Improve response grounding",
                "description": "Require CredGPT to cite the user's relevant score, balance, utilization, APR, or account context when answering high-intent financial questions.",
            }
        )
    if "missing_clear_next_step" in flags:
        recommendations.append(
            {
                "type": "product_model",
                "title": "Add concrete next step",
                "description": "Responses should end with one specific action or decision path.",
            }
        )
    if "unsafe_or_overconfident_language" in flags:
        recommendations.append(
            {
                "type": "safety",
                "title": "Review unsafe or overconfident advice",
                "description": "Route this turn for human/model safety review before changing user-facing behavior.",
            }
        )
    if "bad_feedback" in flags:
        recommendations.append(
            {
                "type": "research",
                "title": "Inspect bad-feedback turn",
                "description": "Use the case file to understand whether the bad rating came from tone, correctness, missing context, or product friction.",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "type": "quality_review",
                "title": "Review flagged CredGPT turn",
                "description": "Inspect the full turn and post-response behavior before assigning product/model work.",
            }
        )
    return recommendations


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _has_grounding(answer: str) -> bool:
    lowered = answer.lower()
    has_number = bool(re.search(r"[$]?\d+([,.]\d+)?%?", lowered))
    has_term = any(term in lowered for term in GROUNDING_TERMS)
    return has_number and has_term


def _has_next_step(answer: str) -> bool:
    lowered = answer.lower()
    return any(
        phrase in lowered
        for phrase in (
            "next step",
            "start by",
            "you should",
            "i recommend",
            "set up",
            "pay",
            "link",
            "open",
            "tap",
        )
    )


def _cluster_type(flag: str) -> str:
    mapping = {
        "unsafe_or_overconfident_language": "unsafe_advice",
        "low_data_grounding_for_personal_finance": "data_grounding",
        "thin_answer_for_high_intent_question": "usefulness",
        "missing_clear_next_step": "next_step_quality",
        "bad_feedback": "pmf_usefulness",
        "interrupted_by_user": "clarity",
        "dropoff_adjacent": "pmf_usefulness",
        "missing_answer": "instrumentation_gap",
    }
    return mapping.get(flag, "pmf_usefulness")


def _cluster_title(cluster_type: str) -> str:
    return {
        "unsafe_advice": "Unsafe or overconfident advice risk",
        "data_grounding": "Weak grounding in user financial data",
        "usefulness": "Thin answers to high-intent questions",
        "next_step_quality": "Missing clear next step",
        "pmf_usefulness": "Low PMF usefulness signal",
        "clarity": "Clarity or interruption issue",
        "instrumentation_gap": "Missing answer or instrumentation gap",
    }.get(cluster_type, "CredGPT quality issue")


def _review_id(turn: dict[str, Any]) -> str:
    return _stable_id(
        "cqr",
        str(turn.get("cohort_id") or ""),
        str(turn.get("user_key") or ""),
        str(turn.get("thread_id") or ""),
        str(turn.get("turn_id") or ""),
        str(turn.get("question") or "")[:100],
    )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
