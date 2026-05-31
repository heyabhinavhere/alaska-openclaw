# Lifecycle Events — Canonical Taxonomy

**Last updated:** 2026-05-29 by Abhinav
**Status:** Draft

---

## Purpose at BON

The canonical list of user-lifecycle events the team agrees on. What fires when, what's reliable, what's broken. Use this file when:

- A skill needs to detect signup, activation, engagement, or churn.
- A watcher subscribes to an event.
- Anyone asks "which event do I use for X?"

If an event isn't listed here, it isn't canonical. Don't invent. The full Amplitude firehose is in `integrations/amplitude.md`. This file curates the subset that maps to user lifecycle.

---

## The 9-step onboarding funnel

The onboarding flow has 9 ordered steps. All emit `onboarding_step_completed` with a `step_name` property.

| Step | `step_name` value | Typical 30d uniques | Notes |
|---|---|---|---|
| 1 | `phone_number_submitted` | ~100 | Entry point. Use to size top of funnel. |
| 2 | `otp_verified` | ~95 | ~5% drop (likely SMS delivery). |
| 3 | `email_verified` | ~89 | |
| 4 | `credit_report_disclaimer_accepted` | ~88 | |
| 5 | `dob_submitted` | ~85 | |
| 6 | `spin_wheel_connection_successful` | ~71 | **Biggest drop, ~15% Spinwheel identity failure.** |
| 7 | `set_pin` | ~73 | |
| 8 | `pin_verified` | ~73 | |
| 9 | `onboarding_complete` | ~73 | **Activation signal: user is now "onboarded."** |

### Additional `step_name` values that fire but aren't in the main funnel

`otp_sent`, `otp_verification_attempted`, `email_submit_attempted`, `dob_confirmed` (recovery path if Spinwheel fails on first DOB), `spin_wheel_connection_attempted`, `face_id_enabled`, `face_id_disabled`.

### Signup / completion proxies (use these, not the legacy events)

- **Signup started:** `onboarding_step_completed{step_name="phone_number_submitted"}`
- **Signup completed:** `onboarding_step_completed{step_name="onboarding_complete"}`

The legacy events `sign_up_started_event` and `sign_up_completed_event` stopped firing around March 17, 2026. Don't use them.

---

## Activation events

Activation = the user did the thing that creates retention pull. At BON, this is typically Plaid linking, but the formal definition is "Activated Saver" (see `definitions/metrics.md` § Activated Saver composite).

| Event | What it signals | Reliability |
|---|---|---|
| `add_card_initiate` | User tapped "Link Card" | Reliable |
| `add_card_successful` | Plaid Link succeeded for a credit card | Reliable but counter mismatches some days |
| `add_card_unsuccessful` | Plaid Link failed for a credit card | Reliable. Props: `failure_reason`, `exit_step`, `institution_name`, `error_type` |
| `add_bank_initiate` | User tapped "Link Bank" | Reliable |
| `add_bank_successful` | Plaid Link succeeded for a bank account | Reliable but counter mismatches |
| `add_bank_unsuccessful` | Plaid Link failed for a bank account | Reliable |

---

## Engagement events

| Event | What it signals | Reliability |
|---|---|---|
| `_active` | Any in-app activity (Amplitude built-in) | Reliable. Use with Real Users filter for DAU/WAU/MAU. |
| `credgpt_chat_started` | User opened a chat session | Misses ~5% of chatters. Use `credgpt_message_sent` for hard engagement. |
| `credgpt_message_sent` | User sent a typed message or tapped a suggested prompt | **Most reliable engagement metric.** Props: `message_text`, `input_type`, `message_length`. |
| `credgpt_response_received` | Agent responded | Sometimes > `message_sent` (includes proactive agent messages or double-fires). |
| `credgpt_suggested_prompt_tapped` | User tapped a suggested prompt button | Reliable. Props: `prompt_text`, `prompt_category`. |
| `credgpt_history_viewed` | User viewed chat history | Reliable. |
| `common_screen_view_tracker` | User viewed a screen | Reliable. Canonical screen tracking. |
| `screen_time_spent` | Time on screen | Fires on screen EXIT only. Undercounts chat-heavy users 3-10×. Don't use as primary engagement. |
| `screen_dropoff` | User dropped off from a screen | Reliable. |
| `feature_used` | User interacted with a feature | Reliable. Props: `feature_name`. |

---

## Conversion events

| Event | What it signals | Reliability |
|---|---|---|
| `spinwheel_started` | Identity verification initiated | Reliable. Fires pre-user_id (no Real Users filter). |
| `spinwheel_completed` | Identity verified | Reliable. |
| `spinwheel_failed` | Identity failed | Reliable but `failure_reason` is always "(none)", not populated. |
| `credit_score` | Credit score event (per refresh) | Reliable. Props: `score`. Fires every ~20 days. Use `gp:credit_score` for current. |
| `autopay_enabled` | User enabled AutoPay | Reliable. **Use this for AutoPay attach.** |

---

## Dormancy / churn events

There is **no explicit churn event** at BON. Dormancy and churn are inferred from absence of activity.

| Signal | Working definition |
|---|---|
| **Dormant** | Real user with no `_active` event in the last 14 days. |
| **Churned** | Real user with no `_active` event in the last 30 days. |
| `delete_membership` | User deleted their account. Reliable. Explicit signal, not inferred. |
| `notification_click` | User tapped a push notification | Fires near-zero (push delivery broken at the permission layer). |
| `fresh_install` | First app launch | Reliable. Duplicate of `[Amplitude] Application Installed`. |

---

## Events that DON'T fire reliably

Don't use these for canonical numbers. Use the alternative listed instead.

| Event | Problem | Use instead |
|---|---|---|
| `sign_up_started_event` | Stopped firing ~March 17, 2026 | `onboarding_step_completed{step_name="phone_number_submitted"}` |
| `sign_up_completed_event` | Stopped firing ~March 17, 2026 | `onboarding_step_completed{step_name="onboarding_complete"}` |
| `sign_up_drop_off` | Counter, not a rate. Fires per screen exit | Step-by-step drop-off from the funnel |
| `credgpt_response_error` | Fires 0 times in 30 days despite real errors | No alternative. Error tracking unimplemented. |
| `credgpt_chat_ended` | Fires for < 15% of sessions | `credgpt_chat_started` for session count |
| `session_start` | Doesn't fire for ~5-10% of users | `_active` uniques for user counts |
| `screen_time_spent` | Fires on screen EXIT only, undercounts chat | `credgpt_message_sent` totals as engagement proxy |
| `autopay_setup_successful` | Fires ~1 user/30d. Dead. | `autopay_enabled` |
| `auto_pay_choose_amount_viewed`, `auto_pay_selected_amount`, `auto_pay_selected_bank`, `auto_pay_select_bank_viewed` | Zero volume. Instrumentation broken (feature is alive). | `autopay_enabled` for terminal AutoPay attach |
| `pay_bill_initiated`, `pay_bill_success`, `one_time_bill_payment_initiated`, `one_time_bill_payment_success`, `one_time_bill_payment_failed`, `bill_payment_select_amount` | Zero volume. Instrumentation broken (manual bill payment is alive). | Backend `spinwheel_payment_requests` table for actual payment events |

---

## LEGACY events (killed features, do NOT compute against)

These events exist in the Amplitude taxonomy but refer to features that have been killed. See `README.md` § Killed features. Don't report numbers from them. Don't surface them in dashboards.

`slot_reward_redeem_initiated`, `slot_reward_redeem_successful`, `slot_reward_redeem_failed` — slot/wheel rewards (killed).

`add_to_cart`, `confirm_order`, `order_summary_viewed`, `select_address`, `stripe_initiated` — commerce / shopping (killed).

`password` — legacy auth event, no longer used.

---

## Definitions used across the team

- **"Signup"** = `phone_number_submitted` fired. The first formal step of onboarding.
- **"Onboarded"** = `onboarding_complete` fired AND `gp:credit_score > 0`. Both required because Spinwheel can fail after the onboarding UI completes.
- **"Activated Saver"** = hit ≥ 2 of the 6 success metrics. See `definitions/metrics.md` § Activated Saver composite.
- **"Chat-engaged"** = sent at least one `credgpt_message_sent` event in the window.
- **"Dormant"** = onboarded user with no `_active` event in the last 14 days.
- **"Churned"** = onboarded user with no `_active` event in the last 30 days.

## Known failure modes / edge cases

- **`spinwheel_*` events fire pre-user_id.** Don't apply the Real Users filter. Would return 0.
- **`failure_reason` on `spinwheel_failed` is always "(none)".** Not populated. Can't filter by failure reason.
- **Counter mismatch:** `add_card_successful + add_card_unsuccessful > add_card_initiate` on some days. Event double-fire bug. Aggregate over multi-day windows.
- **`credgpt_response_received > credgpt_message_sent` on some days.** Likely proactive agent messages or double-fires.
- **Naming inconsistencies in the Amplitude taxonomy:**
  - `credGPTScreenView` (camelCase) vs `screen_view_credgpt_home` (snake_case). Same feature.
  - `utilization_button` vs `utlisation_button`. Typo, two entries.
  - `spent_time_seconds` vs `time_spent_seconds`. Same property, different name on different events.

## Common queries / patterns

| Query | Where |
|---|---|
| 9-step onboarding funnel | `playbooks/common-queries.md` § Onboarding funnel |
| New signups in last hour | `playbooks/common-queries.md` § new_signup filter |
| Card linkage funnel | `playbooks/common-queries.md` § Card linkage funnel |
| Failed Plaid users in window | `playbooks/common-queries.md` § Failed Plaid users |
| Top engaged users (by message count) | `playbooks/common-queries.md` § Top chatters |
| Dormant users (no _active in 14d) | `playbooks/common-queries.md` § Dormant users |

## People

- **Owns event taxonomy:** Pankaj (app-side firing) + Sandeep (CredGPT-side instrumentation).
- **Owns funnel definitions:** Abhinav.
