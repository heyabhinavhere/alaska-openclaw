"""Tests for the User 360 enrichment collector — fixtures only, no live API.

A realistic /profile payload is run through the real (file-loaded) user-profile-360
summarizer into the PMF funnel fact shape, plus identity resolution, profile fetch
status handling, and identity-collision detection. The HTTP layer is injected.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.collectors import identity, user360  # noqa: E402
from pmf_os.store import PmfStore  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WINDOW_START = "2026-06-11T00:00:00-07:00"
WINDOW_END = "2026-06-13T23:59:59-07:00"


def _profile_payload() -> dict:
    # A fully-populated user. Toxic PII (ssn/address/account_number) is present in
    # the raw payload — enrichment must never surface it into the funnel facts.
    return {
        "user_id": 2714,
        "profile": {
            "first_name": "Asha",
            "age": 34,
            "city": "Austin",
            "state": "TX",
            "created_at": "2026-06-11T10:20:00Z",
            "is_card_added": True,
            "is_bank_added": True,
            "is_credit_activated": True,
            "is_paydown_schedule_created": False,
            "email": "asha@example.com",
            "phone_number": "+15551234567",
            "ssn": "123-45-6789",
            "address": "1 Main St",
        },
        "credit_report_history": [
            {
                "report_date": "2026-05-24",
                "credit_score": {
                    "@_Value": "612",
                    "@_Date": "2026-05-24",
                    "@CreditRepositorySourceType": "Equifax",
                    "@_ModelNameTypeOtherDescription": "EquifaxVantageScore3.0",
                },
            }
        ],
        "plaid_profiles": {
            "card_profile": {
                "total_cc_balance_exact": 4200,
                "overall_utilization_exact": 0.62,
                "total_cc_limit_exact": 6800,
                "num_cards_active": 3,
                "weighted_avg_apr_exact": 24.99,
                "monthly_interest_exact": 87,
                "total_min_payment_exact": 142,
                "any_card_overdue": False,
                "account_number": "1234567890",
            },
            "bank_profile": {
                "total_cash_on_hand": 5200,
                "monthly_income_exact": 4200,
                "monthly_spending_exact": 3100,
                "low_balance_risk": False,
            },
        },
        "chat": {
            "total_threads": 3,
            "recent_turns": [
                {"thread_id": "t1", "question": "How do I lower utilization?", "answer": "Pay the highest-APR card first.", "created_at": "2026-06-12T18:00:00Z"},
                {"thread_id": "t1", "question": "What about a balance transfer?", "answer": "A 0% transfer can help.", "created_at": "2026-06-12T18:02:00Z"},
                {"thread_id": "t2", "question": "Your weekly money briefing is ready", "answer": None, "created_at": "2026-06-12T09:00:00Z"},
            ],
            "intent_breakdown": {"debt": 2, "proactive_briefing": 1},
            "feedback_summary": {"thumbs_up": 1, "thumbs_down": 0},
        },
    }


def test_enrich_facts_maps_profile_and_daily_facts():
    result = user360.enrich_facts(_profile_payload())
    pf, df = result["profile_facts"], result["daily_facts"]

    assert pf["bon_user_id"] == 2714
    assert pf["credit_score"] == 612  # Array-canonical MISMO parse via the summarizer
    assert pf["onboarding_complete"] is True
    assert pf["is_card_added"] is True and pf["is_bank_added"] is True

    assert df["meaningful_credgpt_messages"] == 2  # t1's 2 real turns; t2 proactive is filtered
    assert set(df["value_actions"]) == {"card_link_success", "bank_link_success"}
    assert df["pmf_success_metrics"]["linked_financial_context"] == "confirmed"
    assert df["financial_context"]["debt"]["total_cc_balance"] == 4200

    # No toxic PII ever reaches the funnel facts.
    blob = json.dumps(result)
    assert "123-45-6789" not in blob  # ssn
    assert "1 Main St" not in blob  # address
    assert "1234567890" not in blob  # raw account number
    assert "ssn" not in df["financial_context"]


def test_resolve_bon_user_id_precedence():
    # already-known id: no search call
    assert user360.resolve_bon_user_id({"bon_user_id": "2714"})["user_id"] == 2714

    def search_email_hit(query_type, value):
        assert query_type == "email"
        return 200, json.dumps([{"user_id": 2714}]).encode()

    row = {"email": "asha@example.com"}
    res = user360.resolve_bon_user_id(row, search_fetcher=search_email_hit)
    assert res["status"] == "resolved" and res["user_id"] == 2714 and res["detail"] == "email"

    # no usable identifier -> unresolvable, no fetcher invoked
    def boom(query_type, value):  # pragma: no cover - must not be called
        raise AssertionError("should not search without an identifier")

    assert user360.resolve_bon_user_id({}, search_fetcher=boom)["status"] == "unresolvable"

    # multiple matches -> caller disambiguates
    def search_multi(query_type, value):
        return 200, json.dumps([{"user_id": 1}, {"user_id": 2}]).encode()

    assert user360.resolve_bon_user_id({"phone_number": "+15551234567"}, search_fetcher=search_multi)["status"] == "multiple"


def test_fetch_profile_status_handling():
    payload = _profile_payload()

    assert user360.fetch_profile(2714, profile_fetcher=lambda uid: (200, json.dumps(payload).encode()))["status"] == "ok"
    assert user360.fetch_profile(2714, profile_fetcher=lambda uid: (404, b""))["status"] == "not_found"
    assert user360.fetch_profile(2714, profile_fetcher=lambda uid: (401, b""))["status"] == "auth_error"
    mismatch = user360.fetch_profile(2714, profile_fetcher=lambda uid: (200, json.dumps({"user_id": 999}).encode()))
    assert mismatch["status"] == "identity_mismatch"


def test_detect_identity_collisions():
    users = [
        {"user_key": "amp:222", "bon_user_id": "2714"},
        {"user_key": "user:2714", "bon_user_id": "2714"},
        {"user_key": "amp:333", "bon_user_id": "999"},
        {"user_key": "amp:444", "bon_user_id": None},
    ]
    groups = identity.detect_collisions(users)
    assert groups == [{"bon_user_id": "2714", "user_keys": ["amp:222", "user:2714"]}]
    assert identity.canonical_user_key("2714") == "user:2714"
    assert identity.canonical_user_key(None) is None


def test_enrichment_updates_registry_row_in_place():
    db = str(Path(tempfile.mkdtemp(prefix="pmf_u360_")) / "alaska_pmf.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(cohort_id="pmf-u360", name="U360", signup_window_start=WINDOW_START, signup_window_end=WINDOW_END, activate=True)

    # P1-style intake: amplitude_id only, no bon_user_id yet
    key = store.upsert_signup_user(
        "pmf-u360",
        {"event_type": "onboarding_step_completed", "step_name": "phone_number_submitted",
         "event_time": "2026-06-11T10:15:00-07:00", "event_id": "e1", "amplitude_id": 222,
         "user_properties": {"gp:email": "asha@example.com"}},
    )["user_key"]
    assert key == "amp:222"

    enriched = user360.enrich_facts(_profile_payload())
    store.update_user_profile("pmf-u360", key, {**enriched["profile_facts"], "email": "asha@example.com"})

    row = store.get_user("pmf-u360", key)
    assert row["bon_user_id"] == "2714"  # resolved id now on the original row (no new row)
    assert row["credit_score"] == 612
    assert row["is_real_user"] == 1
    assert len(store.list_users("pmf-u360")) == 1  # enriched in place, no duplicate


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
