"""Weekly PMF digest (P11) — the cadence 'step back'.

A deterministic week-over-week read — this week's stage movements, the current funnel +
the 6-metric rollup, product-friction themes, intervention outcomes — plus an LLM
synthesis: are we trending toward PMF, what's working, what's blocking, what to do this
week. Same injectable, key-gated narrator seam as end_cohort.py (narrator=None ->
'skipped', never auto-spends tokens; error -> 'failed'). report_type 'weekly_pmf' already
exists in the schema. Aggregate-only — no per-user PII.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from .model import minimize_secrets, now_utc, rollup_pmf_metrics

# (facts dict) -> raw narrative dict
NarratorFn = Callable[[dict[str, Any]], dict[str, Any]]

DEFAULT_WEEKLY_MODEL = "claude-sonnet-4-6"
_PMF_TRAJECTORY = {"toward_pmf", "flat", "away_from_pmf", "too_early"}
# The queues that signal product friction (vs. value/engagement queues).
_FRICTION_QUEUE_TYPES = {"stuck_onboarding", "spinwheel_stuck", "plaid_failed", "weak_credgpt_response"}


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        out[row.get(key)] = out.get(row.get(key), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: str(kv[0])))


def build_weekly_facts(
    *,
    cohort: dict[str, Any] | None,
    summary: dict[str, Any] | None,
    week_movements: list[dict[str, Any]] | None,
    open_queues: list[dict[str, Any]] | None,
    clusters: list[dict[str, Any]] | None,
    interventions: list[dict[str, Any]] | None,
    metric_records: list[dict[str, Any]] | None,
    week_start: str | None = None,
    week_end: str | None = None,
) -> dict[str, Any]:
    """Deterministic weekly facts. `summary` is the current funnel snapshot; `week_movements`
    are the funnel transitions since week_start; product-friction = friction queues + CredGPT
    clusters; `interventions` rolls up outcomes."""
    summary = summary or {}
    movements = week_movements or []
    promotions = [m for m in movements if m.get("transition_type") == "promotion"]
    demotions = [m for m in movements if m.get("transition_type") == "demotion"]

    friction_counts: dict[str, int] = {}
    for queue in open_queues or []:
        if queue.get("queue_type") in _FRICTION_QUEUE_TYPES:
            friction_counts[queue.get("queue_type")] = friction_counts.get(queue.get("queue_type"), 0) + 1
    cluster_list = [
        {"cluster_type": c.get("cluster_type"), "title": c.get("title"), "severity": c.get("severity")}
        for c in sorted(clusters or [], key=lambda c: (c.get("severity") != "P1", str(c.get("cluster_type") or "")))[:10]
    ]

    iv = interventions or []
    iv_status: dict[str, int] = {}
    iv_outcomes = {"delivered": 0, "opened": 0, "clicked": 0, "converted": 0}
    for item in iv:
        iv_status[item.get("approval_status")] = iv_status.get(item.get("approval_status"), 0) + 1
        outcome = item.get("outcome")
        if isinstance(outcome, dict):
            for key in iv_outcomes:
                if outcome.get(key):
                    iv_outcomes[key] += 1

    return minimize_secrets({
        "schema_version": "pmf_weekly_digest.v1",
        "generated_at": now_utc(),
        "week_start": week_start,
        "week_end": week_end,
        "cohort": cohort or {},
        "funnel_now": {
            "total_signups": summary.get("total_signup_users", 0),
            "real_users": summary.get("real_users", 0),
            "stage_counts": summary.get("stage_counts") or {},
        },
        "movement_this_week": {
            "promotions": len(promotions),
            "demotions": len(demotions),
            "net": len(promotions) - len(demotions),
            "promotion_to_stages": _count_by(promotions, "to_stage"),
            "demotion_to_stages": _count_by(demotions, "to_stage"),
        },
        "pmf_metrics": rollup_pmf_metrics(metric_records),
        "product_friction": {"queue_counts": dict(sorted(friction_counts.items())), "credgpt_clusters": cluster_list},
        "interventions": {
            "total": len(iv),
            "by_status": dict(sorted(iv_status.items(), key=lambda kv: str(kv[0]))),
            "outcomes": iv_outcomes,
        },
    })


def build_weekly_prompt(facts: dict[str, Any]) -> str:
    return (
        "You are Alaska, writing the weekly PMF digest for a fintech launch cohort, for founders. "
        "Step back: read the deterministic facts below (JSON) and judge the trajectory. Use ONLY these "
        "facts — never invent numbers. Respond with ONLY a JSON object: headline (string), trajectory "
        "(object with 'rating' one of toward_pmf|flat|away_from_pmf|too_early and 'reason' string), "
        "whats_working (array of strings), whats_blocking (array of strings), do_this_week (array of "
        "strings).\n\nFACTS:\n" + json.dumps(facts, sort_keys=True)
    )


def normalize_weekly(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a narrator's raw output into the stored weekly-digest shape (defensive)."""
    raw = raw or {}
    traj = raw.get("trajectory") if isinstance(raw.get("trajectory"), dict) else {}
    rating = traj.get("rating")
    return {
        "headline": str(raw.get("headline") or "")[:600],
        "trajectory": {
            "rating": rating if rating in _PMF_TRAJECTORY else "too_early",
            "reason": str(traj.get("reason") or "")[:1000],
        },
        "whats_working": [str(x) for x in (raw.get("whats_working") or [])][:12],
        "whats_blocking": [str(x) for x in (raw.get("whats_blocking") or [])][:12],
        "do_this_week": [str(x) for x in (raw.get("do_this_week") or [])][:12],
    }


def _live_narrator(facts: dict[str, Any], *, model: str | None = None, timeout: float = 90.0) -> dict[str, Any]:
    """Thin live adapter over the shared LLM client. Requires ANTHROPIC_API_KEY."""
    from .llm import anthropic_complete, extract_json

    text = anthropic_complete(
        build_weekly_prompt(facts),
        model=model or os.environ.get("PMF_WEEKLY_MODEL") or DEFAULT_WEEKLY_MODEL,
        max_tokens=1400,
        timeout=timeout,
    )
    return normalize_weekly(extract_json(text))


def default_narrator() -> NarratorFn | None:
    """The live narrator when ANTHROPIC_API_KEY is set, else None (digest -> skipped)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return _live_narrator


def generate_weekly_digest(facts: dict[str, Any], *, narrator: NarratorFn | None = None) -> dict[str, Any]:
    """Attach a narrative to the facts. Explicit narration: narrator=None -> 'skipped'
    (never auto-narrates); a narrator error -> 'failed' (facts kept)."""
    if narrator is None:
        return {"facts": facts, "narrative": None, "narrative_status": "skipped"}
    try:
        return {"facts": facts, "narrative": normalize_weekly(narrator(facts)), "narrative_status": "completed"}
    except Exception as exc:  # noqa: BLE001 - the digest is best-effort over the facts
        return {"facts": facts, "narrative": None, "narrative_status": "failed", "error": str(exc)}
