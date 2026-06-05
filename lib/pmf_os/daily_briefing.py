"""Daily briefing for PMF Cohort OS (P8) — the interpretation layer.

The daily run already produces a deterministic aggregate Slack line. This adds the
founder-facing *briefing*: Alaska's read over the day's deterministic facts — what
changed, who needs you and why, what I'd do today. Same injectable, key-gated
narrator seam as `end_cohort.py`: machines aggregate the facts, the LLM narrates;
`narrator=None` -> 'skipped' (never auto-spends tokens), a narrator error -> 'failed'
(facts kept). Aggregate-only — no per-user PII beyond what the team already sees.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from .model import minimize_secrets, now_utc

# (facts dict) -> raw narrative dict
NarratorFn = Callable[[dict[str, Any]], dict[str, Any]]

DEFAULT_BRIEFING_MODEL = "claude-sonnet-4-6"


def build_briefing_facts(
    *,
    snapshot_date: str,
    summary: dict[str, Any] | None,
    movements: list[dict[str, Any]] | None,
    open_queues: list[dict[str, Any]] | None,
    quality: dict[str, Any] | None = None,
    users: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Deterministic briefing facts: funnel summary, the day's stage movements,
    open operating queues (counts + the P0/P1 items as 'who needs you'), and CredGPT
    quality. Names are attached for the team-visible briefing; minimize_secrets still
    strips SSN/routing/address."""
    summary = summary or {}
    name_by_key = {u.get("user_key"): u.get("name") for u in (users or []) if u.get("user_key")}

    movements = movements or []
    promotions = [m for m in movements if m.get("transition_type") == "promotion"]
    demotions = [m for m in movements if m.get("transition_type") == "demotion"]

    def _move(m: dict[str, Any]) -> dict[str, Any]:
        return {"user_key": m.get("user_key"), "name": name_by_key.get(m.get("user_key")), "to_stage": m.get("to_stage")}

    queues = open_queues or []
    queue_counts: dict[str, int] = {}
    for q in queues:
        queue_counts[q.get("queue_type")] = queue_counts.get(q.get("queue_type"), 0) + 1
    priority_items = [
        {
            "queue_type": q.get("queue_type"), "severity": q.get("severity"),
            "user_key": q.get("user_key"), "name": name_by_key.get(q.get("user_key")),
            "title": q.get("title"), "reason": q.get("reason"),
        }
        for q in sorted(queues, key=lambda q: str(q.get("severity") or "P3"))
        if q.get("severity") in ("P0", "P1")
    ][:15]

    return minimize_secrets({
        "schema_version": "pmf_daily_briefing.v1",
        "generated_at": now_utc(),
        "snapshot_date": snapshot_date,
        "funnel": {
            "total_signups": summary.get("total_signup_users", 0),
            "real_users": summary.get("real_users", 0),
            "stage_counts": summary.get("stage_counts") or {},
        },
        "movements": {
            "promotion_count": len(promotions),
            "demotion_count": len(demotions),
            "promotions": [_move(m) for m in promotions][:30],
            "demotions": [_move(m) for m in demotions][:30],
        },
        "open_queues": {"counts": dict(sorted(queue_counts.items())), "priority_items": priority_items},
        "credgpt_quality": quality or {},
    })


def build_briefing_prompt(facts: dict[str, Any]) -> str:
    return (
        "You are Alaska, writing today's founder briefing for a fintech PMF launch cohort. "
        "Use ONLY the deterministic facts below (JSON) — never invent numbers or users. Be "
        "concise, specific, and action-oriented (you are a teammate, not a dashboard). Respond "
        "with ONLY a JSON object: headline (string), what_changed (array of strings — the day's "
        "movements + notable shifts), who_needs_you (array of objects {user, why, suggested_action}), "
        "recommendations (array of strings — what you'd do today), watch (array of strings — emerging "
        "risks).\n\nFACTS:\n" + json.dumps(facts, sort_keys=True)
    )


def normalize_briefing(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a narrator's raw output into the stored briefing shape (defensive)."""
    raw = raw or {}
    who = []
    for item in (raw.get("who_needs_you") or [])[:15]:
        if isinstance(item, dict):
            who.append({
                "user": str(item.get("user") or "")[:120],
                "why": str(item.get("why") or "")[:500],
                "suggested_action": str(item.get("suggested_action") or "")[:500],
            })
    return {
        "headline": str(raw.get("headline") or "")[:600],
        "what_changed": [str(x) for x in (raw.get("what_changed") or [])][:15],
        "who_needs_you": who,
        "recommendations": [str(x) for x in (raw.get("recommendations") or [])][:15],
        "watch": [str(x) for x in (raw.get("watch") or [])][:15],
    }


def _is_empty_briefing(narrative: dict[str, Any]) -> bool:
    """True when a narrative has no headline and no items in any section — i.e. the
    model returned nothing parseable (e.g. the response was truncated past max_tokens
    so extract_json fell back to {})."""
    n = narrative or {}
    return not (
        n.get("headline") or n.get("what_changed") or n.get("who_needs_you")
        or n.get("recommendations") or n.get("watch")
    )


def _live_narrator(facts: dict[str, Any], *, model: str | None = None, timeout: float = 75.0) -> dict[str, Any]:
    """Thin live adapter over the shared LLM client. Requires ANTHROPIC_API_KEY."""
    from .llm import anthropic_complete, extract_json

    text = anthropic_complete(
        build_briefing_prompt(facts),
        model=model or os.environ.get("PMF_BRIEFING_MODEL") or DEFAULT_BRIEFING_MODEL,
        max_tokens=2000,  # the briefing output (up to 15 who_needs_you objects + 4 arrays)
        timeout=timeout,  # is larger than the weekly digest's; 1200 truncated it → invalid JSON
    )
    return normalize_briefing(extract_json(text))


def default_narrator() -> NarratorFn | None:
    """The live narrator when ANTHROPIC_API_KEY is set, else None (briefing -> skipped)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return _live_narrator


def generate_daily_briefing(facts: dict[str, Any], *, narrator: NarratorFn | None = None) -> dict[str, Any]:
    """Attach a narrative to the facts. Explicit narration: narrator=None -> 'skipped'
    (never auto-narrates); a narrator error -> 'failed' (facts kept)."""
    if narrator is None:
        return {"facts": facts, "narrative": None, "narrative_status": "skipped"}
    try:
        narrative = normalize_briefing(narrator(facts))
    except Exception as exc:  # noqa: BLE001 - briefing is best-effort over the facts
        return {"facts": facts, "narrative": None, "narrative_status": "failed", "error": str(exc)}
    # An empty narrative (the model returned no parseable JSON — e.g. truncated past
    # max_tokens) must NOT post as a successful-but-blank briefing. Mark it failed so
    # the orchestrator skips the Slack post (it only posts on 'completed').
    if _is_empty_briefing(narrative):
        return {"facts": facts, "narrative": None, "narrative_status": "failed",
                "error": "empty narrative (no parseable model output)"}
    return {"facts": facts, "narrative": narrative, "narrative_status": "completed"}
