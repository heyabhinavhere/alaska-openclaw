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

1. If `recipient_slack_id` is set: send a Slack DM to that person.
   Reply format (one line, no narration):
   ```
   _Reminder you set [time ago]:_ <message text>
   ```
   If `linked_task_id` is set, append on a second line: `Linked: T-N — <current title>`.
2. If `recipient_channel_id` is set instead: post to that channel. Use only when the original schedule explicitly targeted a channel.

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

1. Execute the `prompt` — usually a Slack DM (`scope=personal`) or channel post (`scope=team`).
2. **Compute next fire BEFORE marking current fired** (critical — see anti-pattern 4). Invoke the rrule_helper:
   ```bash
   NEXT_FIRE=$(python3 -c "
   from rrule_helper import next_fire_time
   print(next_fire_time('$RECURRENCE_RULE').strftime('%Y-%m-%d %H:%M:%S'))
   ")
   ```
   (PYTHONPATH includes `/opt/lib` per entrypoint.sh — `rrule_helper` is importable directly.)
3. INSERT a fresh `scheduled_actions` row with the SAME `action_id` prefix scheme (generate next SA-N), `fire_at = $NEXT_FIRE`, same `recurrence_rule`, same `recipient_slack_id` / `recipient_channel_id` / `payload` / `created_by_slack_id`, `status='pending'`, `attempts=0`.
4. Mark the current row fired (Step 3 below).

#### `auto_followup`

Payload shape: `{"check_status_first": true, "task_id": "T-N", "message_if_active": "..."}`

1. Look up the task. If status is `done` or `dropped`: skip (follow-up no longer needed). Mark action fired with note like `auto_followup_skipped: task already done/dropped`.
2. If still `active`, `blocked`, or `pending_acceptance`: send `message_if_active` as a DM to the relevant party. Default recipient is the task's `assigner_slack_id` (the person who originally set up the follow-up), falling back to Abhinav if no assigner is set.

### Step 3: Mark action fired (or failed)

After a successful execution:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE scheduled_actions \
  SET status = 'fired', fired_at = CURRENT_TIMESTAMP \
  WHERE id = $ROW_ID;"
```

If the action is linked to a task, append a `task_events` row so the task's audit log carries the firing:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO task_events (task_id, event_type, actor_slack_id, context) \
  VALUES ('$LINKED_TASK_ID', 'scheduled_action_fired', 'agent:reminder-dispatcher', \
          'action_id=$ACTION_ID type=$ACTION_TYPE');"
```

If execution fails (Slack API error, malformed payload, RRULE parse error, etc.):

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE scheduled_actions \
  SET attempts = attempts + 1 \
  WHERE id = $ROW_ID;"
```

If `attempts + 1 >= max_attempts` (default 3): cancel and alert Abhinav.

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE scheduled_actions SET status='cancelled' WHERE id=$ROW_ID;"
# DM Abhinav (U07GKLVA9FE) with action_id, type, and the underlying error.
```

### Step 4: Summary log (silent unless something fired)

If at least one action fired, log a single line to stdout (cron run logs):

```
[reminder-dispatcher] Fired N actions: remind=A surface_task=B escalate=C recurring_routine=D auto_followup=E
```

If 0 actions fired, don't post anything. Silence is the steady-state signal.

## Anti-patterns

1. **Never silently fail.** Failed actions increment `attempts` and write to `task_events` (if linked). Hitting `max_attempts` cancels the row and alerts Abhinav. Silent drops break the trust contract.

2. **Never fire an action twice.** Mark `status='fired'` before any side effects that can't be repeated (Slack post, Notion write). If side effect fails AFTER the status flip, log to `task_events` with context and let the alert flow handle re-runs.

3. **Never assume Notion / Slack / Fireflies is up.** If you see repeated errors from one service across multiple actions in the same batch, check `/data/skills/shared-toolkit/SKILL.md` Section 7 health-check pattern before continuing. Graceful degradation: skip the affected actions, leave them pending, log the outage.

4. **Always compute `next_fire_at` for `recurring_routine` BEFORE marking the current row fired.** If the rrule_helper crashes or returns invalid output, the current routine should stay `pending` so the NEXT dispatcher run can retry. Marking-then-computing means a crash loses the recurrence forever.

5. **Never modify `tasks` or `blockers` rows directly from this skill.** If a fired action implies a task state change (e.g., `escalate` triggering an ack flow), the change happens via the appropriate handler (slack-commands for DM-driven changes, task-handler for write-side dedup). Reminder Dispatcher only writes to `scheduled_actions` and `task_events`.

6. **Never include internal phase labels or skill names in user-facing messages.** Reply text is the final output per SOUL.md Slack discipline — no "Let me check…" / "the reminder-dispatcher fired…" narration. Just the reminder content itself.

## Frequency and cost

Fires every 15 min via OpenClaw cron. Most runs touch 0 rows and exit silently (free). When actions are due, each one is a single SQLite read + 1-2 SQL writes + at most one Slack API call. No LLM calls in steady state — Reminder Dispatcher is pure deterministic execution.

Estimated cost: <$0.01/day. Negligible.
