# BON Credit — Complete Amplitude API Reference for AI Agents

This is the single source of truth for any AI agent querying BON Credit's Amplitude data via the HTTP API. Every filter definition, event name, property key, API quirk, and data quality issue is documented here. If your query returns numbers that don't match the BON Core KPIs dashboards, your filter is wrong — this doc tells you the right one.

**Last updated:** 2026-04-27
**Amplitude org:** `bon-credit` (org ID `310157`)
**Production project ID:** `645917` (BON Prod)
**Dev project ID:** `645915` (BON Dev — do not query for production metrics)
**Timezone:** `America/Los_Angeles` (PST/PDT)

---

## 1. Authentication

All API calls use HTTP Basic Auth with API Key and Secret Key.

```
Authorization: Basic base64(API_KEY:SECRET_KEY)
```

Base URL: `https://amplitude.com/api/2`

---

## 2. The Real Users Filter (MANDATORY)

**Every query MUST apply this filter.** Without it, numbers are inflated 3-5x by anonymous installs, internal team testing, and dev builds.

### Definition

A "Real User" is someone who:
- Has `gp:credit_score > 0` (completed Spinwheel identity verification during onboarding)
- Is NOT in the internal team user_id list
- Is NOT on a dev build

### Internal team user_ids to exclude

```
2503 — Samder (support/ops)
2604 — Darwin (co-founder)
2601 — Darwin
2300 — Darwin
287 — Darwin
2062 — Samder (primary test account, discovered 2026-04-13 — highest activity user at 33 sessions/month)
2605 — Samder (secondary test account)
```

### Internal email domains to exclude

```
@boncredit.ai
@bonhq.com
@mobilefirstapplications.com
```

### API format — Event Segmentation endpoint

Put the filter inside the event definition's `filters` array. Do NOT put it in the `s` (segments) parameter.

```json
{
 "e": {
 "event_type": "_active",
 "filters": [
 {
 "subprop_key": "gp:credit_score",
 "subprop_op": "greater",
 "subprop_type": "user",
 "subprop_value": ["0"]
 },
 {
 "subprop_key": "gp:user_id",
 "subprop_op": "is not",
 "subprop_type": "user",
 "subprop_value": ["2503", "2604", "2601", "2300", "287", "2062", "2605"]
 },
 {
 "subprop_key": "version",
 "subprop_op": "does not contain",
 "subprop_type": "user",
 "subprop_value": ["dev"]
 }
 ]
 },
 "m": "uniques",
 "start": "20260421",
 "end": "20260421",
 "i": "1"
}
```

The `e` parameter must be JSON-encoded as a string when passed as a query parameter.

### Why the `s` parameter doesn't work

The Amplitude V2 HTTP API has an `s` (segments) parameter that APPEARS to accept filter conditions. It silently ignores them and returns unfiltered data. This was discovered after 2 days of debugging. Always put filters inside the `e` parameter's `filters` array.

### Filter operators reference

Valid operator strings for `subprop_op`:
- `"is"` / `"is not"` — exact match (supports arrays for multi-value)
- `"contains"` / `"does not contain"` — substring match
- `"greater"` / `"less"` / `"greater or equal"` / `"less or equal"` — numeric/string comparison (**NOTE:** The API uses short forms like `"greater"` NOT `"greater than"`. The UI shows "greater than" but the API rejects it with 400.)
- `"set is"` / `"set is not"` — set membership
- `"has prefix"` / `"glob match"` / `"glob does not match"` — pattern matching

**CRITICAL API QUIRK:** The Amplitude UI displays filter operators as "greater than", "less than", etc. but the HTTP API requires the SHORT forms: `"greater"`, `"less"`, `"greater or equal"`, `"less or equal"`. Using "greater than" returns HTTP 400. This was discovered through live testing on 2026-04-28.

`subprop_type` values: `"user"` (user property), `"event"` (event property)

---

## 3. API Endpoints

### 3a. Event Segmentation — `/api/2/events/segmentation`

The primary endpoint for metrics. Returns time-series data for event counts, uniques, averages, formulas, etc.

**Parameters:**
| Param | Type | Description |
|---|---|---|
| `e` | JSON string | Event definition with event_type and optional filters (see Section 2) |
| `m` | string | Metric: `uniques`, `totals`, `average`, `formula`, `sums`, `value_avg`, `value_min`, `value_max`, `median`, `histogram`, `frequency`, `prop_count`, `prop_count_avg` |
| `start` | string | Start date `YYYYMMDD` |
| `end` | string | End date `YYYYMMDD` |
| `i` | string | Interval: `"1"` (daily), `"7"` (weekly), `"30"` (monthly) |
| `s` | JSON string | Segment definitions (DO NOT use for filtering — see Section 2) |
| `g` | JSON string | Group-by property |
| `limit` | int | Max group-by values (default 100) |

**Example — Real DAU for a specific day:**
```
GET /api/2/events/segmentation?e={"event_type":"_active","filters":[{"subprop_key":"gp:credit_score","subprop_op":"greater","subprop_type":"user","subprop_value":["0"]},{"subprop_key":"gp:user_id","subprop_op":"is not","subprop_type":"user","subprop_value":["2503","2604","2601","2300","287","2062","2605"]},{"subprop_key":"version","subprop_op":"does not contain","subprop_type":"user","subprop_value":["dev"]}]}&m=uniques&start=20260421&end=20260421&i=1
```

**Example — Real WAU (rolling 7 days):**
```
start=20260415&end=20260421&i=7
```

**Example — Formula (e.g., Spinwheel success rate):**
Use `e` as a JSON array of events, `m=formula`, `formula=TOTALS(A)/(TOTALS(A)+TOTALS(B))`:
```
e=[{"event_type":"spinwheel_completed"},{"event_type":"spinwheel_failed"}]
&m=formula
&formula=TOTALS(A)/(TOTALS(A)+TOTALS(B))
```
Note: formula events may not support inline filters in the same way. Test first.

**Example — Group by user property:**
```
g=gp:is_card_linked
```
Returns separate series for each property value ("true", "false", "(none)").

**Response format:**
```json
{
 "data": {
 "series": [[value1, value2, ...]],
 "xValues": ["2026-04-21", "2026-04-22", ...]
 }
}
```
`series[0]` = first event/segment. Multiple series for multiple events or segments.

### 3b. User Activity — `/api/2/users/search`

Look up individual users by user_id or Amplitude ID.

```
GET /api/2/users/search?user=USER_ID
```

Returns user properties, events timeline, revenue data.

### 3c. Export API — `/api/2/export`

Download all raw events for a date range (NDJSON in a gzip/zip). Used by the daily report bot.

```
GET /api/2/export?start=20260421T00&end=20260421T23
```

Returns every event with full properties. Large responses — 7-minute timeout recommended.

### 3d. Cohort API — `/api/5/cohorts/request`

Request a cohort's user list. Requires cohort ID.

### 3e. Dashboard API

No public API for reading dashboard chart data directly. Use the Event Segmentation endpoint to replicate chart queries.

---

## 4. Complete Event Taxonomy (BON Prod, project 645917)

### 4a. Events — RELIABLE (use these)

| Event | What it tracks | Key properties | Notes |
|---|---|---|---|
| `_active` | Any user activity (Amplitude built-in) | — | Use with Real Users filter for DAU/WAU/MAU |
| `onboarding_step_completed` | Each step of the 9-step onboarding flow | `step_name` | The canonical onboarding event. Filter by step_name for specific steps. |
| `credgpt_chat_started` | User opened/started a chat session | `entry_point` | The agent chat is BON's home screen. |
| `credgpt_message_sent` | User sent a message to the agent | `message_text`, `input_type`, `message_length` | **Most reliable engagement metric.** Hard count of actual typed messages. |
| `credgpt_response_received` | Agent sent a response back | — | Sometimes fires more than message_sent (may include proactive messages). |
| `credgpt_suggested_prompt_tapped` | User tapped a suggested prompt button | `prompt_text`, `prompt_category` | Counts as a message in engagement stats. |
| `credgpt_history_viewed` | User viewed chat history | — | |
| `add_card_initiate` | User tapped "Link Card" | — | Start of Plaid card linking flow. |
| `add_card_successful` | Card link completed via Plaid | — | Known counter mismatch with initiate. |
| `add_card_unsuccessful` | Card link failed | `failure_reason`, `exit_step`, `institution_name`, `error_type` | |
| `add_bank_initiate` | User tapped "Link Bank" | — | |
| `add_bank_successful` | Bank link completed via Plaid | — | Known counter mismatch. |
| `add_bank_unsuccessful` | Bank link failed | `failure_reason`, `exit_step`, `institution_name` | |
| `spinwheel_started` | Spinwheel vendor API call initiated (credit lookup) | — | Fires during onboarding DOB step. |
| `spinwheel_completed` | Spinwheel credit lookup succeeded | — | |
| `spinwheel_failed` | Spinwheel credit lookup failed | `failure_reason` (always "(none)" — not populated) | |
| `common_screen_view_tracker` | User viewed a screen | `screen_name` | Canonical screen tracking event. |
| `screen_time_spent` | Time spent on a screen | `screen_name`, `time_spent_seconds` | Fires on screen EXIT, not during. Undercounts chat-heavy users. |
| `screen_dropoff` | User dropped off from a screen | `screen_name` | Canonical drop-off event. |
| `feature_used` | User interacted with a feature | `feature_name` | Generic feature tracking. Values: notification_permission_granted, push_notification_on, link_card, actions_button, etc. |
| `autopay_enabled` | User enabled auto-pay | — | The CORRECT terminal event for autopay. |
| `notification_click` | User tapped a push notification | `notificationId` | Fires near-zero (0 in recent 30 days). |
| `credit_score` | Credit score event (fires on refresh) | `score` | Event-level score, fires per refresh cycle (~20 days). Use `gp:credit_score` user property for current score. |
| `fresh_install` | First app launch | — | Duplicate of [Amplitude] Application Installed. |
| `delete_membership` | User deleted their account | — | |

### 4b. Events — UNRELIABLE (use with caution or avoid)

| Event | Problem | What to use instead |
|---|---|---|
| `credgpt_response_error` | Fires 0 times in 30 days despite 170+ messages. Error tracking is broken. | No alternative — error signal is missing entirely. |
| `sign_up_started_event` | **Stopped firing ~March 17, 2026.** | Use `onboarding_step_completed` where `step_name = "phone_number_submitted"` |
| `sign_up_completed_event` | **Stopped firing ~March 17, 2026.** | Use `onboarding_step_completed` where `step_name = "onboarding_complete"` |
| `sign_up_drop_off` | Counter, not a rate. Fires per screen exit, not per user. | Use step-by-step drop-off from `onboarding_step_completed` steps. |
| `autopay_setup_successful` | Fires for ~1 user in 30 days. Effectively dead. | Use `autopay_enabled` instead. |
| `auto_pay_choose_amount_viewed` | Zero fires. Dead. | — |
| `auto_pay_selected_amount` | Zero fires. Dead. | — |
| `auto_pay_selected_bank` | Zero fires. Dead. | — |
| `auto_pay_select_bank_viewed` | Zero fires. Dead. | — |
| `pay_bill_initiated` | Zero fires in 30 days. | Feature may be dead or instrumentation broken. |
| `pay_bill_success` | Zero fires. | Same. |
| `one_time_bill_payment_initiated` | Zero fires. | Same. |
| `one_time_bill_payment_success` | Zero fires. | Same. |
| `one_time_bill_payment_failed` | Zero fires. | Same. |
| `bill_payment_select_amount` | Zero fires. | Same. |
| `credgpt_chat_ended` | Fires for <15% of sessions. | Use `credgpt_chat_started` for session count. |
| `session_start` | Doesn't fire for all users — some users have messages but 0 sessions. | Use `_active` uniques for DAU instead. |
| `screen_time_spent` | Only fires on screen EXIT. Users who stay on one screen and close the app never trigger it. **Undercounts chat-heavy users by 3-10x.** | Use `credgpt_message_sent` count as chat engagement proxy. |

### 4c. Events — DEAD (zero volume, safe to ignore)

`slot_reward_redeem_initiated`, `slot_reward_redeem_successful`, `slot_reward_redeem_failed` (killed "BON Points / spin wheel" game), `add_to_cart`, `confirm_order`, `order_summary_viewed`, `select_address` (from an abandoned e-commerce template), `stripe_initiated`, `password`.

### 4d. Onboarding step_name values (for `onboarding_step_completed`)

The onboarding flow has 9 steps. Use these exact `step_name` values when filtering:

| Step | step_name value | Typical 30d uniques |
|---|---|---|
| 1 | `phone_number_submitted` | ~100 |
| 2 | `otp_verified` | ~95 |
| 3 | `email_verified` | ~89 |
| 4 | `credit_report_disclaimer_accepted` | ~88 |
| 5 | `dob_submitted` | ~85 |
| 6 | `spin_wheel_connection_successful` | ~71 (Spinwheel vendor identity check — 15% failure rate) |
| 7 | `set_pin` | ~73 |
| 8 | `pin_verified` | ~73 |
| 9 | `onboarding_complete` | ~73 |

Additional step_names that fire but aren't in the main funnel: `otp_sent`, `otp_verification_attempted`, `email_submit_attempted`, `dob_confirmed` (recovery path if Spinwheel fails on first DOB), `spin_wheel_connection_attempted`, `face_id_enabled`, `face_id_disabled`.

---

## 5. Complete User Properties

| Property key | Type | Description |
|---|---|---|
| `gp:user_id` | string (numeric) | BON's internal user ID. Only assigned after Spinwheel onboarding completes. |
| `gp:credit_score` | number | User's credit score (300-850). > 0 means completed onboarding. |
| `gp:first_name` | string | User's first name (PII). |
| `gp:email` | string | User's email (PII). |
| `gp:phone_number` | string | User's phone number (PII). |
| `gp:dob` | string | Date of birth (PII). |
| `gp:is_card_linked` | string | "true" if user linked a credit card via Plaid. |
| `gp:is_bank_linked` | string | "true" if user linked a bank account via Plaid. |
| `gp:plan` | string | User's plan (e.g., "free"). |
| `gp:push_opted_in` | string | Push notification opt-in status. |
| `gp:created_at` | string | Account creation timestamp. |
| `gp:created_at_bon` | string | BON-specific creation timestamp. |
| `gp:last_active_at` | string | Last activity timestamp. |
| `version` / `[Amplitude] Version` | string | App version (e.g., "1.1.27"). Dev builds contain "dev". |
| `[Amplitude] Platform` | string | "iOS" or "Android". |
| `[Amplitude] Country` | string | Geo-IP country. |
| `[Amplitude] Region` | string | Geo-IP region/state. |
| `[Amplitude] City` | string | Geo-IP city. |
| `[Amplitude] OS` | string | Operating system. |
| `[Amplitude] Device type` | string | Device model. |

**CRITICAL:** Amplitude does NOT include user_properties on every event in raw exports. Only when properties change or `identify()` fires fresh. A returning user's events may have empty user_properties even if they have credit_score set in Amplitude's database. The Event Segmentation API resolves properties server-side (correct), but raw exports may miss them.

---

## 6. Complete Event Properties

| Property key | Used on events | Description |
|---|---|---|
| `step_name` | `onboarding_step_completed` | Which onboarding step (see Section 4d) |
| `screen_name` | `common_screen_view_tracker`, `screen_time_spent`, `screen_dropoff`, `first_screen_after_signup` | Which screen the user is on |
| `time_spent_seconds` | `screen_time_spent` | Seconds spent on the screen (fires on exit) |
| `feature_name` | `feature_used` | Which feature (see feature_used values below) |
| `score` | `credit_score` | The credit score value at time of the event |
| `failure_reason` | `add_card_unsuccessful`, `add_bank_unsuccessful`, `spinwheel_failed` | Why the action failed. Always "(none)" on spinwheel_failed (not populated). |
| `exit_step` | `add_card_unsuccessful`, `add_bank_unsuccessful` | Where in the Plaid flow the user dropped |
| `institution_name` | `add_card_unsuccessful`, `add_bank_unsuccessful` | Which bank/institution |
| `message_text` | `credgpt_message_sent` | The text the user typed (PII-sensitive) |
| `input_type` | `credgpt_message_sent` | "typed" or "suggestion" |
| `message_length` | `credgpt_message_sent` | Character count |
| `prompt_text` | `credgpt_suggested_prompt_tapped` | The suggested prompt text |
| `matched_ai_response` | `chat_thread_processed` (Dev only) | The AI's response text |
| `entry_point` | `credgpt_chat_started` | How the user entered chat |
| `amount` | payment events | Dollar amount |
| `total_amount` | payment events | Total dollar amount |
| `card_ending_number` | card events | Last 4 digits of card |
| `media_source` | `call_from_installConversionData` | AppsFlyer attribution source |
| `campaign` | `call_from_installConversionData` | Campaign name |
| `notificationId` | `notification_click` | Which notification was tapped |
| `dob` | `enter_dob` | Date of birth value (PII) |
| `email` | various | Email value (PII) |
| `first_name` | various | First name value (PII) |

### feature_used `feature_name` values (top ones by volume)

`notification_permission_granted` (187), `push_notification_on` (109), `link_card` (66), `actions_button` (55), `add_card_button` (51), `push_notification_off` (41), `utilization_button` (32), `notification_permission_denied` (28), `payoff_strategy_section_home` (27), `debt_strategy_choose_snowball` (21), `autopay_setup_button` (18), `invite_friend_button` (17), `schedule_create_initiate_snowball` (17), `schedule_create_success_snowball` (17), `referral_sent` (16), `credgpt` (11), `debt_strategy_choose_avalanche` (9), `loan_calculator` (6), `view_subscriptions_button` (6), `tap_bank_balance_home` (5)

### Chat screen names (for `screen_name` filtering)

The chat screen is BON's HOME SCREEN. These three screen_name values identify chat screens:
```
credGPTScreenView
screen_view_credgpt_home
screen_view_credgpt_chat_page
```
Note: `credGPTScreenView` is camelCase while others are snake_case — naming inconsistency in the Flutter client.

### Top screen_name values by unique users (30d)

`credGPTScreenView` (131 users — #1 by far), `screen_view_cards` (56), `screen_view_bank` (50), `screen_view_transactions` (45), `screen_view_array_report` (13), `screen_view_profile` (13), `screen_view_subscription_hub` (10), `screen_view_personal_loans` (3)

---

## 7. User Segments by Plaid Linking

4 segments defined by `gp:is_card_linked` and `gp:is_bank_linked`:

| Segment | Filter | ~% of real users | Behavior pattern |
|---|---|---|---|
| Card Only | `is_card_linked = "true"` AND `is_bank_linked ≠ "true"` | ~9% | Deepest chat sessions (95-113s per chat visit). Chat-focused. |
| Bank Only | `is_card_linked ≠ "true"` AND `is_bank_linked = "true"` | ~14% | Highest non-chat screen time (34s). Data reader. |
| Both Linked | `is_card_linked = "true"` AND `is_bank_linked = "true"` | ~10% | **Returns 3.5x more often than Neither (6.86 sessions/user)** but chats the LEAST (30s per visit). Power data checker. |
| Neither Linked | `is_card_linked ≠ "true"` AND `is_bank_linked ≠ "true"` | ~68% | The majority. Stable chat engagement (~80-87s). Credit-report-only users who need the agent most. |

To query a specific segment, add the appropriate `is_card_linked` and `is_bank_linked` filters to the event definition alongside the Real Users filter.

---

## 8. Chart Building Guide

### Simple count — How many real users were active today?

```
e={"event_type":"_active","filters":[REAL_USERS_FILTER]}
&m=uniques&start=20260421&end=20260421&i=1
```

### Trend — DAU over the last 14 days

```
e={"event_type":"_active","filters":[REAL_USERS_FILTER]}
&m=uniques&start=20260408&end=20260421&i=1
```

### Onboarding funnel — step-by-step conversion

Query each step separately:
```
e={"event_type":"onboarding_step_completed","filters":[{"subprop_key":"step_name","subprop_op":"is","subprop_type":"event","subprop_value":["phone_number_submitted"]}]}
&m=uniques&start=20260322&end=20260421&i=30
```
Repeat for each step_name. The drop between steps = conversion loss.

Alternatively, use multiple events in a single call with the formula endpoint.

### Chat engagement — unique chatters per day

```
e={"event_type":"credgpt_chat_started","filters":[REAL_USERS_FILTER]}
&m=uniques&start=20260408&end=20260421&i=1
```

### Chat depth — messages per chatter

Two approaches:
1. Total messages: `e={"event_type":"credgpt_message_sent","filters":[REAL_USERS_FILTER]}&m=totals`
2. Unique chatters: `e={"event_type":"credgpt_chat_started","filters":[REAL_USERS_FILTER]}&m=uniques`
3. Divide: messages / chatters = messages per chatter

### Plaid link conversion rate

```
e=[
 {"event_type":"add_card_successful","filters":[REAL_USERS_FILTER]},
 {"event_type":"add_card_initiate","filters":[REAL_USERS_FILTER]}
]
&m=formula&formula=TOTALS(A)/TOTALS(B)
```
Card link conversion is ~33%. Bank link conversion is ~63%.

### Spinwheel success rate

```
e=[{"event_type":"spinwheel_completed"},{"event_type":"spinwheel_failed"}]
&m=formula&formula=TOTALS(A)/(TOTALS(A)+TOTALS(B))
```
No Real Users filter needed — spinwheel fires during onboarding before user_id is assigned. Target: >85%.

### Group by a property — e.g., top screens

```
e={"event_type":"common_screen_view_tracker","filters":[REAL_USERS_FILTER]}
&m=uniques&g=screen_name&limit=20
```

### Group by a user property — e.g., users by platform

```
e={"event_type":"_active","filters":[REAL_USERS_FILTER]}
&m=uniques&g=platform
```

### Retention — are onboarded users coming back?

Use the Event Segmentation endpoint with careful date ranges, OR use the Behavioral Cohorts API. The HTTP API doesn't have a dedicated retention endpoint like the Amplitude UI — compute retention by:
1. Getting the set of users who completed onboarding in week X
2. Checking which of those users were active in week X+1, X+2, etc.

This requires multiple API calls or using the Export API to get raw events and computing retention offline.

### Session count per user

```
e={"event_type":"session_start","filters":[REAL_USERS_FILTER]}
&m=average
```
Returns average session_start events per user. Note: `session_start` doesn't fire for ~5-10% of sessions (known instrumentation gap).

---

## 9. Pattern Finding Playbook

### "Is engagement growing or shrinking?"
Query Real DAU over 30 days with daily interval. Plot the trend. Current state: declining from ~12/day to ~1-5/day over the last 30 days.

### "Which screens do users spend the most time on?"
Query `screen_time_spent` grouped by `screen_name`, metric `totals`, Real Users filter. Chat screens dominate (credGPTScreenView = ~1/3 of all screen visits).

### "Are linked users more engaged than unlinked?"
Run the same query (e.g., sessions per user) with 4 different segment filters (Card Only / Bank Only / Both / Neither). Compare.
Key insight: Both Linked users return 3.5x more often but chat the least.

### "Where are users dropping in onboarding?"
Query each `onboarding_step_completed` step_name separately (see Section 4d) and compare user counts. The drop between steps = conversion loss. Biggest drop: `dob_submitted` (85) → `spin_wheel_connection_successful` (71) = Spinwheel identity failure (15% loss).

### "Which users are most active?"
Query `credgpt_message_sent` grouped by `gp:user_id`, metric `totals`, Real Users filter, limit 50. Sort by message count. Top user: MAITE (user 2544, 43 messages in 30 days, credit score 490 "Poor" range).

### "Is the notification system working?"
BON uses Customer.io for push/email/SMS. As of April 2026, notification delivery rate is 8.1% and open rate is 0% across all 30 active campaigns. The Amplitude `notification_click` event fires 0 times in 30 days. The entire notification pipeline is broken.

### "What app versions are users on?"
Query `_active` grouped by `version` (the `[Amplitude] Version` user property), Real Users filter. Current dominant version: 1.1.27. Dev builds (version containing "dev") should be excluded.

### "What's the geographic distribution?"
Query `_active` grouped by `country` then by `region`, Real Users filter. 98% of real users are in the United States. Top states: Texas, California, North Carolina, New York, Pennsylvania, Florida.

### "How healthy is the Spinwheel identity check?"
Query `spinwheel_started`, `spinwheel_completed`, `spinwheel_failed` as separate events over 14 days. Compute success rate = completed / (completed + failed). Target >85%. Note: these fire during onboarding before user_id is assigned, so Real Users filter should NOT be applied to spinwheel events.

---

## 10. Known Data Quality Issues

### Events that undercount or don't fire

| Issue | Impact | Workaround |
|---|---|---|
| `session_start` doesn't fire for ~5-10% of users | Session count per user is underreported | Use `_active` uniques for user counts instead |
| `credgpt_chat_started` doesn't fire for ~5% of chatters | Some users who sent messages have 0 chat_started | Use `credgpt_message_sent` uniques as chat-user proxy |
| `screen_time_spent` only fires on screen EXIT | Users who stay on chat and close the app never trigger it. Undercounts chat-heavy users 3-10x. | Use message count as chat engagement depth proxy |
| `credgpt_response_error` fires 0 times despite real errors | No error visibility | No workaround — error tracking is unimplemented |
| `user_properties` not on every event in raw exports | credit_score, first_name, email may be empty for returning users | API segmentation resolves properties server-side (correct). For raw exports, use numeric user_id as proxy for "onboarded user" |

### Events that are dead (zero recent volume)

All bill payment events (`pay_bill_*`, `one_time_bill_payment_*`, `bill_payment_select_amount`), most autopay funnel steps (`auto_pay_choose_amount_viewed`, `auto_pay_selected_amount`, `auto_pay_selected_bank`), `sign_up_started_event`, `sign_up_completed_event`, all slot_reward events.

### Counter mismatches

- `add_card_successful + add_card_unsuccessful > add_card_initiate` on some days (impossible — events double-fire or initiate doesn't fire for some paths)
- `add_bank_successful > add_bank_initiate` on some days (same issue)
- `credgpt_response_received > credgpt_message_sent` (more responses than messages — may include proactive agent messages or double-fires)

### Naming inconsistencies

- `credGPTScreenView` (camelCase) vs `screen_view_credgpt_home` (snake_case) — same feature
- `utilization_button` vs `utlisation_button` — typo, two separate entries
- `spent_time_seconds` vs `time_spent_seconds` — same property, different names on different events
- `screen` vs `screen_name` — both exist as event properties

---

## 11. Reference Numbers (for validation)

These are known-correct numbers from the BON Core KPIs dashboards. Use them to validate your queries.

### As of early April 2026 (Last 30 Days)

| Metric | Value | Query |
|---|---|---|
| Real MAU | ~100-120 | `_active` uniques, 30-day interval, Real Users filter |
| Real WAU | ~15-50 | `_active` uniques, 7-day interval, Real Users filter |
| Real DAU | ~1-12/day | `_active` uniques, daily interval, Real Users filter |
| Total onboarded users (30d) | ~73 | `onboarding_step_completed{onboarding_complete}` uniques |
| Chat engaged users (30d) | ~130+ | `credgpt_chat_started` uniques, Real Users filter |
| Total messages sent (30d) | ~400+ | `credgpt_message_sent` totals, Real Users filter |
| Plaid card linked users | ~30-40 | `_active` with `gp:is_card_linked = "true"` + Real Users filter |
| Plaid bank linked users | ~25-35 | Same with `gp:is_bank_linked = "true"` |
| Neither Linked users | ~80-110 | Both `is_card_linked ≠ "true"` AND `is_bank_linked ≠ "true"` |
| Card link conversion rate | ~33% | `add_card_successful / add_card_initiate` |
| Bank link conversion rate | ~63% | `add_bank_successful / add_bank_initiate` |
| Spinwheel success rate | ~70-85% | `spinwheel_completed / (completed + failed)` |
| iOS share of Real DAU | ~85-90% | Group by platform |
| US share of Real Users | ~98% | Group by country |

If your query returns numbers significantly outside these ranges, the filter is likely wrong.

### Existing dashboards (correct numbers)

| Dashboard | URL |
|---|---|
| BON Home | https://app.amplitude.com/analytics/bon-credit/dashboard/wrbwlyzr |
| Onboarding Health | https://app.amplitude.com/analytics/bon-credit/dashboard/y3xgj3dy |
| Engagement & Chat | https://app.amplitude.com/analytics/bon-credit/dashboard/5kze9vlg |
| User Segments by Linking | https://app.amplitude.com/analytics/bon-credit/dashboard/pngoueex |
| Plaid & Payments | https://app.amplitude.com/analytics/bon-credit/dashboard/fo4lc1yd |
| Retention | https://app.amplitude.com/analytics/bon-credit/dashboard/a8cow2fl |
| Notifications | https://app.amplitude.com/analytics/bon-credit/dashboard/zsex0u5g |
| Platform & Geography | https://app.amplitude.com/analytics/bon-credit/dashboard/zf5z7ou6 |

---

## 12. Product Context (for interpreting data)

### What BON Credit is
An AI agent-first personal finance app. Users get a free credit report via Spinwheel/Array/Equifax, then an AI agent (internally "CredGPT") analyzes their finances and tells them exactly where they're losing money — with specific dollar amounts. Two pillars: "Save Money" (interest reduction, balance transfers, debt payoff strategies) and "Manage Money" (spending tracking, bill calendar, subscriptions).

### Target users
Blue-collar Americans. DoorDash drivers, plumbers, home health aides. Credit scores 500-650. $5K-$25K in credit card debt. Phone-first. Motivated by immediate financial relief, not long-term wealth building.

### The onboarding flow
Phone → OTP → Email → Credit Disclaimer → DOB → (DOB Confirm if Spinwheel fails) → PIN → PIN Verify → Face ID (optional) → Done. After onboarding, Spinwheel auto-fetches SSN + address, Array pulls the Equifax credit report, the agent analyzes it, and the user gets their first insight.

### The product loop
User opens app → lands on chat (home screen) → agent shows an insight or the user asks a question → agent responds with a dollar-specific recommendation → user optionally acts on it (pay a bill via Spinwheel, link a card, etc.) → agent follows up.

### Current stage
Pre-PMF. Real DAU is 1-12/day. ~100-150 real MAU. Declining engagement. The team does daily manual user audits ("Waymo remote drivers" approach). Architecture redesign in progress (12 new DB tables, 4 backend agents, priority queue).

### What's NOT built yet
Dollar-amount tracking (recommendation_shown, recommendation_acted_on, dollars_saved), credit report refresh cycle events, proper chat error tracking, session replay, voice agent. NPS was explicitly refused as a metric.

---

## 13. API Pitfalls Summary

1. **Filters go inside `e`, NOT `s`.** The `s` parameter is silently ignored.
2. **`_active` without Real Users filter = garbage.** 3-5x inflated by anonymous devices + internal team.
3. **Spinwheel events fire PRE-user_id.** Don't apply Real Users filter to spinwheel_started/completed/failed.
4. **User properties aren't on every raw export event.** The API resolves them server-side for segmentation queries, but raw exports may have empty user_properties for returning users.
5. **Numeric user_id = onboarded user.** BON only assigns numeric user_ids after Spinwheel. UUID-format device_ids = anonymous/pre-onboarding.
6. **`gp:is_card_linked` and `gp:is_bank_linked` are strings, not booleans.** Filter with `"true"` (string), not `true` (boolean).
7. **Credit scores are numbers but sometimes passed as strings.** Use `"greater"` with `["0"]` (string) — Amplitude handles the coercion.
8. **Formula queries use letter references.** First event = A, second = B. Formula example: `TOTALS(A)/UNIQUES(B)`.
9. **`screen_time_spent` undercounts chat users.** Don't use it as the primary engagement metric. Use message count.
10. **All bill payment events are dead.** If asked about payment volume, report it as zero with the caveat that instrumentation may be broken.
