"""Queue -> intervention action loop (P9) — the operator layer.

Turns an OPEN operating queue into a *proposed* Customer.io intervention that lands in
'needs_approval' (linked via queue_id). Alaska proposes WHO + WHAT + WHY; a human owns
the SEND (the P6 guard re-validates at execute). The decision to draft is deterministic
(QUEUE_INTERVENTION_MAP); only the message body is LLM (injectable + key-gated).

Drafting never sends. Not every queue maps: `potential_lover` -> a founder task (not an
automated send); review/quality queues -> no draft. The draft's suppression_check is
HONESTLY unverified — the substantive suppression/frequency check is the live executor's
job before it actually sends (see customerio_exec).
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

# (draft-context dict) -> {subject?, body}. Injectable + key-gated.
CopyDrafterFn = Callable[[dict[str, Any]], dict[str, Any]]
DEFAULT_COPY_MODEL = "claude-sonnet-4-6"

# Deterministic: which actionable queues warrant which intervention. Queues NOT here
# (needs_human_review, weak_credgpt_response, repeated_product_model_issue_cluster,
# spinwheel_stuck, plaid_failed) get NO auto-draft — they're internal review work or
# not a user-facing nudge.
QUEUE_INTERVENTION_MAP: dict[str, dict[str, str]] = {
    "high_intent": {
        "channel": "email", "action_type": "nudge_link_card",
        "intent": "High intent — they tried to link an account but hit a failure. Help them finish linking.",
    },
    "stuck_onboarding": {
        "channel": "email", "action_type": "nudge_resume_onboarding",
        "intent": "Stalled mid-onboarding — a warm nudge to resume the next step.",
    },
    "at_risk": {
        "channel": "push", "action_type": "winback",
        "intent": "A real user has gone quiet — a light win-back to bring them back.",
    },
    "potential_lover": {
        "channel": "internal_task", "action_type": "founder_outreach",
        "intent": "Strong signal — a FOUNDER should personally reach out. Internal task, NOT an automated send.",
    },
}


def _fallback_copy(ctx: dict[str, Any]) -> dict[str, Any]:
    """Deterministic copy when no LLM drafter is wired — never blocks the proposal."""
    return {
        "subject": str(ctx.get("action_type") or "intervention").replace("_", " ").title(),
        "body": ctx.get("intent") or "Personalized nudge (draft — review before sending).",
    }


def _live_copy_drafter(ctx: dict[str, Any], *, model: str | None = None, timeout: float = 45.0) -> dict[str, Any]:
    """Thin live adapter over the shared LLM client (message body only)."""
    from .llm import anthropic_complete, extract_json

    prompt = (
        "You are Alaska drafting a SHORT, warm, on-brand nudge for ONE BON Credit user. "
        "Use ONLY the context below — no placeholders, no invented facts, no links you weren't given. "
        "Respond with ONLY a JSON object: subject (<=60 chars; omit for push/internal_task), body (<=400 chars).\n\n"
        + json.dumps(ctx, sort_keys=True)
    )
    out = extract_json(anthropic_complete(
        prompt, model=model or os.environ.get("PMF_COPY_MODEL") or DEFAULT_COPY_MODEL, max_tokens=400, timeout=timeout,
    ))
    return {"subject": str(out.get("subject") or "")[:60], "body": str(out.get("body") or "")[:400]}


def default_copy_drafter() -> CopyDrafterFn | None:
    """The live copy drafter when ANTHROPIC_API_KEY is set, else None (deterministic fallback)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return _live_copy_drafter


def plan_interventions_for_queues(
    open_queues: list[dict[str, Any]] | None,
    *,
    copy_drafter: CopyDrafterFn | None = None,
) -> list[dict[str, Any]]:
    """Deterministic: which open queues warrant a proposed intervention. Returns draft
    specs ready for `store.draft_intervention` — channel, action_type, queue_id, user_key,
    the drafted copy, a per-user audience (count 1), a dry-run render, and an honestly
    UNVERIFIED suppression_check (the real check is the live executor's job at send)."""
    drafter = copy_drafter or _fallback_copy
    specs: list[dict[str, Any]] = []
    for queue in open_queues or []:
        mapping = QUEUE_INTERVENTION_MAP.get(queue.get("queue_type"))
        if not mapping or not queue.get("user_key"):
            continue
        ctx = {
            "action_type": mapping["action_type"], "channel": mapping["channel"], "intent": mapping["intent"],
            "user_key": queue.get("user_key"), "queue_type": queue.get("queue_type"),
            "queue_title": queue.get("title"), "queue_reason": queue.get("reason"),
        }
        try:
            copy = drafter(ctx) or _fallback_copy(ctx)
        except Exception:  # noqa: BLE001 - a copy failure falls back; it never blocks the proposal
            copy = _fallback_copy(ctx)
        specs.append({
            "queue_id": queue.get("id"),
            "user_key": queue.get("user_key"),
            "channel": mapping["channel"],
            "action_type": mapping["action_type"],
            "draft": {**copy, "intent": mapping["intent"], "source_queue": queue.get("queue_type")},
            "audience_preview": {"count": 1, "users": [queue.get("user_key")]},
            "dry_run": {"rendered": copy},
            "suppression_check": {"verified": False, "note": "live suppression + frequency check required before send"},
        })
    return specs
