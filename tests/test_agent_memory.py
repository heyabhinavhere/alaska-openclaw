"""Tests for Alaska's agent_memory — her private working-memory store (migration 0006).

Covers the schema (table/index/trigger + CHECK constraints), the exact SQL shapes
documented in skills/agent-memory/SKILL.md (remember / recall / list_self_tasks /
complete / archive), the auto-update trigger, and — most importantly — the
PRIVACY INVARIANT that team-facing readers never reference the agent_memory table.

Stdlib only. Runnable directly:
    python3 tests/test_agent_memory.py
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0006_agent_memory.sql"
SKILLS_DIR = REPO_ROOT / "skills"


def _db() -> sqlite3.Connection:
    """Apply migration 0006 to a fresh in-memory DB and return the connection."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def _next_mem_id(conn: sqlite3.Connection) -> str:
    """The exact M-N id-generation expression from the skill's `remember` op."""
    (mem_id,) = conn.execute(
        "SELECT 'M-' || COALESCE(MAX(CAST(SUBSTR(mem_id, 3) AS INTEGER)) + 1, 1) "
        "FROM agent_memory;"
    ).fetchone()
    return mem_id


def _remember(
    conn: sqlite3.Connection,
    kind: str,
    title: str,
    content: str,
    recall_cue: str = "",
    source: str = "self",
    due_at=None,
) -> str:
    """Mirror the skill's `remember` INSERT; return the new mem_id."""
    mem_id = _next_mem_id(conn)
    conn.execute(
        "INSERT INTO agent_memory "
        "(mem_id, kind, title, content, recall_cue, status, source, source_ref, due_at) "
        "VALUES (?, ?, ?, ?, ?, 'open', ?, NULL, ?);",
        (mem_id, kind, title, content, recall_cue, source, due_at),
    )
    conn.commit()
    return mem_id


# --- schema -----------------------------------------------------------------

def test_migration_applies_clean_and_is_idempotent():
    conn = _db()
    # Re-running is a no-op (CREATE IF NOT EXISTS) — must not raise.
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()


def test_table_indexes_and_trigger_exist():
    conn = _db()
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE name IN "
            "('agent_memory','idx_agent_memory_kind_status',"
            "'idx_agent_memory_recall','trg_agent_memory_updated_at');"
        ).fetchall()
    }
    for expected in (
        "agent_memory",
        "idx_agent_memory_kind_status",
        "idx_agent_memory_recall",
        "trg_agent_memory_updated_at",
    ):
        assert expected in names, f"missing schema object: {expected}"


def test_kind_check_constraint_rejects_invalid():
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO agent_memory (mem_id, kind, title, content) "
            "VALUES ('M-1', 'todo', 't', 'c');"  # 'todo' is not a valid kind
        )
        raise AssertionError("invalid kind was accepted")
    except sqlite3.IntegrityError:
        pass


def test_status_check_constraint_rejects_invalid():
    conn = _db()
    try:
        conn.execute(
            "INSERT INTO agent_memory (mem_id, kind, title, content, status) "
            "VALUES ('M-1', 'note', 't', 'c', 'pending');"  # 'pending' invalid
        )
        raise AssertionError("invalid status was accepted")
    except sqlite3.IntegrityError:
        pass


def test_mem_id_is_unique():
    conn = _db()
    _remember(conn, "note", "first", "c")
    try:
        conn.execute(
            "INSERT INTO agent_memory (mem_id, kind, title, content) "
            "VALUES ('M-1', 'note', 'dup', 'c');"
        )
        raise AssertionError("duplicate mem_id was accepted")
    except sqlite3.IntegrityError:
        pass


# --- remember + M-N id generation -------------------------------------------

def test_status_defaults_to_open():
    conn = _db()
    mem_id = _remember(conn, "reference", "CTA table", "row1; row2", "cta, chat")
    (status,) = conn.execute(
        "SELECT status FROM agent_memory WHERE mem_id=?;", (mem_id,)
    ).fetchone()
    assert status == "open", status


def test_mem_id_sequences_numerically_not_lexically():
    conn = _db()
    # Generate M-1 .. M-10 and confirm the 11th is M-11 (CAST -> numeric MAX),
    # NOT M-2 (which a lexical MAX of 'M-9' vs 'M-10' would wrongly yield).
    ids = [_remember(conn, "note", f"n{i}", "c") for i in range(10)]
    assert ids[0] == "M-1", ids[0]
    assert ids[9] == "M-10", ids[9]
    assert _next_mem_id(conn) == "M-11", _next_mem_id(conn)


def test_first_mem_id_on_empty_table_is_M1():
    conn = _db()
    assert _next_mem_id(conn) == "M-1"


# --- recall -----------------------------------------------------------------

def _recall(conn: sqlite3.Connection, kw: str):
    """The exact verified recall shape from the skill."""
    return conn.execute(
        "SELECT mem_id,kind,title,content FROM agent_memory "
        "WHERE status!='archived' "
        "AND (recall_cue LIKE ? OR title LIKE ? OR content LIKE ?) "
        "ORDER BY updated_at DESC;",
        (f"%{kw}%", f"%{kw}%", f"%{kw}%"),
    ).fetchall()


def test_recall_matches_on_recall_cue():
    conn = _db()
    mem_id = _remember(conn, "reference", "CTA reference", "the table body", "cta, chat, agent")
    rows = _recall(conn, "cta")
    assert [r[0] for r in rows] == [mem_id], rows


def test_recall_matches_on_title():
    conn = _db()
    mem_id = _remember(conn, "reference", "Plaid retry sequence", "body", "")
    rows = _recall(conn, "Plaid")
    assert [r[0] for r in rows] == [mem_id], rows


def test_recall_matches_on_content():
    # The fixture is deliberately a PRIVATE note (Alaska's own watch-item) — a
    # team-canonical domain fact like "we use Twilio" belongs in the KB, not here
    # (skill boundary test #1 / anti-pattern #3).
    conn = _db()
    mem_id = _remember(conn, "note", "misc", "watch the Railway deploy after Friday's push", "")
    rows = _recall(conn, "Railway")
    assert [r[0] for r in rows] == [mem_id], rows


def test_recall_excludes_archived():
    conn = _db()
    mem_id = _remember(conn, "reference", "old CTA table", "stale body", "cta")
    # archive it
    conn.execute("UPDATE agent_memory SET status='archived' WHERE mem_id=?;", (mem_id,))
    conn.commit()
    assert _recall(conn, "cta") == [], "archived row should not surface in recall"


def test_recall_orders_newest_first():
    conn = _db()
    a = _remember(conn, "note", "cta a", "c", "cta")
    b = _remember(conn, "note", "cta b", "c", "cta")
    c = _remember(conn, "note", "cta c", "c", "cta")
    # Set distinct updated_at directly. Because this UPDATE *changes* updated_at,
    # OLD.updated_at != NEW.updated_at, so the auto-bump trigger does NOT fire and
    # our explicit values stick — giving a deterministic order to assert.
    conn.execute("UPDATE agent_memory SET updated_at='2020-01-01 00:00:00' WHERE mem_id=?;", (a,))
    conn.execute("UPDATE agent_memory SET updated_at='2022-01-01 00:00:00' WHERE mem_id=?;", (b,))
    conn.execute("UPDATE agent_memory SET updated_at='2024-01-01 00:00:00' WHERE mem_id=?;", (c,))
    conn.commit()
    rows = _recall(conn, "cta")
    assert [r[0] for r in rows] == [c, b, a], rows


def test_recall_empty_when_no_match():
    conn = _db()
    _remember(conn, "note", "something", "unrelated body", "tag")
    assert _recall(conn, "nonexistent-topic") == []


def _recall_multi(conn: sqlite3.Connection, k1: str, k2: str):
    """The Phase-3 multi-keyword recall shape: 2 keywords OR'd across all 3 columns."""
    return conn.execute(
        "SELECT mem_id,kind,title,content FROM agent_memory "
        "WHERE status!='archived' AND ("
        "  recall_cue LIKE ? OR title LIKE ? OR content LIKE ?"
        "  OR recall_cue LIKE ? OR title LIKE ? OR content LIKE ?"
        ") ORDER BY updated_at DESC LIMIT 10;",
        (f"%{k1}%",) * 3 + (f"%{k2}%",) * 3,
    ).fetchall()


def test_multi_keyword_recall_or_semantics():
    """Two derived keywords retrieve rows matching EITHER; unrelated rows stay out."""
    conn = _db()
    a = _remember(conn, "reference", "CTA list", "body", "cta")
    b = _remember(conn, "note", "chat behavior", "body", "chat")
    _remember(conn, "note", "unrelated", "body", "plaid")
    rows = _recall_multi(conn, "cta", "chat")
    assert {r[0] for r in rows} == {a, b}, rows


def test_recall_limit_caps_at_ten_newest_first():
    """The recall LIMIT 10 returns the 10 most recently updated matches only."""
    conn = _db()
    ids = [_remember(conn, "note", f"cta note {i}", "c", "cta") for i in range(12)]
    # Pin deterministic, strictly increasing updated_at (changing the column
    # means OLD != NEW, so the auto-bump trigger does not override our values).
    for i, mem_id in enumerate(ids):
        conn.execute(
            "UPDATE agent_memory SET updated_at=? WHERE mem_id=?;",
            (f"2024-01-{i + 1:02d} 00:00:00", mem_id),
        )
    conn.commit()
    rows = _recall(conn, "cta")  # single-kw helper has no LIMIT — sanity first
    assert len(rows) == 12
    limited = conn.execute(
        "SELECT mem_id FROM agent_memory WHERE status!='archived' "
        "AND (recall_cue LIKE '%cta%' OR title LIKE '%cta%' OR content LIKE '%cta%') "
        "ORDER BY updated_at DESC LIMIT 10;"
    ).fetchall()
    assert len(limited) == 10
    assert [r[0] for r in limited] == [ids[i] for i in range(11, 1, -1)], limited


def test_supersede_archive_then_remember_leaves_one_live():
    """Supersede flow: archive the old row FIRST, then remember the new — recall sees only the new."""
    conn = _db()
    old = _remember(conn, "reference", "CTA list v1", "old body", "cta")
    conn.execute("UPDATE agent_memory SET status='archived' WHERE mem_id=?;", (old,))
    conn.commit()
    new = _remember(conn, "reference", "CTA list v2", "new body", "cta")
    rows = _recall(conn, "cta")
    assert [r[0] for r in rows] == [new], rows


# --- list_self_tasks --------------------------------------------------------

def test_list_self_tasks_only_open_self_tasks():
    conn = _db()
    st_open = _remember(conn, "self_task", "follow up with Sandeep", "Plaid keys")
    _remember(conn, "note", "a note", "not a self task")  # excluded: wrong kind
    st_done = _remember(conn, "self_task", "already done", "x")
    conn.execute("UPDATE agent_memory SET status='done' WHERE mem_id=?;", (st_done,))
    conn.commit()

    rows = conn.execute(
        "SELECT mem_id,title,due_at FROM agent_memory "
        "WHERE kind='self_task' AND status='open' "
        "ORDER BY COALESCE(due_at,created_at);"
    ).fetchall()
    assert [r[0] for r in rows] == [st_open], rows


def test_list_self_tasks_orders_dated_before_undated():
    conn = _db()
    undated = _remember(conn, "self_task", "no due date", "x")
    dated = _remember(conn, "self_task", "due soon", "x", due_at="2026-06-04 09:00:00")
    # created_at for `undated` is "now" (2026+), so the dated 2026-06-04 task sorts
    # alongside; pin created_at far in the future so COALESCE ordering is unambiguous.
    conn.execute("UPDATE agent_memory SET created_at='2099-01-01 00:00:00' WHERE mem_id=?;", (undated,))
    conn.commit()
    rows = conn.execute(
        "SELECT mem_id FROM agent_memory "
        "WHERE kind='self_task' AND status='open' "
        "ORDER BY COALESCE(due_at,created_at);"
    ).fetchall()
    assert [r[0] for r in rows] == [dated, undated], rows


# --- review (morning self-task sweep) ----------------------------------------

def test_review_orders_due_first_then_undated():
    """The review op's exact ORDER BY: due/overdue first, then future-dated, undated last."""
    conn = _db()
    undated = _remember(conn, "self_task", "no date", "x")
    future = _remember(conn, "self_task", "later", "x", due_at="2099-01-01 00:00:00")
    due = _remember(conn, "self_task", "now", "x", due_at="2020-01-01 00:00:00")
    rows = conn.execute(
        "SELECT mem_id FROM agent_memory "
        "WHERE kind='self_task' AND status='open' "
        "ORDER BY (due_at IS NULL), due_at, created_at;"
    ).fetchall()
    assert [r[0] for r in rows] == [due, future, undated], rows


def test_review_kb_proposal_cue_filter():
    """KB proposals are self_tasks tagged recall_cue='kb-proposal'; review bundles exactly those."""
    conn = _db()
    kb = _remember(conn, "self_task", "suggest Twilio A2P page to Abhinav", "c", "kb-proposal")
    _remember(conn, "self_task", "ordinary follow-up", "c", "deploy")
    rows = conn.execute(
        "SELECT mem_id FROM agent_memory "
        "WHERE kind='self_task' AND status='open' "
        "AND recall_cue LIKE '%kb-proposal%';"
    ).fetchall()
    assert [r[0] for r in rows] == [kb], rows


# --- complete / archive lifecycle -------------------------------------------

def test_complete_moves_self_task_to_done():
    conn = _db()
    mem_id = _remember(conn, "self_task", "check deploy", "tomorrow AM")
    conn.execute("UPDATE agent_memory SET status='done' WHERE mem_id=?;", (mem_id,))
    conn.commit()
    (status,) = conn.execute(
        "SELECT status FROM agent_memory WHERE mem_id=?;", (mem_id,)
    ).fetchone()
    assert status == "done"


def test_archive_moves_reference_to_archived():
    conn = _db()
    mem_id = _remember(conn, "reference", "superseded CTA", "old body", "cta")
    conn.execute("UPDATE agent_memory SET status='archived' WHERE mem_id=?;", (mem_id,))
    conn.commit()
    (status,) = conn.execute(
        "SELECT status FROM agent_memory WHERE mem_id=?;", (mem_id,)
    ).fetchone()
    assert status == "archived"


# --- trigger ----------------------------------------------------------------

def test_updated_at_trigger_bumps_on_status_change():
    conn = _db()
    mem_id = _remember(conn, "self_task", "t", "c")
    # Pin updated_at to an old value WITHOUT firing the trigger (changing the column
    # makes OLD != NEW, so the WHEN guard is false).
    conn.execute("UPDATE agent_memory SET updated_at='2020-01-01 00:00:00' WHERE mem_id=?;", (mem_id,))
    conn.commit()
    # Now a status-only update leaves updated_at untouched in the statement, so
    # OLD.updated_at == NEW.updated_at -> the trigger fires and bumps it to now.
    conn.execute("UPDATE agent_memory SET status='done' WHERE mem_id=?;", (mem_id,))
    conn.commit()
    (updated_at,) = conn.execute(
        "SELECT updated_at FROM agent_memory WHERE mem_id=?;", (mem_id,)
    ).fetchone()
    assert updated_at != "2020-01-01 00:00:00", "trigger did not bump updated_at"


# --- PRIVACY INVARIANT (the architectural guarantee) ------------------------

# Team-facing readers per the privacy guard in skills/agent-memory/SKILL.md and
# migration 0006: Daily Pulse, Follow-Through, Risk Radar, and slack-commands'
# "what's X working on". These read tasks/blockers and MUST NEVER query
# agent_memory, so a private self-task or note cannot leak into a team report.
# Safety by construction — this test fails loudly if anyone wires a team-facing
# surface to the agent_memory table.
TEAM_FACING_READER_SKILLS = ["daily-pulse", "follow-through", "risk-radar", "slack-commands"]


def test_team_facing_readers_never_reference_agent_memory():
    for skill in TEAM_FACING_READER_SKILLS:
        path = SKILLS_DIR / skill / "SKILL.md"
        assert path.exists(), f"expected skill not found: {path}"
        text = path.read_text(encoding="utf-8")
        assert "agent_memory" not in text, (
            f"PRIVACY LEAK: team-facing reader '{skill}' references the "
            f"agent_memory table — it must read only tasks/blockers"
        )


def test_agent_memory_skill_does_own_the_table():
    # Sanity: the privacy test above is only meaningful if the agent-memory skill
    # itself genuinely owns/references the table.
    text = (SKILLS_DIR / "agent-memory" / "SKILL.md").read_text(encoding="utf-8")
    assert "agent_memory" in text


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
