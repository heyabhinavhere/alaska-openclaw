---
name: report-health
description: "DEPRECATED (2026-06-05) — Notion heartbeat path is no longer used; operational health now comes from cron lastRunStatus/consecutiveErrors + the Daily Cost Report. Originally wrote heartbeats to the Agent Signals Notion DB."
version: 1.0.0
metadata:
  deprecated: true
  openclaw:
    requires:
      bins: [sqlite3]
    emoji: "💓"
---

# Report Health

> **Status as of 2026-06-05: DEPRECATED.** No cron invokes this skill, and the live write-path no longer uses Notion Agent Signals — operational health is tracked via cron `lastRunStatus`/`consecutiveErrors` + the Daily Cost Report DM. Retained for reference, not maintained. Do not invoke unless Abhinav explicitly asks.
>
> **Scope classification:** workshop-mode skill — if ever revived, any agent-memory writes would be `scope='builder'` (see the agent-memory skill's Memory scopes). It reports on Alaska's own internals, never team work.

Use this skill to report agent health status. Every agent should report its status after completing work.

## How to Report Health

1. Queue the health report to SQLite first:
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO outbox (target, payload, status) VALUES ('notion', '{\"database\": \"Agent Signals\", \"signal\": \"<agent_name> heartbeat\", \"from_agent\": \"<agent_name>\", \"type\": \"status\", \"status\": \"<status>\", \"details\": \"<what_happened>\"}', 'pending');"
```

2. Write to the Agent Signals database in Notion via MCP:
   - Signal: `<agent_name> heartbeat` or `<agent_name> alert`
   - From Agent: the agent reporting
   - To Agent: leave empty for heartbeats, set for handoffs
   - Type: `status` for heartbeats, `alert` for problems, `handoff` for passing work
   - Status: `pending` / `acknowledged` / `resolved`
   - Details: what happened, what was produced, any errors

3. Mark the queue entry as sent after successful write.

## Health Statuses

- **healthy** — agent completed its work successfully
- **degraded** — agent completed but with warnings (e.g., partial data)
- **error** — agent failed, needs investigation
- **silent** — no heartbeat received (detected by health monitor)

## Alert Thresholds

If any agent is silent for >30 minutes during expected operating hours, post an alert to Slack.
