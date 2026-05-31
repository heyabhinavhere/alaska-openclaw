# Amplitude — Product Analytics

**Last updated:** 2026-05-29 by Abhinav
**Status:** Draft

---

## Purpose at BON

Amplitude is BON's **primary product analytics platform**. DAU/MAU, retention, event funnels, user properties, behavioral cohorts. Every product question Alaska answers about engagement, conversion, or user behavior starts here.

Mixpanel runs alongside Amplitude but only for **source-of-user attribution** (organic, website, ads). See `architecture.md` § Pipeline D for the split. Don't use Mixpanel for product metrics.

Use this file when:

- Querying any user metric or event count.
- Building a watcher that subscribes to an event or filter.
- Pulling chat conversations or user behavior for a specific user.
- Hitting a 400 from the API and wondering which subtle filter syntax broke.

This file is the canonical Amplitude reference. Event taxonomy and filter quirks live here.

---

## Architecture

- **Amplitude org:** `bon-credit` (org ID `310157`)
- **Production project:** `645917` (BON Prod). Query this for real metrics.
- **Dev project:** `645915` (BON Dev). Never use for production reporting.
- **Timezone:** `America/Los_Angeles` (PST/PDT)
- **Auth:** HTTP Basic Auth with `$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY`
- **Base URL:** `https://amplitude.com/api/2`

Events fire from the Flutter app directly (not backend). User properties (`gp:*`) are set via the app's `identify()` call after Spinwheel completes.

---

## The Real Users filter (mandatory)

**Every user-count or engagement query MUST apply this filter.** Without it, numbers are inflated 3-5× by anonymous installs, internal team testing, and dev builds.

```python
REAL_USERS_FILTERS = [
    {"subprop_key": "gp:credit_score", "subprop_op": "greater",        "subprop_type": "user", "subprop_value": ["0"]},
    {"subprop_key": "gp:user_id",      "subprop_op": "is not",          "subprop_type": "user", "subprop_value": ["2503", "2604", "2601", "2300", "287", "2062", "2605"]},
    {"subprop_key": "version",         "subprop_op": "does not contain", "subprop_type": "user", "subprop_value": ["dev"]}
]
```

**Filter exception, Spinwheel events fire pre-user_id.** Don't apply the Real Users filter to `spinwheel_started` / `spinwheel_completed` / `spinwheel_failed`. They would return 0.

For the full Real Users specification (test user IDs, internal email domains, rationale), see `definitions/metrics.md` § The Real Users filter.

---

## CredGPT chat data access (read this before answering chat questions)

Alaska has access to the full chat conversation between users and the CredGPT agent. Both the user's questions and the agent's responses are available. Two paths.

### Primary path: User 360 profile API (Sandeep)

Returns the full user profile, which includes the complete chat history with the agent. User questions, agent responses, timestamps. Plus full credit report and Plaid context in the same response. Default to this.

### Fallback path: Amplitude `chat_thread_processed` event

If the User 360 API is unavailable, the full Q&A content is in Amplitude on the `chat_thread_processed` event.

Properties on `chat_thread_processed`:

| Property | What it carries |
|---|---|
| `question` | The user's question. Special value `__PROACTIVE_BRIEFING__` when the agent fires the first proactive message (no user question). |
| `matched_ai_response` | The agent's full response text. Markdown formatted. References real user data (score, balances, account names, dollar amounts). |
| `thread_id` | UUID for the conversation thread. Use this to group a user's events into conversation sessions. |
| `quick_suggestions` | Array of suggested next prompts shown alongside the response. Each item has `suggestion`, `action` (e.g., `continue-chat`, `link-credit-cards`, `open-keyboard`), `type` (`text` or `CTA`), and `prompt`. |
| `chat_stopped_by_user` | Boolean. True if the user interrupted the agent mid-response. |
| `platform` | `ios` or `android`. |
| `user_id` | BON user_id (string). |

To pull a user's chat conversation, query `chat_thread_processed` filtered by `user_id` and sorted by `eventTime`. Each event represents one Q&A turn. Group by `thread_id` to reconstruct sessions.

### Related events for feedback

- `ai_chat_feedback_good` carries `message` (the AI response the user thumbs-upped).
- `ai_chat_feedback_bad` carries `message` + `reasons` (the response + why it was rated bad).

### Rule for Alaska

Do NOT say "I don't have access to agent response text through Amplitude." That is wrong. The text is on `chat_thread_processed`. The default fetch is the User 360 API. If that fails, query Amplitude `chat_thread_processed` and answer with the actual content. Never deflect.

### A note on `credgpt_response_received`

The `credgpt_response_received` event exists but only carries `response_time_ms`, `platform`, `user_id`. It tracks response latency, not response content. The content is on `chat_thread_processed`. Don't conflate.

---

## API surface

### Event Segmentation, `/api/2/events/segmentation`

Primary endpoint. Time-series for event counts, uniques, averages, formulas.

| Param | Type | Description |
|---|---|---|
| `e` | JSON string | Event definition: `{event_type, filters?, group_by?}`. Multiple events as array for formula queries. |
| `m` | string | Metric: `uniques`, `totals`, `average`, `formula`, `sums`, `value_avg`, `value_min`, `value_max`, `median`, `histogram`, `frequency`, `prop_count`, `prop_count_avg` |
| `start` | string | `YYYYMMDD` |
| `end` | string | `YYYYMMDD` |
| `i` | string | Interval: `"1"` (daily), `"7"` (weekly), `"30"` (monthly) |
| `s` | JSON string | **DO NOT USE for filtering. Silently ignored.** |
| `g` | string | Group-by property |
| `limit` | int | Max group-by values (default 100) |

**Use python3 for complex queries.** Curl URL-encoding breaks with nested JSON.

```python
import urllib.parse, urllib.request, json, os, base64
api_key = os.environ['AMPLITUDE_API_KEY']
api_secret = os.environ['AMPLITUDE_SECRET_KEY']
auth = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()

e_param = {"event_type": "_active", "filters": REAL_USERS_FILTERS}
params = {'e': json.dumps(e_param, separators=(',',':')), 'm': 'uniques', 'start': 'YYYYMMDD', 'end': 'YYYYMMDD', 'i': '1'}
url = f"https://amplitude.com/api/2/events/segmentation?{urllib.parse.urlencode(params)}"
req = urllib.request.Request(url, headers={'Authorization': f'Basic {auth}'})
data = json.loads(urllib.request.urlopen(req).read())
# data['data']['series'][0] = daily values
# data['data']['xValues']   = date labels
```

### User Activity, `/api/2/users/search`

Look up individual users by user_id or Amplitude ID.

```
GET /api/2/users/search?user=USER_ID
```

Returns user properties, events timeline, revenue.

### Export API, `/api/2/export`

Download all raw events for a date range (NDJSON in a gzip). Large responses, 7-min timeout recommended.

```
GET /api/2/export?start=20260421T00&end=20260421T23
```

### Cohort API, `/api/5/cohorts/request`

Request a cohort's user list by cohort ID.

### Dashboard API

No public API for reading dashboard chart data directly. Replicate via Event Segmentation.

---

## Filter operators

| API operator | UI label | Notes |
|---|---|---|
| `is` / `is not` | "is" / "is not" | Supports arrays for multi-value |
| `contains` / `does not contain` | substring match | |
| `greater` / `less` | "greater than" / "less than" | **API uses SHORT form. "greater than" returns HTTP 400.** |
| `greater or equal` / `less or equal` | "greater than or equal" / "less than or equal" | Same short-form rule. |
| `set is` / `set is not` | "set is" / "set is not" | Set membership |
| `has prefix` / `glob match` / `glob does not match` | pattern matching | |

`subprop_type`: `"user"` (user property) or `"event"` (event property).

---

## Event taxonomy

### Reliable (use these)

| Event | What it tracks | Key properties |
|---|---|---|
| `_active` | Any user activity (Amplitude built-in) | |
| `onboarding_step_completed` | Each step of the 9-step onboarding flow | `step_name` |
| `credgpt_chat_started` | User opened a chat session | `entry_point`, `platform`, `user_id` |
| `credgpt_message_sent` | User sent a typed message or tapped a prompt | `message_text` (user's exact text), `message_length`, `input_type:` (note trailing colon in property name), `platform`, `user_id` |
| `credgpt_response_received` | Agent response latency event | `response_time_ms`, `platform`, `user_id`. **Does NOT carry response text. Use `chat_thread_processed` for content.** |
| `credgpt_suggested_prompt_tapped` | User tapped a suggested prompt button | `prompt_text`, `prompt_category`, `prompt_position`, `platform`, `user_id` |
| `credgpt_history_viewed` | User viewed chat history | `session_count_viewed`, `platform`, `user_id` |
| `credgpt_chat_ended` | Chat session ended | `last_message_by`, `total_messages`, `platform`, `user_id` |
| `chat_thread_processed` | Full Q&A turn with content | `question`, `matched_ai_response`, `thread_id`, `quick_suggestions`, `chat_stopped_by_user`, `platform`, `user_id`. See CredGPT chat data access section. |
| `ai_chat_feedback_good` | User thumbs-upped an AI response | `message`, `platform`, `user_id` |
| `ai_chat_feedback_bad` | User thumbs-downed an AI response | `message`, `reasons`, `platform`, `user_id` |
| `add_card_initiate` | User tapped "Link Card" | |
| `add_card_successful` | Plaid card link succeeded | |
| `add_card_unsuccessful` | Plaid card link failed | `failure_reason`, `exit_step`, `institution_name`, `error_type` |
| `add_bank_initiate` | User tapped "Link Bank" | |
| `add_bank_successful` | Plaid bank link succeeded | |
| `add_bank_unsuccessful` | Plaid bank link failed | `failure_reason`, `exit_step`, `institution_name` |
| `spinwheel_started` | Spinwheel identity-verification initiated | |
| `spinwheel_completed` | Spinwheel succeeded | |
| `spinwheel_failed` | Spinwheel failed | `failure_reason` (always "(none)", not populated) |
| `common_screen_view_tracker` | User viewed a screen | `screen_name` |
| `screen_time_spent` | Time spent on screen (fires on EXIT) | `screen_name`, `time_spent_seconds` |
| `screen_dropoff` | User dropped off from a screen | `screen_name` |
| `feature_used` | User interacted with a feature | `feature_name` |
| `autopay_enabled` | User enabled AutoPay | |
| `notification_click` | User tapped a push notification | `notificationId` |
| `credit_score` | Credit score event (fires on refresh) | `score` |
| `fresh_install` | First app launch | |
| `delete_membership` | User deleted their account | |

### Unreliable (use with caution, see alternatives in `definitions/lifecycle-events.md`)

| Event | Problem |
|---|---|
| `credgpt_response_error` | Carries `error_type`, but historically fires 0 times in 30d. Error tracking unreliable. |
| `sign_up_started_event`, `sign_up_completed_event` | Stopped firing ~March 17, 2026. Use `onboarding_step_completed` proxies. |
| `sign_up_drop_off` | Counter not a rate. |
| `autopay_setup_successful` | Dead. Use `autopay_enabled`. |
| `credgpt_chat_ended` | Historically fires for < 15% of sessions. The taxonomy is correct but firing reliability is low. |
| `session_start` | Doesn't fire for ~5-10% of users. |
| `screen_time_spent` | Only fires on EXIT, undercounts chat 3-10×. |
| All `pay_bill_*`, `one_time_bill_payment_*`, `bill_payment_*`, `auto_pay_choose_*`, `auto_pay_selected_*` | Zero volume. Instrumentation broken (features themselves are alive, use backend tables). |

### LEGACY events

See `definitions/lifecycle-events.md` § LEGACY events for the full killed-feature event list. Do NOT compute against these.

### Onboarding `step_name` values

| Step | step_name |
|---|---|
| 1 | `phone_number_submitted` |
| 2 | `otp_verified` |
| 3 | `email_verified` |
| 4 | `credit_report_disclaimer_accepted` |
| 5 | `dob_submitted` |
| 6 | `spin_wheel_connection_successful` (biggest drop, Spinwheel identity failure) |
| 7 | `set_pin` |
| 8 | `pin_verified` |
| 9 | `onboarding_complete` |

Additional `step_name` values off the main path: `otp_sent`, `otp_verification_attempted`, `email_submit_attempted`, `dob_confirmed` (recovery after Spinwheel fail), `spin_wheel_connection_attempted`, `face_id_enabled`, `face_id_disabled`.

---

## User properties

| Property | Type | Description |
|---|---|---|
| `gp:user_id` | string (numeric) | BON's `user.user_id`. Only set after Spinwheel completes. |
| `gp:credit_score` | number | Current credit score (300-850). `> 0` is the "real user" gate. |
| `gp:first_name` | string | PII |
| `gp:email` | string | PII |
| `gp:phone_number` | string | PII |
| `gp:dob` | string | PII |
| `gp:is_card_linked` | string `"true"`/`"false"` | After Plaid card link |
| `gp:is_bank_linked` | string `"true"`/`"false"` | After Plaid bank link |
| `gp:plan` | string | e.g., "free" |
| `gp:push_opted_in` | string | iOS/Android push opt-in |
| `gp:created_at` / `gp:created_at_bon` / `gp:last_active_at` | string timestamps | |
| `gp:current_city` / `gp:current_state` / `gp:current_country` | string | Geo from Amplitude |
| `version` / `[Amplitude] Version` | string | App version (e.g., "1.1.27"). Dev builds contain "dev". |
| `[Amplitude] Platform` / `OS` / `Device type` | strings | |
| `[Amplitude] Country` / `Region` / `City` | strings | Geo-IP (not user-entered location) |

**`user_properties` are not present on every raw export event for returning users.** API segmentation resolves them server-side (correct). Raw exports may have empty user_properties.

---

## Chat screen names

Chat is BON's home screen. Three values identify chat screens (naming inconsistency, camelCase vs snake_case):

```
credGPTScreenView
screen_view_credgpt_home
screen_view_credgpt_chat_page
```

Dedupe if rolling up.

---

## User segments by Plaid linking

Four segments defined by `gp:is_card_linked` and `gp:is_bank_linked`. See `definitions/personas.md` § Plaid-linking segments for behavioral patterns and `playbooks/common-queries.md` for query specs.

| Segment | Filter |
|---|---|
| Card Only | `is_card_linked = "true"` AND `is_bank_linked ≠ "true"` |
| Bank Only | `is_card_linked ≠ "true"` AND `is_bank_linked = "true"` |
| Both Linked | both `"true"` |
| Neither Linked | both `≠ "true"` |

---

## Existing dashboards

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

## Definitions used across the team

- **"Real user"** = passes the Real Users filter (credit_score > 0, not in test list, not on dev build). See `definitions/metrics.md`.
- **"Real DAU/WAU/MAU"** = `_active` uniques with Real Users filter applied.
- **"Onboarded user"** = `onboarding_step_completed{step_name="onboarding_complete"}` fired.
- **"Chat-engaged"** = sent at least one `credgpt_message_sent` event.
- **"Linked user"** = `gp:is_card_linked = "true"` OR `gp:is_bank_linked = "true"`.
- **"Chat thread"** = one `thread_id` value on `chat_thread_processed`. Groups Q&A turns into a conversation session.
- **"Proactive briefing"** = `chat_thread_processed` event with `question = "__PROACTIVE_BRIEFING__"`. The agent's first message to a user, fired without a user prompt.

## Known failure modes / edge cases

API pitfalls. Internalize these.

1. **Filters go inside `e`, NOT `s`.** The `s` parameter is silently ignored.
2. **`_active` without Real Users filter = garbage.** 3-5× inflated.
3. **Spinwheel events fire pre-user_id.** Don't apply Real Users filter.
4. **`user_properties` aren't on every raw export event.** API segmentation resolves them. Raw exports may miss.
5. **Numeric `user_id` = onboarded user.** UUID-format `device_id` = anonymous/pre-onboarding.
6. **`gp:is_card_linked` / `gp:is_bank_linked` are strings**, not booleans. Filter with `"true"` (string).
7. **Credit scores sometimes passed as strings.** Use `"greater"` with `["0"]` (string array).
8. **Formula queries use letter references.** First event = A, second = B. `TOTALS(A)/UNIQUES(B)`.
9. **`screen_time_spent` undercounts chat users.** Don't use as primary engagement.
10. **`greater than` / `less than` returns HTTP 400.** Use `greater` / `less`.
11. **`input_type:` has a trailing colon in the property name** on `credgpt_message_sent`. Filter accordingly.
12. **`credgpt_response_received` does NOT carry response text.** Only latency. Use `chat_thread_processed.matched_ai_response` for content.
13. **`credgpt_response_error` fires 0 times historically.** Error visibility through that event is missing.

## Common queries / patterns

| Query | Where |
|---|---|
| Real DAU (today, trend) | `playbooks/common-queries.md` § DAU |
| Onboarding funnel (9 steps) | `playbooks/common-queries.md` § Onboarding funnel |
| Card linkage funnel | `playbooks/common-queries.md` § Card linkage funnel |
| Spinwheel success rate | `playbooks/common-queries.md` § Spinwheel success |
| Group-by queries (platform, country, segment) | `playbooks/common-queries.md` § Group-by patterns |
| User lookup (full profile + chat history) | Use the User 360 profile API (Sandeep) |
| Chat conversation for a specific user | Primary: User 360 API. Fallback: Amplitude `chat_thread_processed` filtered by `user_id`, grouped by `thread_id`. |
| Find proactive briefings | Filter `chat_thread_processed` where `question = "__PROACTIVE_BRIEFING__"`. |
| Find AI responses users rated bad | Query `ai_chat_feedback_bad` and read `message` + `reasons`. |
| Top engaged users | `playbooks/common-queries.md` § Top chatters |
| Score-range filter | `playbooks/common-queries.md` § Score range |

## People

- **Owns Amplitude integration:** Pankaj (app-side firing) + Sandeep (CredGPT-side instrumentation).
- **Owns dashboards:** Abhinav.
