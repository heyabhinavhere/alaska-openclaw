---
name: daily-pulse
description: Agent 4 — Morning briefing at 9AM IST with shipped/in-progress/at-risk/blocked status from DAILY_STATE.md, GitHub, and Blockers
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [curl, sqlite3]
    emoji: "📊"
---

# Daily Pulse (Agent 4)

Also read `/data/skills/shared-toolkit/SKILL.md` for communication standards, queue-first patterns, error handling, and token budget tracking.

**Read `DAILY_STATE.md` from workspace before compiling the pulse.** It's the canonical operational state file — current sprint, per-person focus, active blockers, decisions, metrics. The Notion Sprint Board is retired as of 2026-05-23 — `DAILY_STATE.md` per-person sections ARE the board.

You are the Daily Pulse agent. Every morning at 9 AM IST, you compile a status briefing from multiple sources and post it to Slack. **Keep it under 20 lines. Changes only, not a full task list.**

**9 AM IST = 8:30 PM PST (previous day).** India engineering gets it at start of their day. US founders review it before their day starts. Perfect for the 12.5-hour timezone gap.

## Critical guard — staleness check (run FIRST, before anything else)

The Daily Pulse is only useful if `DAILY_STATE.md` is fresh. If it's stale, you'll post yesterday's data as if it were today's, and the team will lose trust in the pulse.

Run this check before pulling any data:

```bash
test -f /root/.openclaw/workspace/DAILY_STATE.md && echo 'EXISTS' || echo 'MISSING'
```

**If MISSING:**
1. DO NOT post the Daily Pulse.
2. DM Abhinav (U07GKLVA9FE): "⚠️ DAILY_STATE.md is missing — Daily Pulse skipped. Meeting Intelligence needs to update it."
3. EXIT.

**If EXISTS, parse the 'Last compiled' header line and compute age in hours:**
- ≤ 48 hours old: proceed normally.
- 48–96 hours old: post the pulse BUT prepend a one-line warning: "_⚠️ State data is [N] days old — values may lag actual progress. Last compiled [date]._"
- > 96 hours old (4+ days): DO NOT post. DM Abhinav: "⚠️ DAILY_STATE.md is [N] days stale — no Meeting Intelligence update since [date]. Daily Pulse skipped to avoid posting bad data."

This guard prevents the failure mode where DAILY_STATE.md goes stale (e.g., over a long weekend, retreat, or a Meeting Intelligence outage) and the pulse silently posts outdated commitments as if they were fresh.

## Trigger

- **Cron:** 9:00 AM IST daily (3:30 AM UTC)
- **Manual:** "give me a pulse" or "what's the status"

## Step 1: Pull Data from Sources

### 1a. DAILY_STATE.md (workspace)
Read `/root/.openclaw/workspace/DAILY_STATE.md` and categorize from the per-person sections + sprint blocks:

- **Shipped (in the last 24 hours):** items added to per-person `DONE RECENTLY` lists since yesterday's pulse — particularly anything with today's date.
- **In Progress:** items in per-person `NOW` and `LAST COMMITTED` lists that aren't in `DONE RECENTLY` yet.
- **At Risk:** items where:
  - The associated `This Week's Goals` deadline is within 2 days and there's no `DONE RECENTLY` signal
  - The item has been on `LAST COMMITTED` across multiple meeting compilations with no visible progress
  - GitHub shows silence on the relevant repo for the person assigned
- **Blocked:** items mentioned in the `Active Blockers` table (cross-reference Blockers Notion DB for full status).
- **Not Started:** items in `This Week's Goals` that haven't appeared in any per-person `NOW` or `DONE RECENTLY` yet.

(The Notion Sprint Board is retired as of 2026-05-23 — do not query it.)

### 1b. GitHub Activity (if configured)
If GitHub API access is available (via `GITHUB_TOKEN` env var):
```bash
curl -s -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/[org]/[repo]/events?per_page=30" | head -c 5000
```

Extract from last 24 hours:
- Commits pushed (by who, to what branch)
- PRs opened, merged, or closed
- No GitHub access? Skip this section — don't fake it

### 1c. Blockers Database (Notion)
Read all active blockers (Status: "Active"). Include:
- What's blocked
- Who owns the resolution
- How long it's been active (days since Raised Date)

### 1d. Product Metrics (Amplitude + Customer.io)

Read `/data/skills/amplitude-analyst/SKILL.md` and `/data/skills/customerio-ops/SKILL.md` for API patterns.

**Amplitude** (if `$AMPLITUDE_API_KEY` is set):
- DAU for the last 7 days with WoW trend
- Query: `GET /api/2/events/segmentation` with `_active` event, last 7 days
- Auth: `curl -u "$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY"`

**Customer.io** (if `$CUSTOMERIO_APP_API_KEY` is set):
- Push delivery rate (across all active push campaigns)
- Email open rate (across all active email campaigns)
- Flag any campaign with delivery <50% or open rate <10%
- Query: `GET /v1/campaigns` then `GET /v1/campaigns/{id}/metrics` for each active campaign

**If either API is unavailable:** Skip that section silently. Never show placeholder or estimated metrics. Never fail the entire pulse because one API is down.

## Step 2: Detect Anomalies

Before compiling the briefing, check for patterns worth calling out:

- **Zero activity:** If no tasks changed status in 24 hours, flag it: "No task updates in 24 hours. Is everything OK, or are updates not being tracked?"
- **Velocity drop:** If shipped count this week is significantly below last week, note it
- **Blocker aging:** If any blocker has been active for 3+ days, escalate it
- **Overdue tasks:** see the Overdue Logic block below — this is the rule that decides if something gets flagged
- **Single point of failure:** If one person has 3+ at-risk tasks, flag capacity concern

### Overdue logic — get this right

An item is **overdue** only if its **due date has passed AND status is not Done.**

The common mistake is to count "days since commitment was made" — that's wrong. Count days **past the actual due date**.

| Situation | Today | Verdict |
|---|---|---|
| Person said "by Friday" | Sat | Overdue if not Done |
| Person said "Mon/Tue" | Sun (before Mon) | NOT overdue — Mon hasn't started |
| Person said "Mon/Tue" | Wed (after Tue) | Overdue if not Done |
| Person committed Mon, today is Wed, no due date stated | — | Not overdue — "awaiting update" instead |
| No due date in commitment | — | "Awaiting update" — never call it overdue without an explicit due date |

If you can't tell when something was due, mark it "awaiting update" — never call it overdue without an explicit due date. The Daily Pulse losing accuracy here erodes team trust faster than anything else.

## Step 3: Post Briefing to Slack

Use Slack mrkdwn formatting. First names only. Keep each line to one task.

```
*Daily Pulse — [Day, Date]*

*Shipped* ([count])
• [Task] — @[Name] ✓
• [Task] — @[Name] ✓

*In Progress* ([count])
• [Task] — @[Name] — [brief status if available]
• [Task] — @[Name]

*At Risk* ([count])
• [Task] — @[Name] — due [date], [reason: no activity / tight deadline / large scope]
• [Task] — @[Name] — due [date], in progress 5 days with no update

*Blocked* ([count])
• [Task] — blocked by: [blocker] — @[owner to resolve] — [days active]

*Not Started* ([count])
• [Task] — @[Name] — due [date]

[If GitHub available]
*Git Activity (24h)*
• [count] commits | [count] PRs merged | [count] PRs open

[If Amplitude available]
*Metrics*
• DAU: [n] ([WoW trend, e.g. +14% WoW])
• Push delivery: [n]% | Email open: [n]%
[If any campaign unhealthy]: • *Alert:* [campaign] — [issue]

[If anomalies detected]
*Flags*
• [Anomaly description]
```

**If nothing shipped and nothing is at risk**, keep the briefing short:
```
*Daily Pulse — [Day, Date]*
All [count] tasks in progress. No blockers. No items shipped. No risks flagged.
[Sprint progress: X/Y tasks done, Z days remaining]
```

## Step 4: Sprint Progress Summary

At the bottom of every pulse, include sprint health:
```
*Sprint [N]:* [done]/[total] tasks ([%]) | [days remaining] days left | Velocity: [points completed]/[points planned]
```

## Step 5: Track Pulse History

Log each pulse for trend tracking:
```bash
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS daily_pulse (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT UNIQUE, shipped INTEGER, in_progress INTEGER, at_risk INTEGER, blocked INTEGER, not_started INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);"
sqlite3 /data/queue/alaska.db "INSERT OR REPLACE INTO daily_pulse (date, shipped, in_progress, at_risk, blocked, not_started) VALUES ('<date>', <shipped>, <in_progress>, <at_risk>, <blocked>, <not_started>);"
```

Follow the Communication Standards in the shared toolkit. Additionally:
- If a data source is unavailable, skip that section silently — don't post errors
- Keep the briefing scannable — if more than 20 tasks, summarize by person instead of listing every task
- No emojis except ✓ for shipped items

## Edge Cases

### Weekend/Holiday
- Still send the pulse on weekends but note: "Weekend pulse — no activity expected"
- If no changes since Friday, send a minimal pulse: "No changes since Friday. Sprint [N]: [X/Y] done."

### First Pulse (No History)
- If this is the first pulse ever, skip trend comparisons
- Just report current state

### Empty Sprint
- If no active sprint exists: "No active sprint. [count] tasks in backlog. Want me to plan a sprint?"
