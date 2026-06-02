"""Customer.io safety gates for PMF cohort execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PHASE1_ALLOWED_SEND_CHANNELS = {"email", "push"}
CUSTOMERIO_MUTATION_CHANNELS = {"email", "push", "customerio_attribute"}


@dataclass
class CustomerIoDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": self.reasons,
            "warnings": self.warnings,
        }


def validate_customerio_action(action: dict[str, Any]) -> CustomerIoDecision:
    """Validate whether a Customer.io PMF action is executable.

    This function only authorizes execution readiness; it does not call
    Customer.io. Callers must still use the customerio-ops skill/API wrapper to
    perform the write.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    channel = action.get("channel")

    if channel == "sms":
        reasons.append("SMS is blocked in V5 Phase 1 because A2P is not approved.")
    if channel not in PHASE1_ALLOWED_SEND_CHANNELS and channel in {"sms", "in_app"}:
        reasons.append(f"{channel} is not enabled for PMF Phase 1 execution.")
    if channel in CUSTOMERIO_MUTATION_CHANNELS:
        if not action.get("approved_by"):
            reasons.append("Missing explicit approval.")
        if not action.get("dry_run"):
            reasons.append("Missing dry-run result.")
        if not action.get("audience_preview"):
            reasons.append("Missing audience preview.")
        if not action.get("suppression_check"):
            reasons.append("Missing suppression check.")
        if _audience_count(action.get("audience_preview")) == 0:
            warnings.append("Audience preview is empty.")
        if action.get("frequency_cap_checked") is not True:
            warnings.append("Frequency cap check was not confirmed.")
    elif channel == "internal_task":
        if action.get("user_facing") is True:
            reasons.append("Internal task cannot be marked user-facing.")
    elif channel == "slack":
        if action.get("contains_pii") and action.get("privacy_tier") == "team":
            reasons.append("Team Slack summary cannot contain PII.")
    else:
        reasons.append(f"Unsupported Customer.io PMF action channel: {channel!r}.")

    return CustomerIoDecision(allowed=not reasons, reasons=reasons, warnings=warnings)


def build_approval_pack(action: dict[str, Any]) -> dict[str, Any]:
    """Return a structured approval pack for Slack or an HTML/DOCX artifact."""
    return {
        "name": action.get("name") or action.get("action_type") or "PMF cohort action",
        "channel": action.get("channel"),
        "cohort_id": action.get("cohort_id"),
        "queue_type": action.get("queue_type"),
        "audience_count": _audience_count(action.get("audience_preview")),
        "draft": action.get("draft") or action.get("draft_json") or {},
        "dry_run": action.get("dry_run"),
        "audience_preview": action.get("audience_preview"),
        "suppression_check": action.get("suppression_check"),
        "risks": validate_customerio_action(action).as_dict(),
        "requires_approval": action.get("channel") in CUSTOMERIO_MUTATION_CHANNELS,
        "sms_blocked": action.get("channel") == "sms",
    }


def _audience_count(preview: Any) -> int | None:
    if preview is None:
        return None
    if isinstance(preview, dict):
        for key in ("count", "audience_count", "total", "size"):
            if key in preview:
                try:
                    return int(preview[key])
                except (TypeError, ValueError):
                    return None
        users = preview.get("users")
        if isinstance(users, list):
            return len(users)
    if isinstance(preview, list):
        return len(preview)
    return None
