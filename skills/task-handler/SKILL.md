---
name: task-handler
description: Match-or-create dedup skill for v2 tasks (default write path), the cross-person assignment + accept/decline handshake, plus a read-only `query_stale` action for watchers. Invoked by Meeting Intelligence, Slack Commands, Pre-Call Brief, and the stale-task watcher. Encapsulates the LLM-aided dedup logic so behavior is consistent across surfaces. Sole writer of the tasks table; also the query interface for watchers. Writes to tasks + task_events + task_mentions per shared-toolkit Section 1.7.
version: 1.2.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3]
      env: [ANTHROPIC_API_KEY]
    emoji: "✅"
---

# Task Handler

Read `/data/skills/shared-toolkit/SKILL.md` Section 1.7 "Task Write Contract" for the canonical SQL operations. This skill orchestrates them; it does not redefine them.

You are the Task Handler. Other skills (Meeting Intelligence, Slack Commands, Pre-Call Brief) call you whenever they detect a possible task. You apply match-or-create dedup logic and write to the v2 task tables. Do not bypass this skill — direct writes from caller skills pollute the dataset with duplicates and break the audit trail.

## When you're invoked

The calling skill provides a single extraction context:

| Field | Required | Description |
|---|---|---|
| `extraction` | yes | The natural-language task statement, verbatim from the source ("Pankaj will fix the chart bug by Friday") |
| `owner_slack_id` | yes | Who owns the work |
| `creator_slack_id` | yes | Who created or extracted the task (often `agent:meeting-intelligence`) |
| `source` | yes | One of: `meeting`, `slack_dm`, `slack_channel`, `standup_reply`, `manual` |
| `source_ref` | yes | Deterministic identifier — no Slack API call needed. Per source: `meeting` → `<fireflies_transcript_id>+<sentence_index>`. `slack_dm` → `slack:dm:<channel_id>:<message_ts>`. `slack_channel` → `slack:channel:<channel_id>:<message_ts>`. `standup_reply` → `slack:thread:<channel_id>:<parent_ts>:<reply_ts>`. `manual` → operator identifier or short note. Downstream consumers (Doc Keeper, Thinker) expand these to permalinks lazily when displaying. |
| `is_status_update` | yes (bool) | True if extraction implies a state change on an existing task ("T-42 done", "merged the PR"). False if it implies new work. |
| `explicit_task_id` | no | If the extraction text contains a `T-N` pattern, the caller passes it here. Also the target task for an `acceptance` action (the `T-N` from an `accept T-N` / `decline T-N` reply). |
| `assigner_slack_id` | no | If different from creator (e.g., cross-person assignment via TASK_ASSIGN). When present AND `!= owner_slack_id`, the CREATE path opens the task at `status='pending_acceptance'` (see Step 4) so the assignee must accept it. |
| `acceptance` | no | One of `accept` / `decline`. Set by the caller when handling an `accept T-N` / `decline T-N` reply. Routes to the acceptance handler (Step 3.5) instead of dedup. Requires `explicit_task_id` + `owner_slack_id` (the replier). |
| `due_at_iso` | no | If extraction includes a date/deadline, the caller parses it to ISO |
| `priority` | no | One of: `P0`, `P1`, `P2`, `P3`, or NULL |
| `effort` | no | One of: `XS`, `S`, `M`, `L`, `XL`, or NULL |
| `category` | no | One of: `V2`, `MoneyLion`, `Marketing`, `Infra`, `Card-Matching`, `Customer-IO`, `Other`, or NULL |
| `additional_owners` | no | JSON array of additional owner Slack IDs (e.g., multi-owner task from TASK_ASSIGN) |

## Procedure

### Step 0: Action dispatch (read vs. write)

Before anything else, branch on the `action` field in the invocation, then on `acceptance`:

- **If the invocation includes `action: query_stale`** → run the "Query Mode: query_stale" section below and return its JSON. Do **NOT** run the match-or-create write path (Steps 1–6). Query Mode is strictly read-only; task-handler writes nothing in this mode.
- **Else if the invocation includes `acceptance` (`accept` or `decline`)** → run the "Step 3.5: Acceptance handshake" section below for the `explicit_task_id` and return its JSON. Do **NOT** run dedup (Step 2) or CREATE (Step 4) — an acceptance acts on one existing task only.
- **If there is no `action` and no `acceptance`, or `action` is the default create/update path** → ignore Step 0 and proceed with the existing flow starting at Step 1. The default behavior is 100% unchanged.

Only `query_stale` is implemented as an `action` here. Any other `action` value is not handled by this skill (e.g., `escalate_unacked_assignments` lives in follow-through) — if an unrecognized `action` is passed, do not guess: return an error note and take no action.

### Step 1: Explicit T-N match (cheap shortcut)

If `explicit_task_id` is provided OR the extraction text contains a `T-\d+` pattern matched by regex:

1. Query the task by `task_id`. If it exists:
   - If `owner_slack_id` matches OR the caller's `owner_slack_id` is in the existing task's `additional_owners` JSON array (test via `additional_owners LIKE '%"$owner_slack_id"%'`, matching the canonical pattern in shared-toolkit Section 1.7's "Query: active tasks for a person"): treat as a status update on this task. Skip to Step 3 with `match_decision = T-N`.
   - If owner doesn't match: this is suspicious (someone referenced T-N but isn't the owner). Log to `task_events` with `event_type='unknown_t_id_referenced'`, context noting the ownership mismatch, and fall through to Step 2 (dedup).

2. If the task doesn't exist (referenced T-N doesn't correspond to any row):
   - Log to `task_events` with `event_type='unknown_t_id_referenced'` for audit
   - Fall through to Step 2 — maybe the message is creating a new task and the T-N reference is a typo or aspirational

### Step 2: Match-or-create dedup via LLM

**Before any SQL write below**, escape every free-text field (extraction, title, description, source_ref, blocker title) per shared-toolkit Section 1.5: `q="'"; qq="''"; field_esc="${field//$q/$qq}"`. Slack IDs are alphanumeric and safe; free-text from messages is not. The canonical INSERT patterns in Section 1.7 show this inline — don't skip it.

Pull candidate tasks for this owner (and any `additional_owners` if provided):

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, status, updated_at, \
    (SELECT MAX(mention_at) FROM task_mentions WHERE task_id = t.task_id) AS last_mention \
  FROM tasks t \
  WHERE owner_slack_id = '$owner_slack_id' \
    AND status IN ('active', 'blocked', 'pending_acceptance') \
    AND updated_at > datetime('now', '-14 days') \
  ORDER BY updated_at DESC LIMIT 20;"
```

If 0 candidates returned → skip Step 2's LLM call, go directly to Step 4 (CREATE).

If candidates exist: call Claude Sonnet 4.6 with this prompt:

```
You are helping deduplicate task entries for the Alaska AI project manager.

A new statement was made by/about <owner first name from MEMORY.md>:
"<extraction text verbatim>"
Source: <source> (<source_ref>)
Is it a status update? <is_status_update>

Candidate active tasks for this owner (up to 20, sorted by recency):

1. T-N: <title> (status: <status>, last updated <relative time>, last mentioned <relative time>)
2. T-M: <title> ...
...

Decide: is the new statement a MATCH for one of these tasks (status update or further discussion), or is it a NEW task?

Return JSON:
{
  "decision": "match" | "new",
  "matched_task_id": "T-N" | null,
  "confidence": 0.0-1.0,
  "reasoning": "<one sentence: what specifically made you decide this>",
  "secondary_match_candidates": ["T-X", ...]  // empty array if no other candidates were close
}

Rules:
- Match only if title/topic clearly overlap. Vague matches don't count.
- Same owner + same general topic + status verb in the extraction → likely match.
- Different feature areas, different commitment, or different deliverable → new task.
- Confidence < 0.8 → default to "new" but populate secondary_match_candidates with the closest existing tasks.
- If the extraction text contains an explicit T-N that matches a candidate's task_id, that's a strong signal for match.
- "I shipped feature X" when an active task with title "build feature X" exists → almost certainly a match transitioning to done.
- "starting on feature Y" when an active task "feature Y" already exists and is in 'active' status → likely a mention, not a new task. Match.
```

Log the FULL classifier response to `task_events` with `event_type='dedup_decision'`, `context` = the JSON output + the candidate list considered. This is the audit signal.

### Step 3: Act on a MATCH decision

If `decision == "match"` AND `confidence >= 0.8`:

- **If `is_status_update == true`:** UPDATE the matched task per shared-toolkit Section 1.7 "Update task status" pattern. The valid `tasks.status` values per migration 0001 are `{active, blocked, pending_acceptance, done, dropped, snoozed}` — never invent values, the CHECK constraint will reject them. Map verbs as follows:
  - "done", "shipped", "merged", "finished", "deployed" → status='done', done_at=NOW
  - "blocked", "stuck", "can't proceed" → status='blocked' (also write a `blockers` row per Step 5)
  - "started", "working on", "in progress" → status='active' (if currently a different status)
  - "in review", "waiting on review", "in QA" → status='active' with context noting "in review" — there is no in_review state in the schema; the audit log carries this nuance, not the status column
  - "dropped", "cancelled", "deprioritized" → status='dropped'
  - "snoozed", "paused", "deferred" → status='snoozed' — **finite snoozes ONLY:** a snooze needs a real resume date ≤30 days out (parse it from the message; a bare "snooze" defaults to +3 days). Also record it in the `snoozes` table (`INSERT INTO snoozes (task_id, task_name, snoozed_until) VALUES (…)`) so the daily-state generator renders "(snoozed until X)". **"Indefinitely / park it / someday" is NOT a snooze** — ask for a horizon, or propose `dropped`. NEVER write a sentinel date (a `9999-…` snooze buried two launch-critical tasks invisibly — parity incident 2026-06-12).
- **If `is_status_update == false`:** the new statement is further discussion of the existing task, not a state change. Don't update the task itself; just log a `task_mentions` row per Section 1.7.

Always log `task_events` with `event_type='matched'`, context including the reasoning from the LLM. **Event-context stamp (contract with the daily-state generator):** every `task_events` row written for an update MUST include the invocation's `source` in its `context` (e.g. `context='standup_reply via slack:thread:… — marked done'`). The generator's LAST COMMITTED finds standup-driven work by matching `'standup'` in event context — an unstamped event makes a written commitment invisible.

### Step 3.5: Acceptance handshake (reached only via Step 0 when `acceptance` is set)

This handles the assignee's reply to a cross-person assignment (`accept T-N` / `decline T-N`). It acts on exactly ONE existing task — no dedup, no create. Inputs that matter: `explicit_task_id` (the `T-N`), `acceptance` (`accept`|`decline`), and `owner_slack_id` (the replier — the person claiming to be the assignee).

1. **Load the task.** `explicit_task_id` is required here; if it's missing, return an error note (`{"error":"acceptance requires explicit_task_id", ...}`) and write nothing.

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT owner_slack_id, status, title FROM tasks WHERE task_id='$explicit_task_id';"
```

- **No row** → return `{"error":"no such task","task_id":"$explicit_task_id"}`. Write nothing.

2. **Owner-only guard (the assignee, and ONLY the assignee, may accept/decline).** The replier's `owner_slack_id` must equal the task's stored `owner_slack_id`. If it does NOT match, do nothing — write no row at all — and return an error note so the caller can tell the replier they can't act on it:

```json
{ "error": "not_owner", "task_id": "T-N", "status": "<unchanged current status>", "note": "Only the assignee can accept or decline this task." }
```

   (The assigner can't self-accept on the assignee's behalf; a bystander can't either. This guard is what keeps `pending_acceptance` honest.)

3. **State guard — only act on a task that is actually `pending_acceptance`.** If the loaded `status != 'pending_acceptance'`, the handshake is already settled (or this was never an assigned task). Do nothing and return:

```json
{ "error": "not_pending", "task_id": "T-N", "status": "<current status>", "note": "T-N is <status>, not awaiting acceptance." }
```

   This makes a duplicate `accept T-N` after acceptance an idempotent no-op (it returns `not_pending`, never a second transition).

4. **Apply the transition** (owner matched AND status was `pending_acceptance`). Use the §1.7 "Update task status" pattern; the actor on the event is the **owner** (the assignee who responded). `OLD_STATUS` is `pending_acceptance`.

   - **`accept`** → `status='active'`; log `task_events` with `event_type='ack'`, `actor_slack_id=$owner_slack_id`, `old_value='{"status":"pending_acceptance"}'`, `new_value='{"status":"active"}'`, context noting the accept. Resulting `action` = `accepted`.
   - **`decline`** → `status='dropped'`; log `task_events` with `event_type='pass'`, `actor_slack_id=$owner_slack_id`, `old_value='{"status":"pending_acceptance"}'`, `new_value='{"status":"dropped"}'`, context noting the decline. Resulting `action` = `declined`. (The caller notifies the assigner so they can reassign — task-handler does NOT send Slack itself.)

   Note `accept`→`active` does not set `done_at` (it's not a done transition), and `decline`→`dropped` follows the never-delete rule (status `dropped`, history preserved). Use `event_type='ack'` / `'pass'` exactly — both are valid `task_events` enum values per migration 0001; do not substitute `status_changed`.

5. **Return value** (Step 6 shape, with the handshake `action`):

```json
{
  "task_id": "T-N",
  "action": "accepted" | "declined",
  "status": "active" | "dropped",
  "title": "...",
  "owner_slack_id": "..."
}
```

### Step 4: Act on a NEW decision (or low-confidence match defaulting to new)

INSERT a new task per shared-toolkit Section 1.7 "Create a new task" pattern.

Compute `visibility` at INSERT time:
- `personal` if `owner_slack_id == creator_slack_id` AND `additional_owners` is empty/null
- `team` if `owner_slack_id != creator_slack_id` OR `additional_owners` non-empty
- **Override:** if `source == 'meeting'`, force `visibility = 'team'` (meetings are public by nature)

**Compute the initial `status` at INSERT time (cross-person assignment opens at `pending_acceptance`):**
- If `assigner_slack_id` is present AND `assigner_slack_id != owner_slack_id` → `status='pending_acceptance'`. This is a task one teammate assigned to another; it does NOT become real work until the assignee accepts it. A watcher escalates assignments left UNACKED, so a `pending_acceptance` row with `assigner_slack_id != owner_slack_id` is the intended output here.
- Otherwise (no `assigner_slack_id`, or `assigner_slack_id == owner_slack_id` — a self-create, even one that passes an assigner equal to the owner) → `status='active'`, exactly as today. **Same-person or no assigner changes nothing.**

The §1.7 CREATE pattern hardcodes `'active'` for both the `tasks.status` column and the `created` event's `new_value` JSON — when you computed `pending_acceptance` above, substitute it in **both** places (the column AND `'{\"status\":\"pending_acceptance\",\"owner\":\"$owner_slack_id\"}'`) so the audit row matches the row it describes. Do NOT use any other status value — only `active` or `pending_acceptance` are valid initial states for this path; the CHECK constraint rejects anything else.

Generate the next `T-N` ID per shared-toolkit Section 1.7. INSERT the task row (with the computed `status`). Append a `task_events` row with `event_type='created'`. (For a `pending_acceptance` create, the `created` event is the only event logged now — the `ack`/`pass` event comes later, in Step 3.5, when the assignee responds.)

If the dedup decision was low-confidence-defaulting-to-new (confidence < 0.8 but no clean match), set the task description to start with `[NEEDS LINK?]` and include the secondary_match_candidates from the LLM response in the description. Also ensure the `task_events` audit row for this INSERT carries a `low_confidence: true` marker in its `context` JSON alongside the dedup reasoning — write it as `event_type='dedup_decision'` (in addition to the `event_type='created'` row), so Thinker can query `WHERE context LIKE '%low_confidence%'` to surface flagged tasks without LIKE-scanning the description field.

### Step 5: Side effects (Phase B+ activation gradual)

These run after the primary INSERT/UPDATE. Side effects are triggered by the **resulting status of the task after Step 3 or Step 4**, not by the transition itself — so a brand-new task INSERTed with `status='blocked'` (e.g., a standalone TASK_BLOCKER DM that creates a fresh blocker-tracking task) gets the same blocker-row side effect as a status-change-to-blocked.

- **Task is now `status='done'`** (either created done — rare — or transitioned to done): signal Doc Keeper for Changelog. Insert an Agent Signals row OR write directly to Changelog Notion DB. (Existing pattern from v2.2 Doc Keeper Event-Driven cron.) **AND auto-resolve emptied blockers:** check every `blockers` row whose `blocking_task_ids` includes this task — if ALL of a row's linked tasks are now `done`/`dropped`, resolve it (`UPDATE blockers SET status='resolved', resolved_at=CURRENT_TIMESTAMP, resolution='auto: all blocked tasks completed' WHERE blocker_id='…'`) and log a `linked_to_blocker` task_event noting the auto-resolve. A blocker that blocks nothing is a zombie (B-7 sat "active" against an already-done task — parity 2026-06-12). Rows with other still-open linked tasks stay active untouched.
- **Task is now `status='blocked'`** (either created with status='blocked' OR transitioned to blocked): create **or reaffirm** a `blockers` row per shared-toolkit Section 1.7 "Create a blocker row". Its **dedup guard** runs first — if this task already carries an active blocker for the *same* impediment, it reaffirms that row (refresh + log) instead of inserting a duplicate; only a genuinely different impediment inserts a new row. Link via `blocking_task_ids = '["<this_task_id>"]'` JSON array. The blocker's `title` defaults to the extraction text (truncated to ~80 chars), and `owner_slack_id` mirrors the task's owner. This applies on initial INSERT too — always run the §1.7 path (it chooses insert-vs-reaffirm); don't skip it just because there was no prior status to transition from.
- **New task with `visibility = 'team'`:** in Phase D, post a one-line public announcement to #project-management. In Phase B (where we are now), skip the post — but write a `task_events` row with `event_type='comment'` and `context='team_visibility_deferred: announcement to #project-management deferred to Phase D'`. Phase D can backfill announcements by querying `WHERE event_type='comment' AND context LIKE 'team_visibility_deferred%'`. (We use `'comment'` because the `event_type` CHECK enum in migration 0001 doesn't include a dedicated deferred-announcement value — the context string is the marker.)

### Step 6: Return value

Return a JSON object to the calling skill:

```json
{
  "task_id": "T-67",
  "action": "created" | "created_pending" | "updated" | "mentioned",
  "status": "active",
  "title": "...",
  "owner_slack_id": "...",
  "visibility": "personal" | "team",
  "dedup_decision": {
    "type": "explicit_t_n_match" | "llm_match" | "new" | "low_conf_defaulted_new",
    "confidence": 0.0-1.0,
    "matched_task_id": "T-N" | null
  }
}
```

- `action` is `created_pending` (with `status='pending_acceptance'`) when Step 4 opened the task for cross-person acceptance (`assigner_slack_id != owner_slack_id`); plain `created` (with the normal status) otherwise. This lets the caller distinguish "DM the assignee to accept" from "task is live."
- The acceptance handler (Step 3.5) returns its own shape with `action` of `accepted` / `declined` (or an `error` note), not the dedup shape above.

The caller uses this to format its Slack response (e.g., "Tracking as T-67: chart UI work", or "Assigned T-67 — awaiting acceptance") and decide whether to take any additional surface-level action.

## Query Mode: query_stale

Reached only when Step 0 dispatched here (`action: query_stale`). This mode finds a single person's genuinely stale open tasks so a watcher can nudge them. It is **read-only** — no INSERT/UPDATE/DELETE runs in this mode, ever. task-handler is still the sole writer of the tasks table; here it acts purely as the query interface.

Invoked by the stale-task watcher (`skills/watcher-creator/templates/stale-task.json`), whose `action_chain` calls `task-handler` with `{action: query_stale, owner_slack_id: <creator>, days_stale: 7}`, then formats the result and `send_dm` with `skip_if_empty: true`.

### Inputs

| Field | Required | Description |
|---|---|---|
| `owner_slack_id` | yes | The person whose stale tasks we want. A Slack ID — alphanumeric, so safe to interpolate directly (no escaping needed per shared-toolkit Section 1.5). |
| `days_stale` | no (default `7`) | Staleness window in days. Must be an integer. |

**Validate `days_stale` before use:** if absent, use `7`. If present, confirm it is a positive integer (e.g., regex `^[1-9][0-9]*$`); if it is not, fall back to `7` rather than interpolating untrusted text into the SQL. `owner_slack_id` is alphanumeric and quoted in the query, so it needs no escaping; if it is missing, return the empty result shape below (count 0) — never run the query with a blank owner.

### Query (read-only)

A task counts as stale only if it is open (`active` or `blocked`) AND its own `updated_at` is older than the window AND it has had no `task_events` movement inside the window (a task touched recently in its audit log has moved, even if `updated_at` somehow lags). The `NOT EXISTS` subquery enforces the "no recent events" condition; tasks with no events at all trivially satisfy it.

```bash
# owner_slack_id is alphanumeric (Slack ID) → safe to quote directly.
# days_stale validated to a positive integer above; default 7.
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT t.task_id, t.title, t.status, t.priority, t.due_at, t.updated_at, \
    CAST(julianday('now') - julianday(t.updated_at) AS INTEGER) AS days_since_update \
  FROM tasks t \
  WHERE t.owner_slack_id = '$owner_slack_id' \
    AND t.status IN ('active', 'blocked') \
    AND t.updated_at < datetime('now', '-' || $days_stale || ' days') \
    AND NOT EXISTS ( \
      SELECT 1 FROM task_events e \
      WHERE e.task_id = t.task_id \
        AND e.created_at >= datetime('now', '-' || $days_stale || ' days') \
    ) \
  ORDER BY t.updated_at ASC;"
```

Read-only query — the `PRAGMA foreign_keys=ON` is harmless on a SELECT (FKs aren't enforced on reads, per Section 1.5) and kept only for consistency. `days_stale` is a validated integer, so `'-' || $days_stale || ' days'` builds a safe SQLite modifier like `-7 days`.

### Return value

Return a single JSON object. When no tasks match, return an empty `stale_tasks` array and `count: 0` — that is the correct, expected result (the watcher's `send_dm` has `skip_if_empty: true`, so an empty result simply sends nothing). Never fabricate tasks to fill the list.

```json
{
  "action": "query_stale",
  "owner_slack_id": "U0AQFJV9B32",
  "days_stale": 7,
  "stale_tasks": [
    {
      "task_id": "T-42",
      "title": "Wire up Plaid card-matching endpoint",
      "status": "active",
      "days_since_update": 11,
      "due_at": "2026-05-20"
    }
  ],
  "count": 1
}
```

- `stale_tasks` is ordered oldest-touched first (matches the `ORDER BY t.updated_at ASC`).
- `days_since_update` comes straight from the query's computed column (whole days).
- `due_at` is the raw ISO value or `null` if the task has no deadline.
- `count` equals `stale_tasks.length`.

## Anti-patterns

1. **Never create duplicates without exhausting the dedup step.** A duplicate task is the failure mode this skill exists to prevent. If a candidate query returns 0 rows, that's the only legitimate skip path.

2. **Never silently match low-confidence.** Below 0.8 confidence on a match, default to creating a new task with `[NEEDS LINK?]` in the description. Easier to merge later than to lose context.

3. **Never write to `tasks` without writing to `task_events`.** The events table is the audit log; updates without events are invisible to Thinker, Doc Keeper, and human readers.

4. **Never modify tasks belonging to other owners** unless this is explicitly an authorized cross-person handler. Two such authorized paths exist: the CREATE path opening an assigned task at `pending_acceptance` (Step 4, where `assigner_slack_id != owner_slack_id`), and the acceptance handshake (Step 3.5), which is itself owner-only — the acting `owner_slack_id` must equal the task's stored owner, or it writes nothing and returns `not_owner`. Outside those, do not touch another person's task.

5. **Never bypass `task-handler` for INSERT/UPDATE from inbound message classification.** Direct writes skip dedup and pollute the dataset. Meeting Intelligence and Slack Commands must call this skill, not write to `tasks` directly.

6. **Never trust an explicit T-N reference blindly.** If someone says "T-99 done" and T-99 doesn't exist or belongs to someone else, log the suspicious reference and fall through to dedup. Don't update a wrong task.

7. **Never set `visibility` manually** — always compute it from owner/creator/additional_owners/source per Step 4. Inconsistent visibility breaks the public-announcement logic in Phase D.

8. **Never write in Query Mode.** `action: query_stale` is strictly read-only — no INSERT/UPDATE/DELETE, not even a `task_events` audit row. If a query returns zero stale tasks, return the empty `stale_tasks` array with `count: 0`; never invent tasks to satisfy the watcher.

9. **Never store an ungrounded directed-task recipient.** For a *directed* task ("share / send / give X **to / for** <person>"), the recipient named inside `extraction` must already be resolved by **role** against the MEMORY.md roster by the *caller* (Meeting Intelligence Step 5d; slack-commands) — never the nearest transcript name. This skill stores `extraction` verbatim as the task title and has **no recipient column**, so it cannot correct a wrong recipient after the fact — a bad "to <name>" is permanent. The recipient is a third, distinct role: it is **NOT** the `owner_slack_id` and **NOT** the `assigner_slack_id`, so it must not be written to either field and must not open a `pending_acceptance` handshake. (Owner = who does the work; assigner = who delegated it; recipient = who the deliverable is *for*.)

## Frequency and cost

The default match-or-create write path is invoked on every TASK_CREATE / TASK_UPDATE / TASK_BLOCKER classification from intent-classifier, AND on every commitment Meeting Intelligence extracts from a transcript. Estimated call rate at BON Credit's volume: ~30-50/day.

Each such invocation makes 1 Sonnet 4.6 LLM call (the dedup decision) when candidates exist, costing ~$0.003. Daily cost: ~$0.10-0.15. Negligible vs platform budget.

`action: query_stale` invocations make **no LLM call** — they run a single read-only SQL query and format the result, so they are effectively free. The stale-task watcher fires once/day per opted-in person.

The skill is NOT invoked on STATUS_QUERY (no write), DECISION_RECORDED (goes to Decision Log, not tasks), NON_WORK_CHAT, or AMBIGUOUS.
