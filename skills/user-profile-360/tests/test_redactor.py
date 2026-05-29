"""
Tests for redactor.py — synthetic data, deterministic, no real PII.

Runnable standalone:  python3 test_redactor.py
"""
from __future__ import annotations

import os
import sys

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

import redactor  # noqa: E402


def test_profile_strips_dob_address_masks_phone_keeps_age():
    raw = {
        "first_name": "Jane", "last_name": "Doe", "age": 29,
        "date_of_birth": "1996-03-14", "mobile_no": "+1 415 555 0142",
        "address": "742 Evergreen Terrace", "city": "Austin", "state": "TX",
        "postal_code": "78701", "email": "jane@example.com",
    }
    out = redactor.redact_section("profile", raw)
    assert "date_of_birth" not in out          # DOB dropped
    assert out["age"] == 29                     # age kept
    assert "address" not in out                 # street dropped
    assert out["city"] == "Austin" and out["state"] == "TX"  # coarse loc kept
    assert out["mobile_no"].endswith("0142") and out["mobile_no"].startswith("***")
    assert out["email"] == "jane@example.com"   # email kept (low-tox, useful)
    assert redactor.assert_no_toxic_pii(out)


def test_credit_report_borrower_strips_ssn_dob_residence():
    raw = {
        "borrower": {
            "@_FirstName": "Jane", "@_LastName": "Doe",
            "@_SSN": "123-45-6789", "@_BirthDate": "1996-03-14",
            "_RESIDENCE": {"@_StreetAddress": "742 Evergreen"},
        },
        "credit_liability": [
            {"@_AccountIdentifier": "4111111111111234", "@_UnpaidBalanceAmount": "1200"},
        ],
    }
    out = redactor.redact_section("credit_report", raw)
    assert "@_SSN" not in out["borrower"]
    assert "@_BirthDate" not in out["borrower"]
    assert "_RESIDENCE" not in out["borrower"]
    assert out["borrower"]["@_FirstName"] == "Jane"
    # account identifier masked to last 4
    assert out["credit_liability"][0]["@_AccountIdentifier"] == "****1234"
    assert out["credit_liability"][0]["@_UnpaidBalanceAmount"] == "1200"  # balance kept
    assert redactor.assert_no_toxic_pii(out)


def test_spinwheel_strips_ssn_dob_addresses():
    raw = {
        "profile_details": {
            "firstName": "Jane", "creditScore": 712,
            "ssn": "123456789", "dateOfBirth": "1996-03-14",
            "addresses": [{"line1": "742 Evergreen"}],
            "employmentHistory": [{"employer": "Acme"}],  # kept (not in strip list)
        },
        "credit_card_summary": {"creditUtilization": 0.62, "noOfCreditCards": 3},
    }
    out = redactor.redact_section("spinwheel_credit_report", raw)
    pd = out["profile_details"]
    assert "ssn" not in pd and "dateOfBirth" not in pd
    assert "addresses" not in pd
    assert pd["creditScore"] == 712
    assert pd["employmentHistory"] == [{"employer": "Acme"}]  # employer kept
    assert out["credit_card_summary"]["creditUtilization"] == 0.62
    assert redactor.assert_no_toxic_pii(out)


def test_deep_strip_catches_nested_ssn():
    # An SSN buried in an unexpected place is still caught by the deep walk.
    raw = {"a": {"b": [{"c": {"ssn": "999-99-9999", "ok": 1}}]}}
    out = redactor.redact_section("chat", raw)  # 'chat' has no special handler
    assert redactor.assert_no_toxic_pii(out)
    assert out["a"]["b"][0]["c"] == {"ok": 1}


def test_empty_and_none_passthrough():
    assert redactor.redact_section("profile", None) is None
    assert redactor.redact_section("plaid_liabilities", []) == []
    assert redactor.redact_section("persona", {}) == {}


def test_redact_sections_mapping():
    data = {
        "profile": {"age": 30, "ssn": "111-22-3333", "city": "Reno"},
        "persona": {},
    }
    out = redactor.redact_sections(data)
    assert redactor.assert_no_toxic_pii(out)
    assert out["profile"]["age"] == 30 and out["profile"]["city"] == "Reno"


def test_does_not_mutate_input():
    raw = {"profile_details": {"ssn": "123", "creditScore": 700}}
    _ = redactor.redact_section("spinwheel_credit_report", raw)
    assert raw["profile_details"]["ssn"] == "123"  # original untouched


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
