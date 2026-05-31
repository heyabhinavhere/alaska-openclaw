# Spinwheel — Identity Verification + Credit Card Bill Payments

**Last updated:** 2026-05-31 by Abhinav (corrected: `spinwheel_failed` reason field + dead payment events)
**Status:** Draft

---

## Purpose at BON

Spinwheel does two things at BON.

1. **Identity verification.** BON passes a verified phone number and DOB to Spinwheel. Spinwheel returns the user's full profile: full name, residential address, full SSN, and a credit report. BON uses the SSN to create the Array user. **BON does not use Spinwheel's credit report.** The credit report shown in the app comes from Array. Spinwheel requires the credit-report pull as part of using their identity API, so BON pulls it once and discards. Both Spinwheel and Array use Equifax bureau under the hood, but Array is the source of truth in product. ~15% of users fail at this Spinwheel step. Biggest single drop in the onboarding funnel.
2. **Credit card bill payments.** Both AutoPay (scheduled) and manual (one-time) credit card payments run through Spinwheel.

Two distinct roles, same vendor. Different events, different reliability characteristics.

---

## How Alaska gets Spinwheel data

Alaska does NOT call Spinwheel directly. No Spinwheel MCP, no API connector. Same two-path setup as Plaid.

| Question type | Where to go |
|---|---|
| Aggregate identity verification success / failure rates | **Amplitude** (`spinwheel_*` events) |
| AutoPay attach rate | **Amplitude** (`autopay_enabled` — the one reliably-live AutoPay event; the mid-flow `auto_pay_*` events are DEAD, see below) |
| Per-user identity verification history | **Amplitude** events filtered by `user_id` |
| Per-user AutoPay state (active card / bank) | **Amplitude** (`autopay_enabled` filtered by `user_id`) |
| Payment history, amounts, scheduled payments, webhook / payment status | **User 360 profile API** (Sandeep) / backend — the Amplitude bill-payment events are DEAD (zero fires), so do NOT use Amplitude for these |
| Identity content (full name, residential address, full SSN, the discarded Spinwheel credit report if stored) | **User 360 profile API** (Sandeep). Treat SSN as PII. Never log or surface. |

Rule of thumb: Amplitude carries the **identity-verification** events (`spinwheel_*`) plus the one live AutoPay terminal event (`autopay_enabled`). Everything about **payments** (one-time bill payments, amounts, webhook results) is either DEAD in Amplitude or lives in the backend — pull it from the **User 360 API**, not Amplitude.

→ For the per-user data Alaska actually reads (identity, payment records), see `integrations/user-profile-api.md`.

---

## Events fired to Amplitude

Verified against the Amplitude reference (`workspace/references/amplitude-api-reference.md`).

### Identity verification (LIVE)

| Event | Properties | Notes |
|---|---|---|
| `spinwheel_started` | `platform`, `user_id` | Identity verification initiated. Fires pre-`gp:user_id` so Real Users filter would return 0. |
| `spinwheel_completed` | `platform`, `user_id` | Identity verified. |
| `spinwheel_failed` | `platform`, `failure_reason`, `user_id` | Verification failed. **`failure_reason` is always "(none)" — not populated** (per the reference). This event does NOT carry *why* it failed; for the reason, use backend logs / Spinwheel's own error reporting. |

**Critical filter rule.** Do NOT apply the Real Users filter to `spinwheel_*` events. They fire before `gp:user_id` is assigned during onboarding.

### AutoPay

| Event | Properties | Notes |
|---|---|---|
| `autopay_enabled` | `card_name`, `bank_name` | **Canonical terminal AutoPay event — the ONLY reliably-live AutoPay event.** Use this for "users with AutoPay attached." |
| `autopay_setup_initiated` | `payer_id`, `platform`, `user_id` | User started AutoPay setup. Low volume — verify before relying on it for a funnel. |
| `autopay_setup_failed` | `payer_id`, `platform`, `user_id` | AutoPay setup failed (added Mar 13 2026). Low volume. |
| `autopay_setup_successful`, `auto_pay_proceed_click`, `auto_pay_choose_amount_viewed`, `auto_pay_selected_amount`, `auto_pay_select_bank_viewed`, `auto_pay_selected_bank` | — | **DEAD — zero (or ~1) fires / 30 days** per the reference. Do NOT query. Use `autopay_enabled` for attach. |

### Bill payments — DEAD INSTRUMENTATION

**The one-time bill-payment event family fires ZERO times in 30 days** (per the reference — the feature is unshipped or the instrumentation is broken). Do NOT query these for metrics or per-user history — you'll get empty results and fabricate conclusions. For actual payment records / amounts, use the **User 360 profile API** / backend.

Dead (zero fires): `one_time_bill_payment_initiated`, `one_time_bill_payment_success`, `one_time_bill_payment_failed`, `one_time_suggested_bill_payment_initiated`, `bill_payment_select_bank`, `bill_payment_select_amount`, `pay_bill_initiated`, `pay_bill_success`. (`payment_failed`, a generic catch-all with a `reason` prop, is also effectively unused.)

---

## What is NOT in Amplitude (use User 360 API instead)

- **Identity content from Spinwheel.** Full name, residential address, full SSN, and the Spinwheel credit report (which BON does not use). These live in the backend identity profile. Treat SSN and other PII as sensitive. Never log or surface.
- **Payment records.** Because the bill-payment events are dead in Amplitude, per-user payment history / amounts / status come from the **User 360 API** / backend, not Amplitude.

---

## Definitions used across the team

- **"Spinwheel success rate"** = `totals(spinwheel_completed) / (totals(spinwheel_completed) + totals(spinwheel_failed))`. Target > 85%. Do NOT apply Real Users filter.
- **"Spinwheel failure"** = `spinwheel_failed` event. ~15% of users hit this. **The event carries no usable failure reason** (`failure_reason` is always "(none)") — to diagnose *why*, use backend logs / Spinwheel's side.
- **"DOB recovery path"** = the `dob_confirmed` step in onboarding, fired when a user re-confirms DOB after a first Spinwheel attempt fails.
- **"AutoPay"** = scheduled credit card payment feature. Terminal attach event is `autopay_enabled`.
- **"AutoPay attach rate"** = `uniques(autopay_enabled) / uniques(autopay_setup_initiated)` in the window.
- **"Spinwheel chain"** = the sequence: Spinwheel returns identity profile + mandatory (but discarded) credit report → backend creates Array user with the SSN → backend orders + retrieves the Array credit report. The credit report shown to the user is Array's, not Spinwheel's. Code references this collectively as `AfterSpinwheel` paths (note typo in source: `Spiwheel` not `Spinwheel`).

*(The product has "manual bill payment" and "AI-suggested payment" concepts, but their Amplitude events are DEAD — track those via the User 360 API / backend, not Amplitude.)*

## Known failure modes / edge cases

- **`spinwheel_*` events fire pre-user_id.** Don't apply the Real Users filter. Would return 0.
- **`spinwheel_failed` carries no failure reason.** Its `failure_reason` property is always "(none)" — not populated. Don't try to read *why* a verification failed from this event (no `error`/`failure_reason` data); use backend / Spinwheel-side reporting.
- **~15% identity failure** is the biggest single onboarding drop. Likely causes: SSN entry typos, name format mismatches with Equifax records, DOB inconsistencies.
- **Recovery path used.** `dob_confirmed` step. Conversion lift unclear without analysis.
- **Spinwheel-Array chain is fragile.** Spinwheel success → Array user-create call → if Array call fails silently, user has Spinwheel profile but no credit report. Result: `gp:credit_score = 0`, user fails Real Users filter.
- **Bill-payment + most `auto_pay_*` mid-flow events are DEAD** (zero fires). Only `autopay_enabled` (AutoPay attach) and the `spinwheel_*` identity events are reliably live. For payment data, use the User 360 API.

## Common queries / patterns

| Query | How |
|---|---|
| Spinwheel success rate (rolling 14 days) | `totals(spinwheel_completed) / (totals(spinwheel_completed) + totals(spinwheel_failed))`, no Real Users filter |
| Spinwheel funnel: started → completed/failed | Three event uniques, no Real Users filter |
| Spinwheel failure reasons | **Not available from Amplitude** — `spinwheel_failed` has no populated reason field. Use backend / Spinwheel-side error reporting. |
| Users stuck at `dob_submitted` (no `spin_wheel_connection_successful`) | Set diff between onboarding step events |
| AutoPay attach rate | `uniques(autopay_enabled)` over `uniques(autopay_setup_initiated)` in window |
| Per-user AutoPay state (active card, schedule) | `autopay_enabled` event filtered by `user_id` (carries `card_name`, `bank_name`) |
| Bill-payment metrics / per-user payment history / amounts | **Not available from Amplitude (dead events)** — use the User 360 API / backend |
| Per-user identity profile (name, address, SSN) | User 360 API (Sandeep). PII, never surface. |

## People

- **Owns Spinwheel integration (backend):** Sandeep.
- **Owns AutoPay UX:** Pankaj (frontend) + Abhinav (design).
- **Owns onboarding flow design:** Abhinav.
