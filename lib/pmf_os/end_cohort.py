"""End-cohort intelligence memo (P7).

The final memo over a cohort: a deterministic aggregation of the whole story —
funnel outcomes + rates, dropoff, CredGPT quality (incl. LLM verdicts), intervention
outcomes, and the six-metric rollup — with an injectable, key-gated LLM narrator on
top. Machines aggregate the facts; the LLM narrates. Aggregate-only (no per-user
PII). Runs after the window. Narration is explicit: with no narrator, the memo is
the facts with `narrative_status='skipped'` — it never silently spends tokens.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from .model import FUNNEL_STAGES, STAGE_RANK, minimize_secrets, now_utc, rollup_pmf_metrics

# (facts dict) -> raw narrative dict
NarratorFn = Callable[[dict[str, Any]], dict[str, Any]]

DEFAULT_NARRATOR_MODEL = "claude-sonnet-4-6"
_PMF_VERDICTS = {"strong", "promising", "weak", "inconclusive"}


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return []
        return [str(v) for v in parsed] if isinstance(parsed, list) else []
    return []


def build_end_cohort_facts(
    *,
    cohort: dict[str, Any],
    users: list[dict[str, Any]],
    quality_reviews: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    interventions: list[dict[str, Any]],
    metric_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Deterministic end-cohort aggregation. Aggregate-only — no per-user PII."""
    total = len(users)

    # Funnel: count by the highest stage each user ever reached (best outcome).
    reached = {stage: 0 for stage in FUNNEL_STAGES}
    saver_states = {"computed": 0, "candidate": 0}
    health_counts: dict[str, int] = {}
    flag_counts: dict[str, int] = {}
    for user in users:
        rank = STAGE_RANK.get(user.get("highest_stage") or user.get("current_stage") or "signed_up", 0)
        for stage in FUNNEL_STAGES:
            if rank >= STAGE_RANK[stage]:
                reached[stage] += 1
        state = user.get("activated_saver_state")
        if state in saver_states:
            saver_states[state] += 1
        health_counts[str(user.get("current_health") or "unknown")] = (
            health_counts.get(str(user.get("current_health") or "unknown"), 0) + 1
        )
        for flag in _as_list(user.get("flags") or user.get("flags_json")):
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    real, activated = reached["onboarded_real_user"], reached["activated_user"]
    savers, likely, confirmed = reached["activated_saver"], reached["likely_lover"], reached["confirmed_lover"]
    funnel = {
        "total_signups": total,
        "reached": reached,
        "real_users": real,
        "activated_users": activated,
        "activated_savers": savers,
        "likely_lovers": likely,
        "confirmed_lovers": confirmed,
        "activated_saver_state": saver_states,
        "rates": {
            "real_user_rate": _rate(real, total),
            "activation_rate": _rate(activated, real),
            "saver_rate": _rate(savers, activated),
            "lover_rate": _rate(likely + confirmed, savers),
        },
        "health_counts": dict(sorted(health_counts.items())),
    }

    dropoff = {
        "signed_up_not_onboarded": max(total - real, 0),
        "onboarded_not_activated": max(real - activated, 0),
        "activated_not_saver": max(activated - savers, 0),
        "at_risk": health_counts.get("at_risk", 0),
        "flags": dict(sorted(flag_counts.items())),
    }

    state_counts: dict[str, int] = {}
    llm_status_counts: dict[str, int] = {}
    needs_llm = llm_unsafe = 0
    usefulness_vals: list[float] = []
    for review in quality_reviews:
        st = str(review.get("quality_state") or "unknown")
        state_counts[st] = state_counts.get(st, 0) + 1
        if review.get("needs_llm_review"):
            needs_llm += 1
        status = str(review.get("llm_review_status") or "not_needed")
        llm_status_counts[status] = llm_status_counts.get(status, 0) + 1
        verdict = review.get("llm_review")
        if isinstance(verdict, dict) and verdict.get("unsafe_advice"):
            llm_unsafe += 1
        score = review.get("pmf_usefulness_score")
        if isinstance(score, (int, float)):
            usefulness_vals.append(float(score))
    credgpt_quality = {
        "total_reviews": len(quality_reviews),
        "by_state": dict(sorted(state_counts.items())),
        "weak_or_worse": sum(v for k, v in state_counts.items() if k not in ("ok", "unknown")),
        "unsafe_or_risk": state_counts.get("unsafe", 0) + state_counts.get("hallucination_risk", 0),
        "needs_llm_review": needs_llm,
        "llm_review_status": dict(sorted(llm_status_counts.items())),
        "llm_flagged_unsafe": llm_unsafe,
        "avg_pmf_usefulness": round(sum(usefulness_vals) / len(usefulness_vals), 3) if usefulness_vals else None,
        "cluster_count": len(clusters),
        "clusters": [
            {"cluster_type": c.get("cluster_type"), "title": c.get("title"), "severity": c.get("severity")}
            for c in sorted(clusters, key=lambda c: (c.get("severity") != "P1", str(c.get("cluster_type") or "")))[:10]
        ],
    }

    status_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    outcome_totals = {"delivered": 0, "opened": 0, "clicked": 0, "converted": 0}
    executed = 0
    for item in interventions:
        status = str(item.get("approval_status") or "draft")
        status_counts[status] = status_counts.get(status, 0) + 1
        action_counts[str(item.get("action_type") or "intervention")] = (
            action_counts.get(str(item.get("action_type") or "intervention"), 0) + 1
        )
        if status == "executed":
            executed += 1
        outcome = item.get("outcome")
        if isinstance(outcome, dict):
            for key in outcome_totals:
                if outcome.get(key):
                    outcome_totals[key] += 1
    interventions_summary = {
        "total": len(interventions),
        "by_status": dict(sorted(status_counts.items())),
        "by_action_type": dict(sorted(action_counts.items())),
        "executed": executed,
        "outcomes": outcome_totals,
    }

    metric_rollup = rollup_pmf_metrics(metric_records)

    return {
        "schema_version": "pmf_end_cohort.v1",
        "generated_at": now_utc(),
        "cohort": minimize_secrets(cohort),
        "funnel": funnel,
        "dropoff": dropoff,
        "credgpt_quality": credgpt_quality,
        "interventions": interventions_summary,
        "pmf_metrics": metric_rollup,
    }


def build_memo_prompt(facts: dict[str, Any]) -> str:
    return (
        "You are writing the end-of-cohort PMF memo for a fintech launch cohort, for "
        "founders. Use ONLY the deterministic facts below (JSON) — never invent numbers. "
        "Respond with ONLY a JSON object: executive_summary (string), what_worked (array of "
        "strings), what_didnt (array of strings), pmf_verdict (object with 'rating' one of "
        "strong|promising|weak|inconclusive and 'reason' string), recommendations (array of "
        "strings).\n\nFACTS:\n" + json.dumps(facts, sort_keys=True)
    )


def normalize_memo(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a narrator's raw output into the stored memo shape (defensive)."""
    raw = raw or {}
    verdict = raw.get("pmf_verdict") if isinstance(raw.get("pmf_verdict"), dict) else {}
    rating = verdict.get("rating")
    return {
        "executive_summary": str(raw.get("executive_summary") or "")[:4000],
        "what_worked": [str(x) for x in (raw.get("what_worked") or [])][:12],
        "what_didnt": [str(x) for x in (raw.get("what_didnt") or [])][:12],
        "pmf_verdict": {
            "rating": rating if rating in _PMF_VERDICTS else "inconclusive",
            "reason": str(verdict.get("reason") or "")[:1000],
        },
        "recommendations": [str(x) for x in (raw.get("recommendations") or [])][:12],
    }


def _live_narrator(facts: dict[str, Any], *, model: str | None = None, timeout: float = 90.0) -> dict[str, Any]:
    """Thin live adapter over the shared LLM client. Requires ANTHROPIC_API_KEY."""
    from .llm import anthropic_complete, extract_json

    text = anthropic_complete(
        build_memo_prompt(facts),
        model=model or os.environ.get("PMF_MEMO_MODEL") or DEFAULT_NARRATOR_MODEL,
        max_tokens=1500,
        timeout=timeout,
    )
    return normalize_memo(extract_json(text))


def default_narrator() -> NarratorFn | None:
    """The live narrator when ANTHROPIC_API_KEY is set, else None (memo -> skipped)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return _live_narrator


def generate_end_cohort_memo(facts: dict[str, Any], *, narrator: NarratorFn | None = None) -> dict[str, Any]:
    """Attach a narrative to the facts. Narration is explicit: narrator=None ->
    'skipped' (never auto-narrates). A narrator error -> 'failed' (facts kept)."""
    if narrator is None:
        return {"facts": facts, "narrative": None, "narrative_status": "skipped"}
    try:
        return {"facts": facts, "narrative": normalize_memo(narrator(facts)), "narrative_status": "completed"}
    except Exception as exc:  # noqa: BLE001 - narration is best-effort over the facts
        return {"facts": facts, "narrative": None, "narrative_status": "failed", "error": str(exc)}


def compose_memo_slack(report: dict[str, Any]) -> str:
    """Render the end-of-cohort memo as a Slack message (mrkdwn) for --deliver. LLM
    narrative when present; facts-only fallback otherwise (pure text, no HTML file)."""
    facts = report.get("facts") or {}
    nar = report.get("narrative") if report.get("narrative_status") == "completed" else None
    if nar:
        v = nar.get("pmf_verdict") or {}
        lines = [
            "🏁 *End-of-cohort PMF memo*",
            nar.get("headline") or nar.get("executive_summary") or "",
            f"*Verdict:* {v.get('rating', '?')} — {v.get('reason', '')}",
        ]
        for label, key in (("What worked", "what_worked"), ("What didn't", "what_didnt"), ("Next cohort", "recommendations")):
            items = nar.get(key) or []
            if items:
                lines.append(f"*{label}:*\n" + "\n".join(f"• {x}" for x in items[:8]))
        return "\n".join(x for x in lines if x)
    rates = (facts.get("funnel") or {}).get("rates") or {}
    return f"🏁 *End-of-cohort PMF memo* (facts only — run with --narrate-live for the verdict)\nrates: {rates}"
