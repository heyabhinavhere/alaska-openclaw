---
name: slack-commands
description: Handle team queries in Slack — status checks, blocker reports, shipped items, sprint info, and ad-hoc questions
version: 1.0.0
metadata:
  openclaw:
    always: true
    emoji: "💬"
---

# Slack Commands

When team members message Alaska in Slack (DM or channel mention), respond intelligently by pulling live data from Notion and SQLite.

**You are always-on for these.** No cron needed — respond when asked.

## Command: Status Check

**Triggers:** "status of [feature]", "where are we on [task]", "update on [thing]"

**Response:**
1. Search `DAILY_STATE.md` per-person sections + recent Meeting Notes for matching items (by name similarity). The Notion Sprint Board is retired as of 2026-05-23.
2. Return:
```
*[Task Name]*
Status: [status] | Owner: @[name] | Priority: [priority]
Effort: [effort] | Due: [date] | Sprint: [N]
[If blocker exists]: Blocked by: [blocker]
[If overdue]: ⚠ Overdue by [X] days
```
3. If multiple matches, list all with brief status
4. If no match: "I don't see a task matching '[query]' in the current sprint or backlog. Want me to search meeting notes?"

## Command: Blocker Report

**Triggers:** "who's blocked?", "what's blocked?", "active blockers", "blockers"

**Response:**
1. Read Blockers database (Status: "Active")
2. Return:
```
*Active Blockers* ([count])
• [Blocker] — blocking @[owner]'s [task] — raised [date] ([X] days ago)
  Resolution owner: @[name]
```
3. If no active blockers: "No active blockers right now."

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

**Response:**
1. Identify who's asking (from Slack user → MEMORY.md Team Roster).
2. Read their section in `DAILY_STATE.md` (`Per Person` → that person's `NOW`, `LAST COMMITTED`, `BLOCKED`).
3. Return prioritized by recency and priority:
```
*Your Tasks — Sprint [N]*
1. [Task] — [priority] — due [date] — [status]
2. [Task] — [priority] — due [date] — [status]

Suggested focus: [highest priority or nearest deadline task]
```

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

**`source_ref` construction (used by all handlers below):** build a deterministic identifier from the inbound DM event payload — `slack:dm:<channel_id>:<message_ts>` (e.g., `slack:dm:D08QKABCD:1779042600.001200`). Do NOT call any Slack API to resolve a permalink in this skill. The deterministic form is stable, requires no extra call, and Doc Keeper / Thinker can lazily expand it to a permalink later when displaying in Notion. NEVER pass an empty `source_ref` — `tasks.source_ref` is a TEXT column but the audit log depends on it.

**Phase B handlers (DMs only — channel-level TASK_CREATE/UPDATE arrives in Phase D):**

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

### REMINDER_REQUEST handler — DEFERRED (Phase C internally)

Triggered by: "remind me about X in 5 days", "every Friday DM me my tasks".

Phase B response (one line, no internal phase labels in the reply):
> `Reminders aren't available yet — noted. Ping me near the date and I'll surface it.`

(Internally: Phase C wiring will replace this with actual `scheduled_actions` writes. The reply intentionally hides the roadmap from team members.)

### STATUS_QUERY / DECISION_RECORDED / NON_WORK_CHAT / AMBIGUOUS

These intents are NOT handled here in Phase B. Fall through to the existing slack-commands sections (Status Check, My Tasks, Help, General Questions). The classifier output is still logged to `classifier_audit` per Phase A observation mode — we just don't take action.

### Authority note

In Phase B, ALL task actions are SELF-SCOPED — the DM sender is always the owner. Cross-person assignment (TASK_ASSIGN intent) is rejected with a one-line reply (no internal phase labels in the reply):

> `I can't assign tasks across people yet. Share it with them directly and I'll pick it up from your next meeting.`

(Internally: Phase D will replace this with the full TASK_ASSIGN workflow.)

### Anti-patterns

1. **Never write to `tasks` or `blockers` directly from this skill.** Always route through `task-handler` so dedup logic is consistent across surfaces.
2. **Never reply with multi-line internal narration.** One line per acknowledgment, per shared-toolkit Slack discipline rules. Examples of BAD: "Let me check… I'll query the database… Done." GOOD: "Got it — T-42 marked done."
3. **Never invoke task-handler without an `owner_slack_id`.** If the sender can't be resolved (unknown DM, Slack ID not in MEMORY.md), apply SOUL.md self-heal pattern first; if still unresolved, do NOT call task-handler — reply: "Hey! I'm Alaska, BON Credit's PM. I don't think we've met — what's your name?"
4. **Never claim Phase C/D features work in Phase B.** Use the deferred-handler replies above for REMINDER_REQUEST and TASK_ASSIGN.

## General Questions

For anything not matching a specific command, use your judgment:
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
