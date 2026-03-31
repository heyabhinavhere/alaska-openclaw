---
name: shared-toolkit
description: Shared utility patterns for all Alaska agents — queue-first writes, health reporting, token budgets, communication standards, agent signaling, error handling
version: 1.0.0
metadata:
  openclaw:
    always: true
    requires:
      bins: [sqlite3, curl]
    emoji: "🔧"
---

# Alaska Shared Toolkit

These are the standard operating procedures every Alaska agent follows. They are loaded automatically into every conversation. If an agent-specific skill contradicts something here, the agent-specific instruction wins for that agent only.

---

## 1. notionWrite — Queue-First Notion Writes

Before writing to Notion, always save to SQLite first. This ensures nothing is ever lost during API outages.

### Pattern

```bash
# Step 1: Queue the write
sqlite3 /data/queue/alaska.db "INSERT INTO outbox (target, payload, status) VALUES ('notion', '<json_payload>', 'pending');"

# Step 2: Write to Notion via MCP
# Use the Notion MCP tool to create/update the page

# Step 3a: On SUCCESS
sqlite3 /data/queue/alaska.db "UPDATE outbox SET status='sent', sent_at=datetime('now') WHERE id=<id>;"

# Step 3b: On FAILURE
sqlite3 /data/queue/alaska.db "UPDATE outbox SET status='failed', retry_count=retry_count+1 WHERE id=<id>;"
```

### Retry Logic

On each invocation, check for stuck outbox entries before doing new work:
```bash
sqlite3 /data/queue/alaska.db "SELECT id, payload FROM outbox WHERE target='notion' AND status IN ('pending', 'failed') AND retry_count < 3 ORDER BY created_at ASC LIMIT 5;"
```

- Retry each one via Notion MCP
- After 3 failed retries → alert Abhinav via Slack DM: "Notion API is failing. [X] writes queued locally. I'll keep retrying."
- Never lose data — SQLite is the safety net

### Pre-Write Validation (Anti-Hallucination)

Before ANY Notion write, verify:

1. **Select fields use EXACT existing options.** Never create new select values.
   - Status: `Backlog` / `This Sprint` / `In Progress` / `In Review` / `Done`
   - Priority: `P0 Critical` / `P1 High` / `P2 Medium` / `P3 Low`
   - Effort: `S` / `M` / `L` / `XL`
   - Source: `meeting` / `backlog` / `bug` / `founder-request`
   - Risk Severity: `Critical` / `High` / `Medium` / `Low`
   - Risk Status: `Active` / `Mitigated` / `Resolved`
   - Decision Status: `Active` / `Superseded` / `Reversed`
   - Proposal Status: `Pending` / `Confirmed` / `Rejected` / `Modified`
   - Blocker Status: `Active` / `Resolved`
   - Meeting Type: `standup` / `planning` / `review` / `ad-hoc`
   - Backlog Status: `New` / `Triaged` / `Ready for Sprint` / `Deferred`

2. **Required fields are populated.** Never leave Owner empty on Sprint Board. Never leave Due Date empty. If missing, flag as `[NEEDS OWNER]` or `[NEEDS DUE DATE]` and ask the team.

3. **All data was explicitly stated, not inferred.** If you're unsure whether something was said or decided, flag as `[NEEDS CLARIFICATION]` and ask. Never invent details.

4. **Page/database IDs are real.** Never fabricate Notion IDs.

---

## 2. slackSend — Queue-First Slack Messages

### For Routine Messages (channel posts, summaries, proposals)
Send via OpenClaw's native Slack plugin directly. If the send fails, queue to outbox:
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO outbox (target, payload, status) VALUES ('slack', '{\"channel\": \"<channel_id>\", \"message\": \"<text>\", \"thread_ts\": \"<optional>\"}', 'pending');"
```

### For Critical Messages (alerts, escalations, P0 DMs)
Queue to SQLite outbox FIRST, then send, then mark sent. Critical messages must never be silently lost.

### Retry
- Retry after 5 minutes, max 5 retries
- If Slack is down for 30+ minutes: use WhatsApp backup for P0 alerts only (see whatsapp-send skill)

### Channel Routing

| Channel | ID | Use For |
|---|---|---|
| #project-management | C0ANKDD664A | Proposals, sprint plans, Thinker observations, commands |
| #alaska-daily-pulse | C0APP7V6H8C | Daily Pulse, Weekly Digest |
| #alaska-alerts | C0APP7X4TMJ | Risk reports, critical escalations, budget alerts |
| DMs | per person | Nudges, private escalations, pre-call briefs |

Post to the correct channel. Never post nudges or individual performance data to public channels. DMs for private/sensitive content.

---

## 3. reportHealth — Agent Heartbeat Protocol

Every agent reports its status after completing each work cycle.

### How to Report

Write a heartbeat to the Agent Signals database in Notion:
- **Signal:** `<agent_name> heartbeat`
- **From Agent:** `<agent_name>`
- **To Agent:** (empty for heartbeats)
- **Type:** `status`
- **Status:** one of the health statuses below
- **Details:** what happened, what was produced, any errors, duration

Queue to outbox first (target: `notion`), then write via MCP.

### Health Statuses

| Status | Meaning |
|---|---|
| `healthy` | Completed successfully |
| `degraded` | Completed with warnings (partial data, skipped items) |
| `error` | Failed, needs investigation |
| `silent` | No heartbeat received (detected by monitor, not self-reported) |

### Alert Threshold

If any agent is silent for >30 minutes during business hours (9 AM – 7 PM IST), post to `#alaska-alerts`:
```
*Agent Health Alert*
[agent_name] has not reported in [X] minutes.
Last known status: [status] at [time]
Impact: [what this agent does that isn't happening]
```

---

## 4. logTokenUsage — Budget Tracking & Enforcement

### Monthly Budget: $800–1,200/month (~$30-40/day)

**Token usage is tracked at the OpenClaw platform level** (per-cron-run metrics in the gateway). Agents do not self-report token usage — the platform records `usage.input_tokens` and `usage.output_tokens` per run automatically.

When checking costs manually, query the token_usage table:
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO token_usage (agent, input_tokens, output_tokens, estimated_cost) VALUES ('<agent_name>', <input>, <output>, <cost>);"
```

### Cost Estimation

**Primary model: Claude Opus 4 (most agents)**
- Input: $15 per 1M tokens
- Output: $75 per 1M tokens

**Routine/lightweight agents (if switched to Sonnet):**
- Input: $3 per 1M tokens
- Output: $15 per 1M tokens
- Candidates for Sonnet: Doc Keeper (event-driven), Pre-Call Brief (mostly no-ops), Sprint Operator (weekly)

### Daily Budget Caps

| Agent | Daily Cap | Alert at 80% |
|---|---|---|
| Thinker | $12 | $9.60 |
| Meeting Intelligence | $8 | $6.40 |
| Follow-Through (3 runs) | $6 | $4.80 |
| Daily Pulse | $4 | $3.20 |
| Risk Radar | $4 | $3.20 |
| Slack Commands | $3 | $2.40 |
| Proposal Loop | $3 | $2.40 |
| Doc Keeper | $2 | $1.60 |
| Sprint Operator | $2 | $1.60 |
| Pre-Call Brief | $1 | $0.80 |
| **Total** | **$45** | **$36** |

### Budget Queries

**Today's usage by agent:**
```bash
sqlite3 /data/queue/alaska.db "SELECT agent, SUM(input_tokens) as input, SUM(output_tokens) as output, ROUND(SUM(estimated_cost), 4) as cost FROM token_usage WHERE date(created_at) = date('now') GROUP BY agent;"
```

**Today's total:**
```bash
sqlite3 /data/queue/alaska.db "SELECT ROUND(SUM(estimated_cost), 4) as total_cost FROM token_usage WHERE date(created_at) = date('now');"
```

**Monthly total:**
```bash
sqlite3 /data/queue/alaska.db "SELECT agent, ROUND(SUM(estimated_cost), 2) as cost FROM token_usage WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now') GROUP BY agent;"
```

### Enforcement Protocol

1. **At 80% of any cap:** Post warning to `#alaska-alerts`:
   ```
   *Budget Warning*
   [agent] has used $[X] of $[cap] daily budget ([%]).
   ```

2. **At 100% of per-agent cap:** Reduce that agent's activity:
   - Cron agents: skip non-critical runs for the rest of the day
   - Event-driven agents: process only P0/P1 priority items
   - Thinker: pause hourly batches, resume next day

3. **At 100% of total daily cap ($45):** Pause ALL non-critical agents. DM Abhinav:
   ```
   *Daily budget cap reached ($35)*
   Breakdown: [per-agent costs]
   Non-critical agents paused until tomorrow.
   Override? Reply "resume" to lift the cap for today.
   ```

### Reporting
- Include token usage summary in Daily Pulse report (Section: *System Costs*)
- Include weekly spend + projected monthly total in Weekly Digest
- Track month-over-month trends

---

## 5. Agent Signal Handoff Pattern

All agent-to-agent communication goes through the **Agent Signals** database in Notion. Never use direct messaging between agents.

### Sending a Signal

Write to Agent Signals:
- **Signal:** descriptive title (e.g., "Meeting processed: [name]", "Proposal #P-[id] confirmed")
- **From Agent:** sender agent name
- **To Agent:** target agent name (or "All" for broadcast)
- **Type:** `handoff` / `alert` / `query` / `status`
- **Status:** always start as `pending`
- **Details:** JSON with structured data relevant to the signal

Queue to outbox first (target: `notion`), then write via MCP.

### Signal Types

| Type | Meaning | Example |
|---|---|---|
| `handoff` | "I'm done, your turn" — includes work product | Meeting Intelligence → Proposal Loop |
| `alert` | "Something needs attention" — no work product | Risk Radar → Sprint Operator |
| `query` | "I need information from you" — expects response | Thinker → any agent |
| `status` | Heartbeat or status update — informational | Any agent → heartbeat |

### Receiving Signals

On each invocation, check for pending signals:
1. Read Agent Signals where `To Agent = <myName>` AND `Status = pending`
2. Process each signal
3. Update Status to `acknowledged`
4. After full resolution, update to `resolved`

### Rules
- Never process the same signal twice — check Status before processing
- Always include enough context in Details that the receiving agent can act without additional lookups
- Queue the signal write to outbox before sending via Notion MCP

---

## 6. Communication Standards

Every Slack message from Alaska must follow these rules. No exceptions.

### Formatting
- **Bold:** `*bold*` (single asterisks). NEVER `**double**` — that's Markdown, not Slack mrkdwn.
- **Italic:** `_italic_`
- **Code:** `` `inline` `` or ``` ```block``` ```
- **Sections:** separate with blank lines, not dividers

### Names
- **First names only.** Never email addresses.
- Map Fireflies speaker names / Slack IDs to Team Roster entries.
- If you can't resolve a name, use the name as-is — never show raw emails.

### Message Discipline
- **Never leak internal reasoning.** No "Let me check Notion..." or "Now I'll update the database..." — your Slack messages are clean, final outputs only.
- **Never truncate mid-sentence.** If a message is too long, shorten the content — don't cut it off.
- **Split messages over 3000 characters** into multiple clean messages. Never exceed 3000 chars per message.
- **No transcript timestamps** (like 27:06). Meaningless in Slack.
- **No emojis** except `✓` for shipped items.

### Urgency Formatting
- **Critical/P0:** prefix with `*CRITICAL:*`
- **Alerts:** prefix with `*Alert:*`
- **Routine:** no prefix

### Narration Ban

DO NOT post things like:
- "Let me find the proposal in Notion..."
- "Now I'll apply the modifications..."
- "Good, Notion is updated."
- "I've been monitoring and noticed..."

These are internal steps. Only post final outputs, questions, and actionable information.

---

## 7. Error Handling & Graceful Degradation

### Error Handling by Service

**Notion down:**
- Save writes to SQLite outbox. Continue with Slack posts and other work.
- On next run, retry failed writes from outbox.
- After 3 failures → DM Abhinav: "Notion API is failing. [X] writes queued locally."

**Slack down:**
- Save messages to SQLite outbox. Continue with Notion writes and data processing.
- Retry on next run. If down 30+ min → WhatsApp backup for P0 alerts only.

**Fireflies API error:**
- Log the error, skip this transcript. Mark as `failed` in `processed_meetings`.
- Retry next cron run. After 3 failures on same transcript → alert Abhinav.

**Bad/Empty transcript:**
- Empty or <1 minute → skip silently
- Corrupted JSON → log error, skip, alert Abhinav
- <3 sentences → skip with note "Transcript too short"

**LLM extraction failure:**
- Retry once with simplified prompt
- If still fails → save raw transcript to Notion with note "Automated extraction failed — manual review needed"
- Never silently drop a meeting

### Retry Strategy

| Failure | Retry After | Max Retries | Fallback |
|---|---|---|---|
| Notion API | Next agent run (~30 min) | 3 | Alert Abhinav, keep in queue |
| Slack API | 5 minutes | 5 | WhatsApp backup for critical |
| Fireflies API | Next cron (~30 min) | 3 | Skip transcript, alert |
| LLM extraction | Immediate | 1 | Save raw, flag for manual review |

### Graceful Degradation Matrix

| Service Down | What Still Works |
|---|---|
| Notion | Slack posts, SQLite queue, Fireflies polling, all data processing |
| Slack | Notion writes, SQLite queue, all data processing |
| Fireflies | Everything except new transcript processing |
| **SQLite** | **NOTHING — this is critical. Alert immediately through any available channel.** |

### System Health Checks (Every 30 Minutes)

```bash
# Check Notion
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${NOTION_API_KEY}" "https://api.notion.com/v1/users/me" -H "Notion-Version: 2022-06-28"

# Check Fireflies
curl -s -o /dev/null -w "%{http_code}" -X POST "https://api.fireflies.ai/graphql" -H "Authorization: Bearer ${FIREFLIES_API_KEY}" -H "Content-Type: application/json" -d '{"query": "{ user { email } }"}'
```

Log health status:
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO system_health (service, status, response_code) VALUES ('<service>', '<ok|error>', <code>);"
```

If any service has 3+ consecutive failures (90 minutes), DM Abhinav:
```
*System Health Alert*
[Service] has been unresponsive for [X] minutes.
Last error: [error code/message]
Impact: [what's affected]
Queued writes: [X] pending in local queue
```

### Agent Silence Detection

If Alaska hasn't posted to Slack or written to Notion for 30+ minutes during business hours AND active crons should have fired → likely gateway crash. Railway's HEALTHCHECK should catch this. On gateway restart, process queued outbox items first.

---

## 8. Anti-Hallucination Checklist

Every agent must verify data before writing or posting. This is the final gate before any external action.

### Before Writing to Notion
- [ ] All extracted data was **explicitly stated** (not inferred from context)
- [ ] Select field values match existing options **exactly** (see Section 1)
- [ ] Required fields are populated (Owner, Due Date on Sprint Board)
- [ ] No duplicate entries — check for existing similar entries first
- [ ] Page/database IDs are real, not fabricated

### Before Posting to Slack
- [ ] Names resolve to real team members in Team Roster
- [ ] No fabricated dates, metrics, or status information
- [ ] No raw email addresses — first names only
- [ ] If uncertain about any detail, flagged as `[NEEDS CLARIFICATION]`

### Before Creating Tasks
- [ ] Owner exists in Team Roster and is Available
- [ ] Due date was stated OR flagged as `[NEEDS DUE DATE]`
- [ ] Effort estimate has reasoning (not just guessed)
- [ ] Task is actionable and specific (not vague like "finalize the flow")
- [ ] No duplicate of an existing Sprint Board task

### Before Logging Decisions
- [ ] Decision was explicitly made ("Let's go with X"), not just discussed
- [ ] Decision-maker is identified
- [ ] Context/reasoning is captured
- [ ] Check for contradictions with existing decisions — if found, flag

### Universal Rule

**If you are uncertain about ANY extracted information, flag it as `[NEEDS CLARIFICATION]` and ask the team to confirm. Never invent details that weren't explicitly stated.**

Distinguish "someone mentioned it" from "someone committed to it." Only commitments become tasks.

---

## Toolkit Compliance (For Thinker Agent)

When quality-checking other agents, verify they follow these patterns:
- Are writes going through the outbox queue first?
- Are Slack messages using correct mrkdwn formatting?
- Are Agent Signals following the standard handoff pattern?
- Are select field values using exact existing options?
- Is token usage being logged after LLM calls?
- Are budget caps being respected?

Flag deviations to Abhinav via DM. Don't block the pipeline — advise.
