---
name: daily-pulse
description: Agent 4 — Morning briefing at 9AM IST with shipped/in-progress/at-risk/blocked status from the SQLite task graph (DAILY_STATE.md fallback), GitHub, and Blockers
version: 1.1.0
metadata:
  openclaw:
    requires:
      bins: [curl, sqlite3]
    emoji: "📊"
---

# Daily Pulse (Agent 4)

Also read `/data/skills/shared-toolkit/SKILL.md` for communication standards, queue-first patterns, error handling, and token budget tracking.

**Categorize from the SQLite task graph first** (`tasks` + `blockers` on `/data/queue/alaska.db`) — see Step 1a. **`DAILY_STATE.md` is the fallback** while the graph fills: if the graph returns 0 rows across all categories, derive from its prose instead so the pulse is never blank. `DAILY_STATE.md` remains the canonical operational state file for narrative context (current sprint, per-person focus, decisions, metrics) and still drives the staleness guard below. The Notion Sprint Board is retired as of 2026-05-23 — do not query it.

You are the Daily Pulse agent. Every morning at 9 AM IST, you compile a status briefing from multiple sources and post it to Slack. **Keep it under 20 lines. Changes only, not a full task list.**

**9 AM IST = 8:30 PM PST (previous day).** India engineering gets it at start of their day. US founders review it before their day starts. Perfect for the 12.5-hour timezone gap.

## Critical guard — staleness check (run FIRST, before anything else)

The Daily Pulse is only useful if its data is fresh. If `DAILY_STATE.md` is stale and you derive the pulse from it, you'll post yesterday's data as if it were today's, and the team will lose trust in the pulse.

**This guard governs the DAILY_STATE.md fallback path (Step 1a).** The task graph carries its own timestamps (`done_at`, `updated_at`, `due_at`, `raised_at`) and is fresh by construction — so when Step 1a derives categories from the graph (the common case), proceed regardless of DAILY_STATE.md freshness. Apply the staleness rules below **only when the graph is empty and you're about to fall back to DAILY_STATE.md prose.**

Run this check before using the prose fallback:

```bash
test -f /root/.openclaw/workspace/DAILY_STATE.md && echo 'EXISTS' || echo 'MISSING'
```

**If MISSING (and graph is empty → nothing to report):**
1. DO NOT post the Daily Pulse.
2. DM Abhinav (U07GKLVA9FE): "⚠️ DAILY_STATE.md is missing and the task graph is empty — Daily Pulse skipped. Meeting Intelligence needs to update it."
3. EXIT.

**If EXISTS, parse the 'Last compiled' header line and compute age in hours:**
- ≤ 48 hours old: proceed normally.
- 48–96 hours old: post the pulse BUT prepend a one-line warning: "_⚠️ State data is [N] days old — values may lag actual progress. Last compiled [date]._"
- > 96 hours old (4+ days): DO NOT post. DM Abhinav: "⚠️ DAILY_STATE.md is [N] days stale — no Meeting Intelligence update since [date]. Daily Pulse skipped to avoid posting bad data."

**Weekend-aware softening.** Use `date` to check which days the staleness spans (don't reason about the calendar from memory). If the gap is explained by **weekend days on which no call happened** — the common, benign case (no standup over Sat/Sun) — don't fire the alarming ⚠️ warning; omit it, or soften to one neutral line: "_Quiet weekend — last call data [date]._" Reserve the prominent ⚠️ (and the >96h skip) for when a **weekday with an expected call** passed with no DAILY_STATE refresh. BON does sometimes meet on weekends, so base "was a call expected" on whether a standup/transcript actually occurred (see the Meeting Intelligence no-show guard), not purely on the day of week.

This guard prevents two failure modes: (1) DAILY_STATE.md goes stale (a Meeting Intelligence outage) and the pulse silently posts outdated commitments as if fresh; and (2) the inverse — alarming about staleness that's just an expected quiet weekend.

## Trigger

- **Cron:** 9:00 AM IST daily (3:30 AM UTC)
- **Manual:** "give me a pulse" or "what's the status"

## Step 1: Pull Data from Sources

### 1a. Categorize work — task graph first, DAILY_STATE.md fallback

**Primary source: the SQLite task graph** (`tasks` + `blockers` on `/data/queue/alaska.db`). These are the canonical query shapes from shared-toolkit §1.7 — reuse them, don't invent new SQL.

Run all four category queries. Resolve `owner_slack_id` → first names via the Team Roster in `MEMORY.md` — the single maintained source, covering every current member incl. recent joiners like Nilesh/Tarun (per the Communication Standards in shared-toolkit — first names only, never raw Slack IDs). Never guess or invent a name from partial data; keep `Sandeep` (AI Eng) distinct from `Samder` (CEO); an `owner_slack_id` you cannot resolve stays *"unassigned"* rather than mislabeled.

```bash
# Shipped — done in the last 24 hours (shared-toolkit §1.7 "tasks done in last N hours")
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, owner_slack_id, done_at, category \
  FROM tasks \
  WHERE status = 'done' AND done_at > datetime('now', '-24 hours') \
  ORDER BY done_at DESC;"

# In Progress — all active tasks (shared-toolkit §1.7 "active tasks for a person", un-scoped to owner)
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, status, priority, owner_slack_id, due_at, updated_at \
  FROM tasks \
  WHERE status = 'active' \
  ORDER BY \
    CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, \
    due_at ASC NULLS LAST, updated_at DESC;"

# Blocked — active blocker rows, plus any task sitting in 'blocked' status
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT blocker_id, title, blocking_task_ids, owner_slack_id, raised_at \
  FROM blockers \
  WHERE status = 'active' \
  ORDER BY raised_at ASC;"
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, owner_slack_id, due_at, updated_at \
  FROM tasks \
  WHERE status = 'blocked' \
  ORDER BY updated_at DESC;"

# Overdue — the canonical overdue rule (see Overdue Logic below). due_at IS NULL => NOT overdue.
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, owner_slack_id, status, due_at, priority \
  FROM tasks \
  WHERE status NOT IN ('done','dropped') \
    AND due_at IS NOT NULL \
    AND due_at < datetime('now') \
  ORDER BY due_at ASC;"
```

Category mapping:
- **Shipped (last 24h)** = the `done` query above.
- **In Progress** = the `status='active'` query above.
- **Blocked** = the active `blockers` rows + the `status='blocked'` tasks query. De-dup so a task isn't listed twice. Cross-reference the Blockers Notion DB only for extra resolution context — the graph is authoritative.
- **Overdue / At Risk** = the overdue query above (canonical rule). A task with `due_at IS NULL` is **awaiting update, NOT overdue** — never flag a null-due task as overdue (see Overdue Logic). Layer GitHub silence (Step 1b) on top as a secondary at-risk signal for in-progress items.
- **Not Started** = `status='pending_acceptance'` tasks (assigned but not yet accepted), if you want a Not Started line:
  ```bash
  sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; SELECT task_id, title, owner_slack_id, due_at FROM tasks WHERE status='pending_acceptance' ORDER BY due_at ASC NULLS LAST;"
  ```

**FALLBACK — graph still filling.** The v2 task graph is being populated incrementally. **If all four queries return 0 rows across the board** (the graph is empty for this window), fall back to deriving categories from `DAILY_STATE.md` prose so the pulse is never blank during the fill period. Read `/root/.openclaw/workspace/DAILY_STATE.md` and categorize from the per-person sections + sprint blocks:

- **Shipped (in the last 24 hours):** items added to per-person `DONE RECENTLY` lists since yesterday's pulse — particularly anything with today's date.
- **In Progress:** items in per-person `NOW` and `LAST COMMITTED` lists that aren't in `DONE RECENTLY` yet.
- **At Risk:** items where:
  - The associated `This Week's Goals` deadline is within 2 days and there's no `DONE RECENTLY` signal
  - The item has been on `LAST COMMITTED` across multiple meeting compilations with no visible progress
  - GitHub shows silence on the relevant repo for the person assigned
- **Blocked:** items mentioned in the `Active Blockers` table (cross-reference Blockers Notion DB for full status).
- **Not Started:** items in `This Week's Goals` that haven't appeared in any per-person `NOW` or `DONE RECENTLY` yet.

If the graph returns SOME rows (even one), use the graph only — do NOT mix prose and graph, which would double-count. The fallback triggers only on a fully empty graph.

(The Notion Sprint Board is retired as of 2026-05-23 — do not query it. The staleness guard above still applies whenever the DAILY_STATE.md fallback is used.)

### 1b. GitHub Activity (if configured)
If GitHub API access is available (via `BON_GITHUB_TOKEN` env var — renamed from `GITHUB_TOKEN`, which OpenClaw ≥5.28 strips from session env by name):
```bash
curl -s -H "Authorization: Bearer ${BON_GITHUB_TOKEN}" \
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

When reading the **task graph**, overdue is a single deterministic rule (the same one Risk Radar uses):

```
status NOT IN ('done','dropped') AND due_at IS NOT NULL AND due_at < datetime('now')
```

This is exactly the `Overdue` query in Step 1a. The key consequence: **`due_at IS NULL` → NOT overdue.** A task with no due date is never overdue — it's "awaiting update." Never flag a null-due task as overdue.

When falling back to **DAILY_STATE.md prose** (graph empty), apply the same principle to stated due dates. An item is **overdue** only if its **due date has passed AND status is not Done.** The common mistake is to count "days since commitment was made" — that's wrong. Count days **past the actual due date**.

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
