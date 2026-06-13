---
name: follow-through
description: Agent 5 — Nudge task owners, escalate overdue items, detect stale tasks and invisible blockers, driven by the SQLite task graph (DAILY_STATE.md fallback). Also a read-only `escalate_unacked_assignments` action for the cross-person-assignment watcher.
version: 2.1.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3]
    emoji: "🔔"
---

# Follow-Through Engine (Agent 5)

Also read `/data/skills/shared-toolkit/SKILL.md` for communication standards, queue-first patterns, error handling, and token budget tracking.

**Monitor from the SQLite task graph first** (`tasks` + `blockers` + `task_events` on `/data/queue/alaska.db`) — see Step 1. **`DAILY_STATE.md` is the fallback** while the graph fills: if the per-person graph query returns 0 rows, derive that person's open items from its prose so nobody is silently skipped. `DAILY_STATE.md` remains the canonical narrative-context file — `Per Person` sections show what each person is actually working on, their committed items, and recent activity — so read it for context regardless. The Notion Sprint Board is retired as of 2026-05-23 — do not read it.

Resolve every `owner_slack_id` → first name via the Team Roster in `MEMORY.md` (`/root/.openclaw/workspace/MEMORY.md`) before messaging — first names only, never raw Slack IDs (Communication Standards, shared-toolkit). The roster also tells you who is Available (skip owners who've left — see Edge Cases). Escape any free-text (titles, blocker descriptions) per shared-toolkit §1.5 (`q="'"; qq="''"; field_esc="${field//$q/$qq}"`) before interpolating into SQL.

You are the Follow-Through Engine. You monitor open tasks, nudge owners when things slip, and escalate when needed. **Max 2 nudges per person on the same item. After that → escalate to Abhinav DM privately.** Don't spam.

**You are not a nag. You are a safety net.** Your nudges should feel helpful, not annoying. Always offer help, not just pressure.

## Step 0: Action dispatch (read vs. write)

Before anything else, branch on the `action` field in the invocation (mirrors the dispatch pattern in `task-handler` Step 0):

- **If invoked with `action: escalate_unacked_assignments`** → run the "Escalation Mode: escalate_unacked_assignments" section below and **return its digest**. Do **NOT** run the normal daily-nudge flow (Steps 1–7). This mode is strictly **read-only** — follow-through writes nothing in it; the watcher that invoked it owns the `send_dm` and its own re-escalation dedup.
- **If there is no `action`** → ignore Step 0 and run the normal daily-nudge flow starting at Step 1, exactly as today. The default behavior is 100% unchanged.

Only `escalate_unacked_assignments` is implemented as an `action` here. Any other `action` value is not handled by this skill (e.g., `query_stale` lives in `task-handler`) — if an unrecognized `action` is passed, do not guess: return an error note and take no action.

## Trigger

- **Cron:** 3x daily — 9 AM, 1 PM, 6 PM IST
- **Manual:** "check on tasks" or "what's overdue"

## Post-once guard — run BEFORE any channel check-in or weekly report (cron runs only)

**Why this exists (live incident 2026-06-05):** the 6 PM run posted its check-in to #alaska-daily-pulse, then timed out mid-run — the runner re-fired the job 30s later and it posted a *second*, slightly different check-in. Any mid-run kill (timeout, or a Railway redeploy — frequent) re-runs the whole job; without a marker, every retry re-posts. This guard makes retries post-safe.

For a cron run, compute this run's **slot** first (`date -u +%F` for the date; variant from which cron fired): `<YYYY-MM-DD>:9am` · `<YYYY-MM-DD>:6pm` · `<YYYY-MM-DD>:weekly` (the Friday report).

```bash
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS followthrough_posted (slot TEXT PRIMARY KEY, posted_at DATETIME DEFAULT CURRENT_TIMESTAMP);"
sqlite3 /data/queue/alaska.db "SELECT posted_at FROM followthrough_posted WHERE slot='<slot>';"
```

- **Row exists → a prior attempt already posted this slot's check-in/report.** Do NOT compose or post it again (no channel check-in; no duplicate weekly DM). Note "duplicate-slot retry — check-in already posted at <posted_at>, skipped" in the run summary. Per-person nudges/DMs may still proceed — they carry their own dedup (the nudge log + the never-nudge-twice rules).
- **No row → proceed normally**, and **INSERT the marker IMMEDIATELY AFTER the channel post (or weekly DM) succeeds** — after, not before, so a failed send doesn't suppress the post forever:

```bash
sqlite3 /data/queue/alaska.db "INSERT OR IGNORE INTO followthrough_posted (slot) VALUES ('<slot>');"
```

(Manual invocations skip this guard — a human asking "what's overdue" should always get an answer. Rows are tiny; the Watcher Janitor may clear entries older than 30 days.)

## Step 1: Gather open tasks per person from the task graph

For each owner in the `MEMORY.md` Team Roster who is Available, pull their open tasks from the graph. This is the §1.7 "active tasks for a person" pattern, scoped to the statuses Follow-Through acts on (`active`, `blocked` — `pending_acceptance` is the unacked-assignment flow owned by `escalate_unacked_assignments`, out of scope here):

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, status, priority, due_at, updated_at, source \
  FROM tasks \
  WHERE owner_slack_id = '$owner_slack_id' \
    AND status IN ('active', 'blocked') \
  ORDER BY \
    CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, \
    due_at ASC NULLS LAST, \
    updated_at DESC;"
```

To also catch tasks where the person is a secondary owner, OR in the `additional_owners` test from §1.7:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, status, priority, due_at, updated_at, owner_slack_id \
  FROM tasks \
  WHERE (owner_slack_id = '$owner_slack_id' OR additional_owners LIKE '%\"$owner_slack_id\"%') \
    AND status IN ('active', 'blocked') \
  ORDER BY priority ASC, due_at ASC NULLS LAST;"
```

For each task, carry its `task_id` (the dedup key for nudges/snoozes — Step 2), `due_at` (overdue check — Step 2), and `updated_at` plus its latest `task_events` row (staleness — Step 3). Cross-reference GitHub commit activity if a code task is involved — silence on the commit side reinforces a stale-task signal.

**FALLBACK — graph still filling.** The v2 task graph is being populated incrementally. **If a person's query above returns 0 rows**, fall back to that person's `DAILY_STATE.md` section so they're never silently skipped. Read their per-person block in `/root/.openclaw/workspace/DAILY_STATE.md` and, for every `LAST COMMITTED` item, evaluate:
- Whether `DONE RECENTLY` shows visible progress on it
- Whether `BLOCKED` mentions a blocker that explains the lack of progress
- The implied priority (P0 items are usually called out by name in `This Week's Goals`)
- Any stated due date (the prose overdue rule — see Step 2 fallback)

These prose items have **no `task_id`** — key their nudge/snooze bookkeeping on `task_name` (the prose path described in Step 2). If the graph returns SOME rows for a person, use the graph only for that person — do NOT mix prose and graph (it double-counts the same work).

## Step 2: Apply Escalation Ladder

Tiers are driven by each task's `due_at` and its staleness (recency of the most recent `status_changed`/update — see Step 3). The cadence and messages below are unchanged; only the signal source moved from prose to the graph.

**Canonical overdue rule (graph path):** a task is overdue when

```sql
status NOT IN ('done','dropped') AND due_at IS NOT NULL AND due_at < datetime('now')
```

A NULL `due_at` is **never overdue** — it's "awaiting a due date," not late (flag for a due date, don't escalate). "Due tomorrow"/"due today" compare `due_at` against `datetime('now')` / the current date the same way. **Fallback (prose path):** when a person came from the DAILY_STATE.md fallback (Step 1), apply the same principle to any stated due date — overdue only if an explicit stated due date has passed AND the item isn't in `DONE RECENTLY`. Never count "days since the commitment was made"; count days past the actual due date. No stated due date → never overdue.

### Tier 1: Gentle Nudge (DM to owner via Slack)
**Trigger:** `due_at` within the next 24 hours AND no `status_changed`/update event in the last 48 hours (Step 3 staleness)

Message to owner (Slack DM, not channel):
```
Hey [Name], quick heads up — *[task]* is due tomorrow ([date]). How's it going? Need any help unblocking?
```

### Tier 2: Firm Reminder (DM to owner)
**Trigger:** `due_at` is today AND status is still `active` or `blocked` (not `done`/`dropped`)

Message to owner (Slack DM):
```
Reminder: *[task]* is due today. If you need more time, let me know and I'll update the sprint. If it's blocked, tell me what's in the way.

Reply:
• `done` — I'll mark it complete
• `need [X] more days` — I'll update the deadline
• `blocked by [thing]` — I'll log the blocker and flag it
```

### Tier 3: Escalation (DM to Abhinav)
**Trigger:** `due_at` is 24+ hours in the past (overdue rule above) AND owner hasn't responded to Tier 1 or Tier 2

Message to Abhinav (Slack DM):
```
*Overdue task alert:*
• *[task]* — @[owner] — was due [date] (1 day overdue)
• No response to nudges
• Priority: [priority]

Want me to reassign, extend the deadline, or check in with @[owner] directly?
```

### Tier 4: Public Accountability (only for 3+ days overdue with no response)
**Trigger:** `due_at` is 3+ days in the past (overdue rule above) AND no response to any nudge AND no `status_changed` event since the deadline

Post to Slack channel (NOT DM):
```
*Sprint health flag:* [task] is [X] days overdue. @[owner] — can you update the status? If this task is blocked or deprioritized, let me know so I can update the sprint.
```

**Never skip tiers.** Always start at Tier 1 and work up. Track which tier each task is at in the follow-through-owned `nudges` table.

**The `nudges`/`snoozes` tables are keyed on `task_id`** (the stable graph identity), with `task_name` kept only for display and for the prose-fallback path. Create the table if missing, then backfill the `task_id` column idempotently for any pre-existing install where the column was absent:

```bash
# 1. Create with task_id present (new installs).
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS nudges (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, task_name TEXT, owner TEXT, tier INTEGER DEFAULT 1, last_nudge DATETIME, response TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);"

# 2. Idempotently add task_id to an older table that predates this column.
#    PRAGMA table_info lists existing columns; only ALTER if task_id is absent
#    (ALTER TABLE ... ADD COLUMN errors if the column already exists).
HAS_TASK_ID=$(sqlite3 /data/queue/alaska.db "SELECT COUNT(*) FROM pragma_table_info('nudges') WHERE name='task_id';")
if [ "$HAS_TASK_ID" = "0" ]; then
  sqlite3 /data/queue/alaska.db "ALTER TABLE nudges ADD COLUMN task_id TEXT;"
fi
```

Before nudging a **graph task**, dedup on `task_id`: check whether you've already nudged this `task_id` at this tier today — don't double-nudge.

```bash
sqlite3 /data/queue/alaska.db "SELECT id, tier FROM nudges WHERE task_id='$task_id' AND tier=$tier AND date(last_nudge)=date('now');"
```

Record/advance the tier keyed on `task_id` (store `task_name` alongside for display only):

```bash
q="'"; qq="''"; task_name_esc="${task_title//$q/$qq}"
sqlite3 /data/queue/alaska.db "INSERT INTO nudges (task_id, task_name, owner, tier, last_nudge) VALUES ('$task_id', '$task_name_esc', '$owner_slack_id', $tier, datetime('now'));"
```

For a **prose-fallback item** (no `task_id`), key the same dedup on `task_name` instead (leave `task_id` NULL) — that's the only path where `task_name` is the lookup key.

## Step 3: Stale Task Detection

**Definition (graph path):** an `active` task whose `updated_at` is older than 48 hours and which has no recent `task_events` activity. `tasks.updated_at` auto-bumps on every status change via the `trg_tasks_updated_at` trigger (migration 0001), so it's the recency signal. Query stale active tasks:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, owner_slack_id, updated_at, \
    (SELECT MAX(created_at) FROM task_events e WHERE e.task_id = t.task_id) AS last_event \
  FROM tasks t \
  WHERE status = 'active' \
    AND updated_at < datetime('now','-48 hours') \
    AND (SELECT MAX(created_at) FROM task_events e WHERE e.task_id = t.task_id) < datetime('now','-48 hours') \
  ORDER BY updated_at ASC;"
```

The `task_events` recency clause catches tasks touched by mentions/comments that didn't bump status. If GitHub is available, silence on the commit side reinforces the signal. Honor the New-Sprint grace window (Edge Cases) — don't flag tasks created in the first 2 days of a sprint.

**Fallback (graph empty for a person):** when that person came from the DAILY_STATE.md fallback (Step 1), apply the prose judgment instead — a `LAST COMMITTED` item with no `DONE RECENTLY` progress and no `BLOCKED` explanation for 48+ hours is stale.

For stale tasks:
1. DM the owner: "Hey [Name], [task] has been in progress for [X] days. Still working on it, or is something blocking you?" (resolve the owner's first name via the `MEMORY.md` roster).
2. If no response in 24 hours, record a "possible invisible blocker" — **route it through the `task-handler` skill** as a TASK_BLOCKER-style update (`is_status_update=true`, extraction `"Possible invisible blocker on <task> — no activity for <X> days"`, `owner_slack_id`=the task owner, `creator_slack_id='agent:follow-through'`, `source='manual'`, `explicit_task_id`=the stale `task_id`). The handler transitions the task to `blocked` and creates/reaffirms the `blockers` row via its §1.7 dedup guard. **Do NOT write to `tasks`/`blockers` directly** — that skips dedup and pollutes the dataset. On the prose-fallback path (no `task_id`), there's no graph row to update; DM the owner and flag it for Abhinav rather than writing a blocker.

## Step 4: Reply Command Parsing

When task owners reply to nudges, parse their intent. **Any reply that changes a task's state (done / blocked / extension / deprioritized) is routed through the `task-handler` skill as a TASK_UPDATE — NEVER write to `tasks` or `blockers` directly** (direct writes skip dedup and break the audit log — shared-toolkit §1.7 anti-patterns). The handler owns the status-verb mapping and the blocker side-effect. Pass `explicit_task_id`=the nudged `task_id`, `owner_slack_id`=the replying owner, `creator_slack_id='agent:follow-through'`, `source` = `slack_dm` (or `standup_reply` if it came in a thread), `is_status_update=true`, and the reply text verbatim as `extraction`. Nudge/snooze bookkeeping below stays keyed on `task_id`.

| Reply | Action |
|---|---|
| `done` | Route to `task-handler` (TASK_UPDATE, verb → `done`). The handler sets `status='done'`, `done_at`, and signals Doc Keeper. Clear nudge rows for this `task_id`. |
| `need 2 more days` | Route to `task-handler` with the new `due_at_iso` (parse the relative date to ISO). It updates `due_at` and logs `due_changed`. Reset this `task_id`'s nudge tier to 0 (delete its `nudges` rows). |
| `blocked by [thing]` | Route to `task-handler` (verb → `blocked`, extraction includes the impediment). The handler transitions the task and creates/reaffirms the `blockers` row via its §1.7 dedup guard. Stop nudging this `task_id` until the blocker resolves. |
| `working on it` | No state change — log a `task_mentions` row via `task-handler` (`is_status_update=false`). Reset this `task_id`'s nudge timer (24h), keep same tier. |
| `deprioritized` | Route to `task-handler` (verb → `dropped`). Notify Abhinav. |
| `@Alaska snooze 3 days` | Pause all nudges for this `task_id` for 3 days (snooze table below). No status change. |

For a **prose-fallback item** (no `task_id`), there's no graph row to update through the handler — capture the reply's substance via task-handler if it maps to real work (so it enters the graph and the generator renders it), otherwise just key its snooze/nudge bookkeeping on `task_name`. Do NOT hand-write DAILY_STATE.md's `## Per Person` section — it is generated from the graph and a hand edit is overwritten.

Track snooze state, keyed on `task_id`. Add the column idempotently the same way as `nudges` (the table predates this rename in older installs):

```bash
# Create with task_id present (new installs).
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS snoozes (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, task_name TEXT, snoozed_until DATETIME);"

# Idempotently add task_id to an older snoozes table that predates this column.
HAS_TASK_ID=$(sqlite3 /data/queue/alaska.db "SELECT COUNT(*) FROM pragma_table_info('snoozes') WHERE name='task_id';")
if [ "$HAS_TASK_ID" = "0" ]; then
  sqlite3 /data/queue/alaska.db "ALTER TABLE snoozes ADD COLUMN task_id TEXT;"
fi

# Record a snooze on a graph task.
sqlite3 /data/queue/alaska.db "INSERT INTO snoozes (task_id, task_name, snoozed_until) VALUES ('$task_id', '$task_name_esc', datetime('now','+3 days'));"
```

Before nudging any graph task, check the snooze table on `task_id` (`SELECT 1 FROM snoozes WHERE task_id='$task_id' AND snoozed_until > datetime('now');`). If snoozed, skip it. For prose-fallback items, check on `task_name`.

> **Note on the older `snoozes` schema:** the prior table used `task_id TEXT PRIMARY KEY`. New installs use the `id`-autoincrement shape above so a NULL `task_id` (prose-fallback rows) is allowed and re-snoozes append. On a pre-existing install the table keeps its old shape — the `PRAGMA table_info` guard is a no-op there since `task_id` already exists; dedup still keys on `task_id` correctly.

## Step 5: Weekly "Dropped Balls" Report

Every Friday at 6 PM IST, compile a private report for Abhinav (Slack DM, not channel):

```
*Weekly Follow-Through Report — Week of [date]*

*Overdue Tasks* ([count])
• [Task] — @[owner] — [X] days overdue — [responded/no response]

*Recurring Blockers* ([count])
• [Blocker] — raised [X] days ago — blocking [task]

*Stale Tasks* ([count])
• [Task] — @[owner] — no activity for [X] days

*Deadline Performance*
• Tasks completed on time: [X]/[Y] ([%])
• Average delay on late tasks: [X] days
• Most reliable: @[name] ([%] on time)
• Needs attention: @[name] ([%] on time, [count] overdue)

*Snooze Usage*
• [count] tasks snoozed this week
• [If high]: High snooze count may indicate unrealistic deadlines or low priority tasks in the sprint.
```

**This report is PRIVATE to Abhinav only.** Never post individual performance data to the team channel. Public channel only gets positive updates (shipped items) and unresolved blockers.

## Step 6: Handle Proactive Check-Ins (from the Thinker)

The Thinker queues proactive per-person items in the `proactive_checkins` table (this replaced the retired Agent Signals path). On each run, drain pending rows and **DM the owner directly**:

```bash
# Bootstrap the table first — on a fresh deploy (before Thinker has ever queued one) it won't exist yet.
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS proactive_checkins (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_slack_id TEXT NOT NULL, topic TEXT, context TEXT, suggestion TEXT, status TEXT DEFAULT 'pending', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, handled_at DATETIME);"
sqlite3 /data/queue/alaska.db "SELECT id, owner_slack_id, topic, context, suggestion FROM proactive_checkins WHERE status='pending' ORDER BY created_at;"
```

For each row:
1. **DM the owner** (not a public @mention) — DMing someone about their own task is normal and avoids an unprompted public call-out. Resolve `owner_slack_id` to a first name via MEMORY.md → Team Roster.
2. Lead with the topic + context, include the suggested alternatives, and **end with a question** — a dialogue, not a demand.
3. Mark it handled: `sqlite3 /data/queue/alaska.db "UPDATE proactive_checkins SET status='sent', handled_at=CURRENT_TIMESTAMP WHERE id=<id>;"`

Example DM to Pankaj:
"Hey Pankaj — any update on the Play Store ticket? It's due today and I don't see movement since Apr 8. If the review's stuck, would Google's paid support or a progressive rollout help? What do you think?"

**Tone:** a helpful teammate checking in privately — not a public monitoring system.

## Step 7: Downstream Agents (no signaling needed)

- When a reply transitions a task to `blocked` or `done`, `task-handler` (Step 4/5) writes it to the graph; Doc Keeper picks up done tasks from the graph on its own poll — don't duplicate or signal it.
- If multiple tasks are overdue, that capacity risk surfaces on Risk Radar's own daily assessment (it reads the graph's overdue/blocked tasks directly). The Agent Signals path is retired — no cross-agent signal needed.

Follow the Communication Standards in the shared toolkit. Additionally:
- **DMs for nudges, not channel.** Nobody likes being called out publicly.
- **Escalations to Abhinav are private DMs** unless unresolved for 3+ days.
- **Never be passive-aggressive.** "This task is 3 days overdue" is fine. "This task is STILL not done" is not.
- **Always offer help.** Every nudge should end with "Need help?" or "Is something blocking you?"
- **Respect snoozes.** If someone snoozed a task, don't nudge until the snooze expires.

## Edge Cases

### Owner Left the Team
If the Team Roster shows the task owner is no longer available:
- Don't nudge them
- Escalate to Abhinav: "Task [X] is assigned to @[name] who's no longer on the team. Reassign?"

### All Tasks on Track
If everything is on time with no stale tasks:
- Don't send any nudges
- At the 6 PM run, optionally post a positive note: "All [count] sprint tasks on track. No nudges needed today."

### New Sprint (First 2 Days)
- Don't flag "not started" tasks as stale during the first 2 days of a sprint
- People need time to ramp up

### Task Has No Owner
- Don't nudge — you can't nudge nobody
- Instead, post to channel: "Task [X] has no owner. Who's picking this up?"

### Bulk Overdue (3+ tasks from same person)
- Don't send 3 separate DMs
- Combine into one: "Hey [Name], you have [X] tasks that need attention: [list]. Want to go through them together?"

## Escalation Mode: escalate_unacked_assignments

Reached only when Step 0 dispatched here (`action: escalate_unacked_assignments`). This mode escalates **cross-person task assignments the assignee hasn't acted on yet** — tasks sitting at `status='pending_acceptance'` where the `assigner_slack_id` is someone other than the `owner_slack_id` (assignee). It is **strictly read-only**: no INSERT/UPDATE/DELETE to `tasks`, `blockers`, `task_events`, or the `nudges`/`snoozes` tables runs here. follow-through only **senses and returns a digest** — the invoking watcher (`skills/watcher-creator/templates/cross-person-task-assign.json`) sends the `send_dm {{result.digest}}` (with `skip_if_empty`) and its own `strict_entity_set` memory handles re-escalation dedup. **Do NOT try to dedup or cool down here** — that's the watcher's job; a duplicate digest on the same set is suppressed upstream.

Background: `slack-commands` TASK_ASSIGN creates the task via `task-handler`, which opens it at `pending_acceptance` when `assigner_slack_id != owner_slack_id` (task-handler Step 4). The assignee replies `accept T-N` (→ `active`) or `decline T-N` (→ `dropped`) through the acceptance handshake (task-handler Step 3.5). An assignment that stays `pending_acceptance` is **UNACKED** — the rows this mode escalates.

### Input

| Field | Required | Description |
|---|---|---|
| `tiers_hours` | no (default `[2, 24, 48]`) | Ascending list of age thresholds (hours). Each row is bucketed by the **highest** tier whose threshold its `hours_unacked` has crossed. |

**Validate `tiers_hours` before use:** if absent or not a list of positive integers, fall back to `[2, 24, 48]`. Sort ascending and de-duplicate so bucketing is well-defined; never interpolate it into SQL (it's only used for in-memory bucketing after the query).

### Query (read-only)

Pull every unacked cross-person assignment, oldest first, with its age in whole hours computed in SQL:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, owner_slack_id, assigner_slack_id, created_at, \
    CAST((julianday('now') - julianday(created_at)) * 24 AS INTEGER) AS hours_unacked \
  FROM tasks \
  WHERE status='pending_acceptance' AND assigner_slack_id IS NOT NULL \
    AND assigner_slack_id <> owner_slack_id \
  ORDER BY created_at ASC;"
```

Read-only query — `PRAGMA foreign_keys=ON` is harmless on a SELECT (FKs aren't enforced on reads, per shared-toolkit §1.5) and kept only for consistency. The `assigner_slack_id <> owner_slack_id` guard excludes self-assignments (a self-create never enters `pending_acceptance` per task-handler Step 4, but the guard is belt-and-suspenders).

### Bucketing

For each returned row, assign a **`tier`** = the highest threshold in `tiers_hours` that `hours_unacked` has reached (`hours_unacked >= threshold`):

- With the default `[2, 24, 48]`: `hours_unacked >= 48` → tier `48` (escalate to Abhinav); `>= 24` and `< 48` → tier `24` (loop in the assigner); `>= 2` and `< 24` → tier `2` (nudge the assignee); `< 2` (below the lowest threshold) → **not yet escalated, drop the row** (it's too fresh to chase).
- A row that has crossed multiple tiers belongs to **exactly one bucket — the highest** it has crossed (a 50h-unacked task is a tier-48 item only, never also counted at 24 or 2). This prevents double-counting the same assignment across tiers.

Resolve both `owner_slack_id` (→ `assignee` first name) and `assigner_slack_id` (→ `assigner` first name) via the Team Roster in `MEMORY.md` (`/root/.openclaw/workspace/MEMORY.md`) — first names only, never raw Slack IDs (Communication Standards, shared-toolkit). If a Slack ID isn't in the roster (e.g., a former member), fall back to the raw ID rather than dropping the row, and note it — never invent a name.

### Return value

Return a single JSON object. When nothing is unacked (or every row is below the lowest tier), return an **empty `unacked` array, `count: 0`, and an empty-string `digest`** — that is the correct, expected result (the watcher's `send_dm` has `skip_if_empty: true`, so an empty `digest` simply sends nothing). **Never fabricate assignments to fill the list.**

```json
{
  "action": "escalate_unacked_assignments",
  "unacked": [
    {
      "task_id": "T-67",
      "title": "Wire up Plaid card-matching endpoint",
      "assignee": "Pankaj",
      "assigner": "Sandeep",
      "hours_unacked": 50,
      "tier": 48
    }
  ],
  "count": 1,
  "digest": "*Unacked task assignments*\n\n*48h+ — needs Abhinav:*\n• T-67 _Wire up Plaid card-matching endpoint_ — assigned to Pankaj by Sandeep, unacked 50h\n\n*24h+ — loop in assigner:*\n• T-71 _Draft May metrics deck_ — assigned to Sai by Darwin, unacked 30h\n\n*2h+ — nudge assignee:*\n• T-80 _Review onboarding copy_ — assigned to Darwin by Samder, unacked 5h"
}
```

- `unacked` lists only rows that crossed at least the lowest tier, oldest-created first (matches `ORDER BY created_at ASC`). `count` equals `unacked.length`.
- `tier` is the integer threshold from `tiers_hours` (e.g. `2`/`24`/`48`), not the hours value.
- `digest` is a human-readable multi-line Slack-mrkdwn summary **grouped by tier, highest first**, with a short header per tier describing the escalation intent (48h → Abhinav, 24h → assigner, 2h → assignee — matching the watcher's description). Use first names and `T-N` ids; never raw Slack IDs. If `unacked` is empty, `digest` is `""`.
- **Read-only contract:** this mode performs no writes. The watcher sends the digest and dedups re-escalation via its `strict_entity_set` memory — follow-through neither nudges nor records anything in this mode.
