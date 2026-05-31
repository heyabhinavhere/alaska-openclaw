# BON Admin API — the 360 User Profile

**Last updated:** 2026-05-30 · **Status:** Draft. Derived from the live `user-profile-360` skill code (`client.py`, `sections.py`, `SKILL.md`) + schema discovery against the dev backend.

> **What this file is:** BON's internal **admin API** (built by Sandeep) — what it is, how Alaska authenticates, and **what Alaska can pull from it** (the per-user 360 profile: credit, Plaid, subscriptions, chat). The capability inventory.
> **What it is NOT:** how Alaska *uses* it. The resolve → cache → redact → summarize → audit → present workflow lives in the **`user-profile-360` skill** (`skills/user-profile-360/`). This file is the API contract; the skill is the consumer. → see `skills/user-profile-360/SKILL.md`.

---

## What it is

A read-only admin API on BON's backend that exposes everything BON holds on a single user. It's Alaska's deep **per-user** lens — the counterpart to her aggregate tools (Amplitude for "how many users…", Customer.io for messaging). One profile call returns the **whole** user (~559 KB), assembled from BON's credit (Array + Spinwheel), banking (Plaid), subscription-detection, and CredGPT chat subsystems.

## Auth + endpoints (the contract)

| | |
|---|---|
| Base URL | env `BON_API_BASE_URL` (schema discovered against the dev env `agentic-dev.boncredit.ai`) |
| Auth | header `X-Admin-Key: $BON_ADMIN_API_KEY` (env, set in Railway) |
| Style | plain REST/JSON over HTTPS; GET-only for Alaska's use |

**Two endpoints:**

1. **Identity resolution** — `GET /api/admin/users/search?email=<>|phone=<>|name=<>`
   Returns a JSON **array** of matches: `[{user_id, email, name, created_at}, …]`.
   - 0 results → not found · 1 → resolved · many → caller disambiguates (returns up to ~20).
   - `name` is a partial/fuzzy match (often multiple); `email`/`phone` are exact. Phone is normalized to digits with a leading US country code dropped, so `1XXXXXXXXXX` and `XXXXXXXXXX` resolve the same.

2. **The 360 profile** — `GET /api/admin/users/{user_id}/profile`
   Returns the entire profile as **one JSON object**, keyed by section name (catalog below). One call = the whole user; there is no per-section endpoint.

**Status codes Alaska handles:** `200` ok · `404` user not found · `401/403` auth failed (admin key rotated → flag Abhinav) · `400` bad search query · `5xx`/timeout → unavailable. There's also an **identity-mismatch** guard: the profile payload's own `user_id` must equal the requested one (a mismatch is a backend routing bug, not a normal miss).

## What Alaska can pull — the section catalog

The profile is a bag of sections. These are the ones BON actually populates and Alaska reads (canonical source: `sections.py`):

| Section | What's in it |
|---|---|
| `profile` | Demographics + the linking flags: `is_card_added`, `is_bank_added`, `is_credit_activated`, `is_first_card_added`, `is_paydown_schedule_created`. *(The separate `linking_status` section is always empty — read the flags here.)* |
| `persona` | LLM-generated user summary. *(Empty as of 2026-05-27; catalogued so Alaska auto-picks-it-up when the backend starts filling it.)* |
| `credit_report` | Latest **Array** report in raw MISMO JSON (`@_FieldName` keys, string-typed numbers). Holds SSN/DOB/addresses (toxic PII). Prefer the two below for aggregation. |
| `credit_report_history` | Score snapshots over time — the **Array score is canonical** (it's a **VantageScore 3.0, not FICO**). |
| `tradeline_history` | Per-tradeline monthly snapshots with Array+Plaid resolved values + pre-computed deltas (`balance_change`, `utilization_change`, `resolved_utilization`). **Cleanest source for credit aggregations.** |
| `spinwheel_credit_report` | Spinwheel data (cleaner than MISMO): pre-computed `credit_card_summary` / `auto_loan_summary` / `personal_loan_summary` / etc. Fallback/secondary to Array. `profile_details.ssn` is PII. |
| `plaid_accounts` | Accounts by bucket (checking / savings / credit / other) + a `.summary` of pre-summed totals (`total_credit_balance`, `total_credit_limit`, `num_accounts`, …). |
| `plaid_liabilities` | Per-card balance/limit/APR/min_payment/due_date. **Often empty even for linked users** → use `plaid_profiles.card_profile` as the primary, this as backup detail. |
| `plaid_transactions` | `total_count`, `date_range`, `recent_200` (last 200 txns), `by_category_current_month` (pre-summed per Plaid category). |
| `plaid_profiles` | **The MVP section.** `card_profile` = 30 pre-computed debt fields (`total_cc_balance_exact`, `overall_utilization_exact`, `weighted_avg_apr_exact`, `monthly_interest_exact`, `total_min_payment_exact`, `num_cards_overdue`, `highest_util_card_account_id`, …). `bank_profile` = 25 (`monthly_surplus_exact`, `low_balance_risk`, `savings_in_low_yield`, …). `monthly_aggregates_last_6` = 6 months of income/spend/net_flow. |
| `plaid_income` | `income_signals[]` per source: `employer_name` (PII), `net_monthly_income`, `typical_deposit_amount`, `frequency`, `variability`, `last_3_deposits`. |
| `subscriptions` | Detected recurring subs: `monthly_cost_normalized`, `yearly_cost`, `user_marked_kept/cancelled`, `price_hiked`, `detection_confidence`. Slow-changing. |
| `chat` | CredGPT history: `total_threads`, `recent_turns` (last 100, each `{thread_id, question, answer, created_at}`), `intent_breakdown` (10 intents), `agent_breakdown` (5 sub-agents), `feedback_summary` (thumbs up/down). **`answer` is populated only for real multi-turn conversations from 2026-05-27 onward** — null for older history and for proactive/system prompts. |

Addressable sub-sections (plucked client-side, not separate endpoints): `plaid_transactions.{recent_200, by_category_current_month, date_range}` and `chat.{recent_turns, threads, intent_breakdown, agent_breakdown, feedback_summary}`.

**Design principle worth knowing (the capability boundary):** the API *also* returns BON's product-layer interpretations — `user_kpis`, `detected_needs`, `opportunities`, `financial_profile_v2`, `budgeting`, `progress`, `paydown`, `financial_snapshots`. **Alaska deliberately does NOT read these.** They're unpopulated today, and — by design — Alaska forms her *own* read of a user from raw signal (credit / Plaid / chat) so her intelligence stays *parallel to* BON's product logic, not downstream of it. `amplitude_events` / `customerio_events` are also skipped — Alaska has direct live access to those via the **amplitude-analyst** and **customerio-ops** skills.

## BON-specific data facts (so the numbers are read right)

- **Credit = VantageScore 3.0, not FICO.** Canonical source is **Array**; Spinwheel is a fallback (a signup-snapshot that may be stale).
- **Debt aggregates come from `plaid_profiles.card_profile`** (real-time Plaid) first, Spinwheel second. `plaid_liabilities` is unreliable (often empty).
- **Income** is either exact (`plaid_bank`) or estimated (`plaid_income_signals`, inferred from deposit patterns) — read the `source` and qualify accordingly.
- **Toxic PII** (SSN, full DOB, account numbers, street address, `employer_name`) is present in the raw payload (`credit_report`, `spinwheel_credit_report.profile_details.ssn`, `plaid_income`) and is **stripped by the skill's redactor before anything reaches Alaska's context** — she never sees it, so she can't leak it.
- The full payload is large (~559 KB), which is why the skill never reads the whole thing — it pulls a narrow section set per question.

## How Alaska uses this → the skill (pointer, not duplicated here)

All the *workflow* lives in **`skills/user-profile-360/`** — don't re-document it in the KB:
- **Identity resolution** (search-cache-first; 0/1/many handling; fallback to Customer.io / Amplitude when search is down — the CIO `id` *is* the BON `user_id`).
- **Cache-first fetch** with per-section TTLs + a per-user inflight lock (`cache.py`); one profile call refreshes the whole user's cache.
- **Redaction** of toxic PII (`redactor.py`), **summarization** into derived headline metrics (`summarizer.py`), **audit logging** of every access (`audit.py`).
- **Access gating** — only Team-Roster members may look a user up (flat policy: members see exact figures).
- **Intent → section narrowing** (`sections.py` `INTENT_PROFILES`) — the cost/PII control plane — behind one entry point, `lookup.py`.

→ See `skills/user-profile-360/SKILL.md`.

## People / ownership

- **Owns the BON admin API (the backend):** Sandeep (+ the BON backend team).
- **SME for the `user-profile-360` consumer skill:** Abhinav (+ Sandeep).

## Open questions / notes

- **Base URL** is env-driven and currently targets the **dev** backend (`agentic-dev.boncredit.ai`). Confirm the prod URL / cutover for the June 10 launch.
- Several product-layer sections (`persona`, `user_kpis`, `financial_profile_v2`, …) exist but are **empty**. When the backend starts populating them, revisit whether Alaska should read any (today she stays on raw signal by design).
- `chat.answer` has no backfill for pre-2026-05-27 history (those turns stay null).
