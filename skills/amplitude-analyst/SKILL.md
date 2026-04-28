---
name: amplitude-analyst
description: Deep Amplitude analytics — query metrics, pattern match, compare periods, user lookup, distribution analysis, cross-system intelligence
version: 2.0.0
metadata:
  openclaw:
    requires:
      env: [AMPLITUDE_API_KEY, AMPLITUDE_SECRET_KEY]
      bins: [curl, python3]
    primaryEnv: AMPLITUDE_API_KEY
    emoji: "📈"
---

# Amplitude Analyst v2.0

Alaska's deep analytics capability. Query any Amplitude metric with the **Real Users filter** applied by default.

**CRITICAL REFERENCE:** Full event taxonomy, property keys, data quality issues, and validation numbers are in `/root/.openclaw/workspace/references/amplitude-api-reference.md`. READ IT before building any new query pattern.

## API Configuration

**Base URL:** `https://amplitude.com/api/2/`
**Auth:** Basic auth via curl's `-u` flag:
```bash
curl -s -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY" "https://amplitude.com/api/2/<endpoint>"
```

**For complex queries with filters, ALWAYS use python3** (curl URL encoding breaks with nested JSON):
```python
python3 << 'PYEOF'
import urllib.parse, urllib.request, json, os, base64
api_key = os.environ['AMPLITUDE_API_KEY']
api_secret = os.environ['AMPLITUDE_SECRET_KEY']
auth = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()

e_param = { ... }  # event definition with filters
params = {'e': json.dumps(e_param, separators=(',',':')), 'm': 'uniques', 'start': 'YYYYMMDD', 'end': 'YYYYMMDD', 'i': '1'}
url = f"https://amplitude.com/api/2/events/segmentation?{urllib.parse.urlencode(params)}"
req = urllib.request.Request(url, headers={'Authorization': f'Basic {auth}'})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
print(data['data']['series'][0])  # daily values
print(data['data']['xValues'])    # date labels
PYEOF
```

---

## The Real Users Filter (MANDATORY)

**Every query MUST apply this filter.** Without it, numbers are inflated 3-5x.

```python
REAL_USERS_FILTERS = [
    {"subprop_key": "gp:credit_score", "subprop_op": "greater", "subprop_type": "user", "subprop_value": ["0"]},
    {"subprop_key": "gp:user_id", "subprop_op": "is not", "subprop_type": "user", "subprop_value": ["2503", "2604", "2601", "2300", "287", "2062", "2605"]},
    {"subprop_key": "version", "subprop_op": "does not contain", "subprop_type": "user", "subprop_value": ["dev"]}
]
```

**CRITICAL API QUIRK:** The operator is `"greater"` NOT `"greater than"`. The API returns HTTP 400 for "greater than". This also applies to `"less"` (not "less than"), `"greater or equal"`, `"less or equal"`.

### Verified Real DAU numbers (Apr 21-27, 2026 — use for validation)
```
With Real Users filter: [12, 15, 18, 12, 17, 16, 22] — WAU: 85
Without filter:         [55, 41, 32, 30, 37, 26, 35] — WAU: 208
```
If your DAU query returns numbers in the 30-60 range, **the filter is not applied correctly.**

### Exception: Spinwheel events
`spinwheel_started`, `spinwheel_completed`, `spinwheel_failed` fire BEFORE user_id is assigned (during onboarding). Do NOT apply Real Users filter to these — they would return 0.

---

## Standard Query Templates

### Real DAU (7-day trend)

```python
e_param = {"event_type": "_active", "filters": REAL_USERS_FILTERS}
# m=uniques, i=1, start/end = 7 days
```

### Real WAU
Same query with `i=7` and a 7-day date range.

### Chat Engagement (unique chatters)
```python
e_param = {"event_type": "credgpt_message_sent", "filters": REAL_USERS_FILTERS}
# m=uniques for unique chatters, m=totals for message count
```
`credgpt_message_sent` is more reliable than `credgpt_chat_started` (which misses ~5% of chatters).

### Card Linking Funnel
```python
# Query add_card_initiate and add_card_successful separately, both with Real Users filter
# Conversion = successful / initiate. Expected: ~21-33%.
```

### Onboarding Funnel
```python
# Query onboarding_step_completed with step_name filter for each step
# step_names: phone_number_submitted, otp_verified, email_verified, credit_report_disclaimer_accepted,
#   dob_submitted, spin_wheel_connection_successful, set_pin, pin_verified, onboarding_complete
# NO Real Users filter (users aren't "real" until onboarding completes)
e_param = {"event_type": "onboarding_step_completed", "filters": [
    {"subprop_key": "step_name", "subprop_op": "is", "subprop_type": "event", "subprop_value": ["phone_number_submitted"]}
]}
```

### Group-by Queries
```python
# Add group_by to the e_param
e_param = {"event_type": "_active", "filters": REAL_USERS_FILTERS, "group_by": [{"type": "user", "value": "gp:is_card_linked"}]}
# Also pass limit=20 in params
```

---

## Chart Generation

```bash
# Line chart (DAU trend)
python3 /data/skills/amplitude-analyst/charts.py line /tmp/chart.png "DAU — Apr 21-27" "Apr 21,Apr 22,Apr 23,Apr 24,Apr 25,Apr 26,Apr 27" "12,15,18,12,17,16,22"

# Upload to Slack
bash /data/skills/amplitude-analyst/upload_chart.sh /tmp/chart.png <CHANNEL_ID> "Chart Title" "_Comment_"
```

Chart types: `line`, `bar`, `funnel`, `compare`, `distro`. See charts.py for details.

Channel IDs: #alaska-daily-pulse=C0APP7V6H8C, #project-management=C0ANKDD664A, #alaska-alerts=C0APP7X4TMJ.

**NEVER narrate chart generation in Slack.** No "Let me generate..." — just do it and post the result.

---

## Validation Reference Numbers (early April 2026)

| Metric | Expected Range | If outside range |
|---|---|---|
| Real DAU | 1-25/day | Filter likely wrong |
| Real WAU | 15-100 | Check date range |
| Real MAU | 80-150 | — |
| Onboarded (30d) | ~73 | — |
| Chat users (30d) | 100-170 | — |
| Card link conversion | 21-33% | Check event names |
| Bank link conversion | 50-63% | — |
| iOS share | 85-90% | — |

---

## Known Data Quality Issues

- `session_start` doesn't fire for ~5-10% of users → use `_active` uniques
- `credgpt_chat_started` misses ~5% of chatters → use `credgpt_message_sent` uniques
- `screen_time_spent` only fires on screen EXIT → undercounts chat users 3-10x
- `credgpt_response_error` fires 0 times → error tracking is broken
- `sign_up_started_event` / `sign_up_completed_event` stopped firing March 17
- All bill payment events (`pay_bill_*`, `one_time_bill_payment_*`) = dead (zero volume)
- Counter mismatches: `add_card_successful` sometimes > `add_card_initiate` (double-fire bug)

---

## Cross-Reference with Customer.io

When answering metric questions, enrich with Customer.io data when relevant:
- "Why did DAU drop?" → Check if campaigns were paused/changed
- "How are push notifications?" → Customer.io delivery metrics, not just Amplitude events
- "Tell me about user X" → Include messaging history
- Read `/data/skills/customerio-ops/SKILL.md` for API patterns.

---

## Error Handling

- **API 400:** Check filter syntax. Most common: using `"greater than"` instead of `"greater"`.
- **API 401/403:** API key invalid. Say "Amplitude auth failed."
- **API 429:** Rate limited. Skip and note.
- **Empty/no data:** Say "unavailable" — NEVER make up numbers.
- **During cron runs:** Skip metrics section gracefully. Don't fail the entire run.
