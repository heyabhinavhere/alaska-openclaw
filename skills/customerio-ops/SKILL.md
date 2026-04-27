---
name: customerio-ops
description: Customer.io campaign management — list/create/edit/pause campaigns, delivery metrics, user messaging history, segment management
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [CUSTOMERIO_APP_API_KEY, CUSTOMERIO_SITE_ID, CUSTOMERIO_TRACK_API_KEY]
      bins: [curl, sqlite3]
    primaryEnv: CUSTOMERIO_APP_API_KEY
    emoji: "📧"
---

# Customer.io Operations

Alaska's campaign management and messaging intelligence. List campaigns, check delivery metrics, look up user messaging history, create/edit/pause campaigns from Slack.

**Read this skill when:**
- Someone asks about campaigns, push notifications, emails, or delivery rates
- Someone asks to create, edit, or pause a campaign
- User lookup needs messaging history ("what messages did user X receive?")
- Daily Pulse needs campaign health metrics
- Thinker needs to check if a campaign change caused a metric shift

## API Configuration

**Two APIs, two auth methods:**

| API | Base URL | Auth | Purpose |
|---|---|---|---|
| App API | `https://api.customer.io/v1/` | Bearer `$CUSTOMERIO_APP_API_KEY` | Campaigns, metrics, customers, segments |
| Beta API | `https://beta-api.customer.io/v1/api/` | Bearer `$CUSTOMERIO_APP_API_KEY` | User messages, advanced queries |
| Track API | `https://track.customer.io/api/v2/` | Basic `$CUSTOMERIO_SITE_ID:$CUSTOMERIO_TRACK_API_KEY` | Send events, identify users (rarely needed) |

**App API curl pattern (most operations):**
```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/<endpoint>"
```

**Rate limit tracking:** Same SQLite table as Amplitude:
```bash
# Log after each call:
sqlite3 /data/queue/alaska.db "INSERT INTO api_rate_limits (service, endpoint, hour_bucket) VALUES ('customerio', '<endpoint>', strftime('%Y-%m-%d %H', 'now'));"
```

Customer.io rate limits are generous for reads. Be more careful with writes (campaign create/edit).

---

## 1. Campaign Management

### List all campaigns

```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/campaigns"
```

Response includes campaign `id`, `name`, `state` (active/paused/draft), `created`, `updated`, `type`.

Format as:
```
*Active Campaigns:*
1. Transaction Summary Email (ID: 12) — active since Apr 10
2. Welcome Series (ID: 8) — active since Mar 15
3. Card Linking Reminder (ID: 15) — paused Apr 20

*Draft:*
4. Win-Back Push (ID: 18) — draft, not sent
```

### Campaign metrics

```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/campaigns/<CAMPAIGN_ID>/metrics"
```

Returns: `sent`, `delivered`, `opened`, `clicked`, `converted`, `bounced`, `unsubscribed`, `complained`.

Format as:
```
*Transaction Summary Email (ID: 12)*
Sent: 450 | Delivered: 412 (92%) | Opened: 142 (34%)
Clicked: 28 (7%) | Bounced: 38 (8%) | Unsub: 3
```

### Pause a campaign

```bash
curl -s -X PUT -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  -H "Content-Type: application/json" \
  "https://api.customer.io/v1/campaigns/<CAMPAIGN_ID>/actions/pause"
```

**Ambiguity rule:** If the user says "pause the transaction email" and multiple campaigns match "transaction":
1. List all matching campaigns with their IDs and states
2. Ask: "Found 2 campaigns matching 'transaction'. Which one? (1) Transaction Summary Email (ID: 12, active) (2) Transaction Alert Push (ID: 14, active)"
3. Only pause after the user specifies which one
4. If exactly ONE campaign matches → pause immediately, confirm in Slack

Pause is a safety action — no approval needed. Confirm after: "Paused: Transaction Summary Email (ID: 12). Reply 'resume 12' to reactivate."

### Resume a campaign

```bash
curl -s -X PUT -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  -H "Content-Type: application/json" \
  "https://api.customer.io/v1/campaigns/<CAMPAIGN_ID>/actions/start"
```

Resume is also immediate — no approval needed.

### Create a campaign (REQUIRES ABHINAV APPROVAL)

**Step 1:** Draft the campaign details and post to Slack for approval:

```
*Campaign Draft — Awaiting Approval*

*Name:* [campaign name]
*Channel:* push / email / SMS
*Segment:* [segment name] — [X] users
*Subject/Title:* [full subject line]
*Content preview:* [first 2 sentences of message body]
*Schedule:* immediate / daily at [time] / one-time on [date]
*Estimated reach:* [X] users

@Abhinav — approve or reject? This will NOT be activated until you reply "approved".
```

**Step 2:** Wait for explicit "approved" reply from Abhinav. **NO auto-confirm. NO timeout.** Campaign stays as draft indefinitely until approved or rejected.

**Step 3:** On approval:
```bash
curl -s -X POST -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "<name>", "type": "<type>", ...}' \
  "https://api.customer.io/v1/campaigns"
```

Then activate:
```bash
curl -s -X PUT -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/campaigns/<NEW_ID>/actions/start"
```

**On rejection:** "Campaign draft rejected. Not created." Drop it.

### Edit a campaign (REQUIRES ABHINAV APPROVAL)

Same approval flow as create. Show what's changing:

```
*Campaign Edit — Awaiting Approval*

*Campaign:* Transaction Summary Email (ID: 12)
*Change:* Subject line
*From:* "Your Daily Transaction Summary"
*To:* "How your money moved today"

@Abhinav — approve?
```

### Delete a campaign (REQUIRES EXPLICIT CONFIRMATION)

```
Deleting campaign "[name]" (ID: [X]). This cannot be undone.
@Abhinav — reply "delete confirmed" to proceed.
```

Only delete on exact "delete confirmed" reply.

---

## 2. Delivery Monitoring

### Push notification delivery rate

```bash
# Get all push campaigns
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/campaigns" | # filter for push type

# Then get metrics for each push campaign
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/campaigns/<PUSH_CAMPAIGN_ID>/metrics"
```

Calculate delivery rate: `(delivered / sent) * 100`

Format:
```
*Push Notification Health:*
• Overall delivery: 38% (was 4% before fix)
• Transaction Alert: 412/450 delivered (92%)
• Card Linking Reminder: 28/180 delivered (16%) ← problem
```

### Email delivery/open/click

Same pattern — pull metrics for email campaigns, calculate rates.

Flag unhealthy campaigns:
- Delivery < 50% → "*Alert:* [campaign] has [X]% delivery — possible deliverability issue"
- Open rate < 10% → "*Note:* [campaign] has [X]% open rate — subject line may need work"
- Bounce rate > 10% → "*Alert:* [campaign] has [X]% bounce rate — list hygiene needed"

---

## 3. User Messaging History

### What messages did a user receive?

```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://beta-api.customer.io/v1/api/customers/2714/messages"
```

Returns list of messages sent to this user with: campaign name, channel (email/push/SMS), sent_at, delivered, opened, clicked.

Format as:
```
*Messages to User 2714:*
1. Welcome Email (Mar 15) — delivered ✓, opened ✓, clicked ✓
2. Transaction Summary (Apr 20) — delivered ✓, opened ✓
3. Transaction Summary (Apr 21) — delivered ✓, not opened
4. Card Linking Push (Apr 22) — not delivered ✗
5. Transaction Summary (Apr 23) — delivered ✓, opened ✓, clicked ✓
```

### User attributes in Customer.io

```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/customers/2714/attributes"
```

Returns: email, name, created_at, custom attributes, segment membership.

### Cross-reference with Amplitude

When doing a user lookup, ALWAYS combine with Amplitude data if `$AMPLITUDE_API_KEY` is set. Read `/data/skills/amplitude-analyst/SKILL.md` Section 2 for the user lookup pattern. Present both in one Slack message.

---

## 4. Segment Management

### List segments

```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/segments"
```

Format: "Active segments: [name] ([X] users), [name] ([Y] users), ..."

### Check user segment membership

Part of the user attributes response — look for `segments` array.

### Create a segment (REQUIRES ABHINAV APPROVAL)

Same approval pattern as campaign creation. Post draft, wait for "approved."

---

## 5. Campaign Health for Daily Pulse

When Daily Pulse runs, provide a *Campaign Health* section:

1. Query all active campaigns
2. Get metrics for each
3. Flag any with:
   - Delivery < 50%
   - Open rate < 10%
   - Bounce rate > 10%
4. If all healthy, just show totals: "Campaigns: 3 active, all healthy (avg delivery 89%, open 34%)"
5. If any unhealthy, list the problem campaigns

---

## Error Handling

- **401/403:** "Customer.io authentication failed. Check API key." Skip all CIO operations.
- **404 on customer lookup:** "User [X] not found in Customer.io." Show Amplitude data only if available.
- **429:** Log to `api_rate_limits`. "Customer.io rate limited. Retrying shortly."
- **5xx:** "Customer.io API unavailable." Skip CIO sections.
- **During scheduled runs:** Skip CIO sections gracefully. Don't fail the entire Daily Pulse or Thinker run.

**Anti-hallucination rule:** Never guess delivery rates or campaign metrics. If the API call fails, say "unavailable." Never use stale numbers.

---

## When to Cross-Reference Amplitude

When answering campaign questions, check if Amplitude data would make the answer richer:

- **"Is the push notification fix working?"** → Check CIO delivery rate AND Amplitude app_open events from push
- **"Which campaign drives the most engagement?"** → Get CIO click rates AND check if clickers have higher Amplitude session counts
- **"Why are users churning?"** → Check if churned users (Amplitude: no activity 7+ days) received campaigns (CIO: messages sent) — were they ignored?
- **"Should we send more push notifications?"** → Check CIO delivery rate AND Amplitude push-attributed app opens

To query Amplitude, read `/data/skills/amplitude-analyst/SKILL.md` for the API patterns.

---

## Slack Output Formatting

- Campaign lists: numbered, one per line, include status
- Metrics: use the `Sent: X | Delivered: Y (Z%)` inline format
- User message history: numbered, chronological, show delivery + open status with ✓/✗
- Campaign drafts for approval: use the full template above with all required fields
- Use `*bold*` for section headers (Slack mrkdwn)
- Max 20 lines per response
