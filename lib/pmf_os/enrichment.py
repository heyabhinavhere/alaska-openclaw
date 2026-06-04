"""Incremental daily enrichment selection (P13b).

The daily cron does NOT need to re-enrich every cohort user every day — that
doesn't scale (one User-360 HTTP round-trip per user). Instead it enriches a
bounded subset:

  * NEW          — never snapshotted yet (must get a first read after signup)
  * HOT          — stage changed within `active_window_days` (actively moving
                   through the funnel → keep watching closely)
  * SLOW-REFRESH — a capped slice of the rest, OLDEST-enriched first, so EVERY
                   user is refreshed at least every ~ceil(dormant / cap) days
                   (a dormant user who reactivates is picked up within that bound)

Daily load = |new| + |hot| + min(|dormant|, cap) — bounded, not the whole cohort.

Default mode is 'full' (enrich everyone — unchanged behavior); a cohort opts into
'incremental' via its config_json. Pure functions — no DB, no I/O, fully testable.
The slow-refresh cap is the safety net: even if HOT misclassifies a user, they are
still re-enriched within the refresh bound, so staleness is bounded.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

DEFAULT_ENRICHMENT: dict[str, Any] = {
    "mode": "full",            # 'full' | 'incremental'
    "active_window_days": 3,   # stage changed within this many days → HOT (daily)
    "slow_refresh_cap": 150,   # max dormant users refreshed per run (tune from latency)
}

_VALID_MODES = ("full", "incremental")


def resolve_enrichment_config(cohort_config: Any) -> dict[str, Any]:
    """Defaults overlaid with validated overrides from a cohort's config_json (a
    JSON string or dict) under the 'enrichment' key. Unknown/invalid values are
    ignored so a malformed config can never crash the daily run."""
    cfg = dict(DEFAULT_ENRICHMENT)
    raw = cohort_config
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = None
    enr = raw.get("enrichment") if isinstance(raw, dict) else None
    if isinstance(enr, dict):
        if enr.get("mode") in _VALID_MODES:
            cfg["mode"] = enr["mode"]
        for key in ("active_window_days", "slow_refresh_cap"):
            val = enr.get(key)
            if isinstance(val, int) and not isinstance(val, bool) and val >= 0:
                cfg[key] = val
    return cfg


def _date_prefix(value: Any) -> str:
    """First 10 chars (the ISO date) of a date/datetime string; '' if absent."""
    return str(value)[:10] if value else ""


def select_users_to_enrich(
    users: list[dict[str, Any]],
    snapshot_date: str,
    *,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return the subset of `users` (list_users rows) to enrich this run.

    'full' mode returns everyone (unchanged behavior). 'incremental' returns
    NEW + HOT + a capped SLOW-REFRESH slice (oldest-enriched first). Returned
    order is new, then hot, then slow-refresh."""
    if config.get("mode") != "incremental":
        return list(users)

    window = int(config.get("active_window_days", DEFAULT_ENRICHMENT["active_window_days"]))
    cap = int(config.get("slow_refresh_cap", DEFAULT_ENRICHMENT["slow_refresh_cap"]))
    base = _date_prefix(snapshot_date)
    cutoff = (
        (date.fromisoformat(base) - timedelta(days=window)).isoformat()
        if base else date.min.isoformat()  # no snapshot_date → enrich everyone (safe)
    )

    new: list[dict[str, Any]] = []
    hot: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for u in users:
        if not u.get("latest_snapshot_date"):
            new.append(u)                                      # never enriched
        elif _date_prefix(u.get("stage_updated_at")) >= cutoff:
            hot.append(u)                                      # stage moved within window
        else:
            rest.append(u)                                     # dormant → slow refresh
    rest.sort(key=lambda u: _date_prefix(u.get("latest_snapshot_date")))  # oldest first
    return new + hot + rest[: max(0, cap)]
