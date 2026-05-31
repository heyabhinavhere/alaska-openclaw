# Plaid — Banking Data Middleware

**Last updated:** 2026-05-29 by Abhinav
**Status:** Draft

---

## Purpose at BON

Plaid is BON's bank and credit card linking middleware. Users connect their financial accounts through Plaid Link inside the app. Once linked, BON pulls transactions, balances, and credit-card liability details.

Two flows:

- **Bank linking** (`add_bank_*` events). Connects checking and savings for transactions and balance.
- **Card linking** (`add_card_*` events). Connects credit cards for liability data (balance, minimum payment, due date, APR where available).

---

## How Alaska gets Plaid data

Alaska does NOT call Plaid directly. There is no Plaid MCP or Plaid API connector for Alaska. Two access paths only.

| Question type | Where to go |
|---|---|
| Aggregate metrics, funnels, drop-off, segment counts | **Amplitude** (`add_card_*`, `add_bank_*` events) |
| Per-user linkage history: is this user linked? when did they link? did they fail? where did they drop? | **Amplitude** (`add_card_*`, `add_bank_*` events + `gp:is_card_linked` / `gp:is_bank_linked` user properties) |
| Per-user financial content: which cards/banks they have, balances, transactions, APR, due dates, payment history | **User 360 profile API** (Sandeep) |

Rule of thumb: **Amplitude tells you what happened, User 360 tells you what they have.** Both are needed for most per-user investigations. → the per-user card/account data Alaska reads comes via `integrations/user-profile-api.md`. Don't fabricate Plaid endpoint calls. There aren't any for Alaska.

---

## Events fired to Amplitude

All Plaid events come from the Flutter app. Properties verified against Amplitude taxonomy on 2026-05-29.

### `add_card_initiate` / `add_bank_initiate`

Minimal payload. Fires when user taps "Link Card" or "Link Bank". Institution data is NOT here (user hasn't picked one yet).

| Property | Description |
|---|---|
| `platform` | `ios` or `android` |
| `user_id` | BON user_id |

### `add_card_successful` / `add_bank_successful`

23 / 22 properties.

| Property | Description |
|---|---|
| `institution_id`, `institution_name` | Which bank the user linked |
| `institution_search_query` | What the user typed in the institution picker |
| `link_type` | Linking flow variant |
| `accounts_linked_count` | How many accounts in this single Plaid session |
| `link_session_id` | Plaid-side session ID for this link attempt |
| `mfa_type` | If MFA was used, which type |
| `reached_credentials`, `reached_mfa`, `reached_oauth` | Booleans for which flow stages the user passed through |
| `credential_submit_attempts` | How many times user submitted credentials |
| `error_event_count` | Errors encountered mid-flow but still ended successfully |
| `last_error_event_code` | Code of the last error if any |
| `oauth_closed_without_complete` | OAuth aborted intermediately |
| `spent_time_seconds`, `spent_time_milliseconds` | Time on the Plaid modal |
| `card_linking_time_seconds`, `card_linking_time_milliseconds` | End-to-end linking time |
| `session_duration`, `session_id`, `time_on_last_view` | App session context |
| `platform`, `user_id` | Standard |

### `add_card_unsuccessful` / `add_bank_unsuccessful`

32 properties. The richest event for failure analysis.

| Property | Description |
|---|---|
| `error_code` | Plaid error code |
| `error_message` | Human-readable error |
| `error_raw_message` | Unprocessed error from Plaid |
| `error_type` | Plaid error category |
| `failure_reason` | BON-derived reason (often less informative than `error_*`) |
| `has_error`, `last_error_event_code`, `error_event_count` | Error context |
| `exit_step` | Which step in the Plaid Link modal the user dropped from |
| `last_view_name` | Last screen the user saw before exit |
| `view_transitions_count` | How many screens user moved through |
| `reached_credentials`, `reached_mfa`, `reached_oauth` | Booleans for flow position |
| `oauth_closed_without_complete` | OAuth was closed without finishing |
| `credential_submit_attempts` | Attempts before giving up |
| `mfa_type` | MFA stage type if reached |
| `institution_id`, `institution_name`, `institution_search_query` | Which bank |
| `is_linking_from_agentic` | **Whether linking was initiated from the CredGPT chat or the standard button/CTA.** Use this to split chat-driven vs button-driven linkage. |
| `is_update_mode` | Whether updating an existing connection rather than first-time linking |
| `link_session_id`, `link_type`, `request_id` | Plaid session identifiers |
| `spent_time_seconds`, `spent_time_milliseconds`, `session_duration`, `time_on_last_view` | Timing |
| `platform`, `user_id`, `session_id` | Standard |

### Linkage state in Amplitude

After a successful link, the app calls `identify()` to update user properties:

- `gp:is_card_linked` = `"true"` (string, not boolean)
- `gp:is_bank_linked` = `"true"`

Use these for "is the user linked" filters. See `integrations/amplitude.md` § User properties.

---

## What is NOT in Amplitude (use User 360 API instead)

- **Card / bank list and details.** Which institutions, account names, last-4s.
- **Balances, APR, minimum payment, due date, statement balance.** All the actual financial values for each linked card.
- **Transactions.** Plaid transaction-level data.
- **Liability / payment history per card.**
- **Matching engine state.** Whether a linked card matched to a tradeline in the credit report. No `card_match_*` events exist in Amplitude.
- **Plaid item / access_token state.** Whether a connection has expired or needs re-auth lives in the backend.

---

## Definitions used across the team

- **"Card linkage rate"** = `unique users with add_card_successful in window / unique users with add_card_initiate in window`, Real Users filter applied. See `definitions/metrics.md`.
- **"Bank linkage rate"** = same shape for `add_bank_*`.
- **"Plaid drop-off"** = `1 - linkage rate`.
- **"Failed Plaid user"** = real user with `add_card_initiate` or `add_bank_initiate` event but NO corresponding `_successful` event in the same session window (24h default).
- **"Chat-initiated linking"** = `add_card_*` or `add_bank_*` event where `is_linking_from_agentic = true`. The linking attempt came from the CredGPT chat.
- **"Linked user"** = `gp:is_card_linked = "true"` OR `gp:is_bank_linked = "true"` in Amplitude.
- **"Linked but unmatched"** = card linked via Plaid but not tied to a tradeline in the credit report. Backend-only state. Query the User 360 API.

## Known failure modes / edge cases

- **Counter mismatch.** `add_card_successful + add_card_unsuccessful > add_card_initiate` on some days. Event double-fire pattern. Aggregate over multi-day windows.
- **`add_card_initiate` / `add_bank_initiate` payloads are minimal.** Only `platform` and `user_id`. No institution context on initiate.
- **`failure_reason` is often unhelpful.** The richer signal is in `error_type`, `error_code`, `error_message`, `exit_step`, and `last_view_name`.
- **`reached_*` booleans also fire on successful events.** A user reaching MFA on a successful link still has `reached_mfa = true`. Don't assume reached-MFA implies failure.
- **`is_linking_from_agentic` only appears on the linking event** (successful or unsuccessful), not on initiate. If you need to know whether a user STARTED the link from chat, you only see it on the success/failure event that followed.
- **Common error codes:** `BANK_NOT_SUPPORTED` (no retry), `MFA_TIMEOUT` (retryable), and OAuth-related codes paired with `oauth_closed_without_complete = true`.
- **Sync lag after linking.** Transactions and liabilities may not be visible for several minutes after `add_*_successful` because the backend syncs them through Bull queues.
- **Matching engine state is not in Amplitude.** Use the User 360 API for tradeline matching.

## Common queries / patterns

| Query | How |
|---|---|
| Card linkage funnel (initiate → success) | `playbooks/common-queries.md` § Card linkage funnel |
| Bank linkage funnel | `playbooks/common-queries.md` § Bank linkage funnel |
| Plaid drop-off by where in the flow | Group `add_*_unsuccessful` by `exit_step` and `last_view_name` |
| Plaid drop-off by bank | Group `add_*_unsuccessful` by `institution_name` |
| Plaid drop-off by cause | Group `add_*_unsuccessful` by `error_type` or `error_code` |
| Chat-initiated vs button-initiated linking | Filter `add_*_successful` / `add_*_unsuccessful` by `is_linking_from_agentic` |
| Reached-stage analysis | `reached_credentials` / `reached_mfa` / `reached_oauth` on `_unsuccessful` events |
| Plaid session timing | `spent_time_seconds` and `card_linking_time_seconds` on `_successful` |
| Per-user linkage history (when, where, succeed/fail) | Amplitude `add_card_*` / `add_bank_*` events filtered by `user_id` |
| Per-user linkage state flag | Amplitude `gp:is_card_linked` / `gp:is_bank_linked` user properties |
| Per-user card/bank list with balances, APR, due dates, transactions | User 360 API (Sandeep) |
| Linked but unmatched users | User 360 API. Not in Amplitude. |

## People

- **Owns Plaid integration (backend):** Sandeep.
- **Owns Plaid SDK in app:** Pankaj.
- **Owns matching engine:** Sandeep.
- **Owns Plaid linking UX:** Abhinav.
