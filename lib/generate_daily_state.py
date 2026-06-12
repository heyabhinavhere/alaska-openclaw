"""generate_daily_state.py — render DAILY_STATE.md sections from the task graph.

Phase E groundwork: DAILY_STATE.md is becoming a *generated view* of the SQLite
task graph rather than a hand-authored document. This module renders two of its
sections — `## Per Person` and `## Active Blockers` — directly from the `tasks`
and `blockers` tables, then splices them into the existing file, leaving the
`# Last compiled:` header and every other section byte-for-byte intact.

IMPORTANT — parity / dry-run first. This tool SHIPS NOW but is intended to run in
parity (`--dry-run`) mode while Meeting Intelligence still authors those sections.
The cutover (MI stops authoring Per Person / Active Blockers and this generator
becomes authoritative) is a SEPARATE later change. Shipping this module does NOT
change any skill's behavior on its own — nothing invokes it yet.

READ-ONLY against the graph. Every graph query here is a SELECT. This module never
issues INSERT/UPDATE/DELETE against tasks, blockers, task_events, or any other
table. The only thing it writes is the DAILY_STATE.md file (and only on a real,
non-dry-run `main()` invocation).

Field → graph mapping for `## Per Person` (each person = `### <Name> (<role>)`):
  - **NOW:**            active tasks — status IN ('active', 'pending_acceptance').
  - **LAST COMMITTED:** the subset of those active tasks that carry a `due_at`
        (i.e. work the owner has committed to with a deadline). There is no clean
        graph source for "what someone last verbally committed to at standup", so
        we approximate it with deadline-bearing active work. Rendered blank when
        the owner has no deadline-bearing active task. (Documented per task spec.)
  - **DONE RECENTLY:**  status='done' AND done_at >= now - 3 days.
  - **BLOCKED:**        status='blocked' (annotated with the blocker reason/title
        when a blocker links the task via blocking_task_ids).

`## Active Blockers` table (`Blocker | Days Active | Owner | Status`) is rendered
from blockers WHERE status='active'. Days Active = floor(now - raised_at) in days;
Owner = roster name for owner_slack_id (raw id if unknown); Status = 'active'
(plus the linked task titles resolved from blocking_task_ids, when present).

Runnable directly: `python3 lib/generate_daily_state.py --dry-run`.

The production image runs Python 3.11; `from __future__ import annotations` keeps
this importable on the macOS system Python 3.9 used in local dev (PEP 604 unions
in annotations become lazy strings).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Canonical section order for DAILY_STATE.md. Used to insert a section in the
# right place if it is somehow missing from the existing file.
CANONICAL_ORDER = [
    "Current Focus",
    "This Week's Goals",
    "Per Person",
    "Active Decisions",
    "Active Blockers",
    "Metrics",
    "Upcoming",
]

# Format of the staleness header line. Readers parse "# Last compiled: <ts>" and
# refuse to quote dated commitments when it is >48h old, so the prefix and the
# "%Y-%m-%d %H:%M UTC" timestamp shape must be preserved on rewrite.
LAST_COMPILED_PREFIX = "# Last compiled:"
LAST_COMPILED_TS_FMT = "%Y-%m-%d %H:%M UTC"

DEFAULT_DB = "/data/queue/alaska.db"
# Two common workspace locations; main() picks the first that exists.
DEFAULT_STATE_CANDIDATES = [
    "workspace/DAILY_STATE.md",
    "/root/.openclaw/workspace/DAILY_STATE.md",
]
DEFAULT_MEMORY_CANDIDATES = [
    "workspace/MEMORY.md",
    "/root/.openclaw/workspace/MEMORY.md",
]


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------
def load_roster(memory_path: str) -> Dict[str, Dict[str, str]]:
    """Parse the MEMORY.md "Team Roster" markdown table.

    Returns {slack_id: {"name": first_name, "role": role}}. Rows whose Slack ID
    is not a real id (e.g. the external "_external_" marker) are skipped — they
    have no graph tasks anyway. Unknown ids encountered later are NOT dropped;
    callers render them as the raw id (see resolve_name).
    """
    text = Path(memory_path).read_text(encoding="utf-8")
    roster: Dict[str, Dict[str, str]] = {}
    # Slack IDs look like U07GKLVA9FE (U + 8-12 alphanumerics).
    slack_re = re.compile(r"^U[A-Z0-9]{8,}$")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # Roster columns: First Name | Full Name | Slack ID | Notion ID | Role | ...
        if len(cells) < 5:
            continue
        first_name, _full, slack_id, _notion, role = cells[0], cells[1], cells[2], cells[3], cells[4]
        # Strip any backtick wrapping that markdown tables sometimes carry.
        slack_id = slack_id.strip("`").strip()
        if not slack_re.match(slack_id):
            continue  # header row, separator row, external/"_n/a_" rows
        roster[slack_id] = {"name": first_name, "role": role}
    return roster


def resolve_name(slack_id: str, roster: Dict[str, Dict[str, str]]) -> str:
    """Owner display name; falls back to the raw slack id (never dropped)."""
    entry = roster.get(slack_id)
    return entry["name"] if entry else slack_id


def resolve_role(slack_id: str, roster: Dict[str, Dict[str, str]]) -> str:
    entry = roster.get(slack_id)
    return entry["role"] if entry else ""


# ---------------------------------------------------------------------------
# Graph queries (READ-ONLY — SELECT only)
# ---------------------------------------------------------------------------
def _connect_readonly(db_path: str) -> sqlite3.Connection:
    """Open the DB read-only when possible (file:...?mode=ro), else fall back to
    a normal connection. We still only ever issue SELECTs regardless.
    """
    try:
        uri = f"file:{Path(db_path).as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _fetch_snooze_dates(conn: sqlite3.Connection) -> Dict[str, str]:
    """task_id -> snoozed_until from follow-through's `snoozes` table.

    That table is created lazily by the follow-through skill, so it may not
    exist on a given DB — tolerate its absence (SELECT-only either way).
    """
    try:
        rows = conn.execute("SELECT task_id, snoozed_until FROM snoozes").fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r["task_id"]: r["snoozed_until"] for r in rows if r["snoozed_until"]}


def fetch_standup_touched(conn: sqlite3.Connection, now: Optional[datetime] = None, cutoff_hours: int = 36) -> set:
    """task_ids touched by the standup-reply path within the last cycle.

    Two signals (parity redesign 2026-06-12 — replies are the team's primary
    commitment record, so LAST COMMITTED must mean "what the latest reply said"):
      1. tasks created with source='standup_reply' inside the cutoff window;
      2. tasks whose task_events context carries the 'standup' marker inside the
         window (task-handler stamps the invocation source into event context).
    SELECT-only; tolerant of schema drift.
    """
    now = _now(now)
    cutoff = (now - timedelta(hours=cutoff_hours)).strftime("%Y-%m-%d %H:%M:%S")
    touched: set = set()
    try:
        for r in conn.execute(
            "SELECT task_id FROM tasks WHERE source = 'standup_reply' AND created_at >= ?",
            (cutoff,),
        ):
            touched.add(r["task_id"])
        for r in conn.execute(
            "SELECT DISTINCT task_id FROM task_events WHERE created_at >= ? AND context LIKE '%standup%'",
            (cutoff,),
        ):
            touched.add(r["task_id"])
    except sqlite3.OperationalError:
        pass
    return touched


def _due_is_current(due_at: Optional[str], now: datetime) -> bool:
    """True when due_at parses and is NOT stale — today-ish or in the future.

    A deadline that blew past more than a day ago is overdue history, not a
    commitment; rendering it as LAST COMMITTED misleads (parity 2026-06-12:
    two week-old overdue tasks rendered as Sandeep's "commitments").
    """
    if not due_at:
        return False
    dt = _parse_dt(due_at)
    return dt is not None and dt >= now - timedelta(days=1)


def fetch_owner_tasks(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Dict[str, list]]:
    """Group tasks by owner into {slack_id: {"now", "last_committed", "done", "blocked"}}.

    All reads are SELECT-only. `now` is injectable for deterministic tests; the
    done-recent cutoff is now - 3 days.

    Parity redesign (2026-06-12):
      * `snoozed` tasks are INCLUDED in NOW with a "(snoozed until …)" tag —
        an invisible snooze buried Nilesh's two launch-critical tasks.
      * LAST COMMITTED = standup-touched tasks (primary; see
        fetch_standup_touched) plus active tasks with a CURRENT deadline
        (_due_is_current) — never bare/stale due_at.
    """
    now = _now(now)
    snooze_dates = _fetch_snooze_dates(conn)
    standup_touched = fetch_standup_touched(conn, now=now)
    # We fetch all relevant statuses and apply the done-recent (>= now-3d) cutoff
    # in Python via _is_recent, to keep date math identical across DB datetime shapes.
    rows = conn.execute(
        "SELECT task_id, title, status, owner_slack_id, due_at, done_at "
        "FROM tasks "
        "WHERE status IN ('active', 'pending_acceptance', 'blocked', 'done', 'snoozed')"
    ).fetchall()

    by_owner: Dict[str, Dict[str, list]] = {}
    for r in rows:
        owner = r["owner_slack_id"]
        bucket = by_owner.setdefault(
            owner, {"now": [], "last_committed": [], "done": [], "blocked": []}
        )
        status = r["status"]
        if status in ("active", "pending_acceptance"):
            bucket["now"].append(r["title"])
            if r["task_id"] in standup_touched or _due_is_current(r["due_at"], now):
                bucket["last_committed"].append(r["title"])
        elif status == "snoozed":
            until = snooze_dates.get(r["task_id"])
            tag = f"(snoozed until {str(until)[:10]})" if until else "(snoozed)"
            bucket["now"].append(f"{r['title']} {tag}")
        elif status == "blocked":
            bucket["blocked"].append({"task_id": r["task_id"], "title": r["title"]})
            if r["task_id"] in standup_touched:
                bucket["last_committed"].append(r["title"])
        elif status == "done":
            if _is_recent(r["done_at"], now):
                bucket["done"].append(r["title"])
    # Drop owners that ended up with nothing in any bucket (e.g. only old done).
    return {o: b for o, b in by_owner.items() if any(b.values())}


def _is_recent(done_at: Optional[str], now: datetime, days: int = 3) -> bool:
    """True when done_at parses and is within `days` of now (inclusive)."""
    if not done_at:
        return False
    dt = _parse_dt(done_at)
    if dt is None:
        return False
    delta = now - dt
    return 0 <= delta.total_seconds() <= days * 86400 + 1  # +1s slack for equality


def fetch_active_blockers(conn: sqlite3.Connection, now: Optional[datetime] = None) -> List[dict]:
    """Active blockers as [{title, days_active, owner_slack_id, blocking_titles}].

    SELECT-only. Resolves blocking_task_ids (a JSON array of task_ids) to task
    titles via a second SELECT.
    """
    now = _now(now)
    rows = conn.execute(
        "SELECT blocker_id, title, blocking_task_ids, owner_slack_id, raised_at, status "
        "FROM blockers WHERE status = 'active' ORDER BY raised_at ASC"
    ).fetchall()
    out: List[dict] = []
    for r in rows:
        meta = _resolve_blocking_meta(conn, r["blocking_task_ids"])
        # Zombie filter (parity 2026-06-12): a blocker whose linked tasks are ALL
        # done/dropped blocks nothing — skip it rather than render a phantom.
        # Blockers with NO linked tasks (chronic/platform blockers) always render.
        if meta and all(m["status"] in ("done", "dropped") for m in meta):
            continue
        raised = _parse_dt(r["raised_at"])
        days_active = max(0, (now - raised).days) if raised else None
        out.append(
            {
                "title": r["title"],
                "days_active": days_active,
                "owner_slack_id": r["owner_slack_id"],
                # Show only the still-live linked tasks in the "blocking:" cell.
                "blocking_titles": [m["title"] for m in meta if m["status"] not in ("done", "dropped")],
            }
        )
    return out


def _resolve_blocking_meta(conn: sqlite3.Connection, blocking_task_ids: Optional[str]) -> List[dict]:
    """Resolve a blockers.blocking_task_ids JSON array → [{task_id, title, status}].

    Order-preserving; ids with no matching task are skipped. Status is carried so
    callers can detect zombie blockers (all linked tasks done/dropped).
    """
    if not blocking_task_ids:
        return []
    try:
        ids = json.loads(blocking_task_ids)
    except (ValueError, TypeError):
        return []
    if not isinstance(ids, list) or not ids:
        return []
    ids = [str(i) for i in ids]
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT task_id, title, status FROM tasks WHERE task_id IN ({placeholders})", ids
    ).fetchall()
    by_id = {row["task_id"]: {"task_id": row["task_id"], "title": row["title"], "status": row["status"]} for row in rows}
    return [by_id[i] for i in ids if i in by_id]


def fetch_person_status(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, str]:
    """slack_id -> availability line from person_status (migration 0008).

    Rows expire when until_date passes (1-day grace); the table may not exist on
    older DBs — tolerate absence. SELECT-only.
    """
    now = _now(now)
    try:
        rows = conn.execute("SELECT slack_id, status_text, until_date FROM person_status").fetchall()
    except sqlite3.OperationalError:
        return {}
    out: Dict[str, str] = {}
    for r in rows:
        until = _parse_dt(r["until_date"]) if r["until_date"] else None
        if until is not None and until < now - timedelta(days=1):
            continue  # expired
        text = r["status_text"]
        if r["until_date"]:
            text = f"{text} (until {str(r['until_date'])[:10]})"
        out[r["slack_id"]] = text
    return out


def _parse_dt(value: str) -> Optional[datetime]:
    """Parse the datetime shapes SQLite hands back (CURRENT_TIMESTAMP =
    'YYYY-MM-DD HH:MM:SS', or ISO-8601). Returns an aware UTC datetime or None.
    """
    if not value:
        return None
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Try ISO first (handles 'T' separator and offsets), then SQLite's space form.
    for parser in (datetime.fromisoformat,):
        try:
            dt = parser(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _fmt_list(titles: List[str]) -> str:
    return "; ".join(titles) if titles else ""


def render_per_person(
    by_owner: Dict[str, Dict[str, list]],
    active_blockers: List[dict],
    roster: Dict[str, Dict[str, str]],
    person_status: Optional[Dict[str, str]] = None,
) -> str:
    """Render the `## Per Person` section body (heading included).

    One `### <Name> (<role>)` block per owner that has any task, with NOW /
    LAST COMMITTED / DONE RECENTLY / BLOCKED fields. Owners are ordered by their
    position in the roster (so the output is stable), with any unknown ids after.
    """
    # Build a reason lookup keyed by blocked task title (titles are what we carry
    # in the NOW/BLOCKED buckets) so BLOCKED lines can show the blocker reason.
    reason_by_blocked_title: Dict[str, str] = {}
    for b in active_blockers:
        for t in b["blocking_titles"]:
            reason_by_blocked_title.setdefault(t, b["title"])

    # Stable ordering: roster order first, then any unknown owners alphabetically.
    roster_order = list(roster.keys())

    def sort_key(slack_id: str):
        if slack_id in roster_order:
            return (0, roster_order.index(slack_id))
        return (1, slack_id)

    person_status = person_status or {}
    # Include people who have an availability status but no tasks at all.
    all_ids = set(by_owner.keys()) | set(person_status.keys())

    lines: List[str] = ["## Per Person", ""]
    for slack_id in sorted(all_ids, key=sort_key):
        bucket = by_owner.get(
            slack_id, {"now": [], "last_committed": [], "done": [], "blocked": []}
        )
        name = resolve_name(slack_id, roster)
        role = resolve_role(slack_id, roster)
        heading = f"### {name} ({role})" if role else f"### {name}"
        lines.append(heading)

        if slack_id in person_status:
            lines.append(f"- **STATUS:** {person_status[slack_id]}")
        lines.append(f"- **NOW:** {_fmt_list(bucket['now'])}")
        lines.append(f"- **LAST COMMITTED:** {_fmt_list(bucket['last_committed'])}")
        lines.append(f"- **DONE RECENTLY:** {_fmt_list(bucket['done'])}")

        blocked_parts: List[str] = []
        for item in bucket["blocked"]:
            title = item["title"]
            reason = reason_by_blocked_title.get(title)
            blocked_parts.append(f"{title} ({reason})" if reason else title)
        lines.append(f"- **BLOCKED:** {'; '.join(blocked_parts)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_blockers(active_blockers: List[dict], roster: Dict[str, Dict[str, str]]) -> str:
    """Render the `## Active Blockers` section body (heading + markdown table)."""
    lines: List[str] = ["## Active Blockers", ""]
    lines.append("| Blocker | Days Active | Owner | Status |")
    lines.append("|---------|------------|-------|--------|")
    for b in active_blockers:
        days = "?" if b["days_active"] is None else str(b["days_active"])
        owner = resolve_name(b["owner_slack_id"], roster) if b["owner_slack_id"] else ""
        status = "active"
        if b["blocking_titles"]:
            status = "active — blocking: " + ", ".join(b["blocking_titles"])
        blocker_cell = _escape_pipes(b["title"])
        lines.append(f"| {blocker_cell} | {days} | {_escape_pipes(owner)} | {_escape_pipes(status)} |")
    return "\n".join(lines).rstrip() + "\n"


def _escape_pipes(s: str) -> str:
    """A literal pipe inside a markdown table cell must be escaped."""
    return s.replace("|", "\\|")


# ---------------------------------------------------------------------------
# Splicing
# ---------------------------------------------------------------------------
def _section_bounds(lines: List[str], heading_text: str) -> Optional[tuple]:
    """Return (start, end) line indices for a `## <heading_text>` section.

    `start` is the heading line index; `end` is the index of the next line that
    begins a new `## ` section (or len(lines) if the section runs to EOF). The
    body is lines[start:end]. Returns None if the heading is absent.
    """
    start = None
    target = f"## {heading_text}"
    for i, line in enumerate(lines):
        if line.rstrip() == target or line.rstrip().startswith(target + " "):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        # A new section is any line beginning with "## " but NOT "### ".
        stripped = lines[j].rstrip("\n")
        if stripped.startswith("## ") and not stripped.startswith("### "):
            end = j
            break
    return (start, end)


def _insertion_index(lines: List[str], heading_text: str) -> int:
    """Where to insert a missing section so canonical order is preserved.

    Returns the line index at which to splice the new section. We find the
    earliest already-present section that comes *after* heading_text in
    CANONICAL_ORDER and insert before it; if none is present we append at EOF.
    """
    try:
        my_rank = CANONICAL_ORDER.index(heading_text)
    except ValueError:
        return len(lines)
    later = CANONICAL_ORDER[my_rank + 1 :]
    for name in later:
        bounds = _section_bounds(lines, name)
        if bounds is not None:
            return bounds[0]
    return len(lines)


def _replace_or_insert(md: str, heading_text: str, new_block: str) -> str:
    """Replace the `## heading_text` section body with new_block, or insert it in
    canonical order when absent. new_block must include its own heading line.
    """
    # Normalize new_block to end with exactly one trailing newline and a blank
    # separator line after it, so adjacent sections stay visually separated.
    block = new_block.rstrip("\n") + "\n"
    lines = md.split("\n")
    bounds = _section_bounds(lines, heading_text)
    block_lines = block.split("\n")
    # split() on a string ending in "\n" yields a trailing "" — drop it; we manage
    # separators explicitly.
    if block_lines and block_lines[-1] == "":
        block_lines = block_lines[:-1]

    if bounds is not None:
        start, end = bounds
        # Preserve a single blank line after the block (consume any blanks that
        # were already part of the old body's tail; re-add exactly one if there
        # is a following section).
        replacement = list(block_lines)
        if end < len(lines):
            replacement.append("")  # blank line before the next section
        new_lines = lines[:start] + replacement + lines[end:]
        return "\n".join(new_lines)

    # Missing — insert in canonical order.
    idx = _insertion_index(lines, heading_text)
    insertion = list(block_lines) + [""]
    if idx >= len(lines):
        # Append at EOF; ensure a separating blank line before it.
        tail = lines[:]
        if tail and tail[-1].strip() != "":
            tail.append("")
        new_lines = tail + block_lines + [""]
        return "\n".join(new_lines).rstrip("\n") + "\n"
    new_lines = lines[:idx] + insertion + lines[idx:]
    return "\n".join(new_lines)


def splice_sections(existing_md: str, new_per_person: str, new_blockers: str) -> str:
    """Splice the two generated sections into existing_md.

    Replaces ONLY the bodies of `## Per Person` and `## Active Blockers` (each
    bounded by its heading and the next `## ` heading). The `# Last compiled:`
    header and all other sections (Current Focus, This Week's Goals, Active
    Decisions, Metrics, Upcoming) are left untouched. Missing sections are
    inserted in canonical order.
    """
    result = _replace_or_insert(existing_md, "Per Person", new_per_person)
    result = _replace_or_insert(result, "Active Blockers", new_blockers)
    return result


def update_last_compiled(md: str, now: Optional[datetime] = None) -> str:
    """Rewrite the `# Last compiled: <ts>` header line, preserving everything on
    the line after the timestamp (e.g. a "(RECONSTRUCTED ...)" suffix is dropped
    only if it was part of the timestamp; we keep any parenthetical note).
    """
    now = _now(now)
    ts = now.strftime(LAST_COMPILED_TS_FMT)
    lines = md.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(LAST_COMPILED_PREFIX):
            # Keep any trailing parenthetical note after the timestamp.
            note_match = re.search(r"\((.*)\)\s*$", line)
            note = f" ({note_match.group(1)})" if note_match else ""
            lines[i] = f"{LAST_COMPILED_PREFIX} {ts}{note}"
            break
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def generate(db_path: str, state_path: str, memory_path: str, now: Optional[datetime] = None) -> str:
    """Produce the spliced DAILY_STATE.md content (no file write, no header bump).

    Read-only against the graph. Returns the new markdown string.
    """
    roster = load_roster(memory_path)
    conn = _connect_readonly(db_path)
    try:
        by_owner = fetch_owner_tasks(conn, now=now)
        active_blockers = fetch_active_blockers(conn, now=now)
        person_status = fetch_person_status(conn, now=now)
    finally:
        conn.close()
    per_person = render_per_person(by_owner, active_blockers, roster, person_status)
    blockers = render_blockers(active_blockers, roster)
    existing = Path(state_path).read_text(encoding="utf-8")
    return splice_sections(existing, per_person, blockers)


def _first_existing(candidates: List[str]) -> str:
    for c in candidates:
        if Path(c).exists():
            return c
    return candidates[0]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render DAILY_STATE.md Per Person + Active Blockers from the task graph."
    )
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite DB path (default: {DEFAULT_DB})")
    parser.add_argument(
        "--state",
        default=None,
        help="DAILY_STATE.md path (default: first of workspace/ or /root/.openclaw/workspace/)",
    )
    parser.add_argument(
        "--memory",
        default=None,
        help="MEMORY.md path for the roster (default: alongside DAILY_STATE.md)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the spliced result to stdout; do NOT write the file.",
    )
    args = parser.parse_args(argv)

    state_path = args.state or _first_existing(DEFAULT_STATE_CANDIDATES)
    memory_path = args.memory or _first_existing(DEFAULT_MEMORY_CANDIDATES)

    spliced = generate(args.db, state_path, memory_path)

    if args.dry_run:
        # Parity mode: show what WOULD be written, leave the file untouched.
        print(spliced)
        return 0

    # Real write: bump the staleness header, then persist.
    final = update_last_compiled(spliced)
    Path(state_path).write_text(final, encoding="utf-8")
    print(f"Wrote {state_path}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
