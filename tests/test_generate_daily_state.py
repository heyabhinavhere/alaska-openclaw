"""Tests for lib/generate_daily_state.py.

Stdlib only (pytest may be unavailable in the container). Runnable directly:
    python3 tests/test_generate_daily_state.py
Exits nonzero on any failure.

Each test builds a scratch SQLite DB from migrations/0001_v2_task_model.sql,
seeds tasks + a blocker across known slack ids, writes a minimal DAILY_STATE.md
and MEMORY.md roster into a temp dir, runs the generator, and asserts on the
spliced output. A read-only invariant check confirms the DB row counts for
tasks/blockers are unchanged after generation.
"""

import sqlite3
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add lib/ to path (mirrors tests/test_rrule_helper.py).
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import generate_daily_state as g  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0001_v2_task_model.sql"

# Fixed "now" so done-recent / days-active math is deterministic.
NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

# Known slack ids that exist in the seeded roster below.
SANDEEP = "U0AQFJV9B32"
PANKAJ = "U0AQ0817FJM"
ABHINAV = "U07GKLVA9FE"

MINIMAL_ROSTER = """\
### Team Roster (canonical — confirmed)

| First Name | Full Name | Slack ID | Notion User ID | Role | Authority | Location |
|------------|-----------|----------|----------------|------|-----------|----------|
| Abhinav | Abhinav Jain | U07GKLVA9FE | `abc` | Head of Product & Design | Admin | India |
| Pankaj | Pankaj Pal | U0AQ0817FJM | `def` | Frontend Engineer | Engineer | India |
| Sandeep | Sandeep Singh | U0AQFJV9B32 | `ghi` | AI Engineer | Engineer | India |
| Sai | Sai | _external_ | _n/a_ | External | External | India |
"""

# A minimal but representative DAILY_STATE.md: header + all canonical sections.
# The non-generated sections carry unique sentinel content so we can assert they
# survive the splice byte-for-byte.
MINIMAL_STATE = """\
# DAILY_STATE.md — Single Source of Truth
# Last compiled: 2026-05-29 13:00 UTC (RECONSTRUCTED note here)

---

## Current Focus
- SENTINEL_FOCUS: ship June 10.

## This Week's Goals
1. SENTINEL_GOAL: number accuracy.

## Per Person

### Stale Person (Old Role)
- **NOW:** this should be replaced.
- **LAST COMMITTED:** stale.
- **DONE RECENTLY:** stale.
- **BLOCKED:** stale.

## Active Decisions (last ~2 weeks)
1. SENTINEL_DECISION: launch confirmed.

## Active Blockers
| Blocker | Days Active | Owner | Status |
|---------|------------|-------|--------|
| stale blocker | 99 | Nobody | should be replaced |

## Metrics
- SENTINEL_METRIC: DAU ~12-18.

## Upcoming
- SENTINEL_UPCOMING: June 10 launch.
"""


def _make_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def _iso(dt: datetime) -> str:
    """SQLite-friendly 'YYYY-MM-DD HH:MM:SS' (CURRENT_TIMESTAMP shape)."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _seed(path: str) -> None:
    """Seed tasks across 3 owners + one active blocker linking a task.

    Sandeep:  one active-with-due (NOW + LAST COMMITTED), one done-recent.
    Pankaj:   one blocked task (linked by the blocker), one active no-due.
    Abhinav:  one active no-due (NOW only), one OLD done (must NOT appear).
    """
    conn = sqlite3.connect(path)
    insert = (
        "INSERT INTO tasks "
        "(task_id, title, status, owner_slack_id, creator_slack_id, source, due_at, done_at) "
        "VALUES (?, ?, ?, ?, ?, 'manual', ?, ?)"
    )
    rows = [
        # Sandeep
        ("T-1", "Fix tool-call skipping", "active", SANDEEP, SANDEEP, _iso(NOW + timedelta(days=2)), None),
        ("T-2", "Debt misclassification RCA", "done", SANDEEP, SANDEEP, None, _iso(NOW - timedelta(days=1))),
        # Pankaj
        ("T-3", "Android build", "blocked", PANKAJ, PANKAJ, None, None),
        ("T-4", "Returning-user UI", "active", PANKAJ, PANKAJ, None, None),
        # Abhinav
        ("T-5", "PMF card development", "active", ABHINAV, ABHINAV, None, None),
        ("T-6", "Ancient shipped thing", "done", ABHINAV, ABHINAV, None, _iso(NOW - timedelta(days=30))),
    ]
    conn.executemany(insert, rows)
    conn.execute(
        "INSERT INTO blockers (blocker_id, title, blocking_task_ids, owner_slack_id, status, raised_at) "
        "VALUES (?, ?, ?, ?, 'active', ?)",
        ("B-1", "Play Store review pending", '["T-3"]', PANKAJ, _iso(NOW - timedelta(days=13))),
    )
    # A resolved blocker that must NOT appear in the table.
    conn.execute(
        "INSERT INTO blockers (blocker_id, title, blocking_task_ids, owner_slack_id, status, raised_at) "
        "VALUES (?, ?, ?, ?, 'resolved', ?)",
        ("B-2", "Already resolved", "[]", SANDEEP, _iso(NOW - timedelta(days=5))),
    )
    conn.commit()
    conn.close()


def _row_counts(path: str):
    conn = sqlite3.connect(path)
    t = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    b = conn.execute("SELECT COUNT(*) FROM blockers").fetchone()[0]
    e = conn.execute("SELECT COUNT(*) FROM task_events").fetchone()[0]
    conn.close()
    return (t, b, e)


def _fixture():
    """Create a temp dir with db + state + memory; return their paths and the dir."""
    tmp = tempfile.mkdtemp(prefix="alaska_gds_")
    db = str(Path(tmp) / "alaska.db")
    state = str(Path(tmp) / "DAILY_STATE.md")
    memory = str(Path(tmp) / "MEMORY.md")
    _make_db(db)
    _seed(db)
    Path(state).write_text(MINIMAL_STATE, encoding="utf-8")
    Path(memory).write_text(MINIMAL_ROSTER, encoding="utf-8")
    return tmp, db, state, memory


# ---------------------------------------------------------------------------
# Roster parsing
# ---------------------------------------------------------------------------
def test_load_roster_maps_known_ids_skips_external():
    tmp, db, state, memory = _fixture()
    roster = g.load_roster(memory)
    assert roster[SANDEEP] == {"name": "Sandeep", "role": "AI Engineer"}
    assert roster[ABHINAV]["name"] == "Abhinav"
    # External Sai row (Slack ID "_external_") must be skipped.
    assert all(v["name"] != "Sai" for v in roster.values())
    assert len(roster) == 3


def test_resolve_name_falls_back_to_raw_id():
    assert g.resolve_name("U_UNKNOWN_99", {}) == "U_UNKNOWN_99"


# ---------------------------------------------------------------------------
# Per Person rendering
# ---------------------------------------------------------------------------
def test_per_person_buckets_tasks_under_right_person():
    tmp, db, state, memory = _fixture()
    out = g.generate(db, state, memory, now=NOW)

    # Extract the Per Person section for targeted assertions.
    pp = _extract_section(out, "Per Person")

    # Sandeep heading present with role.
    assert "### Sandeep (AI Engineer)" in pp
    # NOW has the active task; LAST COMMITTED has it too (it has a due_at).
    sandeep_block = _person_block(pp, "Sandeep")
    assert "Fix tool-call skipping" in _field(sandeep_block, "NOW")
    assert "Fix tool-call skipping" in _field(sandeep_block, "LAST COMMITTED")
    # DONE RECENTLY has the recent done task.
    assert "Debt misclassification RCA" in _field(sandeep_block, "DONE RECENTLY")

    # Pankaj: blocked task under BLOCKED with the blocker reason annotation.
    pankaj_block = _person_block(pp, "Pankaj")
    assert "Android build" in _field(pankaj_block, "BLOCKED")
    assert "Play Store review pending" in _field(pankaj_block, "BLOCKED")
    assert "Returning-user UI" in _field(pankaj_block, "NOW")

    # Abhinav: active no-due -> NOW only, LAST COMMITTED blank, old done excluded.
    abhinav_block = _person_block(pp, "Abhinav")
    assert "PMF card development" in _field(abhinav_block, "NOW")
    assert _field(abhinav_block, "LAST COMMITTED") == ""
    assert "Ancient shipped thing" not in pp  # 30-day-old done excluded


def test_last_committed_blank_when_no_due():
    tmp, db, state, memory = _fixture()
    out = g.generate(db, state, memory, now=NOW)
    pp = _extract_section(out, "Per Person")
    abhinav_block = _person_block(pp, "Abhinav")
    assert _field(abhinav_block, "LAST COMMITTED") == ""


# ---------------------------------------------------------------------------
# Active Blockers rendering
# ---------------------------------------------------------------------------
def test_active_blockers_table_owner_and_days():
    tmp, db, state, memory = _fixture()
    out = g.generate(db, state, memory, now=NOW)
    ab = _extract_section(out, "Active Blockers")

    # Header row preserved.
    assert "| Blocker | Days Active | Owner | Status |" in ab
    # Seeded active blocker present with owner name "Pankaj" and 13 days active.
    rows = [ln for ln in ab.splitlines() if "Play Store review pending" in ln]
    assert len(rows) == 1, f"expected exactly one blocker row, got: {rows}"
    row = rows[0]
    assert "Pankaj" in row
    assert "| 13 |" in row
    # Resolved blocker excluded.
    assert "Already resolved" not in ab


# ---------------------------------------------------------------------------
# Splice integrity — header + other sections untouched
# ---------------------------------------------------------------------------
def test_header_preserved():
    tmp, db, state, memory = _fixture()
    out = g.generate(db, state, memory, now=NOW)
    # generate() does NOT bump the header (that's a main() non-dry-run concern).
    assert "# Last compiled: 2026-05-29 13:00 UTC (RECONSTRUCTED note here)" in out
    # First line unchanged too.
    assert out.splitlines()[0] == "# DAILY_STATE.md — Single Source of Truth"


def test_other_sections_byte_for_byte_unchanged():
    tmp, db, state, memory = _fixture()
    out = g.generate(db, state, memory, now=NOW)
    for name in ("Current Focus", "This Week's Goals", "Active Decisions", "Metrics", "Upcoming"):
        before = _extract_section(MINIMAL_STATE, name)
        after = _extract_section(out, name)
        assert before == after, f"section '{name}' changed:\n--BEFORE--\n{before}\n--AFTER--\n{after}"


def test_stale_generated_content_is_replaced():
    tmp, db, state, memory = _fixture()
    out = g.generate(db, state, memory, now=NOW)
    # Old Per Person + Active Blockers content must be gone.
    assert "Stale Person" not in out
    assert "stale blocker" not in out


def test_splice_inserts_missing_section_in_canonical_order():
    # A DAILY_STATE.md with NO "## Active Blockers" should get one inserted
    # between Active Decisions and Metrics.
    no_blockers = MINIMAL_STATE.replace(
        "## Active Blockers\n"
        "| Blocker | Days Active | Owner | Status |\n"
        "|---------|------------|-------|--------|\n"
        "| stale blocker | 99 | Nobody | should be replaced |\n\n",
        "",
    )
    assert "## Active Blockers" not in no_blockers
    spliced = g.splice_sections(no_blockers, "## Per Person\n\n(none)\n", "## Active Blockers\n\n(none)\n")
    assert "## Active Blockers" in spliced
    # Order check: Active Decisions ... Active Blockers ... Metrics.
    i_dec = spliced.index("## Active Decisions")
    i_blk = spliced.index("## Active Blockers")
    i_met = spliced.index("## Metrics")
    assert i_dec < i_blk < i_met, "Active Blockers not inserted in canonical order"


# ---------------------------------------------------------------------------
# Read-only invariant
# ---------------------------------------------------------------------------
def test_graph_not_mutated():
    tmp, db, state, memory = _fixture()
    before = _row_counts(db)
    g.generate(db, state, memory, now=NOW)
    after = _row_counts(db)
    assert before == after, f"DB row counts changed: {before} -> {after}"
    # Sanity: we actually seeded data (6 tasks, 2 blockers, 0 events).
    assert before == (6, 2, 0)


# ---------------------------------------------------------------------------
# Header bump (the only write path, exercised without touching the real file)
# ---------------------------------------------------------------------------
def test_update_last_compiled_preserves_format_and_note():
    bumped = g.update_last_compiled(MINIMAL_STATE, now=NOW)
    line = [ln for ln in bumped.splitlines() if ln.startswith("# Last compiled:")][0]
    assert line == "# Last compiled: 2026-06-01 12:00 UTC (RECONSTRUCTED note here)"


def test_dry_run_does_not_write(capsys_unavailable=True):
    tmp, db, state, memory = _fixture()
    original = Path(state).read_text(encoding="utf-8")
    rc = g.main(["--db", db, "--state", state, "--memory", memory, "--dry-run"])
    assert rc == 0
    # File must be byte-for-byte unchanged after a dry run.
    assert Path(state).read_text(encoding="utf-8") == original


def test_real_write_bumps_header_and_writes_file():
    tmp, db, state, memory = _fixture()
    rc = g.main(["--db", db, "--state", state, "--memory", memory])
    assert rc == 0
    written = Path(state).read_text(encoding="utf-8")
    # Header bumped to a fresh timestamp (year 2026, the run year) and file changed.
    assert "# Last compiled:" in written
    assert "Stale Person" not in written
    assert "### Sandeep (AI Engineer)" in written


# ---------------------------------------------------------------------------
# Tiny markdown section helpers (test-local, not under test)
# ---------------------------------------------------------------------------
def _extract_section(md: str, heading_text: str) -> str:
    """Return the body of a `## heading_text` section (heading line excluded),
    bounded by the next `## ` heading. Used only by tests.
    """
    lines = md.split("\n")
    start = None
    target = f"## {heading_text}"
    for i, ln in enumerate(lines):
        s = ln.rstrip()
        if s == target or s.startswith(target + " "):
            start = i
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j].rstrip()
        if s.startswith("## ") and not s.startswith("### "):
            end = j
            break
    return "\n".join(lines[start + 1 : end]).strip("\n")


def _person_block(per_person_body: str, first_name: str) -> str:
    """Return the lines for a single `### <first_name> ...` person block."""
    lines = per_person_body.split("\n")
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(f"### {first_name} ") or ln.rstrip() == f"### {first_name}":
            start = i
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("### "):
            end = j
            break
    return "\n".join(lines[start:end])


def _field(person_block: str, field_name: str) -> str:
    """Return the value text of a `- **FIELD:** value` line within a person block."""
    marker = f"**{field_name}:**"
    for ln in person_block.split("\n"):
        if marker in ln:
            return ln.split(marker, 1)[1].strip()
    return ""


if __name__ == "__main__":
    import inspect

    test_funcs = [
        obj
        for name, obj in inspect.getmembers(sys.modules[__name__])
        if inspect.isfunction(obj) and name.startswith("test_")
    ]
    failed = 0
    for fn in test_funcs:
        try:
            fn()
            print(f"PASS: {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL: {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(test_funcs) - failed}/{len(test_funcs)} passed")
    sys.exit(1 if failed else 0)
