"""audit_validate — programmatic gate the audit JSON must pass before DOCX render.

These rules are taken verbatim from the bon-internal-audit skill
("Validation rules (must pass before DOCX render)" + the pre-output checklist).
They are deterministic so a reviewer (and CI) can trust the data, not the prose.

validate_audit(audit) -> {"ok": bool, "failures": [{rule, detail}], "warnings": [...]}
The DOCX render must refuse to run while ok is False.
"""
from __future__ import annotations

import json
from typing import Any, List

# The seven allowed persona patterns (skill JSON shape).
PERSONAS = {
    "House of cards",
    "Min-payment trap",
    "Lifestyle-inflation premium",
    "Single-card crisis",
    "Collections-only",
    "Healthy with leaks",
    "Credit-thin builder",
}

# Killed BON features. Case-insensitive SUBSTRING match (skill: no_killed_features).
# Note the deliberate phrasing: "spin wheel" (the killed feature) NOT "spinwheel"
# (the credit-report provider); "rewards system" NOT bare "rewards"; "get pillar"
# NOT bare "get". This avoids false positives on legitimate language.
KILLED_FEATURES = [
    "unclaimed property",
    "class action",
    "bon points",
    "daily drop",
    "spin wheel",
    "rewards system",
    "get pillar",
]

# Quit / dismiss button text that the BON voice forbids (skill: no_quit_button).
QUIT_PATTERNS = ["no thanks", "no, thanks", "cancel", "skip", "not now", "dismiss"]

# Approximate language an estimate must use (skill: estimate_language).
ESTIMATE_WORDS = ["approximately", "approx", "estimated", "estimate", "likely", "~"]

# Step-3 hunt patterns; at least one must appear in notes (skill: notes_min_one_pattern).
PATTERN_KEYWORDS = [
    "maxed", "signature card", "annual fee", "annual-fee", "product change",
    "product-change", "payday", "cash advance", "cash-advance", "bnpl",
    "minimum payment", "minimum-payment", "min payment", "min-payment",
    "bank fee", "bank-fee", "self-funded", "lending", "closed account",
    "mismatch", "score factor",
]

VALID_DATA_SOURCES = {"Plaid", "Credit Report", "Both"}

# The 13 always-required flowchart steps + the 2 link-pitch steps handled specially.
_REQUIRED_STEPS = [
    "step_1_data_ingestion", "step_2_calculations", "step_3_rank_and_decide",
    "step_4_opening_message", "step_5_buttons", "step_6_button_1_response",
    "step_7_button_2_response", "step_8_button_3_response", "step_9_not_interested",
    "step_10_off_script", "step_11_task", "step_12_detection", "step_13_followup",
]
_LINK_PITCH_STEPS = ["step_14_link_pitch_trigger", "step_15_link_pitch_text"]

EM_DASH = "—"


def _nonempty(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple)):
        return len(v) > 0 and all(_nonempty(x) for x in v)
    if isinstance(v, dict):
        return len(v) > 0 and all(_nonempty(x) for x in v.values())
    return True  # numbers, bools


def validate_audit(audit: dict) -> dict:
    failures: List[dict] = []
    warnings: List[dict] = []

    def fail(rule: str, detail: str) -> None:
        failures.append({"rule": rule, "detail": detail})

    opps = audit.get("opportunities", []) or []
    flow = audit.get("flowchart", {}) or {}
    user = audit.get("user", {}) or {}
    notes = audit.get("notes_edge_cases", []) or []
    data_available = (audit.get("audit_meta", {}) or {}).get("data_available", "")

    # --- opportunities_sorted -------------------------------------------------
    for i in range(len(opps) - 1):
        if opps[i].get("priority_score", 0) < opps[i + 1].get("priority_score", 0):
            fail("opportunities_sorted",
                 "opportunities are not sorted by priority_score descending")
            break
    for i, opp in enumerate(opps, start=1):
        if opp.get("rank") != i:
            fail("opportunities_sorted",
                 "rank field does not match array position (expected %d, got %r)"
                 % (i, opp.get("rank")))
            break

    # --- priority_score_recomputed -------------------------------------------
    for opp in opps:
        eff = opp.get("effort_score") or 0
        if not eff:
            fail("priority_score_recomputed",
                 "opportunity %r has no/zero effort_score" % opp.get("type"))
            continue
        expected = round(opp.get("yearly_savings", 0) * opp.get("confidence_multiplier", 0) / eff, 2)
        if abs(expected - opp.get("priority_score", 0)) > 0.5:
            fail("priority_score_recomputed",
                 "opportunity %r priority_score %r != recomputed %r"
                 % (opp.get("type"), opp.get("priority_score"), expected))

    # --- flowchart_complete ---------------------------------------------------
    for step in _REQUIRED_STEPS:
        if not _nonempty(flow.get(step)):
            fail("flowchart_complete", "missing or empty %s" % step)
    plaid_fully_linked = ("Card" in data_available) and ("Bank" in data_available)
    if not plaid_fully_linked:
        for step in _LINK_PITCH_STEPS:
            if not _nonempty(flow.get(step)):
                fail("flowchart_complete",
                     "%s required (link pitch may only be null when both Card and Bank are linked)" % step)

    # --- opening_message_length (<= 50 words) --------------------------------
    opening = flow.get("step_4_opening_message", "") or ""
    if len(opening.split()) > 50:
        fail("opening_message_length",
             "opening message is %d words (max 50)" % len(opening.split()))

    # --- buttons_count (2 or 3) ----------------------------------------------
    buttons = flow.get("step_5_buttons", []) or []
    if len(buttons) not in (2, 3):
        fail("buttons_count", "expected 2 or 3 buttons, got %d" % len(buttons))

    # --- no_quit_button -------------------------------------------------------
    for b in buttons:
        low = str(b).lower()
        if any(p in low for p in QUIT_PATTERNS):
            fail("no_quit_button", "button %r reads as a quit/dismiss option" % b)

    # --- whole-document scans (killed features, em dashes) -------------------
    blob = json.dumps(audit, ensure_ascii=False)
    low_blob = blob.lower()
    for phrase in KILLED_FEATURES:
        if phrase in low_blob:
            fail("no_killed_features", "document mentions killed feature %r" % phrase)
    if EM_DASH in blob:
        fail("no_em_dashes", "document contains an em dash (use a period or comma)")

    # --- dollar_traceable -----------------------------------------------------
    for opp in opps:
        has_dollar = opp.get("yearly_savings") or opp.get("monthly_savings")
        if not has_dollar:
            continue
        ev = str(opp.get("evidence", "")).lower()
        traceable = (
            opp.get("data_source") in VALID_DATA_SOURCES
            or "plaid" in ev or "credit report" in ev or "credit-report" in ev
        )
        if not traceable:
            fail("dollar_traceable",
                 "opportunity %r has a dollar figure with no traceable source" % opp.get("type"))

    # --- estimate_language ----------------------------------------------------
    for opp in opps:
        if opp.get("confidence_multiplier", 1.0) < 1.0:
            ev = str(opp.get("evidence", "")).lower()
            if not any(w in ev for w in ESTIMATE_WORDS):
                fail("estimate_language",
                     "estimated opportunity %r must hedge (approximately/estimated/likely/~)"
                     % opp.get("type"))

    # --- persona_pattern_valid ------------------------------------------------
    if user.get("persona_pattern") not in PERSONAS:
        fail("persona_pattern_valid",
             "persona_pattern %r is not one of the seven defined values"
             % user.get("persona_pattern"))

    # --- notes_min_one_pattern ------------------------------------------------
    notes_low = " ".join(str(n).lower() for n in notes)
    named = any(k in notes_low for k in PATTERN_KEYWORDS)
    opted_out = "no non-obvious patterns" in notes_low
    if not (named or opted_out):
        fail("notes_min_one_pattern",
             "notes must name a Step-3 pattern or state 'No non-obvious patterns detected'")

    # --- confidence_audit_consistent (warning only, per skill) ---------------
    ca = audit.get("confidence_audit") or {}
    if ca and sum(int(v or 0) for v in ca.values()) == 0:
        warnings.append({"rule": "confidence_audit_consistent",
                         "detail": "confidence_audit counts are all zero"})

    return {"ok": len(failures) == 0, "failures": failures, "warnings": warnings}
