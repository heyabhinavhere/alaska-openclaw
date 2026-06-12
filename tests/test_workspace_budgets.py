"""Bootstrap-file injection budgets — the forcing function.

OpenClaw (>=2026.5.28) injects workspace bootstrap files with a hard cap of
DEFAULT_BOOTSTRAP_MAX_CHARS = 12,000 chars per file and 60,000 total. An
over-budget file is NOT cut at the end: the loader keeps the first 75% and the
last 25% of the budget and SILENTLY DROPS THE MIDDLE (see
workspace/MEMORY.md -> Lessons). On 2026-06-05..12 this silently removed the
Action-Requests routing, the grounding table, and the Authority rules from
SOUL.md in every live session.

These budgets leave headroom under the 12k cap. If this test fails, do NOT
raise the budget — trim the file or relocate detail to the owning skill /
TOOLS.md / memory/. (A 20k/80k config override exists in config/openclaw.json
as a safety net for runtime-volume edits between deploys; it is not a license
to grow these files.)
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

PER_FILE_BUDGETS = {
    "workspace/SOUL.md": 11_800,  # the rules file runs denser; hard cap is 12,000
    "workspace/MEMORY.md": 11_500,
    "workspace/AGENT_RULES.md": 11_000,
    "workspace/TOOLS.md": 11_500,
    "workspace/AGENTS.md": 11_000,
    "workspace/USER.md": 4_000,
}

# Default loader total is 60,000 across the injected set; keep margin.
TOTAL_BUDGET = 55_000


def _size(rel: str) -> int:
    return len((ROOT / rel).read_text(encoding="utf-8"))


def test_bootstrap_files_exist():
    """Every budgeted bootstrap file must exist — a missing rulebook is worse than a fat one."""
    missing = [rel for rel in PER_FILE_BUDGETS if not (ROOT / rel).exists()]
    assert not missing, "Missing bootstrap file(s): " + ", ".join(missing)


def test_each_bootstrap_file_within_injection_budget():
    """Each bootstrap file stays under its per-file injection budget (hard cap 12k chars)."""
    over = [
        f"{rel}: {_size(rel):,} > {budget:,}"
        for rel, budget in PER_FILE_BUDGETS.items()
        if (ROOT / rel).exists() and _size(rel) > budget
    ]
    assert not over, (
        "Bootstrap file(s) over the injection budget (loader hard-truncates at "
        "12k chars/file, DROPPING THE MIDDLE — rules silently vanish): "
        + "; ".join(over)
        + ". Trim or relocate content (skills / TOOLS.md / memory/) — do not raise the budget."
    )


def test_bootstrap_set_total_within_budget():
    """The whole injected set stays under the total budget (loader default total cap 60k)."""
    total = sum(_size(rel) for rel in PER_FILE_BUDGETS if (ROOT / rel).exists())
    assert total <= TOTAL_BUDGET, (
        f"Injected bootstrap set totals {total:,} chars > {TOTAL_BUDGET:,} "
        "(loader default total cap is 60,000 — files past the budget get squeezed or skipped)."
    )


# HEARTBEAT.md is NOT loader-injected (not in PER_FILE_BUDGETS on purpose): the
# platform heartbeat file-reads it in the main session every ~30 min. Its cost is
# recurring token burn, not the 12k truncation cliff — hence a separate soft cap.
HEARTBEAT_SOFT_CAP = 1_200


def test_heartbeat_stays_small():
    """HEARTBEAT.md is re-read every ~30 min heartbeat — keep it lean."""
    size = _size("workspace/HEARTBEAT.md")
    assert size <= HEARTBEAT_SOFT_CAP, (
        f"workspace/HEARTBEAT.md is {size:,} chars > {HEARTBEAT_SOFT_CAP:,} soft cap "
        "— it is file-read on every heartbeat (~30 min); trim it rather than raising the cap."
    )
