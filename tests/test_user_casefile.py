"""user_casefile — test suite (stdlib only, no live network, no live lookup).

Covers the three layers of /alaska user <id>:
  * build_casefile_docflow  — pure summary -> DocFlow spec (populated + dormant)
  * the value formatters     — money/pct/yn/int null-safety + pct normalization
  * generate                 — orchestration with an injected lookup_result and a
                               fake Slack transport (ok / not_found / render /
                               stale / private-delivery / PII-bracket paths)
  * run_lookup               — subprocess failure is reported, never raised
  * isolation                — alaska_capabilities imports no workstream code

Run: python3 -m pytest tests/test_user_casefile.py -q
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from alaska_artifacts import docflow  # noqa: E402
from alaska_capabilities import user_casefile as uc  # noqa: E402

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------

def _populated_summary() -> dict:
    return {
        "identity": {"first_name": "Maria", "age": 34, "location": "Austin, TX",
                     "days_since_signup": 212, "platform": "iOS"},
        "linking": {"card_linked": True, "bank_linked": True, "credit_activated": False},
        "credit": {"score": 668, "score_band": "good", "source": "BON model",
                   "model": "BON-v2", "bureau": "TransUnion", "as_of": "2026-05-30"},
        "debt": {"total_cc_balance": 8420.55, "total_cc_limit": 13500, "utilization": 0.624,
                 "utilization_band": "high (50-75%)", "weighted_avg_apr": 23.99,
                 "monthly_interest": 168.4, "total_min_payment": 295, "num_cards": 3,
                 "any_overdue": False, "source": "Plaid"},
        "liquidity": {"cash_on_hand": 412.18, "low_balance_risk": True},
        "income": {"monthly_income": 5200, "stability": "stable", "source": "Plaid payroll"},
        "spending": {"current_month_total": 3180.42, "source": "Plaid",
                     "top_categories": [{"category": "Rent", "amount": 1500},
                                        {"category": "Groceries", "amount": 612.33}]},
        "subscriptions": {"active_count": 6, "monthly_total": 96.94},
        "chat": {"total_threads": 14, "real_turns": 47, "proactive_turns": 9,
                 "dominant_topics": [{"topic": "lowering APR", "count": 8}],
                 "thumbs_up": 6, "thumbs_down": 1},
        "_meta": {"sections_present": ["identity", "credit", "debt"], "sections_empty": []},
    }


def _ok_lookup(summary, user_id=2762, **over) -> dict:
    res = {"status": "ok", "user_id": user_id, "intent": "user_summary",
           "mode": "headline", "summary": summary, "served_stale": False, "notes": []}
    res.update(over)
    return res


def _docx_text(path) -> str:
    xml = zipfile.ZipFile(path).read("word/document.xml")
    root = ET.fromstring(xml)
    return "\n".join(t.text or "" for t in root.iter(_W + "t"))


class _FakeSlack:
    """Records calls; replays canned (status, bytes) responses in order."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self._i = 0

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        self.calls.append({"method": method, "url": url, "body": body})
        resp = self.responses[self._i]
        self._i += 1
        return resp


def _slack_ok():
    return _FakeSlack([
        (200, json.dumps({"ok": True, "upload_url": "https://up.example/x", "file_id": "F1"}).encode()),
        (200, b""),
        (200, json.dumps({"ok": True}).encode()),
    ])


# --------------------------------------------------------------------------
# formatters
# --------------------------------------------------------------------------

def test_formatters_are_null_safe():
    assert uc._money(None) == uc.DASH
    assert uc._money("nope") == uc.DASH
    assert uc._money(1500) == "$1,500.00"
    assert uc._money(8420.55) == "$8,420.55"
    assert uc._int(None) == uc.DASH
    assert uc._int(13500) == "13,500"
    assert uc._yn(None) == uc.DASH
    assert uc._yn(True) == "Yes" and uc._yn(False) == "No"
    assert uc._txt(None) == uc.DASH and uc._txt("") == uc.DASH
    assert uc._txt("iOS") == "iOS"


def test_pct_normalizes_fraction_and_percent_consistently():
    # Fraction form and percent form of the same ratio render identically...
    assert uc._pct(0.624) == "62.4%"
    assert uc._pct(62.4) == "62.4%"
    # ...so the printed percent can never contradict the summarizer's band text.
    assert uc._pct(23.99) == "24.0%"   # APR stored as percent
    assert uc._pct(0.2399) == "24.0%"  # APR stored as fraction
    assert uc._pct(None) == uc.DASH


def test_join_drops_empty_parts():
    assert uc._join([668, "good"]) == "668 · good"
    assert uc._join([668, None]) == "668"
    assert uc._join([None, None]) == uc.DASH


# --------------------------------------------------------------------------
# build_casefile_docflow — pure
# --------------------------------------------------------------------------

def test_build_populated_is_valid_docflow():
    spec = uc.build_casefile_docflow(_populated_summary(), 2762, now="2026-06-05")
    assert docflow.validate_docflow(spec) == []          # structurally valid
    assert spec["meta"]["title"] == "User Case File — Maria"
    # First block is the PII warning callout — always.
    assert spec["blocks"][0]["type"] == "callout"
    assert spec["blocks"][0]["style"] == "warning"
    assert "PII" in spec["blocks"][0]["text"]
    # Every table row matches its column count (the docflow gate enforces this).
    for b in spec["blocks"]:
        if b.get("type") == "table":
            assert all(len(r) == len(b["columns"]) for r in b["rows"]), b.get("title")


def test_build_dormant_user_does_not_crash_and_shows_dashes():
    # A brand-new user: identity only, everything else empty/None.
    dormant = {
        "identity": {"first_name": None, "age": None, "location": None,
                     "days_since_signup": 0, "platform": "Android"},
        "linking": {"card_linked": False, "bank_linked": False, "credit_activated": False},
        "credit": {}, "debt": {}, "liquidity": {}, "income": {}, "spending": {},
        "subscriptions": {}, "chat": {},
        "_meta": {"sections_present": ["identity"],
                  "sections_empty": ["credit", "debt", "income", "spending", "chat"]},
    }
    spec = uc.build_casefile_docflow(dormant, 9001, now="2026-06-05")
    assert docflow.validate_docflow(spec) == []
    assert spec["meta"]["title"] == "User Case File — User #9001"  # falls back to id
    # No top-categories / dominant-topics tables when those lists are absent.
    titles = [b.get("title") for b in spec["blocks"] if b.get("type") == "table"]
    assert "Top spending categories" not in titles
    assert "Dominant chat topics" not in titles


def test_build_includes_stale_and_notes_callouts():
    spec = uc.build_casefile_docflow(_populated_summary(), 2762, served_stale=True,
                                     notes=["Bank refresh is 6 days old."], now="2026-06-05")
    texts = [b.get("text", "") for b in spec["blocks"] if b.get("type") == "callout"]
    assert any("stale cache" in t for t in texts)
    assert any("6 days old" in t for t in texts)


# --------------------------------------------------------------------------
# generate — orchestration (injected lookup, no network)
# --------------------------------------------------------------------------

def test_generate_ok_renders_validates_and_stores():
    base = tempfile.mkdtemp()
    out = tempfile.mkdtemp()
    res = uc.generate(2762, "U07GKLVA9FE", requester_authority="admin",
                      lookup_result=_ok_lookup(_populated_summary()),
                      base_dir=base, out_dir=out, deliver=False, now="2026-06-05")
    assert res["ok"] is True and res["status"] == "ok"
    assert res["artifact_id"].startswith("user-casefile/2762/")
    assert os.path.exists(res["path"]) and res["bytes"] > 0
    # The stored sidecar records who asked.
    meta = json.load(open(res["path"] + ".meta.json"))
    assert meta["owner_skill"] == "user-casefile"
    assert meta["extra"]["requester_slack_id"] == "U07GKLVA9FE"
    text = _docx_text(res["path"])
    for must in ("Maria", "Austin, TX", "$8,420.55", "Top spending categories", "Data sources"):
        assert must in text, must


def test_generate_not_found_returns_error_without_rendering():
    res = uc.generate(404, "U07GKLVA9FE",
                      lookup_result={"status": "not_found", "user_id": 404,
                                     "message": "No user matches 404."},
                      deliver=False)
    assert res["ok"] is False and res["status"] == "not_found"
    assert "404" in res["message"]
    assert "path" not in res  # nothing was rendered


def test_generate_multiple_matches_is_surfaced():
    res = uc.generate("maria", "U07GKLVA9FE",
                      lookup_result={"status": "multiple", "matches": [1, 2, 3],
                                     "message": "3 users match."},
                      deliver=False)
    assert res["ok"] is False and res["status"] == "multiple"
    assert res["matches"] == [1, 2, 3]


def test_generate_renders_real_data_containing_brackets():
    # The whole reason generate() validates with check_placeholders=False: real
    # user data can legitimately contain "[...]" (here, a chat topic). A naive
    # placeholder gate would reject a perfectly valid case file.
    s = _populated_summary()
    s["chat"]["dominant_topics"] = [{"topic": "[disputed charge] follow-up", "count": 3}]
    res = uc.generate(2762, "U07GKLVA9FE", lookup_result=_ok_lookup(s),
                      base_dir=tempfile.mkdtemp(), out_dir=tempfile.mkdtemp(),
                      deliver=False, now="2026-06-05")
    assert res["ok"] is True, res
    assert "[disputed charge] follow-up" in _docx_text(res["path"])


def test_generate_private_delivery_uploads_to_requester_channel():
    fake = _slack_ok()
    res = uc.generate(2762, "U07GKLVA9FE", lookup_result=_ok_lookup(_populated_summary()),
                      base_dir=tempfile.mkdtemp(), out_dir=tempfile.mkdtemp(),
                      channel_id="D0ANP0LQM44", token="xoxb-test", http_request=fake,
                      deliver=True, now="2026-06-05")
    assert res["ok"] is True and res["delivered"] is True
    assert res["slack"]["ok"] is True and res["slack"]["file_id"] == "F1"
    # Delivered to the DM we were handed — never a broadcast channel of our choosing.
    complete_body = json.loads(fake.calls[2]["body"])
    assert complete_body["channel_id"] == "D0ANP0LQM44"
    assert "PII" in complete_body["initial_comment"] or "do not forward" in complete_body["initial_comment"]


def test_generate_without_channel_does_not_attempt_delivery():
    res = uc.generate(2762, "U07GKLVA9FE", lookup_result=_ok_lookup(_populated_summary()),
                      base_dir=tempfile.mkdtemp(), out_dir=tempfile.mkdtemp(),
                      channel_id=None, deliver=True, now="2026-06-05")
    assert res["ok"] is True
    assert "delivered" not in res and "slack" not in res  # generated, not sent


def test_generate_delivery_failure_keeps_artifact():
    fake = _FakeSlack([(200, json.dumps({"ok": False, "error": "channel_not_found"}).encode())])
    res = uc.generate(2762, "U07GKLVA9FE", lookup_result=_ok_lookup(_populated_summary()),
                      base_dir=tempfile.mkdtemp(), out_dir=tempfile.mkdtemp(),
                      channel_id="Cbad", token="xoxb-test", http_request=fake,
                      deliver=True, now="2026-06-05")
    # The document was made + stored even though Slack delivery failed.
    assert res["ok"] is True and res["delivered"] is False
    assert os.path.exists(res["path"])


def test_generate_passes_stale_flag_into_document():
    res = uc.generate(2762, "U07GKLVA9FE",
                      lookup_result=_ok_lookup(_populated_summary(), served_stale=True),
                      base_dir=tempfile.mkdtemp(), out_dir=tempfile.mkdtemp(),
                      deliver=False, now="2026-06-05")
    assert res["served_stale"] is True
    assert "stale cache" in _docx_text(res["path"])


# --------------------------------------------------------------------------
# run_lookup — subprocess failure is reported, never raised
# --------------------------------------------------------------------------

def test_run_lookup_missing_script_returns_generator_error():
    empty = tempfile.mkdtemp()  # no user-profile-360/lookup.py here
    res = uc.run_lookup(2762, "U07GKLVA9FE", skills_dir=empty)
    assert res["status"] == "generator_error"
    assert "lookup" in res["message"].lower()


def test_run_lookup_requests_the_full_case_file_intent(monkeypatch):
    """Regression for the 'almost-empty case file' root cause: `user_summary`
    fetches only profile+persona, so every other table rendered as '—'. The case
    file must request the rich `case_file` intent."""
    captured = {}

    class _Proc:
        stdout = '{"status": "not_found"}'
        stderr = ""

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(uc.subprocess, "run", fake_run)
    uc.run_lookup(1980, "U07GKLVA9FE", skills_dir="/tmp")
    cmd = captured["cmd"]
    assert "--intent" in cmd
    assert cmd[cmd.index("--intent") + 1] == "case_file"  # NOT user_summary


def test_case_file_intent_covers_every_summarizer_block():
    """Guard: the `case_file` intent (in user-profile-360/sections.py) must fetch a
    source for every block the case file renders — else fields go silently empty."""
    sections = (REPO_ROOT / "skills" / "user-profile-360" / "sections.py").read_text(encoding="utf-8")
    block = sections.split('"case_file": [', 1)
    assert len(block) == 2, "the case_file intent must exist in INTENT_PROFILES"
    body = block[1].split("],", 1)[0]
    for needed in ("profile", "credit_report_history", "plaid_profiles", "plaid_income",
                   "plaid_transactions", "subscriptions", "chat.recent_turns", "chat.feedback_summary"):
        assert needed in body, "case_file intent is missing the source for: %s" % needed


def test_generate_propagates_generator_error_from_lookup():
    empty = tempfile.mkdtemp()
    res = uc.generate(2762, "U07GKLVA9FE", skills_dir=empty, deliver=False)
    assert res["ok"] is False and res["status"] == "generator_error"


# --------------------------------------------------------------------------
# PMF cohort cross-pointer — best-effort `!case` -> `!pmf user` disambiguation
#
# When the queried user is a member of the ACTIVE PMF cohort, the 360 Slack
# message gains ONE pointer line to the PMF cohort case file (`!pmf user <id>`).
# The 360 document itself is unchanged. The lookup is best-effort: an absent /
# unreadable alaska_pmf.db must never break or delay 360 delivery.
# --------------------------------------------------------------------------

import sqlite3  # noqa: E402

from pmf_os.store import PmfStore  # noqa: E402

_PMF_MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
_PMF_WS, _PMF_WE = "2026-05-27T00:00:00-07:00", "2026-05-29T23:59:59-07:00"


def _seed_pmf_db(*, active=True, member_id="2762", stage="activated_user") -> str:
    """Build a REAL alaska_pmf.db: one cohort (optionally active) and, when
    member_id is set, one registry member at `stage`. Returns the db path.
    Mirrors the seeding in test_pmf_om3_membership so the pointer exercises the
    real get_active_cohort_membership against a real schema (no method mocking)."""
    db = str(Path(tempfile.mkdtemp(prefix="casefile_pmf_")) / "alaska_pmf.db")
    conn = sqlite3.connect(db)
    conn.executescript(_PMF_MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    PmfStore(db).create_cohort(cohort_id="c1", name="C1", signup_window_start=_PMF_WS,
                               signup_window_end=_PMF_WE, activate=active)
    if member_id is not None:
        conn = sqlite3.connect(db)
        conn.execute(
            "INSERT INTO pmf_cohort_users (cohort_id, user_key, bon_user_id, "
            "signup_event_time, current_stage, highest_stage) VALUES (?,?,?,?,?,?)",
            ("c1", "user:%s" % member_id, member_id, "2026-05-28T10:00:00Z", stage, stage),
        )
        conn.commit()
        conn.close()
    return db


# ----- the pure helper -----

def test_pmf_pointer_present_for_active_cohort_member():
    db = _seed_pmf_db(active=True, member_id="2762", stage="activated_user")
    line = uc.pmf_cohort_pointer(2762, pmf_db_path=db)
    assert "active PMF cohort" in line       # names the surface
    assert "activated_user" in line          # surfaces the funnel stage
    assert "!pmf user 2762" in line          # points at the PMF cohort case file


def test_pmf_pointer_empty_for_non_member():
    db = _seed_pmf_db(active=True, member_id="2762", stage="activated_user")
    assert uc.pmf_cohort_pointer(9999, pmf_db_path=db) == ""   # different id -> not a member


def test_pmf_pointer_empty_when_no_active_cohort():
    db = _seed_pmf_db(active=False, member_id="2762")          # cohort 'planned', not active
    assert uc.pmf_cohort_pointer(2762, pmf_db_path=db) == ""   # member exists, but no ACTIVE cohort


def test_pmf_pointer_empty_and_safe_when_db_absent():
    missing = str(Path(tempfile.mkdtemp()) / "no_such_alaska_pmf.db")
    assert uc.pmf_cohort_pointer(2762, pmf_db_path=missing) == ""   # absent DB -> no pointer, no raise


# ----- wired through generate() into the Slack initial_comment -----

def test_generate_appends_pmf_pointer_to_initial_comment_for_member():
    db = _seed_pmf_db(active=True, member_id="2762", stage="activated_user")
    fake = _slack_ok()
    res = uc.generate(2762, "U07GKLVA9FE", lookup_result=_ok_lookup(_populated_summary()),
                      base_dir=tempfile.mkdtemp(), out_dir=tempfile.mkdtemp(),
                      channel_id="C0ANKDD664A", token="xoxb-test", http_request=fake,
                      deliver=True, now="2026-06-05", pmf_db_path=db)
    assert res["ok"] is True and res["delivered"] is True
    comment = json.loads(fake.calls[2]["body"])["initial_comment"]
    # The 360 keeps its PII warning AND gains exactly the cross-pointer line.
    assert "do not forward" in comment
    assert "active PMF cohort" in comment and "!pmf user 2762" in comment
    assert "activated_user" in comment
    assert res.get("pmf_pointer")            # also surfaced on the result


def test_generate_no_pmf_pointer_for_non_cohort_member():
    db = _seed_pmf_db(active=True, member_id="2762", stage="activated_user")
    fake = _slack_ok()
    res = uc.generate(9999, "U07GKLVA9FE",
                      lookup_result=_ok_lookup(_populated_summary(), user_id=9999),
                      base_dir=tempfile.mkdtemp(), out_dir=tempfile.mkdtemp(),
                      channel_id="C0ANKDD664A", token="xoxb-test", http_request=fake,
                      deliver=True, now="2026-06-05", pmf_db_path=db)
    assert res["ok"] is True and res["delivered"] is True
    comment = json.loads(fake.calls[2]["body"])["initial_comment"]
    assert "PMF cohort" not in comment       # no pointer for a non-member
    assert "pmf_pointer" not in res


def test_generate_pmf_lookup_failure_never_breaks_delivery():
    missing = str(Path(tempfile.mkdtemp()) / "absent.db")
    fake = _slack_ok()
    res = uc.generate(2762, "U07GKLVA9FE", lookup_result=_ok_lookup(_populated_summary()),
                      base_dir=tempfile.mkdtemp(), out_dir=tempfile.mkdtemp(),
                      channel_id="C0ANKDD664A", token="xoxb-test", http_request=fake,
                      deliver=True, now="2026-06-05", pmf_db_path=missing)
    # The 360 still delivers cleanly; the absent PMF DB is silently ignored.
    assert res["ok"] is True and res["delivered"] is True
    comment = json.loads(fake.calls[2]["body"])["initial_comment"]
    assert "do not forward" in comment and "PMF cohort" not in comment


# --------------------------------------------------------------------------
# isolation — the capabilities layer carries NO *import-time* dependency on the
# workstream packages (pmf_os / audit_* / bon_internal): importing
# alaska_capabilities must never drag them in. A LAZY import inside a function
# (e.g. user_casefile.pmf_cohort_pointer's guarded PMF cohort lookup) IS allowed —
# it only binds when that code path runs, and is wrapped so a missing package/DB
# can't break the capability. So we forbid only MODULE-LEVEL (column-0) workstream
# imports, not indented in-function ones.
# --------------------------------------------------------------------------

_WORKSTREAM_IMPORT = re.compile(r"^(import|from)\s+(lib\.)?(pmf_os|audit_[a-z]+|bon_internal)")


def test_capabilities_have_no_module_level_workstream_import():
    pkg = REPO_ROOT / "lib" / "alaska_capabilities"
    for pyfile in pkg.glob("*.py"):
        for line in pyfile.read_text(encoding="utf-8").splitlines():
            # Match the RAW line (NOT stripped): only a column-0 import is an
            # import-time dependency. An indented lazy import inside a function is fine.
            assert not _WORKSTREAM_IMPORT.match(line), \
                "%s has a module-level workstream import: %s" % (pyfile.name, line)


def test_pmf_cross_pointer_import_is_lazy_not_module_level():
    """user_casefile reaches pmf_os ONLY via a lazy, in-function import, so importing
    the capabilities package never requires the PMF workstream to be installed. This
    pins that decision: a refactor that hoists the pmf_os import to module level
    (re-introducing an import-time dependency) must fail here."""
    src = (REPO_ROOT / "lib" / "alaska_capabilities" / "user_casefile.py").read_text(encoding="utf-8")
    pmf_imports = [ln for ln in src.splitlines() if re.search(r"\b(from|import)\s+pmf_os\b", ln)]
    assert pmf_imports, "expected user_casefile to reference pmf_os for the cross-pointer"
    # Every such import must be indented (inside a function), never at column 0.
    assert all(ln != ln.lstrip() for ln in pmf_imports), \
        "pmf_os must be imported lazily (indented, in-function), not at module level: %s" % pmf_imports
