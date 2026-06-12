# Common Queries — Recipes for the Questions Alaska Gets Asked

**Last updated:** 2026-05-30 by Abhinav
**Status:** Draft

> **What this file is:** reusable recipes for the natural-language questions Alaska gets asked most often. Each recipe maps a question pattern to the system(s) to hit, the actual query, how to read the result, and the gotchas specific to that query.
>
> **What it is NOT:** documentation of the underlying systems (that lives in `integrations/`). Not exhaustive (only the common ones). Not workflow (which agent runs what, when, where the output lands lives in `docs/alaska-operating-model.md`). Not watcher event-filter patterns (those will live in their own file with Watchers V1).

---

## Recipe shape

Every recipe follows the same shape so Alaska can scan fast:

- **Question pattern:** the natural-language question.
- **System(s):** which API surface(s) to hit.
- **Pre-conditions:** filters, identity resolution, auth scope, anything required before the query runs.
- **Query:** the actual code or API call.
- **Result handling:** how to read the response and how to present it.
- **Common gotchas:** query-specific failure modes.

---

## Conventions

**Auth boilerplate** lives in each integration file. Don't restate here. The relevant references:

- Amplitude → `integrations/amplitude.md` § auth, Real Users filter
- Customer.io → `integrations/customerio.md` § APIs and auth
- User-profile-API → `integrations/user-profile-api.md` § auth
- GitHub → `integrations/github.md` § auth (read-only by discipline)
- Notion → `integrations/notion.md` § auth, version routing
- Fireflies → `integrations/fireflies.md` § API and auth
- Slack → `integrations/slack.md` § auth

**Addresses live in MEMORY.md, not here:**

- Slack channel IDs → `workspace/MEMORY.md` § Slack Channels
- Notion data source IDs and write DB IDs → `workspace/MEMORY.md` § Notion Data Sources
- GitHub team handles + repo list → `integrations/github.md` (handle table + repo map)
- Team roster → `workspace/MEMORY.md` § Team Roster

**Dates** are written as relative pseudocode (`<today>`, `<today - 30d>`) so recipes don't go stale. Compute at query time:

```python
from datetime import date, timedelta
today_yyyymmdd = date.today().strftime("%Y%m%d")  # Amplitude format
today_iso = date.today().isoformat() + "T00:00:00Z"  # GitHub / CIO / Fireflies format
```

**Result handling defaults:** lead with the answer, never dump raw JSON into Slack. Specific message-length caps live in `workspace/SOUL.md` § Slack Message Discipline.

---

## 1. One specific user — deep dive

The most-asked Alaska pattern. Someone in Slack mentions a user by email/phone/name and wants a full picture.

### 1.1 Resolve a user from email, phone, or name

- **Question pattern:** "Who is [[email protected]](/cdn-cgi/l/email-protection)? / +1 555 123 4567 / Sarah from Atlanta?"
- **System(s):** user-profile-api (search endpoint).
- **Pre-conditions:** none.
- **Query:**

```bash
curl -s -H "X-Admin-Key: $BON_ADMIN_API_KEY" \
  "$BON_API_BASE_URL/api/admin/users/search?email=<URL_ENCODED_EMAIL>"

# or by phone (digits only, leading 1 OK or omitted):
curl -s -H "X-Admin-Key: $BON_ADMIN_API_KEY" \
  "$BON_API_BASE_URL/api/admin/users/search?phone=<DIGITS>"

# or by name (fuzzy / partial):
curl -s -H "X-Admin-Key: $BON_ADMIN_API_KEY" \
  "$BON_API_BASE_URL/api/admin/users/search?name=<URL_ENCODED_NAME>"
```

- **Result handling:** returns a JSON array. 0 matches = not found, 1 = resolved, many = ask the asker to disambiguate. Show id, email, name, created_at for each.
- **Common gotchas:** name search returns up to ~20 partial matches; never auto-pick the first. Email/phone are exact.

### 1.2 Full 360 profile for a user

- **Question pattern:** "Tell me everything about user X."
- **System(s):** user-profile-api (profile endpoint).
- **Pre-conditions:** user_id resolved (from 1.1 above). Toxic PII (SSN, full DOB, employer name) is stripped by the user-profile-360 skill's redactor before reaching Alaska's context.
- **Query:**

```bash
curl -s -H "X-Admin-Key: $BON_ADMIN_API_KEY" \
  "$BON_API_BASE_URL/api/admin/users/{user_id}/profile"
```

- **Result handling:** returns ~559 KB JSON. The user-profile-360 skill narrows to the relevant sections per intent. Manual reads should target specific sections (see 1.3-1.6 below) rather than scanning the whole payload.
- **Common gotchas:** the response's own `user_id` must equal the requested one (mismatch = backend routing bug, not a normal miss). Several product-layer sections (`persona`, `user_kpis`, `financial_profile_v2`) are empty by design — Alaska doesn't read these.

### 1.3 User's credit picture

- **Question pattern:** "What's user X's credit score? Latest tradelines? Score trend?"
- **System(s):** user-profile-api sections `credit_report_history`, `tradeline_history`, `spinwheel_credit_report`.
- **Pre-conditions:** user_id resolved.
- **Result handling:**
  - **Primary:** Score = the **latest `credit_report_history` row by `report_date`** (the array isn't guaranteed sorted — pick max `report_date`, don't assume index `[0]`). It's an **Equifax VantageScore 3.0** (not FICO). Score trend = walk `credit_report_history` over time. Tradelines = `tradeline_history` (cleanest source, pre-resolved Array data with monthly deltas).
  - **Fallback if Array data is missing:** `spinwheel_credit_report` (one-time signup snapshot). Label as "Spinwheel signup snapshot, may be stale" so it's not confused with current Array data.
  - **If both are empty:** the user has no credit report at all. Say so honestly.
- **Common gotchas:** never quote a FICO number. BON's canonical credit number is **Equifax** (delivered through Array). Always say "Equifax" when reporting, not "credit score" alone and never "FICO." Array is the only credit source BON actively refreshes (every ~20 days); Spinwheel is a one-time signup pull and never updates, so use it as fallback but label staleness.

### 1.4 User's debt and utilization

- **Question pattern:** "How much credit card debt does user X carry? What's their utilization? Highest-APR card?"
- **System(s):** user-profile-api.
- **Pre-conditions:** check `profile.is_card_added`. The source you read depends on the answer.
- **Result handling:**
  - **If `is_card_added == true`** (Plaid linked, real-time data available) → read `plaid_profiles.card_profile`:
    - Total CC balance = `total_cc_balance_exact`.
    - Overall utilization = `overall_utilization_exact`.
    - Weighted avg APR = `weighted_avg_apr_exact`.
    - Monthly interest cost = `monthly_interest_exact`.
    - Highest-util card = `highest_util_card_account_id`.
  - **If `is_card_added == false`** (no Plaid) → fall back to credit-bureau data in user-profile-api. Three tiers in order of freshness:
    - **Tier 2 (Array, refreshed every ~20 days):** `tradeline_history` is the cleanest source. Walk credit-card tradelines and sum balances. Limits and per-card detail are in here. Use `credit_report` (raw MISMO) only if `tradeline_history` is missing fields you need. Label as "Array (Equifax) snapshot, may be up to 20 days old."
    - **Tier 3 (Spinwheel, one-time signup snapshot):** `spinwheel_credit_report.credit_card_summary` has pre-computed totals. Use only if Array is also missing. Label as "Spinwheel signup snapshot, may be stale."
- **Common gotchas:**
  - Prefer `plaid_profiles.card_profile` over `plaid_liabilities` even when Plaid is linked. The latter is often empty.
  - Array is the primary credit source and the only one BON refreshes. Spinwheel is a legitimate fallback when Array data is missing, but it never updates, so always label its staleness.

### 1.5 User's income and cashflow

- **Question pattern:** "How much does user X make? What's their monthly surplus?"
- **System(s):** user-profile-api sections `plaid_income`, `plaid_profiles.bank_profile`, `plaid_profiles.monthly_aggregates_last_6`.
- **Result handling:**
  - Income estimate = `plaid_income.income_signals[0].net_monthly_income` (label as estimate, not exact, unless source = `plaid_bank`).
  - Monthly surplus = `plaid_profiles.bank_profile.monthly_surplus_exact`.
  - 6-month trend = `plaid_profiles.monthly_aggregates_last_6`.
- **Common gotchas:** `plaid_income` is inferred from deposit patterns. Distinguish "estimated" vs "exact" in any output.

### 1.6 User's recent CredGPT chat history

- **Question pattern:** "What did user X ask CredGPT lately? What did CredGPT answer?"
- **System(s):** user-profile-api section `chat.recent_turns` (primary), Amplitude `chat_thread_processed` event (fallback).
- **Result handling:**
  - **Primary:** read `chat.recent_turns` from user-profile-api. Returns last 100 `{thread_id, question, answer, created_at}` tuples.
  - **Fallback if `answer` is null:** pull the full chat thread from Amplitude:
    ```python
    e_param = {"event_type": "chat_thread_processed",
               "filters": [{"subprop_key": "gp:user_id", "subprop_op": "is", "subprop_type": "user",
                            "subprop_value": ["<user_id>"]}]}
    # The event payload contains: question, matched_ai_response, quick_suggestions, thread_id
    ```
  - Group by `thread_id` to reconstruct conversations. `matched_ai_response` is the assistant turn that's missing from user-profile-api's `answer` field.
- **Common gotchas:** if a user has chatted with CredGPT at all, Alaska almost always has the conversation history. The fallback path is robust. Don't conclude "no answer was given" without checking Amplitude.

### 1.7 User's full Slack-ready summary (orchestrated)

- **Question pattern:** "Give me everything we know about user X in one message."
- **System(s):** user-profile-api + Amplitude (recent activity) + Customer.io (message history).
- **Steps:**
  1. Resolve user_id (recipe 1.1).
  2. Pull profile (recipe 1.2), read sections 1.3-1.6 worth of fields.
  3. Amplitude recent activity:
     ```python
     url = f"https://amplitude.com/api/2/users/{user_id}/timeline"
     # GET with Basic auth (see integrations/amplitude.md)
     ```
  4. CIO message history:
     ```bash
     curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
       "https://beta-api.customer.io/v1/api/customers/{user_id}/messages"
     ```
  5. Combine into one Slack message: identity → score → debt → income → recent activity → recent messages.
- **Common gotchas:** the CIO user_id IS the BON user_id. No mapping needed. PII (SSN, full DOB, employer name) is already redacted by the skill, but double-check before posting to Slack.

---

## 2. Aggregate product metrics

The "how many / what rate / how is X trending" pattern. Almost all of these hit Amplitude.

### 2.1 Real DAU / WAU / MAU

- **Question pattern:** "How many active users today? This week? This month?"
- **System(s):** Amplitude.
- **Pre-conditions:** Real Users filter applied (`integrations/amplitude.md` § The Real Users filter).
- **Query:**

```python
# DAU
e_param = {"event_type": "_active", "filters": REAL_USERS_FILTERS}
params = {"e": json.dumps(e_param), "m": "uniques",
          "start": today_yyyymmdd, "end": today_yyyymmdd, "i": "1"}

# WAU (rolling 7-day window)
params = {"e": json.dumps(e_param), "m": "uniques",
          "start": (today - 6d), "end": today_yyyymmdd, "i": "7"}

# MAU (rolling 30-day window)
params = {"e": json.dumps(e_param), "m": "uniques",
          "start": (today - 29d), "end": today_yyyymmdd, "i": "30"}
```

- **Result handling:** `data['series'][0][0]` for a single-day number, `data['series'][0]` for a trend.
- **Common gotchas:** without Real Users filter the count inflates from test traffic and pre-onboarding users.

### 2.2 Signups in last N days

- **Question pattern:** "How many users signed up in the last week / month?"
- **System(s):** Amplitude.
- **Pre-conditions:** no Real Users filter (signup is the moment they become real).
- **Query:**

```python
filters = [{"subprop_key": "step_name", "subprop_op": "is", "subprop_type": "event",
            "subprop_value": ["onboarding_complete"]}]
e_param = {"event_type": "onboarding_step_completed", "filters": filters}
params = {"e": json.dumps(e_param), "m": "uniques",
          "start": (today - N days), "end": today_yyyymmdd, "i": str(N)}
```

- **Result handling:** `data['series'][0][0]` = signups in window.
- **Common gotchas:** `onboarding_complete` is the canonical signup marker. Don't use `phone_number_submitted` (that's funnel start, not signup).

### 2.3 Onboarding funnel drop-off (9 steps)

- **Question pattern:** "Where are users dropping off in onboarding?"
- **System(s):** Amplitude.
- **Pre-conditions:** no Real Users filter.
- **Query:** loop the 9 steps with `m=uniques` and compare consecutive counts.

```python
steps = [
    "phone_number_submitted", "otp_verified", "email_verified",
    "credit_report_disclaimer_accepted", "dob_submitted",
    "spin_wheel_connection_successful", "set_pin", "pin_verified",
    "onboarding_complete"
]
results = {}
for step in steps:
    e_param = {"event_type": "onboarding_step_completed",
               "filters": [{"subprop_key": "step_name", "subprop_op": "is",
                            "subprop_type": "event", "subprop_value": [step]}]}
    params = {"e": json.dumps(e_param), "m": "uniques",
              "start": (today - 30d), "end": today_yyyymmdd, "i": "30"}
    results[step] = fetch(params)
```

- **Result handling:** drop between consecutive steps = conversion loss for that step. The known current pattern: OTP step ~5% drop (not the stale 30% figure), Spinwheel identity ~15% drop is the biggest leak. See `definitions/lifecycle-events.md` for the corrected funnel truth.
- **Common gotchas:** don't quote the stale "OTP 30% drop" figure. It's been wrong since 2026-04.

### 2.4 Card linkage conversion (Plaid)

- **Question pattern:** "What's our card-linking conversion?"
- **System(s):** Amplitude.
- **Query:**

```python
e_param = [
    {"event_type": "add_card_initiate",   "filters": REAL_USERS_FILTERS},
    {"event_type": "add_card_successful", "filters": REAL_USERS_FILTERS}
]
params = {"e": json.dumps(e_param), "m": "formula",
          "formula": "TOTALS(B)/TOTALS(A)",
          "start": (today - 30d), "end": today_yyyymmdd, "i": "30"}
```

- **Result handling:** returns decimal.
- **Common gotchas:** don't quote an expected range. Pull the live number.

### 2.5 Bank linkage conversion (Plaid)

Same shape as 2.4 with `add_bank_initiate` / `add_bank_successful`.

### 2.6 Spinwheel success rate

- **Question pattern:** "Is Spinwheel identity working?"
- **System(s):** Amplitude.
- **Pre-conditions:** **no** Real Users filter (Spinwheel fires pre-user_id).
- **Query:**

```python
e_param = [
    {"event_type": "spinwheel_completed"},
    {"event_type": "spinwheel_failed"}
]
params = {"e": json.dumps(e_param), "m": "formula",
          "formula": "TOTALS(A)/(TOTALS(A)+TOTALS(B))",
          "start": (today - 14d), "end": today_yyyymmdd, "i": "30"}
```

- **Common gotchas:** `spinwheel_failed` carries **no usable failure reason** — its `failure_reason` property is always "(none)" (per the Amplitude reference). Amplitude can't tell you *why* it failed; use the backend / Spinwheel-side error reporting for that.

### 2.7 Plaid failures by exit step or institution

- **Question pattern:** "Where in Plaid Link are users dropping? Which banks are blocking?"
- **System(s):** Amplitude.
- **Query:**

```python
e_param = {"event_type": "add_card_unsuccessful", "filters": REAL_USERS_FILTERS}
# By exit step:
params = {"e": json.dumps(e_param), "m": "totals", "g": "exit_step",
          "start": (today - 30d), "end": today_yyyymmdd, "i": "30", "limit": "20"}
# By institution:
params["g"] = "institution_name"
```

- **Common gotchas:** `add_card_unsuccessful` has 32 properties; exit_step and institution_name are the high-signal ones.

---

## 3. Engagement and chat

### 3.1 Unique chatters per day

- **Question pattern:** "How many users chatted today? This week?"
- **System(s):** Amplitude.
- **Query:**

```python
e_param = {"event_type": "credgpt_message_sent", "filters": REAL_USERS_FILTERS}
params = {"e": json.dumps(e_param), "m": "uniques",
          "start": today_yyyymmdd, "end": today_yyyymmdd, "i": "1"}
```

- **Common gotchas:** use `credgpt_message_sent` not `credgpt_chat_started` (the latter misses ~5%).

### 3.2 Chat depth (messages per chatter)

- **Question pattern:** "How deep are conversations?"
- **System(s):** Amplitude.
- **Query:** two queries, divide.

```python
# Total messages
e_param_a = {"event_type": "credgpt_message_sent", "filters": REAL_USERS_FILTERS}
# Unique chatters
e_param_b = {"event_type": "credgpt_chat_started", "filters": REAL_USERS_FILTERS}
# messages_per_chatter = totals(A) / uniques(B)
```

### 3.3 Top chatters by message volume

- **Question pattern:** "Who are our heaviest CredGPT users?"
- **System(s):** Amplitude.
- **Query:**

```python
e_param = {"event_type": "credgpt_message_sent", "filters": REAL_USERS_FILTERS}
params = {"e": json.dumps(e_param), "m": "totals", "g": "gp:user_id",
          "start": (today - 30d), "end": today_yyyymmdd, "i": "30", "limit": "50"}
```

- **Result handling:** returns user_ids ordered by message count. Resolve user_ids → emails via user-profile-api (recipe 1.1 reversed: `users/{user_id}/profile` returns email).

### 3.4 A specific user's recent chat history

See recipe 1.6 (`chat.recent_turns` via user-profile-api).

---

## 4. Engineering activity

GitHub is the source. Reference `integrations/github.md` for the handle table and repo map. Don't embed handles or repos here.

### 4.1 Recent commits in one repo

- **Question pattern:** "What's been pushed to repo X lately?"
- **System(s):** GitHub.
- **Pre-conditions:** confirm default branch from `integrations/github.md` repo map. `bon_webservices` defaults to `dev_testing`, not `main`.
- **Query:**

```bash
curl -s -H "Authorization: Bearer $BON_GITHUB_TOKEN" \
  "https://api.github.com/repos/<org>/<repo>/commits?per_page=20"
```

### 4.2 PRs merged today by a specific author

- **Question pattern:** "What did Sandeep merge today?"
- **System(s):** GitHub.
- **Pre-conditions:** look up GitHub handle from the table in `integrations/github.md`.
- **Query:**

```bash
curl -s -H "Authorization: Bearer $BON_GITHUB_TOKEN" \
  "https://api.github.com/search/issues?q=repo:<org>/<repo>+is:pr+is:merged+author:<handle>+merged:>=<today_iso_date>"
```

- **Common gotchas:** MobileFirst (external agency) authored a large share of `bon_app` and `bon_webservices` history. Filtering by internal handles undercounts real activity. See `integrations/github.md` § author-filtering caveat.

### 4.3 Cross-repo activity for a team member

- **Question pattern:** "What did X ship across all repos this week?"
- **System(s):** GitHub.
- **Steps:**
  1. Look up handle from `integrations/github.md`.
  2. Loop the 9 repos.
  3. Per repo: `commits?author=<handle>&since=<today - 7d>` ISO date.
  4. Aggregate.
- **Common gotchas:** rate limit is 5000 req/hr authenticated. Cache or batch if running this in a loop. Two orgs (`Bonhq/*` and `Bonlife/*`), no org-level rollup endpoint.

### 4.4 Read a specific file at the right branch

- **Question pattern:** "What does function X in file Y look like right now?"
- **System(s):** GitHub Contents API.
- **Pre-conditions:** confirm branch from repo map.
- **Query:**

```bash
curl -s -H "Authorization: Bearer $BON_GITHUB_TOKEN" -H "User-Agent: alaska" \
  "https://api.github.com/repos/<org>/<repo>/contents/<path>?ref=<branch>" \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())"
```

- **Result handling:** quote the actual bytes. Name the repo, branch, and path. See `integrations/github.md` § grounded reading discipline.
- **Common gotchas:** never guess a path. If unsure, list the file tree first (`git/trees/<branch>?recursive=1`), then read.

---

## 5. Campaign and messaging health

Customer.io is the source. Reference `integrations/customerio.md` for env IDs and approval rules.

### 5.1 List active campaigns

- **Question pattern:** "What campaigns are running right now?"
- **System(s):** CIO.
- **Query:**

```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/environments/211696/campaigns" \
  | jq '.campaigns[] | select(.state == "running") | {id, name, type}'
```

- **Common gotchas:** always query Prod env ID (`211696`), not Dev (`210456`). Pull the live campaign count/inventory from the API — don't quote a static number (it goes stale).

### 5.2 Per-campaign delivery health

- **Question pattern:** "How healthy is campaign X?"
- **System(s):** CIO.
- **Query:**

```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/environments/211696/campaigns/<id>/metrics"
```

- **Result handling:** read `metric.total_sent`, `total_delivered`, `total_opened`, `total_clicked`, `total_bounced`. Compute rates. The response includes 45-day daily arrays per channel plus rolled-up totals.

### 5.3 Push notification health (system-wide)

- **Question pattern:** "Is push working? Why is delivery so low?"
- **System(s):** CIO + Amplitude.
- **Steps:**
  1. Loop running campaigns from 5.1, filter to push type.
  2. For each, fetch metrics (5.2), sum per-channel push totals.
  3. Compute system-wide delivery / open / bounce rates.
  4. Check upstream permission grant rate from Amplitude:
     ```python
     e_param = [
         {"event_type": "feature_used",
          "filters": [{"subprop_key": "feature_name", "subprop_op": "is", "subprop_type": "event",
                       "subprop_value": ["notification_permission_granted"]}]},
         {"event_type": "feature_used",
          "filters": [{"subprop_key": "feature_name", "subprop_op": "is", "subprop_type": "event",
                       "subprop_value": ["notification_permission_denied"]}]}
     ]
     # formula: TOTALS(A) / (TOTALS(A) + TOTALS(B)) = opt-in rate
     ```
- **Result handling:** low delivery is almost always a permission-opt-in problem at the iOS/Android layer, not a backend issue. Frame as UX, not engineering. See `integrations/customerio.md` § push delivery has historically been low.

### 5.4 Per-user message history

- **Question pattern:** "What messages did user X get from us?"
- **System(s):** CIO Beta API.
- **Query:**

```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://beta-api.customer.io/v1/api/customers/<user_id>/messages"
```

### 5.5 Pause or resume a campaign

- **Question pattern:** "Pause the [X] campaign / start it again."
- **System(s):** CIO write.
- **Pre-conditions:** no approval needed for pause or resume (safety actions). Confirm match if name is ambiguous.
- **Query:**

```bash
# Pause
curl -s -X PUT -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/environments/211696/campaigns/<id>/actions/pause"
# Resume
curl -s -X PUT -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/environments/211696/campaigns/<id>/actions/start"
```

- **Common gotchas:** if multiple campaigns match the name (e.g., "Transaction Posted" vs "Transaction summary email"), list them with IDs and ask. Don't pause silently. See `integrations/customerio.md` § campaign ambiguity in Slack commands.

### 5.6 Create or edit a campaign

Approval required (Abhinav or Founders). See `integrations/customerio.md` § Approval required. Don't try to do this from common-queries.

---

## 6. Meeting and decision history

Fireflies for transcript search and pull. Notion for the Decision Log archive. Sometimes both.

### 6.1 List recent transcripts

- **Question pattern:** "What calls happened in the last N days?"
- **System(s):** Fireflies.
- **Query:**

```bash
curl -s -X POST "https://api.fireflies.ai/graphql" \
  -H "Authorization: Bearer $FIREFLIES_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"{ transcripts(fromDate: \"<today - 7d ISO>\", toDate: \"<today ISO>\", limit: 20) { id title date duration organizer_email participants } }"}'
```

### 6.2 Pull one transcript with full sentences

- **Question pattern:** "What did we actually say on the X call?"
- **System(s):** Fireflies.
- **Query:**

```bash
curl -s -X POST "https://api.fireflies.ai/graphql" \
  -H "Authorization: Bearer $FIREFLIES_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"{ transcript(id: \"<ID>\") { id title date sentences { text speaker_name start_time } summary { overview action_items keywords } } }"}'
```

- **Result handling:** sentences are the ground truth. Fireflies' auto-`summary.action_items` can miss or mis-attribute. Use sentences for anything load-bearing.
- **Common gotchas:** calls are often Hinglish, and proper nouns drift. The known case: MoneyLion frequently transcribed as "Moneyline." Normalize to MoneyLion.

### 6.3 Search transcripts by keyword

- **Question pattern:** "Did we ever talk about X?"
- **System(s):** Fireflies.
- **Query:**

```bash
curl -s -X POST "https://api.fireflies.ai/graphql" \
  -H "Authorization: Bearer $FIREFLIES_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"{ transcripts(keyword: \"engine integration\") { id title date } }"}'
```

### 6.4 Find a recent decision in Notion

- **Question pattern:** "What did we decide about X?"
- **System(s):** Notion (Decision Log).
- **Pre-conditions:** look up Decision Log data source ID from `workspace/MEMORY.md` § Notion Data Sources.
- **Query:**

```bash
curl -s -X POST -H "Authorization: Bearer $NOTION_API_KEY" \
  -H "Notion-Version: 2025-09-03" -H "Content-Type: application/json" \
  --data '{"page_size": 20, "sorts": [{"timestamp": "created_time", "direction": "descending"}]}' \
  "https://api.notion.com/v1/data_sources/<DECISION_LOG_DATA_SOURCE_ID>/query"
```

- **Common gotchas:** use `Notion-Version: 2025-09-03` for reads, `2022-06-28` for writes. Mixing → cryptic 400s. See `integrations/notion.md` § version routing.

### 6.5 "When did we decide X?" (cross-system)

- **Question pattern:** "When did we lock in the decision about X?"
- **System(s):** Fireflies (find the call) + Notion (the formal record).
- **Steps:**
  1. Search Fireflies for keyword (6.3).
  2. For the most recent match, pull the transcript (6.2) and quote the sentences where the decision was made.
  3. Query Notion Decision Log filtered by keyword in title to find the formal record.
  4. Present both: when said, who said it (Fireflies), and the formal record (Notion).
- **Common gotchas:** the Notion Decision Log lags Fireflies by up to a day (MI writes after processing the transcript). For very recent decisions, Fireflies may have it before Notion does.

---

## 7. Outbound and Slack

Slack is Alaska's primary outbound surface. Reference `workspace/MEMORY.md` § Slack Channels for IDs.

### 7.1 Post to a channel

- **Question pattern:** "Post X to channel Y."
- **System(s):** Slack.
- **Pre-conditions:** bot must be a member of the channel. Look up channel ID from MEMORY.md (don't use channel name in API call).
- **Query:**

```bash
curl -s -X POST -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  --data '{"channel":"<CHANNEL_ID>", "text":"*Title*\nBody text"}' \
  "https://slack.com/api/chat.postMessage"
```

- **Common gotchas:** mrkdwn, not Markdown. `*bold*` (single asterisks). `**bold**` renders as literal asterisks. See `integrations/slack.md` § formatting. First names only, no Slack IDs visible to humans, no email addresses. See `workspace/SOUL.md` § Slack Message Discipline.

### 7.2 DM a team member

- **Question pattern:** "DM Sandeep / Pankaj / Samder this update."
- **System(s):** Slack.
- **Pre-conditions:** look up the team member's Slack user ID from `workspace/MEMORY.md` § Team Roster.
- **Query:** same as 7.1 with the Slack user ID (`U…`) in the `channel` field. Slack auto-opens the IM.
- **Common gotchas:** "user" elsewhere in this file means a BON app user. In Slack outbound, "team member" is the right word. Don't DM Alaska's own bot account or the `alaska@boncredit.ai` placeholder account. See `integrations/slack.md` § bot identity.

### 7.3 React to a message

- **Question pattern:** "React with [emoji] to message X."
- **System(s):** Slack.
- **Query:**

```bash
curl -s -X POST -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  --data "channel=<CHANNEL_ID>&timestamp=<TS>&name=<emoji_name_without_colons>" \
  "https://slack.com/api/reactions.add"
```

### 7.4 Look up an unknown Slack team member (identity self-heal)

- **Question pattern:** "Who is this Slack ID?"
- **System(s):** Slack.
- **Query:**

```bash
curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  "https://slack.com/api/users.info?user=<SLACK_USER_ID>"
```

- **Result handling:** read `profile.real_name` and `profile.display_name`. Compare against first names in `workspace/MEMORY.md` § Team Roster. If first-name match found, update MEMORY.md. If no match, ask the person directly. Never default to "must be Abhinav." See `workspace/SOUL.md` § Identity Resolution.
- **Common gotchas:** this is for **team members** inside the BON Slack workspace, not BON app users (those live in user-profile-api, see Section 1). The `users.info` API returns Slack workspace identity, not BON product identity.

### 7.5 Reply in a thread

- **Question pattern:** "Reply to message X in its thread."
- **System(s):** Slack.
- **Query:** same as 7.1 with `thread_ts` set to the parent message's `ts`. Add `reply_broadcast: true` to also surface in the channel.
- **Common gotchas:** `thread_ts` must be the **parent's** `ts`, not a reply's. In standup threads, a reply in Shailesh's thread saying "On leave today" updates Shailesh's status, not the replier's. Always check whose thread you're in. See `integrations/slack.md` § failure modes.

---

## People

- **Owns this file:** Abhinav.
- **Owns query patterns:** Sandeep (Amplitude + CIO + shared-toolkit) + Abhinav (review).
