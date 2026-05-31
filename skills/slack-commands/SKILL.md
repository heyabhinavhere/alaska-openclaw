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
4. **Never claim cross-person task assignment works yet (deferred handler).** Use the deferred-handler reply above for TASK_ASSIGN. (REMINDER_REQUEST is now live as of Phase C — it's no longer deferred.)

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

### `@alaska watchers` — list the requester's active watchers
```bash
sqlite3 /data/queue/alaska.db \
  "SELECT watcher_id, description, trigger_type, status FROM watchers \
   WHERE created_by_slack_id='<requester>' AND status IN ('active','paused') \
   ORDER BY watcher_id;"
```
Render one line per watcher: `W-N · <description> · <trigger summary> · <status>`. If none: `No active watchers — say "watch …" or "activate <template>" to create one.`

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
