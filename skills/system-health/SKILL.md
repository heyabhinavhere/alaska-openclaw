---
name: system-health
description: Error handling, graceful degradation, and system health monitoring for all agents
version: 1.0.0
metadata:
  openclaw:
    always: true
    requires:
      bins: [sqlite3, curl]
    emoji: "🏥"
---

# System Health & Error Handling

This skill defines how Alaska handles failures gracefully. Every agent must follow these rules.

## SQLite Queue-First (Failure Protection)

Before writing to ANY external service, save to SQLite first:
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO outbox (target, payload, status) VALUES ('<target>', '<json>', 'pending');"
```

After successful delivery:
```bash
sqlite3 /data/queue/alaska.db "UPDATE outbox SET status='sent', sent_at=datetime('now') WHERE id=<id>;"
```

On failure:
```bash
sqlite3 /data/queue/alaska.db "UPDATE outbox SET status='failed', retry_count=retry_count+1 WHERE id=<id>;"
```

## Error Handling by Service

### Notion Down / API Error
- Save the write to SQLite outbox with target='notion'
- Continue with other operations (post to Slack, etc.)
- On next agent run, retry failed Notion writes from outbox
- After 3 failed retries, alert Abhinav via Slack DM: "Notion API is failing. [X] writes queued locally. I'll keep retrying."
- Never lose data — SQLite is the safety net

### Slack Down / API Error
- Save the message to SQLite outbox with target='slack'
- Retry on next run
- If Slack is down for 30+ minutes, try WhatsApp backup (if configured) for critical alerts only
- Log the outage for System Health page

### Fireflies API Error
- Log the error, skip this transcript
- Mark as 'failed' in processed_meetings table
- Retry on next cron run
- After 3 failures on same transcript: "Fireflies API failed 3 times on '[meeting name]'. Skipping. Check API key validity."

### Bad/Empty Transcript
- If Fireflies returns an empty transcript or <1 minute of content: skip silently
- If transcript is corrupted (malformed JSON): log error, skip, alert Abhinav
- If transcript has <3 sentences: skip with note "Transcript too short to process"

### LLM Extraction Failure
- If the extraction returns empty results on a valid transcript: retry once with a simplified prompt
- If still fails: save raw transcript to Notion Meeting Notes with note "Automated extraction failed — manual review needed"
- Never silently drop a meeting

## System Health Check

Every 30 minutes, verify core integrations:

```bash
# Check Notion
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${NOTION_API_KEY}" "https://api.notion.com/v1/users/me" -H "Notion-Version: 2022-06-28"

# Check Fireflies
curl -s -o /dev/null -w "%{http_code}" -X POST "https://api.fireflies.ai/graphql" -H "Authorization: Bearer ${FIREFLIES_API_KEY}" -H "Content-Type: application/json" -d '{"query": "{ user { email } }"}'
```

Log health status:
```bash
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS system_health (id INTEGER PRIMARY KEY AUTOINCREMENT, service TEXT, status TEXT, response_code INTEGER, checked_at DATETIME DEFAULT CURRENT_TIMESTAMP);"
sqlite3 /data/queue/alaska.db "INSERT INTO system_health (service, status, response_code) VALUES ('<service>', '<ok|error>', <code>);"
```

If any service has been down for 3+ consecutive checks (90 minutes), DM Abhinav:
```
*System Health Alert*
[Service] has been unresponsive for [X] minutes.
Last error: [error code/message]
Impact: [what's affected — e.g., "Meeting Intelligence can't write to Notion"]
Queued writes: [X] pending in local queue
```

## Retry Strategy

| Failure | Retry After | Max Retries | Fallback |
|---|---|---|---|
| Notion API error | Next agent run (30 min) | 3 | Alert Abhinav, keep in queue |
| Slack API error | 5 minutes | 5 | WhatsApp backup for critical |
| Fireflies API error | Next cron (30 min) | 3 | Skip transcript, alert |
| LLM extraction fail | Immediate (1 retry) | 1 | Save raw, flag for manual |

## Graceful Degradation

If a service is down, don't stop everything. Continue with what works:

| Service Down | What Still Works |
|---|---|
| Notion | Slack posts, SQLite queue, Fireflies polling |
| Slack | Notion writes, SQLite queue, all data processing |
| Fireflies | Everything except new transcript processing |
| SQLite | NOTHING — this is critical. Alert immediately. |

## Agent Silence Detection

If Alaska hasn't posted anything to Slack or written to Notion for 30+ minutes during business hours AND there are active cron jobs that should have fired:
- This means the gateway is likely down or crashed
- Railway's health check should catch this (HEALTHCHECK in Dockerfile)
- If gateway restarts, process any queued items from SQLite outbox first
