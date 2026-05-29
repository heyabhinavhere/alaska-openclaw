---
name: task-handler
description: Match-or-create dedup skill for v2 tasks. Invoked by Meeting Intelligence, Slack Commands, Pre-Call Brief. Encapsulates the LLM-aided dedup logic so behavior is consistent across surfaces. Writes to tasks + task_events + task_mentions per shared-toolkit Section 1.7.
version: 1.0.0
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
| `explicit_task_id` | no | If the extraction text contains a `T-N` pattern, the caller passes it here |
| `assigner_slack_id` | no | If different from creator (e.g., cross-person assignment via TASK_ASSIGN) |
| `due_at_iso` | no | If extraction includes a date/deadline, the caller parses it to ISO |
| `priority` | no | One of: `P0`, `P1`, `P2`, `P3`, or NULL |
| `effort` | no | One of: `XS`, `S`, `M`, `L`, `XL`, or NULL |
| `category` | no | One of: `V2`, `MoneyLion`, `Marketing`, `Infra`, `Card-Matching`, `Customer-IO`, `Other`, or NULL |
| `additional_owners` | no | JSON array of additional owner Slack IDs (e.g., multi-owner task from TASK_ASSIGN) |

## Procedure

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
  - "snoozed", "paused", "deferred" → status='snoozed'
- **If `is_status_update == false`:** the new statement is further discussion of the existing task, not a state change. Don't update the task itself; just log a `task_mentions` row per Section 1.7.

Always log `task_events` with `event_type='matched'`, context including the reasoning from the LLM.

### Step 4: Act on a NEW decision (or low-confidence match defaulting to new)

INSERT a new task per shared-toolkit Section 1.7 "Create a new task" pattern.

Compute `visibility` at INSERT time:
- `personal` if `owner_slack_id == creator_slack_id` AND `additional_owners` is empty/null
- `team` if `owner_slack_id != creator_slack_id` OR `additional_owners` non-empty
- **Override:** if `source == 'meeting'`, force `visibility = 'team'` (meetings are public by nature)

Generate the next `T-N` ID per shared-toolkit Section 1.7. INSERT the task row. Append a `task_events` row with `event_type='created'`.

If the dedup decision was low-confidence-defaulting-to-new (confidence < 0.8 but no clean match), set the task description to start with `[NEEDS LINK?]` and include the secondary_match_candidates from the LLM response in the description. Also ensure the `task_events` audit row for this INSERT carries a `low_confidence: true` marker in its `context` JSON alongside the dedup reasoning — write it as `event_type='dedup_decision'` (in addition to the `event_type='created'` row), so Thinker can query `WHERE context LIKE '%low_confidence%'` to surface flagged tasks without LIKE-scanning the description field.

### Step 5: Side effects (Phase B+ activation gradual)

These run after the primary INSERT/UPDATE. Side effects are triggered by the **resulting status of the task after Step 3 or Step 4**, not by the transition itself — so a brand-new task INSERTed with `status='blocked'` (e.g., a standalone TASK_BLOCKER DM that creates a fresh blocker-tracking task) gets the same blocker-row side effect as a status-change-to-blocked.

- **Task is now `status='done'`** (either created done — rare — or transitioned to done): signal Doc Keeper for Changelog. Insert an Agent Signals row OR write directly to Changelog Notion DB. (Existing pattern from v2.2 Doc Keeper Event-Driven cron.)
- **Task is now `status='blocked'`** (either created with status='blocked' OR transitioned to blocked): create a `blockers` row per shared-toolkit Section 1.7 "Create a blocker row", link via `blocking_task_ids = '["<this_task_id>"]'` JSON array. The blocker's `title` defaults to the extraction text (truncated to ~80 chars), and `owner_slack_id` mirrors the task's owner. This applies on initial INSERT too — do NOT skip blocker-row creation just because there was no prior status to transition from.
- **New task with `visibility = 'team'`:** in Phase D, post a one-line public announcement to #project-management. In Phase B (where we are now), skip the post — but write a `task_events` row with `event_type='comment'` and `context='team_visibility_deferred: announcement to #project-management deferred to Phase D'`. Phase D can backfill announcements by querying `WHERE event_type='comment' AND context LIKE 'team_visibility_deferred%'`. (We use `'comment'` because the `event_type` CHECK enum in migration 0001 doesn't include a dedicated deferred-announcement value — the context string is the marker.)

### Step 6: Return value

Return a JSON object to the calling skill:

```json
{
  "task_id": "T-67",
  "action": "created" | "updated" | "mentioned",
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

The caller uses this to format its Slack response (e.g., "Tracking as T-67: chart UI work") and decide whether to take any additional surface-level action.

## Anti-patterns

1. **Never create duplicates without exhausting the dedup step.** A duplicate task is the failure mode this skill exists to prevent. If a candidate query returns 0 rows, that's the only legitimate skip path.

2. **Never silently match low-confidence.** Below 0.8 confidence on a match, default to creating a new task with `[NEEDS LINK?]` in the description. Easier to merge later than to lose context.

3. **Never write to `tasks` without writing to `task_events`.** The events table is the audit log; updates without events are invisible to Thinker, Doc Keeper, and human readers.

4. **Never modify tasks belonging to other owners** unless this is explicitly an authorized cross-person handler (Phase D's TASK_ASSIGN reassignment flow, not Phase B).

5. **Never bypass `task-handler` for INSERT/UPDATE from inbound message classification.** Direct writes skip dedup and pollute the dataset. Meeting Intelligence and Slack Commands must call this skill, not write to `tasks` directly.

6. **Never trust an explicit T-N reference blindly.** If someone says "T-99 done" and T-99 doesn't exist or belongs to someone else, log the suspicious reference and fall through to dedup. Don't update a wrong task.

7. **Never set `visibility` manually** — always compute it from owner/creator/additional_owners/source per Step 4. Inconsistent visibility breaks the public-announcement logic in Phase D.

## Frequency and cost

This skill is invoked on every TASK_CREATE / TASK_UPDATE / TASK_BLOCKER classification from intent-classifier, AND on every commitment Meeting Intelligence extracts from a transcript. Estimated call rate at BON Credit's volume: ~30-50/day.

Each invocation makes 1 Sonnet 4.6 LLM call (the dedup decision) when candidates exist, costing ~$0.003. Daily cost: ~$0.10-0.15. Negligible vs platform budget.

The skill is NOT invoked on STATUS_QUERY (no write), DECISION_RECORDED (goes to Decision Log, not tasks), NON_WORK_CHAT, or AMBIGUOUS.
