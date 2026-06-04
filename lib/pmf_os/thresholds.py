"""Per-cohort tunable thresholds for the PMF funnel (P12).

The funnel/metric dials live here as DEFAULT_THRESHOLDS — the single source of the
current values — and are overridable per cohort via `pmf_cohorts.config_json['thresholds']`,
so operators tune the funnel without code edits. `resolve_thresholds()` merges validated
overrides over the defaults; passing the result into `evaluate_funnel` /
`compute_pmf_success_metrics` moves the dials. With no overrides (or thresholds=None),
behaviour is exactly today's.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_THRESHOLDS: dict[str, int] = {
    # activated_user gate
    "activation_meaningful_messages": 3,     # greeting-filtered CredGPT messages
    "activation_high_intent_qas": 2,         # high-intent usable Q&As
    # activation_depth metric (confirmed-only)
    "activation_depth_threads": 2,           # distinct meaningful threads
    "activation_depth_messages": 5,          # meaningful messages
    # repeat_engagement metric
    "repeat_engagement_confirmed_days": 3,   # active days -> confirmed
    "repeat_engagement_candidate_days": 2,   # active days -> candidate
    # activated_saver bar (the "2 of 6")
    "activated_saver_confirmed_metrics": 2,  # confirmed metrics -> computed saver
    "activated_saver_candidate_metrics": 2,  # confirmed+candidate metrics -> candidate saver
    # likely_lover
    "likely_lover_active_days": 2,
    # at_risk health
    "at_risk_inactive_days": 3,
}


def resolve_thresholds(cohort_config: Any) -> dict[str, int]:
    """Merge a cohort's threshold overrides over the defaults.

    `cohort_config` may be a dict or the raw JSON string from `pmf_cohorts.config_json`.
    Only KNOWN keys with non-negative integer values are accepted — anything else (unknown
    key, wrong type, negative, bool) is ignored and the default stands. Always returns a
    complete threshold set.
    """
    resolved = dict(DEFAULT_THRESHOLDS)
    if isinstance(cohort_config, str):
        try:
            cohort_config = json.loads(cohort_config)
        except (json.JSONDecodeError, ValueError):
            cohort_config = None
    overrides = cohort_config.get("thresholds") if isinstance(cohort_config, dict) else None
    if isinstance(overrides, dict):
        for key, value in overrides.items():
            if (
                key in DEFAULT_THRESHOLDS
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value >= 0
            ):
                resolved[key] = int(value)
    return resolved
