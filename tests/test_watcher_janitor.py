"""Static invariants for the Watcher Janitor — guard the snapshot-integrity gate
and the Step 6 adopt-before-alarm fix that stop the cron.list partial-read false
alarms (the W-2/W-3 cried-wolf; builder self-task M-2).

Root cause these guard against: `cron.list` can return a partial/near-empty
snapshot (e.g. a freshly-restarted gateway), and the janitor used to reconcile
against it with no integrity check — making healthy active watchers look orphaned.
A running janitor whose OWN cron is absent from the snapshot is, by necessity,
looking at a bad READ (a true store-wipe would have taken its own cron too), so
the gate aborts rather than crying wolf.

Stdlib only. Runnable directly:
    python3 tests/test_watcher_janitor.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
JANITOR = REPO_ROOT / "skills" / "watcher-janitor" / "SKILL.md"


def _text() -> str:
    return JANITOR.read_text(encoding="utf-8")


def _section(heading: str) -> str:
    # Return just the named step's block (from its heading to the next "### "), so
    # an assertion can't false-pass on a word that lives in a DIFFERENT step
    # (e.g. "adopt" already appears in Step 4 — a Step 6 check must be scoped).
    text = _text()
    start = text.find(heading)
    assert start != -1, f"missing heading: {heading!r}"
    nxt = text.find("\n### ", start + len(heading))
    return (text[start:] if nxt == -1 else text[start:nxt]).lower()


def test_has_snapshot_integrity_gate():
    # The gate must exist as its own step — the janitor must validate cron.list
    # before reconciling, or a partial read manufactures false orphans.
    assert "snapshot integrity" in _section("### Step 1.5:"), (
        "missing the snapshot-integrity gate (Step 1.5) — a partial cron.list read "
        "would still produce false orphan alarms"
    )


def test_gate_uses_self_reference_invariant():
    # The gate must key on the janitor's OWN cron being present in the snapshot:
    # a running janitor whose own cron is absent is looking at a bad READ, not a
    # real cron-store reset.
    assert "own cron" in _section("### Step 1.5:"), (
        "the integrity gate must assert the janitor's own cron must appear in a "
        "valid snapshot (the self-reference invariant)"
    )


def test_gate_aborts_on_unreliable_snapshot():
    # On an unreliable snapshot the janitor must ABORT — not flag, remove, or add.
    assert "abort" in _section("### Step 1.5:"), (
        "the integrity gate must ABORT the run on an unreliable snapshot rather "
        "than reconcile against it"
    )


def test_step6_adopts_before_alarming():
    # Step 6 must re-link (adopt) an active watcher whose cron actually exists in
    # the snapshot, not alarm 'lost cron' — mirrors Step 4's adopt path. Scoped to
    # the Step 6 block so it can't false-pass on Step 4's "Adopt".
    s6 = _section("### Step 6:")
    assert "adopt" in s6 and "re-link" in s6, (
        "Step 6 must adopt/re-link an existing cron before flagging it as lost"
    )


if __name__ == "__main__":
    import inspect

    fns = [
        obj
        for name, obj in inspect.getmembers(sys.modules[__name__])
        if inspect.isfunction(obj) and name.startswith("test_")
    ]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS: {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL: {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
