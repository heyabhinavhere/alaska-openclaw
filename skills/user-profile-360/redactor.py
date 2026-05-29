"""
redactor.py — strip toxic PII from raw BON sections before they reach Alaska.

Policy (confirmed 2026-05-29): FLAT. Anyone authorized (= anyone in the Team
Roster) sees the same thing. There is no admin/founder/engineer tiering of
financial numbers — exact figures are shown to all authorized callers. The
"who is authorized" gate (in-roster vs unknown) lives in the SKILL layer, not
here.

What this module guarantees regardless of caller: four classes of PII are
ALWAYS stripped, because they're never needed in a Slack message and are pure
liability —

  1. SSN              (credit_report.borrower.@_SSN, spinwheel.profile_details.ssn)
  2. Full DOB         (kept as age, which the API already provides in profile.age)
  3. Full account #   (Plaid already masks to last-4; we drop any fuller identifier)
  4. Full street addr (kept as city / state / postal)

Strategy is defense-in-depth: a deep recursive walk removes toxic keys wherever
they appear (so a schema change that moves SSN somewhere new is still caught),
plus section-specific transforms for the structured cases (phone, address).

This runs on RAW section data before it's shown verbatim (chat deep-dive,
transaction detail) or fed to the summarizer. The summarizer's own output is
derived numbers with no toxic PII by construction, but running raw through
here first is the belt-and-suspenders.
"""
from __future__ import annotations

import copy
from typing import Any

# Keys removed wherever they appear, at any depth, in any section. Case and
# MISMO (@_) variants included. This is the safety net.
ALWAYS_DROP_KEYS = {
    # SSN
    "@_SSN", "ssn", "SSN", "social_security_number", "ssn_last4",
    # Full date of birth (age is kept from profile.age)
    "@_BirthDate", "date_of_birth", "dateOfBirth", "dob", "birth_date",
}

# profile address: keep coarse location, drop the street line.
_PROFILE_ADDRESS_DROP = {"address"}  # street line; city/state/postal_code kept


def _deep_strip(obj: Any) -> Any:
    """Recursively drop ALWAYS_DROP_KEYS from dicts/lists. Returns a new
    structure; does not mutate the input."""
    if isinstance(obj, dict):
        return {
            k: _deep_strip(v)
            for k, v in obj.items()
            if k not in ALWAYS_DROP_KEYS
        }
    if isinstance(obj, list):
        return [_deep_strip(x) for x in obj]
    return obj


def _mask_phone(value: Any) -> Any:
    """Keep only the last 4 digits of a phone number."""
    if not isinstance(value, str):
        return value
    digits = "".join(ch for ch in value if ch.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "***"


def _mask_account_identifier(value: Any) -> Any:
    """Mask a raw account identifier to last-4 (Plaid's `mask` field is already
    last-4 and is left alone; this is for fuller identifiers like MISMO's
    @_AccountIdentifier)."""
    if not isinstance(value, str) or len(value) <= 4:
        return value
    return f"****{value[-4:]}"


# Account-identifier key names to mask (NOT drop — last-4 is useful context).
_ACCOUNT_ID_KEYS = {"@_AccountIdentifier", "account_number", "accountNumber"}


def _mask_account_ids(obj: Any) -> Any:
    """Recursively mask account-identifier values."""
    if isinstance(obj, dict):
        return {
            k: (_mask_account_identifier(v) if k in _ACCOUNT_ID_KEYS else _mask_account_ids(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_mask_account_ids(x) for x in obj]
    return obj


def _redact_profile(data: dict) -> dict:
    out = {k: v for k, v in data.items() if k not in _PROFILE_ADDRESS_DROP}
    if "mobile_no" in out:
        out["mobile_no"] = _mask_phone(out["mobile_no"])
    return out


def _redact_spinwheel(data: dict) -> dict:
    # Drop full address list; keep summaries, scores, names, liabilities.
    out = dict(data)
    pd = out.get("profile_details")
    if isinstance(pd, dict):
        pd = dict(pd)
        pd.pop("addresses", None)  # full addresses
        out["profile_details"] = pd
    return out


def _redact_credit_report(data: dict) -> dict:
    # borrower._RESIDENCE is the address block; drop it. (SSN/DOB already gone
    # via deep strip.) Account identifiers in credit_liability get masked.
    out = dict(data)
    borrower = out.get("borrower")
    if isinstance(borrower, dict):
        borrower = dict(borrower)
        borrower.pop("_RESIDENCE", None)
        out["borrower"] = borrower
    return out


# section name -> structural handler (applied AFTER the deep toxic-key strip)
_SECTION_HANDLERS = {
    "profile": _redact_profile,
    "spinwheel_credit_report": _redact_spinwheel,
    "credit_report": _redact_credit_report,
}


def redact_section(section_name: str, data: Any) -> Any:
    """Return a redacted copy of one raw section. Safe on None / {} / []."""
    if data is None or data == {} or data == []:
        return data
    # 1. Universal deep strip of toxic keys (SSN, DOB).
    cleaned = _deep_strip(copy.deepcopy(data))
    # 2. Mask account identifiers everywhere.
    cleaned = _mask_account_ids(cleaned)
    # 3. Section-specific structural transforms (address, phone).
    handler = _SECTION_HANDLERS.get(section_name)
    if handler is not None and isinstance(cleaned, dict):
        cleaned = handler(cleaned)
    return cleaned


def redact_sections(sections_data: dict[str, Any]) -> dict[str, Any]:
    """Redact a {section_name: raw_data} mapping (as returned by
    client.fetch_sections)."""
    return {name: redact_section(name, data) for name, data in sections_data.items()}


def assert_no_toxic_pii(obj: Any) -> bool:
    """Test/guard helper: returns True iff no ALWAYS_DROP_KEYS remain anywhere
    in the structure. Useful as a final gate in tests."""
    if isinstance(obj, dict):
        if any(k in ALWAYS_DROP_KEYS for k in obj.keys()):
            return False
        return all(assert_no_toxic_pii(v) for v in obj.values())
    if isinstance(obj, list):
        return all(assert_no_toxic_pii(x) for x in obj)
    return True
