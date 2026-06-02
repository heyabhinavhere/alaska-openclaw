"""Shared PMF OS model types and constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


FUNNEL_STAGES = [
    "signed_up",
    "onboarded_real_user",
    "activated_user",
    "activated_saver",
    "likely_lover",
    "confirmed_lover",
]

STAGE_RANK = {stage: idx for idx, stage in enumerate(FUNNEL_STAGES)}

ACTIVATED_SAVER_COMPUTED = "computed"
ACTIVATED_SAVER_CANDIDATE = "candidate"

EVIDENCE_STATES = {"missing", "stale", "unavailable", "false", "confirmed"}
FRESHNESS_STATES = EVIDENCE_STATES

MEANINGFUL_CHAT_INTENTS = {
    "budget",
    "paydown",
    "credit_score",
    "credit_report",
    "card_linking",
    "debt",
    "apr",
    "autopay",
    "strategy",
    "saving",
    "subscription",
    "cashflow",
}

LOW_VALUE_CHAT_PATTERNS = {
    "hi",
    "hello",
    "hey",
    "thanks",
    "thank you",
    "ok",
    "okay",
    "test",
    "help",
}

VALUE_ACTION_TYPES = {
    "card_link_success",
    "bank_link_success",
    "strategy_created",
    "budget_created",
    "paydown_plan_created",
    "autopay_enabled",
    "personalized_financial_action",
}

PMF_SUCCESS_METRICS = [
    "activation_depth",
    "repeat_engagement",
    "financial_action",
    "linked_financial_context",
    "qualitative_positive_signal",
    "retained_value",
]

PII_KEYS = {
    "name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "phone_number",
    "dob",
    "ssn",
    "address",
    "street",
    "employer_name",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_stage(stage: str | None) -> str:
    if stage in STAGE_RANK:
        return stage
    return "signed_up"


def higher_stage(a: str | None, b: str | None) -> str:
    stage_a = normalize_stage(a)
    stage_b = normalize_stage(b)
    return stage_a if STAGE_RANK[stage_a] >= STAGE_RANK[stage_b] else stage_b


@dataclass(frozen=True)
class Evidence:
    claim_key: str
    state: str = "confirmed"
    freshness: str = "confirmed"
    confidence: float = 1.0
    source_system: str = "alaska"
    source_ref: str | None = None
    observed_at: str | None = None
    value: Any = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in EVIDENCE_STATES:
            raise ValueError(f"bad evidence state: {self.state}")
        if self.freshness not in FRESHNESS_STATES:
            raise ValueError(f"bad freshness state: {self.freshness}")
        if not 0 <= self.confidence <= 1:
            raise ValueError("evidence confidence must be between 0 and 1")

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_key": self.claim_key,
            "state": self.state,
            "freshness": self.freshness,
            "confidence": self.confidence,
            "source_system": self.source_system,
            "source_ref": self.source_ref,
            "observed_at": self.observed_at,
            "value": self.value,
            "details": self.details,
        }


@dataclass
class FunnelResult:
    stage: str
    highest_stage: str
    activated_saver_state: str | None = None
    health: str = "unknown"
    flags: list[str] = field(default_factory=list)
    queues: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "highest_stage": self.highest_stage,
            "activated_saver_state": self.activated_saver_state,
            "health": self.health,
            "flags": self.flags,
            "queues": self.queues,
            "confidence": self.confidence,
            "evidence": [item.as_dict() for item in self.evidence],
        }
