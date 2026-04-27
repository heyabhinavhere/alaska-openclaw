---
name: amplitude-analyst
description: Deep Amplitude analytics — query metrics, pattern match, compare periods, user lookup, distribution analysis, cross-system intelligence
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [AMPLITUDE_API_KEY, AMPLITUDE_SECRET_KEY]
      bins: [curl, sqlite3]
    primaryEnv: AMPLITUDE_API_KEY
    emoji: "📈"
---

# Amplitude Analyst

Alaska's deep analytics capability. Query any Amplitude metric, pattern match, compare periods, look up individual users, and cross-reference with Customer.io data.

**Read this skill when:**
- Someone asks a metric question in Slack ("what's DAU?", "show me retention", "who are our power users?")
- Daily Pulse needs real metrics for the morning briefing
- Thinker needs data to back an observation
- Meeting Intelligence needs to verify a metric claim from a meeting

## API Configuration

**Base URL:** `https://amplitude.com/api/2/`
**Auth:** Basic auth via curl's `-u` flag (handles base64 encoding automatically)

```bash
curl -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" "https://amplitude.com/api/2/<endpoint>"
```

**Rate limits:** ~360 requests/hour general. User search/activity endpoints may have lower limits. Track every request:

```bash
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS api_rate_limits (id INTEGER PRIMARY KEY AUTOINCREMENT, service TEXT NOT NULL, endpoint TEXT, request_count INTEGER DEFAULT 1, hour_bucket TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);"

# Before EVERY API call, check current hour count:
sqlite3 /data/queue/alaska.db "SELECT COALESCE(SUM(request_count), 0) FROM api_rate_limits WHERE service='amplitude' AND hour_bucket=strftime('%Y-%m-%d %H', 'now');"

# If count > 300: respond "Amplitude rate limit approaching. I'll check this in a few minutes." and skip the query.

# After each successful call, log it:
sqlite3 /data/queue/alaska.db "INSERT INTO api_rate_limits (service, endpoint, hour_bucket) VALUES ('amplitude', '<endpoint_path>', strftime('%Y-%m-%d %H', 'now'));"
```

---

## 1. Metric Queries

### DAU / WAU / MAU

```bash
# DAU for the last 7 days
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/events/segmentation?e=%7B%22event_type%22%3A%22_active%22%7D&start=<YYYYMMDD>&end=<YYYYMMDD>&m=uniques"
```

Parameters:
- `e` = URL-encoded JSON: `{"event_type":"_active"}` for active users
- `start` / `end` = date range in YYYYMMDD format
- `m` = metric type: `uniques` for unique users

Parse the response `data.series` array for daily values. Format as:

```
DAU (Apr 21-27):
Mon  Tue  Wed  Thu  Fri  Sat  Sun
 7    9    12   11   8    5    6
WoW: -14% (last week avg: 10.1)
```

### Retention

```bash
# First-day retention for users who signed up in the last 30 days
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/retention?se=%7B%22event_type%22%3A%22sign_up%22%7D&re=%7B%22event_type%22%3A%22_active%22%7D&start=<YYYYMMDD>&end=<YYYYMMDD>&rm=bracket&rb=1,3,7,14,30"
```

Parameters:
- `se` = starting event (URL-encoded JSON)
- `re` = return event
- `rm` = retention mode: `bracket` for bracketed retention
- `rb` = retention brackets: day 1, 3, 7, 14, 30

### Funnel Conversion

```bash
# Multi-step funnel
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/funnels?e=%5B%7B%22event_type%22%3A%22sign_up%22%7D%2C%7B%22event_type%22%3A%22credit_report_viewed%22%7D%2C%7B%22event_type%22%3A%22card_linked%22%7D%5D&start=<YYYYMMDD>&end=<YYYYMMDD>"
```

Parameters:
- `e` = URL-encoded JSON array of funnel steps
- Each step: `{"event_type": "<event_name>"}`

**Important:** You need to know BON Credit's actual event names. Common ones from PROJECT_STATE.md context: sign_up, credit_report_viewed, card_linked, chat_started, app_opened. If unsure of exact event names, use the event list endpoint first:

```bash
# List all event types
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/taxonomy/event"
```

### Event Segmentation (most flexible)

```bash
# Any event, grouped by any property
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/events/segmentation?e=%7B%22event_type%22%3A%22<EVENT_NAME>%22%7D&start=<YYYYMMDD>&end=<YYYYMMDD>&m=uniques&g=<GROUP_BY_PROPERTY>"
```

Parameters:
- `g` = group-by property (user property or event property)
- `m` = metric: `uniques`, `totals`, `average`, `pct_dau`

---

## 2. User-Level Lookup

When someone asks "@Alaska tell me about user 2714":

### Step 1: Find the user's Amplitude ID

```bash
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/usersearch?user=2714"
```

Returns user matches with `amplitude_id`. Use this for the activity lookup.

### Step 2: Get recent activity

```bash
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/useractivity?user=<AMPLITUDE_ID>&limit=100"
```

**Data volume constraint:** This can return thousands of events. ALWAYS use `limit=100`. Summarize the response into:

- **Last session:** date and duration
- **Top 5 events:** most frequent event types with counts
- **Key properties:** credit score, card linking status, device, app version
- **Session count:** total sessions in last 7 days

Format as max 15 lines in Slack.

### Step 3: Cross-reference with Customer.io

If `customerio-ops` skill is available and `$CUSTOMERIO_APP_API_KEY` is set, also query:

```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/customers/2714/attributes"
```

Combine into one unified response:

```
*User 2714*

*Amplitude:*
• Last active: Apr 26 (3 sessions this week)
• Top events: chat_started (12), credit_report_viewed (8), card_link_attempted (3)
• Credit score: 620 | Cards linked: 1
• Avg session: 4.2 min

*Customer.io:*
• Campaigns received: 8 (5 opened, 2 clicked)
• Last email: Transaction Summary (Apr 25) — opened
• Segment: active_users, credit_score_below_670

*Sprint context:*
• Card linking fix (Sprint 5) would affect this user — they attempted 3 times
```

### If user not found in Amplitude

Respond: "No Amplitude data for user 2714. They may have denied tracking permission." If Customer.io has data, show that alone.

---

## 3. Pattern Matching & Comparison

### Week-over-Week comparison

Query the same metric for two periods and calculate the delta:

```bash
# This week
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/events/segmentation?e=%7B%22event_type%22%3A%22_active%22%7D&start=<THIS_WEEK_START>&end=<TODAY>&m=uniques"

# Last week
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/events/segmentation?e=%7B%22event_type%22%3A%22_active%22%7D&start=<LAST_WEEK_START>&end=<LAST_WEEK_END>&m=uniques"
```

Calculate: `((this_week_avg - last_week_avg) / last_week_avg) * 100`

Format: "DAU this week: 8.5 avg (last week: 10.1 avg, -16% WoW)"

### Anomaly detection

When querying metrics for Daily Pulse or Thinker, flag if:
- DAU drops >20% WoW → flag in Abhinav DM
- Any key metric drops >30% in a single day → flag immediately
- A metric suddenly improves >50% → likely a deploy effect, cross-reference with GitHub Events API for recent deploys

### Deploy → Metric Impact

When Meeting Intelligence signals a deploy was discussed (via Agent Signals), query Amplitude for the 48 hours before and after the deploy date:

```bash
# 48h before deploy
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/events/segmentation?e=%7B%22event_type%22%3A%22_active%22%7D&start=<DEPLOY_DATE_MINUS_2>&end=<DEPLOY_DATE>&m=uniques"

# 48h after deploy
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/events/segmentation?e=%7B%22event_type%22%3A%22_active%22%7D&start=<DEPLOY_DATE>&end=<DEPLOY_DATE_PLUS_2>&m=uniques"
```

Report: "After the push fix deploy (Apr 23): DAU went from avg 7 to avg 11 (+57%). Push delivery: 4% → 38%."

---

## 4. Distribution Analysis

### User property distribution

```bash
# Credit score distribution
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/events/segmentation?e=%7B%22event_type%22%3A%22_active%22%7D&start=<YYYYMMDD>&end=<YYYYMMDD>&m=uniques&g=credit_score_range"
```

Format as:
```
Credit Score Distribution (active users):
Below 580:  ████████ 32%
580-669:    ██████████ 39%
670-739:    ████ 18%
740-799:    ██ 8%
800+:       █ 3%
```

### Power user identification

Query for users with highest session counts or event counts. Use event segmentation with user-level grouping.

### Cohort comparison

Compare users who completed a key action (card linking) vs those who didn't:

```bash
# Users who linked a card — retention
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" \
  "https://amplitude.com/api/2/retention?se=%7B%22event_type%22%3A%22card_linked%22%7D&re=%7B%22event_type%22%3A%22_active%22%7D&start=<YYYYMMDD>&end=<YYYYMMDD>"
```

---

## 5. Chart Creation

**Status: Text tables only.** The Amplitude HTTP V2 API does not have a public chart creation endpoint. Instead, format metric data as clean text in Slack using code blocks:

```
DAU (Apr 21-27):
Mon  Tue  Wed  Thu  Fri  Sat  Sun
 7    9    12   11   8    5    6
```

For deeper visual exploration, link to the Amplitude dashboard: "For the full interactive chart, see your Amplitude dashboard."

---

## Error Handling

- **API returns 401/403:** API key invalid or expired. Respond: "Amplitude authentication failed. The API key may need regeneration." Skip the query.
- **API returns 429:** Rate limited. Log to `api_rate_limits`, respond: "Amplitude rate limit hit. I'll try again in a few minutes."
- **API returns 5xx:** Server error. Skip and note "Amplitude unavailable right now."
- **Empty response / no data:** Respond with "No data available for that date range" — never make up numbers.
- **During scheduled runs (Daily Pulse, Thinker):** Skip the metrics section gracefully. Don't fail the entire run.

**Anti-hallucination rule:** If you cannot fetch a metric from the API, say "unavailable." NEVER estimate, guess, or use stale numbers from PROJECT_STATE.md as if they were live data. The only exception: if the query fails, you may say "Last known value from [date]: X" with the date clearly stated.

---

## When to Cross-Reference Customer.io

When answering metric questions, check if the answer would be richer with Customer.io data:

- **"Why did DAU drop?"** → Check if any campaigns were paused/changed in Customer.io around that date
- **"How are push notifications performing?"** → Query Customer.io delivery metrics, not just Amplitude event counts
- **"Tell me about user X"** → Always include Customer.io messaging history alongside Amplitude events
- **"Compare users who linked cards vs didn't"** → Check if the two groups received different campaigns

To query Customer.io, read `/data/skills/customerio-ops/SKILL.md` for the API patterns.

---

## Slack Output Formatting

- Use code blocks (triple backticks) for data tables — Slack doesn't support markdown tables
- Keep column widths narrow for mobile readability
- Max 20 lines per response for metric queries
- Max 15 lines for user lookups
- Always include the date range in the response ("DAU for Apr 21-27")
- Include WoW or trend context ("up 14% from last week")
- Use `*bold*` for section headers (Slack mrkdwn, not **markdown**)
