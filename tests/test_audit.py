"""BON Internal Audit Agent — test suite (fixtures only, no live API).

Covers: audit_compute (formulas), audit_validate (skill rules),
audit_fetch (vendored client + redaction), audit_render (DOCX template fill),
audit_slack (delivery), and the audit_agent CLI orchestration.

Run: python3 -m pytest tests/test_audit.py -q
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

# The audit skill modules live co-located in skills/bon-internal-audit/.
SKILL_DIR = Path(__file__).parent.parent / "skills" / "bon-internal-audit"
sys.path.insert(0, str(SKILL_DIR))

import audit_compute as C  # noqa: E402
import audit_validate as V  # noqa: E402
import audit_fetch as F  # noqa: E402
import audit_render as R  # noqa: E402
import audit_slack as S  # noqa: E402
import audit_agent as A  # noqa: E402
import datetime as _dt  # noqa: E402

TEMPLATE = SKILL_DIR / "references" / "Internal_Report_Template.docx"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_text(path) -> str:
    """All visible text in word/document.xml (concatenated <w:t> runs)."""
    import xml.etree.ElementTree as ET
    xml = zipfile.ZipFile(path).read("word/document.xml")
    root = ET.fromstring(xml)
    return "\n".join(t.text or "" for t in root.iter(_W + "t"))

FIXTURES = SKILL_DIR / "references" / "fixtures"


def _golden() -> dict:
    """A fresh copy of the known-good audit JSON for each test to mutate."""
    return json.loads((FIXTURES / "golden_audit.json").read_text(encoding="utf-8"))


def _rules_failed(result: dict):
    return {f["rule"] for f in result["failures"]}


# --------------------------------------------------------------------------
# audit_compute — the fixed formulas (skill "Step 2. Run the math")
# --------------------------------------------------------------------------

def test_apr_score_bands_match_skill_table():
    assert C.estimate_apr_from_score_band(560) == 29.5   # 300-579
    assert C.estimate_apr_from_score_band(600) == 27.5   # 580-619
    assert C.estimate_apr_from_score_band(640) == 24.0   # 620-659
    assert C.estimate_apr_from_score_band(680) == 20.0   # 660-699
    assert C.estimate_apr_from_score_band(720) == 18.0   # 700-749
    assert C.estimate_apr_from_score_band(800) == 16.0   # 750+


def test_apr_band_boundaries_inclusive():
    assert C.estimate_apr_from_score_band(579) == 29.5
    assert C.estimate_apr_from_score_band(580) == 27.5
    assert C.estimate_apr_from_score_band(750) == 16.0


def test_apr_below_table_floors_to_poor_band():
    # Defensive: a missing/very low score uses the worst band, never invents.
    assert C.estimate_apr_from_score_band(250) == 29.5


def test_monthly_interest_formula():
    # balance * (apr/100) / 12  ->  10000 * 0.24 / 12 = 200
    assert C.monthly_interest(10000, 24.0) == 200.0
    assert C.monthly_interest(0, 24.0) == 0.0


def test_utilization_pct_and_missing_limit():
    assert C.utilization_pct(900, 1000) == 90.0
    assert C.utilization_pct(500, None) is None   # limit not reported -> skip
    assert C.utilization_pct(500, 0) is None       # never divide by zero


def test_utilization_severity_bands():
    assert C.utilization_severity(10) == "good"
    assert C.utilization_severity(29.99) == "good"
    assert C.utilization_severity(30) == "moderate"
    assert C.utilization_severity(49) == "moderate"
    assert C.utilization_severity(50) == "significant"
    assert C.utilization_severity(74) == "significant"
    assert C.utilization_severity(75) == "severe"
    assert C.utilization_severity(100) == "severe"


def test_overall_utilization_two_versions():
    # Card A: 900/1000 (has balance). Card B: 0/2000 (no balance).
    accounts = [
        {"type": "CC", "balance": 900, "limit": 1000, "status": "Open"},
        {"type": "CC", "balance": 0, "limit": 2000, "status": "Open"},
    ]
    res = C.overall_utilization(accounts)
    # Across all open revolving: 900 / 3000 = 30.0
    assert round(res["overall_pct"], 2) == 30.0
    # Across only cards with balances: 900 / 1000 = 90.0
    assert round(res["cards_with_balance_pct"], 2) == 90.0


def test_overall_utilization_ignores_non_revolving_and_missing_limits():
    accounts = [
        {"type": "CC", "balance": 500, "limit": 1000, "status": "Open"},
        {"type": "Auto", "balance": 9000, "limit": None, "status": "Open"},
        {"type": "CC", "balance": 100, "limit": None, "status": "Open"},  # no limit -> excluded
    ]
    res = C.overall_utilization(accounts)
    assert round(res["overall_pct"], 2) == 50.0  # only 500/1000 counts


def test_confidence_multiplier_mapping():
    assert C.confidence_multiplier_for("EXACT") == 1.0
    assert C.confidence_multiplier_for("COMPUTED") == 1.0
    assert C.confidence_multiplier_for("INFERENCE") == 0.7
    assert C.confidence_multiplier_for("ASSUMPTION") == 0.5


def test_priority_score_formula():
    # (yearly_savings * confidence) / effort
    assert C.priority_score(3000, 1.0, 3) == 1000.0
    assert C.priority_score(2500, 1.0, 2) == 1250.0
    # The skill's canonical example: a $2,500 effort-2 fix beats a $3,300 effort-3 paydown.
    assert C.priority_score(2500, 1.0, 2) > C.priority_score(3300, 1.0, 3)


def test_rank_opportunities_sorts_by_priority_desc_and_assigns_rank():
    opps = [
        {"type": "CC Interest", "yearly_savings": 3300, "confidence_multiplier": 1.0, "effort_score": 3},
        {"type": "Bank Fees", "yearly_savings": 2500, "confidence_multiplier": 1.0, "effort_score": 2},
    ]
    ranked = C.rank_opportunities(opps)
    assert ranked[0]["type"] == "Bank Fees"   # higher priority score leads
    assert ranked[0]["rank"] == 1
    assert ranked[1]["rank"] == 2
    # priority_score is filled in
    assert ranked[0]["priority_score"] == 1250.0


def test_collections_monthly_cost():
    # total_cc_debt * (apr_delta/100) / 12 ; 12000 * 0.03 / 12 = 30
    assert C.collections_monthly_cost(12000, 3.0) == 30.0
    assert C.collections_monthly_cost(0, 3.0) == 0.0


# --------------------------------------------------------------------------
# audit_validate — the skill's programmatic rules (gate before DOCX render)
# --------------------------------------------------------------------------

def test_validate_golden_audit_passes_all_rules():
    result = V.validate_audit(_golden())
    assert result["ok"] is True, result["failures"]
    assert result["failures"] == []


def test_validate_detects_unsorted_opportunities():
    a = _golden()
    a["opportunities"][0], a["opportunities"][1] = a["opportunities"][1], a["opportunities"][0]
    assert "opportunities_sorted" in _rules_failed(V.validate_audit(a))


def test_validate_detects_wrong_priority_score():
    a = _golden()
    a["opportunities"][0]["priority_score"] = 9999.0
    assert "priority_score_recomputed" in _rules_failed(V.validate_audit(a))


def test_validate_detects_overlong_opening_message():
    a = _golden()
    a["flowchart"]["step_4_opening_message"] = " ".join(["word"] * 60)
    assert "opening_message_length" in _rules_failed(V.validate_audit(a))


def test_validate_detects_bad_button_count():
    a = _golden()
    a["flowchart"]["step_5_buttons"] = ["only one"]
    assert "buttons_count" in _rules_failed(V.validate_audit(a))


def test_validate_detects_quit_button():
    a = _golden()
    a["flowchart"]["step_5_buttons"] = ["Show me the fees", "No thanks"]
    assert "no_quit_button" in _rules_failed(V.validate_audit(a))


def test_validate_detects_killed_feature():
    a = _golden()
    a["notes_edge_cases"].append("Pitch the spin wheel daily drop to re-engage.")
    assert "no_killed_features" in _rules_failed(V.validate_audit(a))


def test_validate_does_not_flag_spinwheel_data_source():
    # 'Spinwheel' is the credit-report provider, NOT the killed 'spin wheel' feature.
    a = _golden()
    a["notes_edge_cases"].append("Score sourced from spinwheel_credit_report at signup.")
    assert "no_killed_features" not in _rules_failed(V.validate_audit(a))


def test_validate_does_not_flag_rewards_optimization():
    # Legitimate financial advice, distinct from BON's killed 'rewards system'.
    a = _golden()
    a["opportunities"][2]["type"] = "Rewards optimization"
    assert "no_killed_features" not in _rules_failed(V.validate_audit(a))


def test_validate_detects_em_dash():
    a = _golden()
    a["flowchart"]["step_6_button_1_response"] = "Two fees — both waive."
    assert "no_em_dashes" in _rules_failed(V.validate_audit(a))


def test_validate_detects_invalid_persona():
    a = _golden()
    a["user"]["persona_pattern"] = "Big Spender"
    assert "persona_pattern_valid" in _rules_failed(V.validate_audit(a))


def test_validate_detects_missing_flowchart_step():
    a = _golden()
    a["flowchart"]["step_7_button_2_response"] = ""
    assert "flowchart_complete" in _rules_failed(V.validate_audit(a))


def test_validate_link_pitch_null_allowed_only_when_card_and_bank_linked():
    a = _golden()
    # CR+Card+Bank with null link-pitch -> fine (already passes in golden).
    assert "flowchart_complete" not in _rules_failed(V.validate_audit(a))
    # CR-only with null link-pitch -> must be filled, so this fails.
    a["audit_meta"]["data_available"] = "CR Only"
    assert "flowchart_complete" in _rules_failed(V.validate_audit(a))


def test_validate_detects_missing_estimate_language():
    a = _golden()
    # rank-3 opp has confidence_multiplier 0.7 -> evidence must hedge.
    a["opportunities"][2]["evidence"] = "Saves 240 dollars per year by rebalancing."
    assert "estimate_language" in _rules_failed(V.validate_audit(a))


def test_validate_detects_untraceable_dollar():
    a = _golden()
    del a["opportunities"][0]["data_source"]
    a["opportunities"][0]["evidence"] = "Just trust me."
    assert "dollar_traceable" in _rules_failed(V.validate_audit(a))


def test_validate_requires_a_named_pattern_in_notes():
    a = _golden()
    a["notes_edge_cases"] = ["The user seems fine."]
    assert "notes_min_one_pattern" in _rules_failed(V.validate_audit(a))
    # The explicit honest opt-out satisfies the rule.
    a["notes_edge_cases"] = ["No non-obvious patterns detected."]
    assert "notes_min_one_pattern" not in _rules_failed(V.validate_audit(a))


# --------------------------------------------------------------------------
# audit_fetch — vendored BON Admin client + redaction + reliable aggregates
# --------------------------------------------------------------------------

def _profile(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _http_returning(status: int, body: bytes):
    """Build an injectable http_request that always returns (status, body)."""
    calls = {"n": 0}

    def http(method, url, headers=None, timeout=25):
        calls["n"] += 1
        return status, body
    http.calls = calls
    return http


def test_validate_user_id_accepts_numeric():
    ok, uid, err = F.validate_user_id("1414")
    assert ok and uid == 1414 and err is None
    ok, uid, err = F.validate_user_id(2714)
    assert ok and uid == 2714


def test_validate_user_id_rejects_malformed():
    for bad in ["", "  ", "abc", "12x", "-5", "0", "3.5", None]:
        ok, uid, err = F.validate_user_id(bad)
        assert ok is False and uid is None and err, "expected rejection for %r" % (bad,)


def test_fetch_profile_ok():
    body = json.dumps(_profile("profile_cr_card_bank.json")).encode()
    res = F.fetch_profile(1414, base_url="https://api.test", api_key="k",
                          http_request=_http_returning(200, body))
    assert res["status"] == "ok"
    assert res["payload"]["user_id"] == 1414


def test_fetch_profile_sends_admin_key_header_to_right_url():
    seen = {}

    def http(method, url, headers=None, timeout=25):
        seen["method"], seen["url"], seen["headers"] = method, url, headers or {}
        return 200, json.dumps(_profile("profile_cr_card_bank.json")).encode()

    F.fetch_profile(1414, base_url="https://api.test/", api_key="secret", http_request=http)
    assert seen["method"] == "GET"
    assert seen["url"] == "https://api.test/api/admin/users/1414/profile"
    assert seen["headers"].get("X-Admin-Key") == "secret"


def test_fetch_profile_not_found():
    res = F.fetch_profile(999, base_url="https://api.test", api_key="k",
                          http_request=_http_returning(404, b'{"error":"no user"}'))
    assert res["status"] == "not_found"


def test_fetch_profile_auth_error():
    res = F.fetch_profile(1, base_url="https://api.test", api_key="bad",
                          http_request=_http_returning(401, b'{"error":"unauthorized"}'))
    assert res["status"] == "auth_error"


def test_fetch_profile_non_json_is_api_error():
    res = F.fetch_profile(1414, base_url="https://api.test", api_key="k",
                          http_request=_http_returning(200, b'<html>oops</html>'))
    assert res["status"] == "api_error"


def test_fetch_profile_retries_once_on_5xx_then_succeeds():
    state = {"n": 0}
    body = json.dumps(_profile("profile_cr_card_bank.json")).encode()

    def flaky(method, url, headers=None, timeout=25):
        state["n"] += 1
        if state["n"] == 1:
            return 503, b"busy"
        return 200, body

    res = F.fetch_profile(1414, base_url="https://api.test", api_key="k", http_request=flaky)
    assert res["status"] == "ok"
    assert state["n"] == 2  # one retry


def test_fetch_profile_identity_mismatch():
    body = json.dumps({"user_id": 999, "profile": {}}).encode()
    res = F.fetch_profile(1414, base_url="https://api.test", api_key="k",
                          http_request=_http_returning(200, body))
    assert res["status"] == "identity_mismatch"


def test_redact_strips_toxic_pii_but_keeps_useful_context():
    payload = _profile("profile_cr_card_bank.json")
    red = F.redact(payload)
    blob = json.dumps(red)
    # SSN and full DOB gone everywhere (deep strip).
    assert "123-45-6789" not in blob and "123456789" not in blob
    assert "1979-02-14" not in blob
    # Street line dropped; coarse location kept.
    assert "742 Evergreen Terrace" not in blob
    assert red["profile"]["city"] == "Toledo" and red["profile"]["state"] == "OH"
    # Full account identifier masked to last-4 (not the full PAN).
    assert "4147202099887766" not in blob
    # Age and score survive (needed for the audit).
    assert red["profile"]["age"] == 47


def test_redact_is_nondestructive_to_input():
    payload = _profile("profile_cr_card_bank.json")
    F.redact(payload)
    assert payload["profile"]["ssn"] == "123-45-6789"  # original untouched


def test_classify_data_available():
    assert F.classify_data_available(_profile("profile_cr_card_bank.json")) == "CR + Card + Bank"
    assert F.classify_data_available(_profile("profile_cr_only.json")) == "CR Only"
    card_only = _profile("profile_cr_card_bank.json")
    card_only["profile"]["is_bank_added"] = False
    card_only["plaid_profiles"]["bank_profile"] = {}
    assert F.classify_data_available(card_only) == "CR + Card"


def test_score_band_label():
    assert F.score_band_for(598) == "Poor"
    assert F.score_band_for(642) == "Fair"
    assert F.score_band_for(710) == "Good"
    assert F.score_band_for(800) == "Excellent"


def test_summarize_for_audit_pulls_flat_reliable_fields():
    s = F.summarize_for_audit(_profile("profile_cr_card_bank.json"))
    assert s["first_name"] == "Albert"
    assert s["credit_score"] == 642
    assert s["data_available"] == "CR + Card + Bank"
    # Plaid exact aggregates are surfaced with EXACT confidence.
    assert s["plaid_card"]["weighted_avg_apr_exact"] == 24.99
    assert s["plaid_bank"]["monthly_income_exact"] == 5200.0
    assert s["apr_confidence"] == "EXACT"


def test_summarize_no_plaid_marks_apr_estimated_and_no_bank():
    s = F.summarize_for_audit(_profile("profile_cr_only.json"))
    assert s["data_available"] == "CR Only"
    assert s["plaid_card"] is None  # nothing invented
    assert s["plaid_bank"] is None
    # APR must be estimated from the score band, flagged INFERENCE.
    assert s["apr_confidence"] == "INFERENCE"
    assert s["estimated_apr_pct"] == C.estimate_apr_from_score_band(598)


# --------------------------------------------------------------------------
# audit_render — fill the Internal Report DOCX template (stdlib only)
# --------------------------------------------------------------------------

def _render_golden(tmp_path_name="out.docx") -> str:
    out = str(Path(tempfile.mkdtemp(prefix="audit_render_")) / tmp_path_name)
    return R.render_docx(_golden(), str(TEMPLATE), out)


def test_render_produces_valid_docx_zip():
    out = _render_golden()
    assert Path(out).exists()
    zf = zipfile.ZipFile(out)            # raises if not a valid zip
    assert "word/document.xml" in zf.namelist()
    # styles/header survive (we only rewrite document.xml).
    assert "word/styles.xml" in zf.namelist()


def test_render_leaves_no_placeholders():
    text = _docx_text(_render_golden())
    assert "[Write here]" not in text
    for token in ["[Name]", "[Score]", "[First Name]", "[MM/DD/YYYY]", "[X]", "[Type]", "[band]"]:
        assert token not in text, "leftover placeholder %s" % token


def test_render_fills_user_overview():
    text = _docx_text(_render_golden())
    assert "1414" in text          # user id
    assert "Albert" in text        # first name
    assert "642" in text           # score
    assert "Fair" in text          # band
    assert "CR + Card + Bank" in text


def test_render_account_inventory_lists_every_account():
    text = _docx_text(_render_golden())
    assert "Citi Executive" in text
    assert "Capital One Quicksilver" in text
    assert "Wells Fargo Auto" in text


def test_render_opportunity_ranking_in_priority_order():
    text = _docx_text(_render_golden())
    assert "Bank fee elimination" in text
    # rank-1 (bank fee) appears before rank-2 (Citi paydown) in document order.
    assert text.index("Bank fee elimination") < text.index("CC interest reduction")


def test_render_includes_flowchart_opening_message():
    text = _docx_text(_render_golden())
    assert "bank fees you can kill today" in text


def test_render_marks_confidential():
    text = _docx_text(_render_golden())
    assert "CONFIDENTIAL" in text


def test_render_has_no_em_dash():
    text = _docx_text(_render_golden())
    assert "—" not in text


def test_render_handles_null_link_pitch_gracefully():
    text = _docx_text(_render_golden())
    # golden has CR+Card+Bank so steps 14/15 are null; must not render "None"
    # or leave a placeholder.
    assert "None" not in text.split("Link Pitch")[-1][:400] if "Link Pitch" in text else True
    assert "already linked" in text.lower()


def test_render_refuses_when_validation_fails():
    a = _golden()
    a["user"]["persona_pattern"] = "Not A Real Persona"
    out = str(Path(tempfile.mkdtemp(prefix="audit_render_")) / "bad.docx")
    try:
        R.render_docx(a, str(TEMPLATE), out)
        assert False, "render should refuse an invalid audit"
    except R.AuditValidationError:
        pass
    assert not Path(out).exists()  # nothing written on refusal


def test_render_cr_only_smaller_report_no_invented_plaid():
    # A thin CR-only audit still renders; must not claim exact Plaid figures.
    a = _golden()
    a["audit_meta"]["data_available"] = "CR Only"
    a["user"]["persona_pattern"] = "Credit-thin builder"
    # link pitch now required (no Plaid) -> provide it
    a["flowchart"]["step_14_link_pitch_trigger"] = "After delivering the first concrete saving."
    a["flowchart"]["step_15_link_pitch_text"] = "Link your card and I can see your exact rates. Right now I am estimating."
    out = str(Path(tempfile.mkdtemp(prefix="audit_render_")) / "cronly.docx")
    R.render_docx(a, str(TEMPLATE), out)
    text = _docx_text(out)
    assert "CR Only" in text
    assert "estimating" in text


# --------------------------------------------------------------------------
# audit_slack — concise summary + post + 3-step file upload (vendored, thin)
# --------------------------------------------------------------------------

def _slack_recorder(complete_ok=True):
    """A fake Slack transport that records calls and walks the 3-step upload."""
    calls = []

    def http(method, url, headers=None, body=None, timeout=30):
        calls.append({"method": method, "url": url, "headers": headers or {}, "body": body})
        if "chat.postMessage" in url:
            return 200, json.dumps({"ok": True, "ts": "111.222"}).encode()
        if "files.getUploadURLExternal" in url:
            return 200, json.dumps({"ok": True, "upload_url": "https://files.slack/up/x", "file_id": "F1"}).encode()
        if url.startswith("https://files.slack/up/"):
            return 200, b"OK"
        if "files.completeUploadExternal" in url:
            return 200, json.dumps({"ok": complete_ok, "files": [{"id": "F1"}]}).encode()
        return 404, b"{}"

    http.calls = calls
    return http


def test_build_summary_has_required_fields():
    s = S.build_summary(_golden())
    assert "1414" in s
    assert "Single-card crisis" in s
    assert "Bank fee elimination" in s
    assert "360" in s              # ~$360/year
    assert "confidence" in s.lower()


def test_build_summary_carries_no_raw_pii():
    s = S.build_summary(_golden())
    # No SSN / account-number-like long digit runs in the summary.
    import re as _re
    assert not _re.search(r"\d{9,}", s), "summary leaks a long digit sequence"
    assert "ssn" not in s.lower()


def test_post_message_hits_chat_postmessage_with_bearer():
    http = _slack_recorder()
    res = S.post_message("C0ANK", "hello", token="xoxb-test", http_request=http)
    assert res["ok"] is True
    call = http.calls[0]
    assert "chat.postMessage" in call["url"]
    assert call["headers"].get("Authorization") == "Bearer xoxb-test"


def test_upload_file_walks_three_step_flow(tmp_path_factory=None):
    f = Path(tempfile.mkdtemp(prefix="audit_up_")) / "r.docx"
    f.write_bytes(b"PK fake docx bytes")
    http = _slack_recorder()
    res = S.upload_file("C0ANK", str(f), "Internal Report", token="xoxb-test", http_request=http)
    assert res["ok"] is True
    urls = " ".join(c["url"] for c in http.calls)
    assert "files.getUploadURLExternal" in urls
    assert "files.completeUploadExternal" in urls


def test_upload_file_without_token_raises():
    f = Path(tempfile.mkdtemp(prefix="audit_up_")) / "r.docx"
    f.write_bytes(b"x")
    try:
        S.upload_file("C0ANK", str(f), "t", token=None, http_request=_slack_recorder())
        assert False, "expected SlackAuthError"
    except S.SlackAuthError:
        pass


def test_deliver_posts_summary_and_uploads():
    f = Path(tempfile.mkdtemp(prefix="audit_dl_")) / "r.docx"
    f.write_bytes(b"PK fake")
    http = _slack_recorder()
    res = S.deliver("C0ANK", "Audit complete for user 1414.", str(f),
                    token="xoxb-test", http_request=http)
    assert res["summary"]["ok"] is True
    assert res["file"]["ok"] is True


def test_deliver_upload_failure_preserves_artifact_and_does_not_raise():
    f = Path(tempfile.mkdtemp(prefix="audit_dl_")) / "r.docx"
    f.write_bytes(b"PK fake")
    http = _slack_recorder(complete_ok=False)  # upload completion fails
    res = S.deliver("C0ANK", "summary", str(f), token="xoxb-test", http_request=http)
    assert res["summary"]["ok"] is True       # summary still delivered
    assert res["file"]["ok"] is False         # upload failed, reported
    assert Path(f).exists()                   # artifact NOT lost


# --------------------------------------------------------------------------
# audit_agent — command parsing, run_audit orchestration, run logging
# --------------------------------------------------------------------------

def _tmp_db() -> str:
    return str(Path(tempfile.mkdtemp(prefix="audit_db_")) / "alaska_audit.db")


def _tmp_artifacts() -> str:
    return str(Path(tempfile.mkdtemp(prefix="audit_art_")))


def test_parse_command_extracts_numeric_user_id():
    ok, uid, err = A.parse_command("hey @alaska /audit 1414")
    assert ok and uid == 1414 and err is None


def test_parse_command_tolerates_mention_and_trailing_words():
    ok, uid, err = A.parse_command("<@U07GKLVA9FE> /audit 1414 please run it")
    assert ok and uid == 1414


def test_parse_command_missing_user_id_fails_safely():
    ok, uid, err = A.parse_command("/audit")
    assert ok is False and uid is None and "user_id" in err


def test_parse_command_non_numeric_fails_safely():
    ok, uid, err = A.parse_command("@alaska /audit abc")
    assert ok is False and uid is None and err


def test_parse_command_not_an_audit_command():
    ok, uid, err = A.parse_command("good morning everyone")
    assert ok is False and uid is None and err


def test_init_db_creates_audit_runs_table():
    db = _tmp_db()
    A.init_db(db)
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(audit_runs)")}
    conn.close()
    assert {"audit_id", "user_id", "status", "artifact_path", "error_reason"} <= cols


def test_run_audit_dry_success_renders_logs_and_summarizes():
    db, art = _tmp_db(), _tmp_artifacts()
    res = A.run_audit(_golden(), template_path=str(TEMPLATE), artifact_root=art,
                      db_path=db, now=_dt.datetime(2026, 6, 5, 10, 0, 0))
    assert res["status"] == "success"
    assert Path(res["artifact_path"]).exists()
    assert zipfile.ZipFile(res["artifact_path"]).testzip() is None
    assert "1414" in res["summary"]
    # logged
    row = A.get_run(db, res["audit_id"])
    assert row["status"] == "success"
    assert row["artifact_path"] == res["artifact_path"]
    assert row["user_id"] == 1414


def test_run_audit_invalid_logs_failure_and_writes_no_artifact():
    db, art = _tmp_db(), _tmp_artifacts()
    bad = _golden()
    bad["user"]["persona_pattern"] = "Nope"
    res = A.run_audit(bad, template_path=str(TEMPLATE), artifact_root=art, db_path=db,
                      now=_dt.datetime(2026, 6, 5, 10, 0, 0))
    assert res["status"] == "validation_failed"
    assert res.get("artifact_path") in (None, "")
    row = A.get_run(db, res["audit_id"])
    assert row["status"] == "validation_failed"
    assert row["error_reason"]


def test_run_audit_does_not_overwrite_previous_report():
    db, art = _tmp_db(), _tmp_artifacts()
    r1 = A.run_audit(_golden(), template_path=str(TEMPLATE), artifact_root=art, db_path=db,
                     now=_dt.datetime(2026, 6, 5, 10, 0, 0))
    r2 = A.run_audit(_golden(), template_path=str(TEMPLATE), artifact_root=art, db_path=db,
                     now=_dt.datetime(2026, 6, 5, 11, 30, 0))
    assert r1["audit_id"] != r2["audit_id"]
    assert r1["artifact_path"] != r2["artifact_path"]
    assert Path(r1["artifact_path"]).exists() and Path(r2["artifact_path"]).exists()


def test_run_audit_render_error_is_logged():
    db, art = _tmp_db(), _tmp_artifacts()
    res = A.run_audit(_golden(), template_path="/no/such/template.docx",
                      artifact_root=art, db_path=db,
                      now=_dt.datetime(2026, 6, 5, 10, 0, 0))
    assert res["status"] in ("render_error", "failed")
    row = A.get_run(db, res["audit_id"])
    assert row["status"] == res["status"]
    assert row["error_reason"]


def _run_cli(args):
    import subprocess
    return subprocess.run(
        [sys.executable, str(SKILL_DIR / "audit_agent.py")] + args,
        capture_output=True, text=True)


def test_cli_validate_exit_codes():
    golden_path = str(FIXTURES / "golden_audit.json")
    ok = _run_cli(["validate", "--audit-json", golden_path])
    assert ok.returncode == 0, ok.stderr
    bad = _golden()
    bad["flowchart"]["step_5_buttons"] = ["No thanks"]
    bad_path = str(Path(tempfile.mkdtemp()) / "bad.json")
    Path(bad_path).write_text(json.dumps(bad))
    fail = _run_cli(["validate", "--audit-json", bad_path])
    assert fail.returncode != 0


def test_cli_run_dry_run_produces_docx_and_json():
    db, art = _tmp_db(), _tmp_artifacts()
    out = _run_cli(["run", "--audit-json", str(FIXTURES / "golden_audit.json"),
                    "--dry-run", "--db", db, "--artifact-root", art,
                    "--template", str(TEMPLATE)])
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["status"] == "success"
    assert Path(payload["artifact_path"]).exists()


# --------------------------------------------------------------------------
# isolation guards — the audit must not couple to or write V4/V5 state
# --------------------------------------------------------------------------

def test_audit_uses_its_own_isolated_db():
    # Default DB is a separate file from the V4 task graph and V5 PMF store.
    assert A.DEFAULT_DB.endswith("alaska_audit.db")
    assert not A.DEFAULT_DB.endswith("/alaska.db")
    assert "alaska_pmf.db" not in A.DEFAULT_DB


def test_audit_modules_never_import_v4_v5_internals():
    # Read-only static check: no actual import of lib/pmf_os, and no V4/V5
    # database file is referenced in code. Prose comments that *explain* the
    # isolation (e.g. "does not import pmf_os") are allowed; real imports are not.
    import re as _re
    for py in sorted(SKILL_DIR.glob("*.py")):
        src = py.read_text(encoding="utf-8")
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not _re.match(r"^(import|from)\b.*pmf_os", stripped), \
                "%s imports pmf_os: %s" % (py.name, stripped)
        # Never reference the V4 task graph DB or the V5 PMF DB as a path.
        assert "alaska_pmf.db" not in src, "%s references the V5 PMF db" % py.name
        assert "/data/queue/alaska.db" not in src, "%s references the V4 task db" % py.name


def test_parse_command_accepts_bang_slash_and_bare():
    # canonical !audit, legacy /audit, and bare audit all parse the user_id
    for text in ("!audit 1414", "/audit 1414", "audit 1414",
                 "hey @alaska !audit 1453", "Alaska, /audit 2762 please"):
        ok, uid, err = A.parse_command(text)
        assert ok and uid is not None, "should parse %r (err=%s)" % (text, err)


def test_parse_command_rejects_missing_id_and_non_command():
    ok, _, err = A.parse_command("!audit")
    assert not ok and "user_id" in (err or "")
    ok, _, _ = A.parse_command("just chatting, nothing to do here")
    assert not ok


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
