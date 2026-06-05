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


def test_generate_propagates_generator_error_from_lookup():
    empty = tempfile.mkdtemp()
    res = uc.generate(2762, "U07GKLVA9FE", skills_dir=empty, deliver=False)
    assert res["ok"] is False and res["status"] == "generator_error"


# --------------------------------------------------------------------------
# isolation — capabilities layer imports no workstream code at runtime
# --------------------------------------------------------------------------

def test_capabilities_do_not_import_workstream_code():
    pkg = REPO_ROOT / "lib" / "alaska_capabilities"
    forbidden = re.compile(r"^(import|from)\s+(lib\.)?(pmf_os|audit_[a-z]+|bon_internal)")
    for pyfile in pkg.glob("*.py"):
        for line in pyfile.read_text(encoding="utf-8").splitlines():
            assert not forbidden.match(line.strip()), "%s imports workstream code: %s" % (pyfile.name, line)
