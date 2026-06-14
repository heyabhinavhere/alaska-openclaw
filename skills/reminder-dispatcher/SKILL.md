---
name: reminder-dispatcher
description: Fires due scheduled_actions every 15 min. Handles remind / surface_task / escalate / recurring_routine / auto_followup. Re-queues recurring actions per RRULE.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3, python3]
    emoji: "⏰"
---

# Reminder Dispatcher

Read `/data/skills/shared-toolkit/SKILL.md` for queue patterns, Slack channel routing, communication standards, and Section 1.5 SQL-escape rules. Read `/data/skills/task-handler/SKILL.md` only if a fired action needs to update a task (rare).

You are the Reminder Dispatcher. Cron fires you every 15 min. You read due scheduled_actions, execute each, and re-queue recurring ones. Write paths touch `scheduled_actions` and `task_events` only — never `tasks` or `blockers` directly.

## Procedure

### Step 1: Read due actions

Pull up to 20 pending actions whose `fire_at` has passed:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT id, action_id, action_type, recipient_slack_id, recipient_channel_id, \
         linked_task_id, payload, recurrence_rule, attempts, max_attempts, scope \
  FROM scheduled_actions \
  WHERE status = 'pending' AND fire_at <= datetime('now') \
  ORDER BY fire_at ASC LIMIT 20;"
```

If 0 rows: exit silently (no action needed, no log post).

### Step 2: Execute each due action

Parse `payload` as JSON. Dispatch by `action_type`:

#### `remind`

Payload shape: `{"message": "...", "linked_task_id": "T-N" or null}`

1. **Stale-work guard (parity with `surface_task`/`escalate`/`auto_followup`, which all do this):** if `linked_task_id` is set, look it up — if the task is `done` or `dropped`, **skip the send** (the work is already finished; the reminder is stale) and mark the action `fired` with a note (`remind_skipped: task already done/dropped`). Only continue when there is no linked task, or the linked task is still open.
2. If `recipient_slack_id` is set: send a Slack DM to that person.
   Reply format (one line, no narration):
   ```
   _Reminder you set [time ago]:_ <message text>
   ```
   If `linked_task_id` is set, append on a second line: `Linked: T-N — <current title>`.
3. If `recipient_channel_id` is set instead: post to that channel. Use only when the original schedule explicitly targeted a channel.

#### `surface_task`

Payload shape: `{"task_id": "T-N", "reason": "user_snoozed_until_today" | ...}`

1. Look up the task. If status is `done` or `dropped`, skip (the surface action is stale). Mark action fired with note in `task_events.context`.
2. If still active, write a `task_events` row with `event_type='dispatcher_surfaced'` and `context` = the reason. The next pre-call brief / Daily Pulse naturally surfaces the task; no direct Slack post here.

#### `escalate`

Payload shape: `{"reason": "no_ack_after_2h" | "deadline_4h_warning" | "overdue_24h", "task_id": "T-N"}`

1. Look up the task. If status is `done` or `dropped`, skip (no escalation needed). Mark action fired with note.
2. Dispatch by reason:
   - `no_ack_after_2h`: DM Abhinav (`U07GKLVA9FE`): `T-N has not been ack'd by <owner first name> (assigned by <assigner first name> Xh ago). Want me to proceed with default, chase the owner, or reassign?`
   - `deadline_4h_warning`: DM the task owner: `Heads-up: T-N is due in 4h. Status update?`
   - `overdue_24h`: DM both the task owner AND the assigner (or Abhinav if no assigner): `T-N is 24h overdue. <Owner first name> — what's the status?`

Resolve first names from `/root/.openclaw/workspace/MEMORY.md` Team Roster.

#### `recurring_routine`

Payload shape: `{"prompt": "<the recurring action's prompt>", "scope": "personal" | "team"}`

This action_type has TWO distinct side effects (the prompt execution AND the next-occurrence INSERT). Their ordering is critical for recurrence-schedule integrity — see Step 3a below for the full deterministic sequence.

The side effect IN STEP 3c is: execute the `prompt` — usually a Slack DM (`scope=personal`) or channel post (`scope=team`). Step 3a handles next-occurrence prep before this side effect runs, so the schedule stays intact even if this Friday's Slack post fails.

(PYTHONPATH includes `/opt/lib` per entrypoint.sh — `rrule_helper` is importable directly inside the `python3 -c "..."` calls.)

#### `auto_followup`

Payload shape: `{"check_status_first": true, "task_id": "T-N", "message_if_active": "..."}`

1. Look up the task. If status is `done` or `dropped`: skip (follow-up no longer needed). Mark action fired with note like `auto_followup_skipped: task already done/dropped`.
2. If still `active`, `blocked`, or `pending_acceptance`: send `message_if_active` as a DM to the relevant party. Default recipient is the task's `assigner_slack_id` (the person who originally set up the follow-up), falling back to Abhinav if no assigner is set.

### Step 3: Execute the action — flip-first ordering for idempotency

**Critical:** the order below is non-negotiable. Mark the row `fired` BEFORE running any side effect (Slack post, Notion write, etc.). If a side effect crashes mid-flight (container OOM, cron timeout, Slack API hang), the row is already `fired` and the next 15-min dispatcher run will NOT re-execute it. We accept the rare cost of "one lost reminder" to prevent the common failure mode "duplicate Slack reminders on every retry."

Per action, run in this exact sequence:

#### Step 3a: Deterministic prep (no side effects yet)

For `recurring_routine` only: compute the next fire time AND insert the next occurrence row FIRST. This protects the recurrence schedule even if the current occurrence's side effect fails — next Friday's reminder still fires regardless of whether this Friday's Slack post succeeded.

```bash
# For recurring_routine, prep the next occurrence row before anything else
NEXT_FIRE=$(python3 -c "
from rrule_helper import next_fire_time
print(next_fire_time('$RECURRENCE_RULE').strftime('%Y-%m-%d %H:%M:%S'))
")

NEXT_ACTION_ID=$(sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT 'SA-' || COALESCE(MAX(CAST(SUBSTR(action_id, 4) AS INTEGER)) + 1, 1) FROM scheduled_actions;")

sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO scheduled_actions \
    (action_id, action_type, fire_at, recurrence_rule, recipient_slack_id, recipient_channel_id, \
     linked_task_id, payload, scope, created_by_slack_id, approved_by_slack_id, status) \
  VALUES \
    ('$NEXT_ACTION_ID', 'recurring_routine', '$NEXT_FIRE', '$RECURRENCE_RULE', \
     '$RECIPIENT_SLACK_ID', '$RECIPIENT_CHANNEL_ID', $LINKED_TASK_ID_OR_NULL, \
     '$PAYLOAD_JSON', '$SCOPE', '$CREATED_BY', '$APPROVED_BY', 'pending');"
```

If RRULE evaluation or the INSERT fails: do NOT proceed to Step 3b. Increment `attempts` on the current row, write a `task_events` failure marker if linked, and surface a Slack alert per Step 3d. The recurrence schedule must not break silently — Abhinav needs to know if a recurring rule is wedged.

#### Step 3b: Mark current row fired BEFORE executing side effects

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE scheduled_actions \
  SET status = 'fired', fired_at = CURRENT_TIMESTAMP \
  WHERE id = $ROW_ID AND status = 'pending';"
```

The `AND status = 'pending'` guard ensures only one dispatcher process can claim the row even if two cron ticks overlap. After this UPDATE, the row is permanently marked fired — no retry path.

#### Step 3c: Execute the side effect (Slack post, etc.)

Per action_type (see Step 2 above for the per-type logic). Capture success or failure into a local variable; don't crash the loop on one action's failure.

#### Step 3d: Audit + alert based on outcome

On **success**, log a `task_events` row if linked:

```bash
if [ -n "$LINKED_TASK_ID" ]; then
  sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
    INSERT INTO task_events (task_id, event_type, actor_slack_id, context) \
    VALUES ('$LINKED_TASK_ID', 'scheduled_action_fired', 'agent:reminder-dispatcher', \
            'action_id=$ACTION_ID type=$ACTION_TYPE outcome=success');"
fi
```

On **failure** (Step 3c side effect errored), log the failure and increment attempts on a follow-up tracking pattern — note the action is ALREADY marked `fired`, so we don't retry. Instead the failure is recorded as a permanent audit event AND Abhinav gets alerted:

```bash
# Audit: log the failure on the linked task (if any)
if [ -n "$LINKED_TASK_ID" ]; then
  sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
    INSERT INTO task_events (task_id, event_type, actor_slack_id, context) \
    VALUES ('$LINKED_TASK_ID', 'scheduled_action_fired', 'agent:reminder-dispatcher', \
            'action_id=$ACTION_ID type=$ACTION_TYPE outcome=FAILED error=<short_error>');"
fi

# Bump attempts on the (already-fired) row for ops visibility
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE scheduled_actions SET attempts = attempts + 1 WHERE id = $ROW_ID;"

# Alert Abhinav once per failure
# DM target: U07GKLVA9FE
# Message: "Reminder $ACTION_ID ($ACTION_TYPE) failed to fire. Linked task: $LINKED_TASK_ID. Error: <short_error>. Won't retry — manually re-create if still needed."
```

We don't retry failed sends because Step 3b already flipped status to `fired` for idempotency. The `attempts` field becomes an ops-visibility counter ("how many sends went sideways?") rather than a retry trigger. If a recurring routine starts failing repeatedly, Abhinav can see `attempts >= 2` across multiple SA-N rows for the same recurrence_rule and decide whether to fix the rule or cancel it.

### Step 4: Summary log (silent unless something fired)

If at least one action fired, log a single line to stdout (cron run logs):

```
[reminder-dispatcher] Fired N actions: remind=A surface_task=B escalate=C recurring_routine=D auto_followup=E
```

If 0 actions fired, don't post anything. Silence is the steady-state signal.

## Anti-patterns

1. **Never silently fail.** Every failed side effect writes to `task_events` (if linked) AND bumps `attempts` AND alerts Abhinav once. Silent drops break the trust contract — we'd rather over-alert than miss a broken reminder.

2. **Never fire an action twice.** Mark `status='fired'` BEFORE any side effect that can't be repeated (Slack post, Notion write). This is Step 3b's guard. The `WHERE id = $ROW_ID AND status = 'pending'` clause is the lock — if two cron ticks overlap, only one wins the UPDATE and the other sees zero affected rows and skips the action.

3. **Never assume Notion / Slack / Fireflies is up.** If you see repeated errors from one service across multiple actions in the same batch, check `/data/skills/shared-toolkit/SKILL.md` Section 7 health-check pattern before continuing. Graceful degradation: for actions you haven't yet flipped to `fired` in Step 3b, leave them `pending` for the next 15-min run. Log the outage once to Abhinav.

4. **For `recurring_routine`: INSERT the next-occurrence row in Step 3a BEFORE Step 3b flips the current row fired.** This protects the recurrence schedule from being lost if the current occurrence's side effect (Step 3c) crashes. Order: compute next fire → INSERT next row (pending) → flip current to fired → execute side effect. If Step 3a INSERT fails, do NOT proceed to Step 3b — the current row stays `pending` so the next dispatcher run can retry the whole sequence.

5. **Never modify `tasks` or `blockers` rows directly from this skill.** If a fired action implies a task state change (e.g., `escalate` triggering an ack flow), the change happens via the appropriate handler (slack-commands for DM-driven changes, task-handler for write-side dedup). Reminder Dispatcher only writes to `scheduled_actions` and `task_events`.

6. **Never include internal phase labels or skill names in user-facing messages.** Reply text is the final output per SOUL.md Slack discipline — no "Let me check…" / "the reminder-dispatcher fired…" narration. Just the reminder content itself.

## Frequency and cost

Fires every 15 min via OpenClaw cron. Most runs touch 0 rows and exit silently (free). When actions are due, each one is a single SQLite read + 1-2 SQL writes + at most one Slack API call. No LLM calls in steady state — Reminder Dispatcher is pure deterministic execution.

Estimated cost: <$0.01/day. Negligible.
