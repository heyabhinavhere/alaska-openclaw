---
name: slack-commands
description: Handle team queries in Slack — status checks, blocker reports, shipped items, sprint info, cross-person task assignment + accept/decline handshake, and ad-hoc questions
version: 1.2.0
metadata:
  openclaw:
    always: true
    emoji: "💬"
---

# Slack Commands

When team members message Alaska in Slack (DM or channel mention), respond intelligently by pulling live data from Notion and SQLite.

**You are always-on for these.** No cron needed — respond when asked.

## Command: Status Check

**Triggers:** "status of [feature]", "where are we on [task]", "update on [thing]", "what's [person] working on", "what's [person] on", "what's blocked", "who's blocked", "what's overdue"

**Source of truth: the SQLite task graph (`tasks` / `blockers`), with DAILY_STATE.md prose as fallback.** Query the graph FIRST; fall back to the markdown read only when the graph returns 0 rows. Don't narrate which source you used.

Resolve people via the MEMORY.md Team Roster — never guess an owner. If you build any SQL fragment from free message text (e.g., a feature-title search), escape apostrophes per shared-toolkit §1.5 (`q="'"; qq="''"; text_esc="${text//$q/$qq}"`).

### A. "what's [person] working on" / "what's [person] on"

1. Resolve the person's NAME → `owner_slack_id` via the MEMORY.md Team Roster (first-name match, case-insensitive). If the name isn't in the roster, say so and stop — don't guess.
2. Pull their active work — shared-toolkit §1.7 "active tasks for a person" (reuse the exact shape):
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, status, priority, due_at, updated_at, source \
  FROM tasks \
  WHERE owner_slack_id = '$person_slack_id' \
    AND status IN ('active', 'blocked', 'pending_acceptance') \
  ORDER BY \
    CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, \
    due_at ASC NULLS LAST, \
    updated_at DESC;"
```
   Optionally add what they recently finished (§1.7 "tasks done in last N hours", widened to 48h):
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, done_at \
  FROM tasks \
  WHERE owner_slack_id = '$person_slack_id' \
    AND status = 'done' AND done_at > datetime('now', '-48 hours') \
  ORDER BY done_at DESC;"
```
3. **If ≥1 active row**, format a short list (first name resolved from the roster):
```
*[First name] is on:*
• T-N: [title] — [status][ · due [date] if due_at not null]
• T-N: [title] — [status]
[If any recent done]: Shipped recently: T-N [title]✓
```
4. **FALLBACK — 0 active rows:** read that person's `Per Person` section in `DAILY_STATE.md` (`NOW`, `LAST COMMITTED`, `BLOCKED`) and answer from the prose.

### B. "what's blocked" / "who's blocked"

(This is the canonical blocker answer — the "Blocker Report" section below now defers here.)

1. Active blocker rows:
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT blocker_id, title, blocking_task_ids, owner_slack_id, raised_at \
  FROM blockers \
  WHERE status = 'active' \
  ORDER BY raised_at ASC;"
```
2. For each blocker, `blocking_task_ids` is a JSON array of `T-N` (e.g., `["T-42","T-43"]`, or `[]`/NULL for a standalone blocker). Resolve those IDs to titles so the answer names the blocked work:
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, owner_slack_id FROM tasks WHERE task_id IN ('T-42','T-43');"
```
   Parse the JSON defensively — `[]`, NULL, or malformed → just render the blocker with no linked task (don't error).
3. Also surface tasks sitting in `status='blocked'` that no active blocker row references yet (belt-and-suspenders, since the graph is still filling):
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, owner_slack_id, updated_at \
  FROM tasks \
  WHERE status = 'blocked' \
  ORDER BY updated_at DESC;"
```
4. **If ≥1 active blocker or blocked task**, render (resolve owner Slack IDs → first names via roster; raised "X days ago" from `raised_at`):
```
*Active blockers* ([count])
• B-N: [title] — blocking [first name]'s T-N [task title] — raised [X]d ago
• [blocked task with no blocker row]: T-N [title] — [first name] — blocked
```
5. **FALLBACK — 0 active blockers AND 0 blocked tasks:** scan `DAILY_STATE.md` per-person `BLOCKED:` lines; list those. If those are all "None", reply: `No active blockers right now.`

### C. "what's overdue"

1. Tasks past their due date (a NULL `due_at` means NO due date → NOT overdue; never call a null-due task overdue):
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, owner_slack_id, due_at, status \
  FROM tasks \
  WHERE status NOT IN ('done', 'dropped') \
    AND due_at IS NOT NULL \
    AND due_at < datetime('now') \
  ORDER BY due_at ASC;"
```
2. **If ≥1 row**, render (owner → first name via roster; overdue-by from `due_at` vs now):
```
*Overdue* ([count])
• T-N: [title] — [first name] — due [date], overdue by [X]d — [status]
```
3. **FALLBACK — 0 rows:** there's nothing past-due in the graph. Reply: `Nothing's overdue right now.` (Do NOT fall back to DAILY_STATE prose for overdue — the markdown has no reliable structured due dates, so a graph 0-count is authoritative here. Snoozed/blocked tasks still count as overdue if their `due_at` has passed — they're filtered only by the done/dropped exclusion above.)

### D. "status of [feature]" / "where are we on [thing]" / "update on [thing]"

A free-text feature/topic lookup (not a person or a blocked/overdue query).
1. Try the graph first — title match on the escaped query text (§1.5 escaping):
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, status, owner_slack_id, priority, due_at \
  FROM tasks \
  WHERE title LIKE '%$query_esc%' AND status NOT IN ('dropped') \
  ORDER BY updated_at DESC LIMIT 10;"
```
2. **If ≥1 match**, render each (owner → first name; flag overdue only if `due_at` not null AND past):
```
*[title]*
Status: [status] | Owner: [first name][ | Priority: [priority] if set]
[ | Due: [date] if due_at not null][; ⚠ overdue by [X]d if due_at < now]
[If blocked]: Blocked — see "what's blocked"
```
   Multiple matches → list each with brief status.
3. **FALLBACK — 0 matches:** search `DAILY_STATE.md` per-person sections + recent Meeting Notes by name similarity (the Notion Sprint Board is retired as of 2026-05-23). If still nothing: "I don't see a task matching '[query]' in the task graph or current focus. Want me to search meeting notes?"

## Command: Blocker Report

**Triggers:** "who's blocked?", "what's blocked?", "active blockers", "blockers"

Use the canonical blocker procedure in **Status Check §B** above — it queries the `blockers` table (`status='active'`) plus `tasks` with `status='blocked'`, resolves `blocking_task_ids` JSON to task titles, and falls back to DAILY_STATE.md `BLOCKED:` lines only when the graph is empty. Do not maintain a second divergent procedure here. If no active blockers and no blocked tasks: "No active blockers right now."

## Command: Shipped Report

**Triggers:** "what shipped this week?", "what did we ship?", "changelog", "what's done?"

**Response:**
1. Read Changelog for entries in the last 7 days
2. Return:
```
*Shipped This Week* ([count])
• [What shipped] — @[name] — [date]
```
3. If nothing shipped: "Nothing marked as shipped this week. [X] tasks are in progress."

## Command: Sprint Status

**Triggers:** "sprint status", "how's the sprint?", "sprint health", "sprint progress"

**Response:**
1. Read `DAILY_STATE.md` — `Current Sprint` section + `Per Person` sections.
2. Calculate:
   - Tasks by status (Done / In Progress / In Review / Not started yet / Backlog)
   - Effort points completed vs planned
   - Days remaining
   - Per-person load
3. Return:
```
*Sprint [N] — [X] days remaining*
Done: [count] ([points] pts) | In Progress: [count] | Blocked: [count] | Not Started: [count]
Completion: [%] of tasks, [%] of effort points
[If behind pace]: At current velocity, we'll complete ~[X]% by sprint end.

*Per Person:*
• @[Name]: [done]/[total] tasks — [status: on track / behind / blocked]
```

## Command: My Tasks

**Triggers:** "my tasks", "what's on my plate", "what should I work on"

**Source of truth: the SQLite task graph (`tasks` / `blockers`), with DAILY_STATE.md prose as fallback.** Query the graph FIRST; only fall back to the markdown read if the graph returns 0 rows (so answers never go blank while the graph is still filling). Don't narrate which source you used.

**Response:**
1. Identify who's asking (the asker's own Slack ID — already known from the inbound DM/mention event; no name parsing needed).
2. Pull their active tasks from the graph — the shared-toolkit §1.7 "active tasks for a person" query (reuse the exact shape), keyed on the asker's Slack ID:
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, status, priority, due_at, updated_at, source \
  FROM tasks \
  WHERE owner_slack_id = '$asker_slack_id' \
    AND status IN ('active', 'blocked', 'pending_acceptance') \
  ORDER BY \
    CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, \
    due_at ASC NULLS LAST, \
    updated_at DESC;"
```
   Optionally also pull what they just finished (§1.7 "tasks done in last N hours", widened to 48h) to show momentum:
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, done_at \
  FROM tasks \
  WHERE owner_slack_id = '$asker_slack_id' \
    AND status = 'done' AND done_at > datetime('now', '-48 hours') \
  ORDER BY done_at DESC;"
```
3. **If the active query returned ≥1 row**, format a short list (one line per task), prioritized as the query already ordered them:
```
*Your tasks*
• T-N: [title] — [status][ · due [date] if due_at not null][ · [priority] if set]
• T-N: [title] — [status]

[If any recent done]: Recently shipped: T-N [title]✓
Suggested focus: [first task in the list — highest priority / nearest deadline]
```
   - `due_at IS NULL` → show no due date for that line (never invent one).
4. **FALLBACK — if the active query returned 0 rows:** read the asker's section in `DAILY_STATE.md` (`Per Person` → their `NOW`, `LAST COMMITTED`, `BLOCKED`) and answer from that prose, prioritized by recency:
```
*Your tasks*
1. [item from NOW / LAST COMMITTED] — [status]
2. ...

Suggested focus: [highest priority or nearest deadline item]
```
   - If the asker can't be resolved to a roster Slack ID at all, apply the SOUL.md self-heal / unknown-DM reply (see Anti-patterns #3 above) instead of guessing.

## Command: Decisions

**Triggers:** "what did we decide about [topic]?", "decisions from [meeting]", "decision log"

**Response:**
1. Search Decision Log by topic or meeting
2. Return:
```
*Decisions about [topic]:*
• [Decision] — by [who] — [date]
  Context: [why]
  Status: [active/superseded]
```

## Command: Help

**Triggers:** "help", "what can you do?", "commands"

**Response:**
```
Here's what you can ask me:

• *status of [feature]* — current task status
• *who's blocked?* — active blockers
• *what shipped this week?* — recent changelog
• *sprint status* — sprint health and progress
• *my tasks* — your current assignments
• *what did we decide about [topic]?* — decision history
• *plan next sprint* — trigger sprint planning
• *process latest meeting* — run Meeting Intelligence on newest transcript

Or just ask me anything about the project — I'll pull from Notion, Fireflies, and sprint data to answer.
```

## Analytics & Campaign Queries

**Metric questions** — read `/data/skills/amplitude-analyst/SKILL.md` and query Amplitude:
- "what's DAU?" / "show me retention" / "conversion funnel" / "who are our power users?"
- "compare this week vs last week" / "what happened to DAU on [date]?"
- "distribution of credit scores" / "user property breakdown"

**Campaign questions** — read `/data/skills/customerio-ops/SKILL.md` and query Customer.io:
- "list active campaigns" / "what's push delivery rate?" / "campaign metrics for [name]"
- "pause [campaign]" / "resume [campaign]"
- "create a push campaign for [segment]" → drafts for Abhinav approval
- "what messages did user [X] receive?"

**User lookup** — queries BOTH Amplitude + Customer.io:
- "tell me about user [X]" → Amplitude events + CIO messages + Notion context in one answer
- Uses the same user_id across both systems

**Cross-system questions:**
- "did users who got [campaign] open the app?" → CIO recipients + Amplitude app_opens
- "is the push fix working?" → CIO delivery rate + Amplitude push-attributed events

## Intent-driven actions (Phase B+)

For every DM Alaska receives, BEFORE falling through to the existing query/help responses below:

1. Invoke `intent-classifier` (synchronous mode — see `/data/skills/intent-classifier/SKILL.md` "DM handling"). Pass the DM message text, sender Slack ID, and timestamp.
2. Classifier returns `{intent, confidence, entities, would_have_done}`.
3. If `intent` is one of the action intents below AND `confidence >= 0.7`, run the matching handler. Otherwise fall through to the existing static commands (Status Check, Blocker Report, etc.) — those still work as before for low-confidence or non-action messages.

**`source_ref` construction (used by all handlers below):** build a deterministic identifier from the inbound event payload — `slack:dm:<channel_id>:<message_ts>` for a DM (e.g., `slack:dm:D08QKABCD:1779042600.001200`), or `slack:channel:<channel_id>:<message_ts>` for a channel mention. Do NOT call any Slack API to resolve a permalink in this skill. The deterministic form is stable, requires no extra call, and Doc Keeper / Thinker can lazily expand it to a permalink later when displaying in Notion. NEVER pass an empty `source_ref` — `tasks.source_ref` is a TEXT column but the audit log depends on it.

**Phase B self-create handlers (TASK_CREATE / TASK_UPDATE / TASK_BLOCKER are DM-only — channel-level self-create arrives in Phase D; the TASK_ASSIGN handler below works from either a DM or a channel mention):**

### TASK_CREATE handler

Triggered by: "starting on X", "I'll do Y", "add task: Z", "new task: Z" — the classifier's TASK_CREATE label.

1. Read `/data/skills/task-handler/SKILL.md`.
2. Invoke task-handler with:
   - `extraction`: the verbatim DM message text
   - `owner_slack_id`: the DM sender's Slack ID
   - `creator_slack_id`: the same Slack ID (self-create → personal task)
   - `source`: `slack_dm`
   - `source_ref`: `slack:dm:<channel_id>:<message_ts>` per the construction rule in the preamble above
   - `is_status_update`: `false`
   - `due_at_iso`: if the message contains a date hint ("by Friday", "tomorrow"), parse to ISO and pass — otherwise omit
3. task-handler returns `{task_id, action, title, ...}`.
4. Reply ONE LINE in the DM (no narration, per shared-toolkit Section 9 Slack discipline):
   > `Tracking as T-N: <title>. I'll surface it in your standup brief.`
5. If `dedup_decision.type == 'low_conf_defaulted_new'`, append `(flagged for review)` to your reply so the sender knows we created a possibly-duplicate task.

### TASK_UPDATE handler

Triggered by: "T-42 done", "still working on T-65", "blocked on T-58", "merged the PR" — the classifier's TASK_UPDATE label.

1. Look for a `T-\d+` pattern in the message text. If found, that's the `explicit_task_id`. If NOT found:
   - Pull the sender's active tasks from SQLite (per shared-toolkit Section 1.7 "Query: active tasks for a person", LIMIT 5 so you can disambiguate).
   - If exactly 1 active task AND it was `updated_at` within the last 20 minutes → it's almost certainly the one the sender means (they were just talking about it). Use it as `explicit_task_id` and proceed silently.
   - If exactly 1 active task BUT it's older than 20 minutes → **CONFIRM before acting.** Reply: `Marking T-N "<title>" as <inferred status> — confirm with 'yes' or specify a different T-N.` Do NOT invoke task-handler yet. Wait for the sender's reply.
   - If 0 active tasks → reply: `No active tasks tracked for you yet — start one with "new task: <description>".` and stop.
   - If 2+ active tasks → reply: `Which task? Reply with the T-N (e.g., "T-42 done") or describe it. Your active tasks: T-A — <title-a>, T-B — <title-b>, ...` and stop.
2. Invoke task-handler with:
   - `extraction`: verbatim message text
   - `owner_slack_id`: DM sender
   - `creator_slack_id`: DM sender
   - `source`: `slack_dm`
   - `source_ref`: `slack:dm:<channel_id>:<message_ts>` per the preamble
   - `is_status_update`: `true`
   - `explicit_task_id`: the T-N from step 1
3. task-handler determines the target status from the verb (done/blocked/active/dropped/snoozed) per its own verb-mapping rules.
4. Reply ONE LINE in the DM:
   > `Got it — T-N marked as <status>.`
   For `done`: also append `Will show up in tomorrow's Daily Pulse shipped list.`
   For `blocked`: also append `Logged blocker B-N.` (task-handler creates the blocker row per Step 5 of its procedure).

### TASK_BLOCKER handler

Triggered by: "blocked on Plaid docs", "can't proceed until X", "waiting on Sandeep" — the classifier's TASK_BLOCKER label (where no specific T-N is implied as the BLOCKED task — i.e., it's a standalone blocker report, not a status update on a known task).

If the message DOES reference a T-N (e.g., "T-42 is blocked on Plaid"), this is a TASK_UPDATE — let TASK_UPDATE handler handle it instead. Classifier should distinguish; if you see ambiguity, prefer TASK_UPDATE.

For a standalone TASK_BLOCKER (no T-N):

1. Invoke task-handler with:
   - `extraction`: verbatim message text
   - `owner_slack_id`: DM sender
   - `creator_slack_id`: DM sender
   - `source`: `slack_dm`
   - `source_ref`: `slack:dm:<channel_id>:<message_ts>` per the preamble
   - `is_status_update`: `false` (this creates a NEW blocker-tracking task, status='blocked' from creation)
2. task-handler creates a task with `status='blocked'` and, per its Step 5 side effect, also creates a `blockers` row.
3. Reply ONE LINE in the DM:
   > `Logged blocker B-N (task T-N). I'll surface it in tonight's brief and check back tomorrow.`

### REMINDER_REQUEST handler

Triggered by: "remind me about X in 5 days", "every Friday at 5 PM DM me my open tasks", "follow up with Pankaj on T-42 tomorrow".

#### Step 1: Parse the request

Extract these fields from the message text (use the LLM if regex isn't enough):

- **One-shot vs recurring** — "in 5 days", "tomorrow at 9am", "next Friday" = one-shot; "every Friday", "daily at 9am", "every weekday" = recurring.
- **Recipient** — usually the DM sender (self). For team routines, the recipient is a channel (e.g., "post to #project-management every Monday").
- **Linked task** — any `T-\d+` reference in the message.
- **Fire time** — parse relative dates ("in 5 days", "tomorrow at 9am", "Friday at 5pm") to an ISO UTC timestamp. For recurring, parse the natural-language schedule into an RRULE string (`FREQ=WEEKLY;BYDAY=FR;BYHOUR=17;BYMINUTE=0`, etc.).
- **Message text** — what to remind about. Default to a one-line summary of the request itself if not explicit.

#### Step 2: Determine scope

- **`personal`** if the recipient is the DM sender AND no other people / channels are mentioned. Single-person reminders.
- **`team`** if the recipient is a channel OR multiple people are tagged OR the action posts publicly OR the description implies team-wide behavior (e.g., "every Friday post the standup summary to #project-management").

Personal scope → create the scheduled_action directly. Team scope → create a routine_proposal and gate on Abhinav approval (see Step 4).

#### Step 3: Personal scope — create scheduled_action directly

For one-shot reminders, generate the action ID per the shared-toolkit Section 1.7 pattern (substitute `action_id` / `SA-`):

```bash
ACTION_ID=$(sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT 'SA-' || COALESCE(MAX(CAST(SUBSTR(action_id, 4) AS INTEGER)) + 1, 1) FROM scheduled_actions;")

# Escape any apostrophes in the message text per Section 1.5.
q="'"; qq="''"
payload_json="{\"message\":\"${message_text//$q/$qq}\",\"linked_task_id\":${linked_task_id_json}}"

sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO scheduled_actions \
    (action_id, action_type, fire_at, recipient_slack_id, linked_task_id, \
     payload, scope, created_by_slack_id) \
  VALUES \
    ('$ACTION_ID', 'remind', '$FIRE_AT_ISO', '$SENDER_SLACK_ID', \
     $LINKED_TASK_ID_OR_NULL, \
     '$payload_json', 'personal', '$SENDER_SLACK_ID');"
```

For recurring reminders, validate the RRULE via the helper first, then INSERT with `action_type='recurring_routine'`:

```bash
# Validate (exits non-zero on invalid)
python3 -c "
from rrule_helper import validate_rrule
import sys
valid, err = validate_rrule('$RRULE_STRING')
sys.exit(0 if valid else 1)
"

# Compute first fire time
FIRST_FIRE=$(python3 -c "
from rrule_helper import next_fire_time
print(next_fire_time('$RRULE_STRING').strftime('%Y-%m-%d %H:%M:%S'))
")

sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO scheduled_actions \
    (action_id, action_type, fire_at, recurrence_rule, recipient_slack_id, \
     payload, scope, created_by_slack_id) \
  VALUES \
    ('$ACTION_ID', 'recurring_routine', '$FIRST_FIRE', '$RRULE_STRING', \
     '$SENDER_SLACK_ID', '$payload_json', 'personal', '$SENDER_SLACK_ID');"
```

If RRULE validation fails, do NOT create the row. Reply to the sender: `Couldn't parse "<their text>" as a schedule. Try something like "every Friday at 5 PM" or "in 5 days".`

Confirm in DM (one line, no narration):

> `Got it — I'll remind you <describe_rrule output OR formatted one-shot time>. <If linked: Linked to T-N.> Reminder ID: SA-N (reply 'cancel SA-N' to remove it).`

For `describe_rrule` output, call the helper:

```bash
DESC=$(python3 -c "from rrule_helper import describe_rrule; print(describe_rrule('$RRULE_STRING'))")
```

#### Step 4: Team scope — create routine_proposal (gated on Abhinav)

DO NOT create the scheduled_action yet. First create a proposal:

```bash
PROPOSAL_ID=$(sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT 'RP-' || COALESCE(MAX(CAST(SUBSTR(proposal_id, 4) AS INTEGER)) + 1, 1) FROM routine_proposals;")

# Same apostrophe escape as above for description + payload
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO routine_proposals \
    (proposal_id, proposed_by_slack_id, description, proposed_payload, \
     proposed_recurrence_rule, proposed_recipient, expires_at) \
  VALUES \
    ('$PROPOSAL_ID', '$SENDER_SLACK_ID', '$description_esc', \
     '$payload_json', '$RRULE_STRING', '$RECIPIENT_DESCRIPTION', \
     datetime('now', '+7 days'));"
```

Reply to the proposer:

> `That's a team-wide routine — I need Abhinav to approve it first. Flagged for him (RP-N). I'll let you know once he responds (or after 7 days if he doesn't).`

DM Abhinav (`U07GKLVA9FE`):

```
*Routine proposal RP-N* from <proposer first name>:
"<description>"
Schedule: <describe_rrule output>
Recipient: <recipient description>

Reply: 'approve RP-N' / 'decline RP-N because <reason>' / 'modify RP-N: <changes>'
Expires in 7 days if no response.
```

### WATCHER_REQUEST handler

Triggered by: "watch X", "track X and do Y", "alert me when Z", "every Monday show me …", "every Tuesday create …", or "@alaska activate <template>" — the classifier's WATCHER_REQUEST label. (A bare reminder with no data query is REMINDER_REQUEST, not this — see the REMINDER-vs-WATCHER disambiguation rule in intent-classifier.)

1. Read `/data/skills/watcher-creator/SKILL.md` and execute its procedure end-to-end.
2. watcher-creator owns the entire conversational flow — parse intent, load the BON KB, draft the watcher, run its single clarifier round, route the $3/day approval gate, and (on confirmation) reserve the `watchers` row and `cron.add`. slack-commands does NOTHING here beyond routing.
3. Return watcher-creator's reply text verbatim as the DM response — no narration or summaries of your own.

### STATUS_QUERY

A read-only "what's the state of X" question — route to the graph-backed handlers above, no writes:
- "what's [person] working on / on" → **Status Check §A** (resolve name → `owner_slack_id` via roster, §1.7 active-tasks query, DAILY_STATE fallback).
- "what's blocked" / "who's blocked" → **Status Check §B** (`blockers` where `status='active'` + tasks `status='blocked'`, DAILY_STATE `BLOCKED:` fallback).
- "what's overdue" → **Status Check §C** (`status NOT IN ('done','dropped') AND due_at IS NOT NULL AND due_at < datetime('now')`; null `due_at` is never overdue).
- "my tasks" / "what's on my plate" → **My Tasks** handler (asker's own Slack ID, §1.7 active-tasks query, DAILY_STATE fallback).
- "status of [feature]" / "where are we on X" → **Status Check §D** (title LIKE on escaped query, DAILY_STATE + Meeting Notes fallback).

These are pure reads (no `task-handler`, no `tasks`/`blockers` writes). The classifier output is still logged to `classifier_audit`.

### DECISION_RECORDED / NON_WORK_CHAT / AMBIGUOUS

These intents are NOT handled here in Phase B. Fall through to the existing slack-commands sections (Help, General Questions). The classifier output is still logged to `classifier_audit` per Phase A observation mode — we just don't take action.

### TASK_ASSIGN handler

Triggered by: "assign X to Pankaj", "Sandeep should do Y", "give the chart bug to Sai", "@alaska have Darwin pick up Z" — the classifier's TASK_ASSIGN label, where the work is assigned to **someone other than the sender**. This creates a task at `status='pending_acceptance'` and asks the assignee to accept it.

1. **Resolve the assignee NAME → `owner_slack_id` via the MEMORY.md Team Roster** (first-name match, case-insensitive). Never guess an owner.
   - **Not in the roster, or the message names no clear assignee** → ask, don't guess: `Who should I assign this to? (couldn't match "<name>" to the team)`. Stop — do not invoke task-handler.
   - **Ambiguous** (the name matches more than one person, or the phrasing makes the assignee unclear) → ask the sender to disambiguate by first name. Stop.
   - **Assignee resolves to an external person with no Slack ID** (e.g., Sai is `_external_` in the roster) → we can't DM them to accept. Reply: `<Name> is external — I can't route an acceptance to them. Want me to track it as your own task instead?` Stop (don't open a pending_acceptance task no one can accept).
   - **Assignee == the sender** → this isn't a cross-person assign; treat it as a normal TASK_CREATE (self-owned) instead.
2. Read `/data/skills/task-handler/SKILL.md`. Invoke task-handler with:
   - `extraction`: the verbatim DM/message text (task-handler escapes free text per shared-toolkit §1.5 — pass it raw, don't pre-escape).
   - `owner_slack_id`: the **assignee's** Slack ID (resolved in step 1).
   - `creator_slack_id`: the **requester's** Slack ID (the sender).
   - `assigner_slack_id`: the **requester's** Slack ID (same as creator here — this is what makes task-handler open the task at `pending_acceptance`).
   - `source`: `slack_dm` if this came as a DM, `slack_channel` if from a channel mention.
   - `source_ref`: per the preamble construction rule (`slack:dm:<channel_id>:<message_ts>` or `slack:channel:<channel_id>:<message_ts>`).
   - `is_status_update`: `false`.
   - `due_at_iso`: if the message carries a date hint, parse to ISO and pass; otherwise omit.
3. task-handler returns `{task_id, action: "created_pending", status: "pending_acceptance", title, ...}`.
4. **DM the assignee** (their Slack ID is the resolved `owner_slack_id`) — one line, assigner's first name from the roster:
   > `<Assigner first name> assigned you <T-N>: <title>. Reply \`accept <T-N>\` or \`decline <T-N>\`.`
5. **Confirm to the assigner** in the channel/thread they asked in — one line:
   > `Assigned <T-N> to <assignee first name> — awaiting their acceptance.`

This is the one place slack-commands legitimately initiates contact with a third party (the assignee) without the requester re-confirming — the assign request IS the instruction to do so, so the "don't loop in third parties unprompted" rule (below) is satisfied. Do not also @-mention anyone else.

### Assignment acceptance — `accept T-N` / `decline T-N` (assignee-only)

This is the reply to the TASK_ASSIGN DM (a task sitting at `status='pending_acceptance'`). Matched by the grammar `accept T-\d+` / `decline T-\d+` (case-insensitive) — it does NOT need the intent classifier. The replier is the **assignee** (the task's owner); task-handler enforces that.

1. Parse the `T-N` from the message. Read `/data/skills/task-handler/SKILL.md`. Invoke task-handler with:
   - `explicit_task_id`: the `T-N`.
   - `acceptance`: `accept` or `decline` (from the verb).
   - `owner_slack_id`: the **replier's** own Slack ID (already known from the inbound DM event — no name parsing).
2. task-handler returns the handshake result (Step 3.5): `{task_id, action: "accepted"|"declined", status, title, owner_slack_id}` on success, or an `error` note (`not_owner` / `not_pending` / `no such task`).
3. **On `accept`** (`action: "accepted"`):
   - Reply to the assignee (one line): `Got it — <T-N> is now active.`
   - **Notify the assigner** so they know it was picked up. Look up the task's assigner to get their Slack ID + the title:
     ```bash
     sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
       SELECT assigner_slack_id, title FROM tasks WHERE task_id='<T-N>';"
     ```
     DM that `assigner_slack_id` (resolve replier's first name via roster): `<Assignee first name> accepted <T-N>: <title>.` (Skip the DM if `assigner_slack_id` is null/empty or equals the assignee — nothing to notify.)
4. **On `decline`** (`action: "declined"`):
   - Reply to the assignee (one line): `Noted, <T-N> declined.`
   - **Notify the assigner** so they can reassign (same lookup as above): DM the `assigner_slack_id`: `<Assignee first name> declined <T-N>: <title>. You'll want to reassign it.`
5. **On an `error` note** — reply one line to the replier, no third-party notification:
   - `not_owner` → `That's not your task to accept — <T-N> was assigned to someone else.`
   - `not_pending` → `<T-N> isn't awaiting acceptance (it's <status>).`
   - `no such task` → `I don't have a task <T-N>.`

Notifying the assigner here is authorized for the same reason as the TASK_ASSIGN DM: the assigner explicitly started this handshake, so closing the loop back to them is part of the action they requested — not an unprompted third-party ping.

### Authority note

Self-scoped task actions (TASK_CREATE / TASK_UPDATE / TASK_BLOCKER) always treat the DM sender as the owner. Cross-person assignment is handled by the **TASK_ASSIGN handler** above (assignee accepts via `accept T-N` / `decline T-N` — see the reply grammar just above).

### Anti-patterns

1. **Never write to `tasks` or `blockers` directly from this skill.** Always route through `task-handler` so dedup logic is consistent across surfaces.
2. **Never reply with multi-line internal narration.** One line per acknowledgment, per shared-toolkit Slack discipline rules. Examples of BAD: "Let me check… I'll query the database… Done." GOOD: "Got it — T-42 marked done."
3. **Never invoke task-handler without an `owner_slack_id`.** If the sender can't be resolved (unknown DM, Slack ID not in MEMORY.md), apply SOUL.md self-heal pattern first; if still unresolved, do NOT call task-handler — reply: "Hey! I'm Alaska, BON Credit's PM. I don't think we've met — what's your name?"
4. **Cross-person assignment routes through the TASK_ASSIGN handler — never write `pending_acceptance` yourself.** Resolve the assignee via the roster (never guess; ask if unresolved/ambiguous/external), invoke task-handler with `assigner_slack_id`, then DM the assignee to `accept T-N` / `decline T-N`. The acceptance reply also routes through task-handler (it owns the owner-only guard) — slack-commands never flips a task's status directly. (REMINDER_REQUEST and TASK_ASSIGN are both live now — neither is deferred.)

5. **Never hand-roll a cron or scheduled_action for a recurring/conditional DM request.** A recurring data report, a conditional alert, or "every X do Y / alert me when Z" is a WATCHER (route to `watcher-creator`) or a plain reminder (REMINDER_REQUEST handler). NEVER `cron.add` it directly or hand-write `scheduled_actions`/`watchers` — improvising infrastructure skips the draft→confirm gate, the cost gate, memory/dedup, and the audit trail (this is exactly the bug that produced a rogue cron on the first live watcher test). If you're about to create a cron for someone's DM request, stop and route to the handler.

## Routine Proposal Approval (Abhinav-only)

When Abhinav DMs `approve RP-N` / `decline RP-N because <reason>` / `modify RP-N: <changes>`:

1. **Verify the sender is Abhinav** (`U07GKLVA9FE`). If not, respond: `Only Abhinav can approve routines.` Stop.
2. **Look up the proposal.** If `status != 'pending'`, respond: `RP-N is already <status>.` Stop.
3. **On `approve`:**
   - Compute the first fire time from the stored `proposed_recurrence_rule` via rrule_helper.
   - Generate the next `SA-N` action ID.
   - INSERT into `scheduled_actions` with: `action_type='recurring_routine'`, `fire_at=<first_fire>`, `recurrence_rule=<proposed_recurrence_rule>`, `recipient_slack_id` or `recipient_channel_id` per the proposal's recipient, `payload` = `proposed_payload`, `scope='team'`, `created_by_slack_id=<proposer>`, `approved_by_slack_id='U07GKLVA9FE'`.
   - UPDATE `routine_proposals`: `status='approved'`, `abhinav_response=NULL`, `responded_at=CURRENT_TIMESTAMP`.
   - DM Abhinav: `RP-N approved. Routine SA-N created — first fire <date>.`
   - DM the original proposer: `Your routine RP-N was approved by Abhinav. It's live as SA-N — first fire <date>.`
4. **On `decline`:**
   - Parse the reason from the message (everything after "because" / "—" / colon, or the full remainder if no separator).
   - UPDATE `routine_proposals`: `status='declined'`, `abhinav_response=<reason>`, `responded_at=CURRENT_TIMESTAMP`.
   - DM the proposer: `Your routine proposal RP-N was declined. Reason: <reason>`
   - No DM back to Abhinav (his decline IS the acknowledgment).
5. **On `modify`:**
   - Parse the modification description (everything after "modify RP-N:").
   - UPDATE the proposal fields per the modification (e.g., new RRULE, new recipient, new message). Keep `status='pending'`.
   - Re-validate any new RRULE via rrule_helper before saving. If invalid: reply to Abhinav `RP-N modify failed — RRULE invalid: <error>. Proposal unchanged.`
   - DM the proposer: `RP-N was modified by Abhinav. New schedule: <describe_rrule output>. He'll do a final approve next.`
   - DM Abhinav: `RP-N updated with your modifications. Reply 'approve RP-N' when you're ready to activate it.`
   - Modified proposals still require a final `approve` to become live — modify alone is NOT activation.

If the proposal has expired (`expires_at < now()` AND `status='pending'`):
- UPDATE: `status='expired'`.
- DM the proposer once: `Your routine proposal RP-N expired after 7 days with no response from Abhinav. Send it again when you want to revisit.`
- This expiration check can run on every routine-proposal cron tick (see C5) or lazily on the next approval-reply attempt.

## Watcher Approval (creation gate + per-fire)

Two distinct watcher approval grammars land here. **Disambiguate by the word `fire`:** `approve W-N fire` is a per-fire approval (a specific drafted run); `approve W-N` (no `fire`) is the creation gate for a `>$3/day`/external/other-recipient watcher. They act on different objects and have different approvers, so check the grammar first.

### A. Creation gate — `approve W-N` / `decline W-N because <reason>` / `modify W-N: <changes>` (Abhinav-only)

This is the reply to watcher-creator's Step 7 routing DM (a watcher sitting at `status='pending_approval'`).

1. **Verify the sender is Abhinav** (`U07GKLVA9FE`). If not: `Only Abhinav can approve watchers.` Stop.
2. **Look up the watcher.** `SELECT status FROM watchers WHERE watcher_id='W-N';` If no row: `No watcher W-N.` If `status != 'pending_approval'`: `W-N is already <status>.` Stop. (Idempotent — a second `approve` after activation is a no-op.)
3. **On `approve`:** Read `/data/skills/watcher-creator/SKILL.md` and execute its **Step 8** for W-N — the row is already reserved at `pending_approval`, so Step 8 stamps `approved_by_slack_id='U07GKLVA9FE'` + `approved_at`, transitions `pending_approval → pending_cron_create → cron.add → active`, and sends the Step 8d confirmations to the creator and Abhinav. Do NOT re-implement the activation SQL here — delegate to watcher-creator so the write-ahead lifecycle stays in one place.
4. **On `decline`:** parse the reason (after `because`/`—`/`:`), then execute watcher-creator **Step 9** for W-N (`status='cancelled'`, `decline_reason`, DM the creator). No cron exists yet (decline precedes activation), so nothing to remove.
5. **On `modify`:** parse the change, `UPDATE` the reserved row's drafted fields (keep `status='pending_approval'`), and re-DM Abhinav the updated proposal in watcher-creator Step 7 format. Modify alone is NOT activation — a final `approve W-N` is still required.

### B. Per-fire approval — `approve W-N fire` / `decline W-N fire <reason>` / `modify W-N fire: <change>` (creator-only)

This is the reply to a rung-0 watcher's `awaiting_approval` draft (dispatcher Step 7). The approver is the watcher's **creator** (locked decision #14), not necessarily Abhinav.

1. **Look up the watcher + the pending fire.**
   ```bash
   sqlite3 /data/queue/alaska.db \
     "SELECT created_by_slack_id, status FROM watchers WHERE watcher_id='W-N';"
   sqlite3 /data/queue/alaska.db \
     "SELECT id, fact_key, action_summary FROM watcher_fires \
      WHERE watcher_id='W-N' AND outcome='awaiting_approval' ORDER BY fired_at DESC LIMIT 1;"
   ```
2. **Authority check:** the replying user must equal `watchers.created_by_slack_id`. If not: `Only the watcher's creator can approve its fires.` Stop.
3. If no `awaiting_approval` fire row: `Nothing's pending approval for W-N.` Stop. If the watcher's `status != 'active'` (paused/expired/cancelled since the draft): `W-N is <status> now — not sending.` and `UPDATE` the fire `outcome='declined'`, `action_summary` noting `watcher_inactive`. Stop.
4. **On `approve`:** execute the remaining acting steps recorded in the fire's `action_summary` (the draft + resolved args + remaining steps the dispatcher stored), following **watcher-dispatcher Step 8 acting+record semantics**. Then:
   - `UPDATE watcher_fires SET outcome='approved', action_summary=<append result> WHERE id=<fire_id>;`
   - Apply the memory update the dispatcher deferred for rung-0 (its anti-pattern #7 — memory advances only on a real action): `UPDATE watchers SET memory_state=<{"last_fact_key":"<fire fact_key>","last_fired_at":"<now>"}>, last_fired_at=CURRENT_TIMESTAMP, fire_count=fire_count+1, last_action_summary=<...> WHERE watcher_id='W-N';`
   - Reply to the creator (one line): `Sent W-N.`
   - On execution failure: `UPDATE` the fire `outcome='failed'`, `error=<short>`; DM Abhinav once; do NOT advance `last_fact_key` (next scheduled fire re-drafts).
5. **On `decline`:** parse the reason; `UPDATE watcher_fires SET outcome='declined', action_summary=<reason> WHERE id=<fire_id>;`. No send, and do NOT touch `memory_state` — the next scheduled fire should re-draft fresh. Reply: `Skipped W-N this round.`
6. **On `modify`:** parse the change, re-draft with it, DM the creator the new draft, and keep `outcome='awaiting_approval'` (`UPDATE` the fire's `action_summary` to the new draft). Re-approval required.

**Anti-patterns (watcher approval):** never let a non-creator approve a per-fire draft, or a non-Abhinav approve a creation gate. Never advance `memory_state.last_fact_key` on a decline or a failure. Never re-implement watcher-creator's activation or the dispatcher's acting logic here — delegate/follow them so there's one source of truth. Never double-send: the `awaiting_approval → approved/declined` transition is the lock; if the fire row is no longer `awaiting_approval`, it was already resolved.

## Watcher Management

Explicit watcher commands (matched by their grammar — not the intent classifier): `@alaska watchers`, `@alaska show W-N`, `@alaska pause/resume/delete W-N`, `@alaska modify W-N: <change>`, `@alaska watcher templates`, `@alaska activate <template>`.

**Authority (applies to `show`/`pause`/`resume`/`delete`/`modify` on a specific W-N):** the requester must be the watcher's **creator** (`watchers.created_by_slack_id`) OR **Abhinav** (`U07GKLVA9FE`). Otherwise: `That's not your watcher.` Resolve once with `SELECT created_by_slack_id, status FROM watchers WHERE watcher_id='W-N';` (no row → `No watcher W-N.`).

**Cost privacy:** cost (`cost_class`, any projection) is shown ONLY when the requester is Abhinav. Never expose it to a non-Abhinav creator in `show` or anywhere else (matches watcher-creator / dispatcher cost-privacy rules).

**Report only what the row says — never assume.** A watcher's recipient, schedule, and status are whatever its `watchers` row stores — NOT inferred from where you're chatting. ("We're talking in #x, so all my watchers must post to #x" is exactly the wrong move that misled a real `@alaska watchers` reply.) Read every field you report from the table *this turn*; if you didn't read it, don't state it. Applies to `watchers`, `show`, and any "what watchers do I have" question. **And compute any "next run / first fire" you state with `python3` + `zoneinfo` from the watcher's cron schedule + now — NEVER by hand.** (A "Mondays" watcher's first run is *today* when today is Monday; saying "tomorrow" because you mis-derived the weekday is a real bug we hit.)

### `@alaska watchers` — list the requester's active watchers
```bash
sqlite3 /data/queue/alaska.db \
  "SELECT watcher_id, description, trigger_type, status, recipient FROM watchers \
   WHERE created_by_slack_id='<requester>' AND status IN ('active','paused') \
   ORDER BY watcher_id;"
```
Render one line per watcher, stating the **actual destination from each row's `recipient`** (resolve `slack_dm`→"your DM", `slack_channel`→the real "#channel-name", `email`→the address) — never assume "this channel": `W-N · <description> · <trigger summary> · → <destination> · <status>`. If none: `No active watchers — say "watch …" or "activate <template>" to create one.`

### `@alaska watchers all` — Abhinav-only
If requester ≠ `U07GKLVA9FE`: `Only Abhinav can list everyone's watchers.` Else the same query without the `created_by_slack_id` filter, grouped by creator first name (from MEMORY.md).

### `@alaska show W-N`
After the authority check, render: description; trigger (schedule+tz, or event+filter, plain English); action chain as numbered prose (render the `action_chain` JSON the same way watcher-creator Step 6 does — never dump JSON); recipient; memory strategy + `last_fact_key` presence ("last fired on <fact>"/"—"); expiry; per-fire approval ON/OFF; the **last 5 fires** —
```bash
sqlite3 /data/queue/alaska.db \
  "SELECT fired_at, outcome, COALESCE(error,'') FROM watcher_fires \
   WHERE watcher_id='W-N' ORDER BY fired_at DESC LIMIT 5;"
```
Append `cost_class` **only if the requester is Abhinav**.

### `@alaska pause W-N`
`UPDATE watchers SET status='paused' WHERE watcher_id='W-N' AND status='active';` Do **not** remove the cron — the dispatcher bails on a non-active row (Step 1), so a paused watcher's cron fires a cheap no-op. Reply: `Paused W-N — it won't act until you resume it.`

### `@alaska resume W-N`
`UPDATE watchers SET status='active' WHERE watcher_id='W-N' AND status='paused';` (Event watchers resume too — the poller skips non-active rows, so this just re-includes it.) Reply: `Resumed W-N.`

### `@alaska delete W-N`
`UPDATE watchers SET status='cancelled' WHERE watcher_id='W-N';` then, for a cron-type watcher with a non-NULL `openclaw_cron_id`, call the in-session **`cron.remove`** on that id (event watchers have no per-watcher cron — skip). Reply: `Deleted W-N.` (We soft-cancel + remove the cron rather than hard-DELETE the row, so `watcher_fires` history stays referentially intact.)

### `@alaska modify W-N: <change>`
After the authority check, parse the change and `UPDATE` the affected fields. Then:
- **Trigger changed** (schedule/event): `cron.remove` the old `openclaw_cron_id`, then `cron.add` the new one (re-roll stagger), and store the new id — reuse watcher-creator Step 8b/8c.
- **Cost class rises** (crosses >$3/day, OR adds an external write, OR changes recipient away from the creator): re-gate — set `status='pending_approval'` and route to Abhinav (watcher-creator Step 7). Modify alone is not re-activation in that case.
- **Otherwise** (description, volume_cap, memory, recipient still self, cost unchanged): apply in place, reply `Updated W-N.`

### `@alaska watcher templates`
List the pre-built templates from `/data/skills/watcher-creator/templates/*.json` — read each file's `display_name` + `description` (do not hardcode the list; there are 5 today: bug-cluster, customer-signal, stale-task, deploy-impact, cross-person-task-assign). If a template carries a `gated` field, append `(not ready yet — <gated.reason>)`.

### `@alaska activate <template>`
Route to watcher-creator: read `/data/skills/watcher-creator/SKILL.md` and run its template-activation path (Step 6) for `<template>` — it reads the template JSON, asks only `parameters_to_ask`, and runs the normal draft→confirm→approve→activate flow. slack-commands does nothing beyond routing.

## Code & repo questions

When someone asks about source code, a bug's location, "what does function X do," "where is Y," or to trace logic across the codebase:

1. **Read before you claim.** Fetch the actual file via the GitHub contents API (TOOLS.md → "Reading source files"), then quote the real lines and name the repo + branch you read. Every code claim is either "I read it — here are the exact lines" or "I couldn't read it." Never "here's what's probably there."
2. **Never invent specifics.** Do NOT state a file path, line number, function name, or "there's another copy here too" unless it came from a file you actually fetched in THIS turn. Inferred specifics are forbidden — they send engineers chasing ghosts (this is exactly how a debt-classification "RCA" went wrong once).
3. **Name your boundary.** If the file 404s, has moved, or the logic lives outside the 9 repos — e.g., the hosted agentic service (`theagentic.ai` / `convo_agent_v3`) whose runtime you can't inspect — say so plainly and name the owner (Sandeep for AI/CredGPT, Nilesh/Sai for backend, Pankaj for the app). See TOOLS.md → "What you can and cannot reach."
4. **Answer ≠ investigation.** Answer the specific question with grounded quotes. Do NOT spin up an unprompted multi-repo investigation and broadcast conclusions. If a deeper dig is genuinely warranted, offer it and let the asker decide.

(See alaska-core → Honesty & Restraint #1 and #2.)

## Action restraint — don't loop in third parties unprompted

You may always answer the person talking to you. You may NOT, on your own initiative, @-mention, DM, or forward work to a THIRD person (anyone other than the requester) unless they explicitly asked you to in THIS message.

- If you think someone else should see something → ask the requester first: "Want me to flag this to <name>?" — then wait for their yes.
- This holds even when looping them in feels obviously helpful.
- **Why this is strict:** each Slack surface (a DM, a channel mention) runs as a SEPARATE session with no memory of your other conversations. An instruction someone gave you elsewhere — like "don't send this to anyone yet" — cannot reach the session you're in now. So the safe default is: never initiate contact with a third party off your own judgment. The person in front of you decides who else gets pulled in.

(See alaska-core → Honesty & Restraint #3.)

## General Questions

For anything not matching a specific command, use your judgment — but always within the two guardrails just above: **ground every code/factual claim** in data you actually pulled, and **never loop in a third party unprompted**. Then:
1. Search relevant Notion databases
2. Check recent meeting notes
3. Check Fireflies transcripts if relevant
4. **Query Amplitude** for metric questions (read amplitude-analyst skill)
5. **Query Customer.io** for campaign/messaging questions (read customerio-ops skill)
6. Respond with data, not guesses
7. If you don't know: "I don't have data on that. Want me to check [specific source]?"

Follow the Communication Standards in the shared toolkit. Additionally:
- Always respond within the same channel/thread you were asked in
- Keep responses concise — data, not paragraphs
- If a question requires checking multiple sources, just do it — don't narrate each step
