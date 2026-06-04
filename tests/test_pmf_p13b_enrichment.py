"""P13b: incremental enrichment selection. resolve_enrichment_config (defaults +
validated overrides) and select_users_to_enrich (full vs incremental: NEW + HOT +
capped slow-refresh, oldest-first, every-user-eventually-refreshed). Pure, no DB."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.enrichment import (  # noqa: E402
    DEFAULT_ENRICHMENT,
    resolve_enrichment_config,
    select_users_to_enrich,
)

INCR = {"mode": "incremental", "active_window_days": 3, "slow_refresh_cap": 2}
SNAP = "2026-06-10"  # cutoff = 2026-06-07


def _u(key, *, snap=None, stage_at=None):
    return {"user_key": key, "latest_snapshot_date": snap, "stage_updated_at": stage_at}


# ---- resolve_enrichment_config ----

def test_resolve_defaults_and_overrides():
    assert resolve_enrichment_config(None) == DEFAULT_ENRICHMENT
    assert resolve_enrichment_config({}) == DEFAULT_ENRICHMENT
    r = resolve_enrichment_config({"enrichment": {"mode": "incremental", "slow_refresh_cap": 300}})
    assert r["mode"] == "incremental" and r["slow_refresh_cap"] == 300
    assert r["active_window_days"] == DEFAULT_ENRICHMENT["active_window_days"]  # untouched
    # config_json arrives as a JSON string from the DB — must be parsed
    assert resolve_enrichment_config('{"enrichment": {"mode": "incremental"}}')["mode"] == "incremental"


def test_resolve_rejects_invalid():
    r = resolve_enrichment_config({"enrichment": {
        "mode": "bogus", "active_window_days": -1, "slow_refresh_cap": True, "unknown": 9,
    }})
    assert r["mode"] == "full"                                                 # bad mode → default
    assert r["active_window_days"] == DEFAULT_ENRICHMENT["active_window_days"]  # negative rejected
    assert r["slow_refresh_cap"] == DEFAULT_ENRICHMENT["slow_refresh_cap"]      # bool rejected
    assert "unknown" not in r


# ---- select: full mode is unchanged behavior ----

def test_full_mode_returns_everyone():
    users = [_u("a"), _u("b", snap="2026-06-09"), _u("c", snap="2026-01-01")]
    out = select_users_to_enrich(users, SNAP, config={"mode": "full"})
    assert [u["user_key"] for u in out] == ["a", "b", "c"]


# ---- select: incremental buckets ----

def test_incremental_new_and_hot_always_selected_dormant_capped():
    users = [
        _u("new", snap=None),                                          # NEW (no snapshot)
        _u("hot", snap="2026-06-09", stage_at="2026-06-09 10:00:00"),  # HOT (stage moved in window)
        _u("dorm_old", snap="2026-06-01", stage_at="2026-05-30 00:00:00"),
        _u("dorm_mid", snap="2026-06-03", stage_at="2026-05-30 00:00:00"),
        _u("dorm_new", snap="2026-06-05", stage_at="2026-05-30 00:00:00"),
    ]
    out = {u["user_key"] for u in select_users_to_enrich(users, SNAP, config=INCR)}
    assert {"new", "hot"} <= out                       # new + hot always in
    assert {"dorm_old", "dorm_mid"} <= out             # 2 oldest dormant (cap=2)
    assert "dorm_new" not in out                       # newest-enriched dormant deferred
    assert len(out) == 4


def test_incremental_slow_refresh_eventually_covers_everyone():
    # 5 dormant users (old stage_updated_at → never HOT), distinct snapshot ages; cap=2.
    users = {f"u{i}": _u(f"u{i}", snap=f"2026-05-0{i + 1}", stage_at="2026-04-01 00:00:00") for i in range(5)}
    refreshed: set[str] = set()
    day = date(2026, 6, 10)
    for _ in range(3):  # ceil(5 / 2) = 3 rounds
        sel = select_users_to_enrich(list(users.values()), day.isoformat(), config=INCR)
        for u in sel:
            refreshed.add(u["user_key"])
            users[u["user_key"]]["latest_snapshot_date"] = day.isoformat()  # mark refreshed today
        day += timedelta(days=1)
    assert refreshed == set(users)  # every dormant user refreshed within the bound


def test_incremental_cap_zero_keeps_only_new_and_hot():
    users = [
        _u("new", snap=None),
        _u("hot", snap="2026-06-09", stage_at="2026-06-09 10:00:00"),
        _u("dormant", snap="2026-06-01", stage_at="2026-05-01 00:00:00"),
    ]
    out = {u["user_key"] for u in select_users_to_enrich(users, SNAP, config={**INCR, "slow_refresh_cap": 0})}
    assert out == {"new", "hot"}  # dormant gets no slow-refresh slot this run


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
