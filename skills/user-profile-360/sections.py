"""
sections.py — Section catalog for the user-profile-360 skill.

Single source of truth for:
  - Which sections of the BON 360 API we know how to fetch
  - How long to cache each one (TTL)
  - How sensitive each one is (PII tier — drives redactor strictness)
  - Which sections satisfy which kinds of question (intent → section map)

Grounded in actual schema discovery against agentic-dev.boncredit.ai
(user 2762 fully populated, user 287 partial). Sections that were empty
for the fully-populated test user (linking_status, user_kpis,
detected_needs, financial_snapshots, financial_profile_v2, opportunities,
tasks, budgeting, progress, triggers, paydown) are intentionally NOT in
this catalog — they exist in the API response but the backend isn't
populating them yet, and reading product-layer interpretations would
make Alaska's intelligence downstream of BON's product logic rather
than parallel to it.

amplitude_events and customerio_events are also excluded — Alaska has
direct live access to those source APIs via amplitude-analyst and
customerio-ops respectively.

Update this file when:
  - The BON API surface changes (new section, removed section)
  - A previously-empty section starts being populated by the backend
  - A new intent emerges from real usage patterns
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PiiTier = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Section:
    """One fetchable section of the BON 360 user profile."""
    name: str
    pii_tier: PiiTier
    ttl_seconds: int
    notes: str = ""


# ============================================================
# Section catalog
# ============================================================
# TTL guidance:
#   900    (15 min) — chat (user activity, freshness-sensitive)
#   1800   (30 min) — current credit data
#   3600   (1 hr)   — most accounts / balances; aligns with Sandeep's
#                    nightly Array (02:00 UTC) + Plaid (03:00 UTC) jobs
#   21600  (6 hr)   — slow-changing historical or derived data
#
# PII tier guidance:
#   high   — contains identifiers, balances, SSN, DOB, account numbers,
#            employer names, raw chat content. Redactor must strip or band.
#   medium — derived/aggregated; may include exact numbers but no raw
#            identifiers. Redactor may band amounts for non-admin tiers.
#   low    — abstracted summary; safe to surface verbatim.

_SECTIONS: list[Section] = [
    # ---------------- Identity ----------------
    Section(
        "profile",
        pii_tier="high",
        ttl_seconds=3600,
        notes=(
            "Demographics + linking flags. is_card_added / is_bank_added / "
            "is_credit_activated / is_first_card_added / is_paydown_schedule_created "
            "all live here — the separate `linking_status` section is always "
            "empty, so we read flags from profile instead."
        ),
    ),
    Section(
        "persona",
        pii_tier="low",
        ttl_seconds=21600,
        notes=(
            "LLM-generated user summary. Empty for the fully-populated test "
            "user as of 2026-05-27 — kept in catalog so we pick it up "
            "automatically when backend starts populating."
        ),
    ),

    # ---------------- Credit (Array side — raw MISMO) ----------------
    Section(
        "credit_report",
        pii_tier="high",
        ttl_seconds=1800,
        notes=(
            "Latest Array report in raw MISMO JSON (@_FieldName keys, "
            "string-typed numbers). Contains borrower.@_SSN, @_BirthDate, "
            "addresses. Prefer tradeline_history + spinwheel for aggregation; "
            "fetch this only when the raw MISMO is genuinely needed."
        ),
    ),
    Section(
        "credit_report_history",
        pii_tier="medium",
        ttl_seconds=21600,
        notes="Score snapshots over time (not full reports). Lightweight.",
    ),
    Section(
        "tradeline_history",
        pii_tier="medium",
        ttl_seconds=21600,
        notes=(
            "Per-tradeline per-month snapshots with Array+Plaid resolved "
            "values and pre-computed deltas (balance_change, "
            "utilization_change, resolved_utilization). The cleanest data "
            "source for credit aggregations — prefer over credit_report."
        ),
    ),

    # ---------------- Credit (Spinwheel side — pre-aggregated) ----------------
    Section(
        "spinwheel_credit_report",
        pii_tier="high",
        ttl_seconds=1800,
        notes=(
            "Spinwheel data, cleaner format than MISMO. profile_details.ssn "
            "is PII. credit_card_summary, auto_loan_summary, personal_loan_summary, "
            "miscellaneous_liability_summary are pre-computed aggregates with "
            "currentOutstandingBalance / creditUtilization / etc."
        ),
    ),

    # ---------------- Plaid surfaces ----------------
    Section(
        "plaid_accounts",
        pii_tier="high",
        ttl_seconds=3600,
        notes=(
            "Accounts split by bucket: checking, savings, credit, other. Plus "
            ".summary with pre-computed totals: total_checking_balance, "
            "total_savings_balance, total_credit_balance, total_credit_limit, "
            "num_accounts."
        ),
    ),
    Section(
        "plaid_liabilities",
        pii_tier="high",
        ttl_seconds=3600,
        notes=(
            "Per-card balance/limit/APR/min_payment/due_date. Often empty "
            "(was empty for user 2762 despite full Plaid linkage) — use "
            "plaid_profiles.card_profile aggregates as the primary source, "
            "this as backup detail."
        ),
    ),
    Section(
        "plaid_transactions",
        pii_tier="high",
        ttl_seconds=3600,
        notes=(
            "Container. Useful sub-keys: total_count, date_range, recent_200 "
            "(capped at last 200 txns — much smaller than originally feared), "
            "by_category_current_month (pre-summed per Plaid category)."
        ),
    ),
    Section(
        "plaid_profiles",
        pii_tier="medium",
        ttl_seconds=3600,
        notes=(
            "The MVP section of the entire API. card_profile has 30 "
            "pre-computed fields (total_cc_balance_exact, "
            "overall_utilization_exact, weighted_avg_apr_exact, "
            "monthly_interest_exact, total_min_payment_exact, "
            "num_cards_overdue, highest_util_card_account_id, etc). "
            "bank_profile has 25 (low_balance_risk, savings_in_low_yield, "
            "estimated_yield_gain_yearly, monthly_surplus_exact, etc). "
            "monthly_aggregates_last_6 has 6 months of income/spend/net_flow."
        ),
    ),
    Section(
        "plaid_income",
        pii_tier="high",
        ttl_seconds=3600,
        notes=(
            "income_signals[] has per-source records with employer_name "
            "(PII), net_monthly_income, typical_deposit_amount, frequency, "
            "variability, last_3_deposits. Also plaid_link_items."
        ),
    ),

    # ---------------- Derived from Plaid ----------------
    Section(
        "subscriptions",
        pii_tier="medium",
        ttl_seconds=21600,
        notes=(
            "Detected recurring subs with monthly_cost_normalized + yearly_cost "
            "pre-computed, plus user_marked_kept/cancelled, price_hiked flag, "
            "detection_confidence. Slow-changing."
        ),
    ),

    # ---------------- Chat ----------------
    Section(
        "chat",
        pii_tier="high",
        ttl_seconds=900,
        notes=(
            "Container. Sub-keys: total_threads, threads, recent_turns, "
            "intent_breakdown (10 intent counts), agent_breakdown (5 sub-agent "
            "counts), feedback_summary (thumbs_up/down). "
            "recent_turns[] schema as of 2026-05-27 redeploy: "
            "{thread_id, question, answer, created_at}, capped at last 100. "
            "`answer` is populated ONLY for real multi-turn conversations "
            "from 2026-05-27 onward. It is NULL for: (a) all pre-05-27 "
            "history (no backfill), and (b) proactive/system prompts — which "
            "appear as single-turn threads (1 turn per thread_id, short "
            "templated `question`, no user-typed input). Verified empirically: "
            "real chats (e.g. 50 turns across 2 threads) carry answers; "
            "proactive prompts (e.g. 100 turns across 100 threads, ~20 distinct "
            "templated questions) never do. "
            "SUMMARIZER RULE: to show genuine user questions, filter to turns "
            "where answer is non-null OR the thread has >1 turn. Single-turn + "
            "null-answer turns are proactive prompts the user never typed — do "
            "NOT present them as 'the user asked X'. Treat null answer on a real "
            "turn as '[response not recorded]', not an error. "
            "The earlier per-turn fields (intent, agent, suggestions, "
            "latency_ms) were removed in the 05-27 redeploy, so we can no "
            "longer filter proactive turns by intent at the turn level — use "
            "the thread/answer heuristic above. Container-level "
            "intent_breakdown / agent_breakdown aggregates remain (that's what "
            "chat_topics relies on), but note they likely COUNT proactive "
            "prompts too, so 'proactive_briefing' inflates the totals."
        ),
    ),
]

# Indexed lookup
SECTIONS: dict[str, Section] = {s.name: s for s in _SECTIONS}


# ============================================================
# Sub-sections — addressable nested keys for container sections
# ============================================================
# These are not separately cached entries — they're plucked from their
# parent section's data after fetch. But intents can reference them so
# we know what's actually being read into context (matters for token
# cost and the redactor's per-field rules).

SUBSECTIONS: dict[str, str] = {
    # parent.subsection -> parent
    "plaid_transactions.recent_200": "plaid_transactions",
    "plaid_transactions.by_category_current_month": "plaid_transactions",
    "plaid_transactions.date_range": "plaid_transactions",
    "chat.recent_turns": "chat",
    "chat.threads": "chat",
    "chat.intent_breakdown": "chat",
    "chat.agent_breakdown": "chat",
    "chat.feedback_summary": "chat",
}


# ============================================================
# Intent → section list
# ============================================================
# The cost-and-PII control plane. When Alaska is asked a user-level
# question, she classifies it into one of these intents and we read
# only the listed sections/sub-sections — never the whole 559KB payload.
#
# Rules:
#   - Every intent includes "profile" (almost always needed for context)
#   - Chat-touching intents use sub-section names so the redactor knows
#     what's actually being read
#   - "full_picture" is intentionally NOT a union of all sections — it
#     caps at the highest-signal-per-byte slice
#   - When the LLM-classified intent doesn't fit, prefer asking the user
#     to disambiguate over silently fetching everything

INTENT_PROFILES: dict[str, list[str]] = {
    "user_summary": [
        "profile",
        "persona",
    ],
    "credit_health": [
        "profile",
        "credit_report_history",
        "tradeline_history",
        "spinwheel_credit_report",
    ],
    "debt_situation": [
        "profile",
        "credit_report_history",   # Array score (canonical) — see summarizer credit block
        "tradeline_history",
        "spinwheel_credit_report",
        "plaid_profiles",          # card_profile has the aggregates
        "plaid_liabilities",       # per-card detail when needed
    ],
    "spending_patterns": [
        "profile",
        "plaid_accounts",
        "plaid_transactions.by_category_current_month",
        "plaid_transactions.recent_200",
        "subscriptions",
        "plaid_profiles",
    ],
    "income_situation": [
        "profile",
        "plaid_income",
        "plaid_profiles",          # bank_profile has monthly_income_exact
    ],
    "subscription_review": [
        "profile",
        "subscriptions",
        "plaid_income",            # for ratio-to-income context
    ],
    "chat_topics": [
        "profile",
        "chat.intent_breakdown",
        "chat.agent_breakdown",
        "chat.feedback_summary",
        "chat.threads",
    ],
    "chat_deep_dive": [
        "profile",
        "chat.threads",
        "chat.recent_turns",
    ],
    "full_picture": [
        "profile",
        "persona",
        "credit_report_history",   # Array score (canonical); was missing -> only
                                   # stale Spinwheel showed on broad lookups
        "tradeline_history",
        "spinwheel_credit_report",
        "plaid_profiles",
        "plaid_accounts",
        "plaid_transactions.by_category_current_month",
        "subscriptions",
        "chat.intent_breakdown",
        "chat.feedback_summary",
    ],
}


# ============================================================
# Helpers
# ============================================================

def is_valid_section_or_subsection(name: str) -> bool:
    return name in SECTIONS or name in SUBSECTIONS


def get_parent(name: str) -> str:
    """Return the top-level section name for a section or sub-section."""
    if name in SECTIONS:
        return name
    if name in SUBSECTIONS:
        return SUBSECTIONS[name]
    raise ValueError(f"Unknown section: {name}")


def get_ttl(name: str) -> int:
    """TTL in seconds. Sub-sections inherit their parent's TTL."""
    return SECTIONS[get_parent(name)].ttl_seconds


def get_pii_tier(name: str) -> PiiTier:
    """PII tier. Sub-sections inherit their parent's tier."""
    return SECTIONS[get_parent(name)].pii_tier


def get_sections_for_intent(intent: str) -> list[str]:
    """Sections/sub-sections to satisfy a classified intent. Raises on
    unknown intent — we don't fall through to "fetch everything" silently."""
    if intent not in INTENT_PROFILES:
        raise ValueError(
            f"Unknown intent: {intent!r}. Known: {sorted(INTENT_PROFILES.keys())}"
        )
    return list(INTENT_PROFILES[intent])


def get_parents_for_intent(intent: str) -> set[str]:
    """Distinct top-level sections needed for an intent (de-duplicates
    sub-section parents). This is what the fetcher actually pulls from
    the API — sub-sections are extracted client-side."""
    return {get_parent(s) for s in get_sections_for_intent(intent)}


def all_intents() -> list[str]:
    """Sorted list of known intent names. Used by the classifier."""
    return sorted(INTENT_PROFILES.keys())


def all_sections() -> list[str]:
    """Sorted list of known section names (top-level only)."""
    return sorted(SECTIONS.keys())
