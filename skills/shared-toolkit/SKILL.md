---
name: shared-toolkit
description: Shared utility patterns for all Alaska agents — queue-first writes, health reporting, token budgets, communication standards, agent signaling, error handling
version: 1.0.0
metadata:
  openclaw:
    always: true
    requires:
      bins: [sqlite3, curl]
    emoji: "🔧"
---

# Alaska Shared Toolkit

These are the standard operating procedures every Alaska agent follows. They are loaded automatically into every conversation. If an agent-specific skill contradicts something here, the agent-specific instruction wins for that agent only.

---

## 1. notionWrite — Queue-First Notion Writes

Before writing to Notion, always save to SQLite first. This ensures nothing is ever lost during API outages.

### Pattern

```bash
# Step 1: Queue the write
sqlite3 /data/queue/alaska.db "INSERT INTO outbox (target, payload, status) VALUES ('notion', '<json_payload>', 'pending');"

# Step 2: Write to Notion via MCP
# Use the Notion MCP tool to create/update the page

# Step 3a: On SUCCESS
sqlite3 /data/queue/alaska.db "UPDATE outbox SET status='sent', sent_at=datetime('now') WHERE id=<id>;"

# Step 3b: On FAILURE
sqlite3 /data/queue/alaska.db "UPDATE outbox SET status='failed', retry_count=retry_count+1 WHERE id=<id>;"
```

### Retry Logic

On each invocation, check for stuck outbox entries before doing new work:
```bash
sqlite3 /data/queue/alaska.db "SELECT id, payload FROM outbox WHERE target='notion' AND status IN ('pending', 'failed') AND retry_count < 3 ORDER BY created_at ASC LIMIT 5;"
```

- Retry each one via Notion MCP
- After 3 failed retries → alert Abhinav via Slack DM: "Notion API is failing. [X] writes queued locally. I'll keep retrying."
- Never lose data — SQLite is the safety net

### Pre-Write Validation (Anti-Hallucination)

Before ANY Notion write, verify:

1. **Select fields use EXACT existing options.** Never create new select values.
   - Status: `Backlog` / `Not started yet` / `In Progress` / `In Review` / `Done` / `Blocked`
   - Priority: `P0 Critical` / `P1 High` / `P2 Medium` / `P3 Low`
   - Effort: `S` / `M` / `L` / `XL`
   - Source: `meeting` / `backlog` / `bug` / `founder-request`
   - Risk Severity: `Critical` / `High` / `Medium` / `Low`
   - Risk Status: `Active` / `Mitigated` / `Resolved`
   - Decision Status: `Active` / `Superseded` / `Reversed`
   - Proposal Status: `Pending` / `Confirmed` / `Rejected` / `Modified`
   - Blocker Status: `Active` / `Resolved`
   - Meeting Type: `standup` / `planning` / `review` / `ad-hoc`
   - Backlog Status: `New` / `Triaged` / `Ready for Sprint` / `Deferred`

2. **Required fields are populated.** Never leave Due Date empty. If missing, flag as `[NEEDS DUE DATE]` and ask the team. (Owner field is ENABLED as of 2026-05-29 — see "Owner field — enabled" below; use the roster Notion IDs, fallback to first-name-in-Notes only if a person has no ID.)

3. **All data was explicitly stated, not inferred.** If you're unsure whether something was said or decided, flag as `[NEEDS CLARIFICATION]` and ask. Never invent details.

4. **Page/database IDs are real.** Never fabricate Notion IDs. See `/root/.openclaw/workspace/MEMORY.md` → Notion Data Sources for the canonical ID list.

### Notion API headers — get these right

- **Reads (data source queries):** `Notion-Version: 2025-09-03`, endpoint `POST /v1/data_sources/{data_source_id}/query`. The older `/databases/{id}/query` endpoint is deprecated.
- **Writes (page create/update):** `Notion-Version: 2022-06-28`, endpoints `POST /v1/pages` and `PATCH /v1/pages/{page_id}`. The newer 2025-09-03 version does NOT accept all the field-write shapes we use.

Wrong header → silent write failure. Symptom: API returns 200 but the field doesn't appear when you read the page back.

### Notion Write Contract — exact JSON shapes

These are the property-value shapes you MUST use when writing. Per-property type comes from the database schema; use the type below for each property.

```
Status (select):       {"select": {"name": "Done"}}
Priority (select):     {"select": {"name": "P0 Critical"}}
Effort (select):       {"select": {"name": "L"}}
Source (select):       {"select": {"name": "meeting"}}
Owner (people):        {"people": [{"id": "<notion_user_uuid>"}]}
Due Date (date):       {"date": {"start": "2026-05-23"}}
Multi-select tag:      {"multi_select": [{"name": "AI"}, {"name": "Backend"}]}
Number:                {"number": 5}
Checkbox:              {"checkbox": true}
Rich text:             {"rich_text": [{"text": {"content": "Some text"}}]}
Title:                 {"title": [{"text": {"content": "Page title"}}]}
URL:                   {"url": "https://example.com"}
Relation:              {"relation": [{"id": "<other_page_id>"}]}
Email:                 {"email": "person@example.com"}
Phone:                 {"phone_number": "+1234567890"}
```

**Common mistakes (these all fail silently with the wrong API version or wrong shape):**
- Writing Status as `{"status": {"name": "Done"}}` — wrong. The Status field in our schema is a `select` type, not the new Notion `status` type. Use `{"select": {"name": "..."}}`.
- Writing Owner as `{"rich_text": [{"text": {"content": "Pankaj"}}]}` — wrong. Owner is a `people` field requiring `{"people": [{"id": "<uuid>"}]}`.
- Using `Notion-Version: 2025-09-03` on a `POST /v1/pages` write — some shapes will be rejected.

### Owner field — ENABLED as of 2026-05-29

Notion User IDs are now captured in `MEMORY.md` → Team Roster for all 8 internal team members, so the Owner (people) field can be written.

To set Owner:
- Look up the person's **Notion User ID** in `MEMORY.md` → Team Roster and write `{"people": [{"id": "<notion_user_uuid>"}]}` (per the Write Contract above).
- **Graceful fallback — never fail the write:** if the person has no Notion User ID (external like Sai, or a new/unmatched person), fall back to writing the first name into the Notes/description field prefixed with `Owner: `, exactly as before.
- **Never guess a Notion User ID.** Not in the roster → use the fallback. Read the page back after writing to confirm the field populated (wrong API version/shape fails silently — see headers note above).

---

## 1.5 SQLite — Foreign Key Enforcement Pattern

The v2 task model schema (migration `0001_v2_task_model.sql`) declares foreign
keys between tasks, task_events, task_mentions, scheduled_actions, blockers,
intent_inbox, and classifier_audit. SQLite enforces these ONLY when
`PRAGMA foreign_keys = ON;` is set on the current connection.

**Every sqlite3 invocation that writes to v2 task tables MUST include the
pragma.** Pattern:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; <your INSERT/UPDATE/DELETE>"
```

Read-only queries don't need the pragma (FKs aren't enforced on SELECT), but
adding it is harmless — when in doubt, include it.

**Wrong (silently corrupts audit log if task doesn't exist):**
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO task_events (task_id, event_type, ...) VALUES ('T-nonexistent', 'created', ...);"
```

**Right (errors immediately if task doesn't exist):**
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; INSERT INTO task_events (task_id, event_type, ...) VALUES ('T-nonexistent', 'created', ...);"
```

Why: per-connection default is OFF in SQLite. Agents that forget the pragma
will silently insert orphan rows that violate referential integrity, polluting
the audit log permanently.

---

## 1.6 Slack message ingestion → `intent_inbox`

Any skill that reads Slack channel messages should ALSO write each message to the `intent_inbox` table for the v2 intent-classifier (Phase A onwards) to process in batched mode. The pattern is `INSERT OR IGNORE` against the `(channel_id, message_ts)` unique constraint — duplicate ingestion attempts are harmless, so it's safe to re-ingest on every cron pull.

### Pattern

After fetching new channel messages, for each message:

```bash
# Escape single quotes in message_text for safe SQL interpolation.
# Slack messages routinely contain apostrophes ("I'm done", "let's ship") —
# without doubling them, the INSERT will break with a SQL syntax error.
# Pattern matches migrations/run_migrations.sh:22-25.
q="'"; qq="''"
text_escaped="${message_text//$q/$qq}"

# Construct thread_ts SQL literal: NULL (unquoted) for top-level messages,
# 'parent_ts' (quoted) for thread replies. Variable expansion can't toggle
# quoting cleanly inside the SQL string, so build the literal here.
if [ -z "$thread_ts" ]; then
  thread_ts_literal="NULL"
else
  thread_ts_literal="'$thread_ts'"
fi

# Now do the insert. PRAGMA is a no-op for intent_inbox (no outgoing FKs)
# but kept for consistency with Section 1.5 — always include it on v2 task table writes.
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; INSERT OR IGNORE INTO intent_inbox (message_ts, channel_id, author_slack_id, message_text, thread_ts) VALUES ('$message_ts', '$channel_id', '$author_slack_id', '$text_escaped', $thread_ts_literal);"
```

**Important:** the ingester writes ONLY `message_ts`, `channel_id`, `author_slack_id`, `message_text`, and `thread_ts`. Do NOT pre-populate `processed`, `intent`, `confidence`, `classifier_output`, or `processed_at` — those columns are owned by the intent-classifier skill. The schema defaults `processed` to 0, which is correct.

**Other special characters:** Slack messages contain newlines, backticks, dollar signs, and backslashes. The pattern above is safe for these because: (1) the bash variable expansion is inside `"..."` (double quotes) which doesn't re-expand `$var` or backticks already substituted, and (2) SQLite's single-quoted string literals only need apostrophe-doubling. If you see SQL errors from a specific message, capture the raw bytes and inspect — likely a backslash or null byte edge case. In Phase A, we accept rare drops on truly pathological messages; classifier_audit count vs intent_inbox count will surface any systematic loss.

Fields:
- `message_ts`: Slack's `ts` field (string, format `1234567890.123456`).
- `channel_id`: the Slack channel ID (e.g., `C0ANKDD664A` for #project-management).
- `author_slack_id`: the message author's Slack user ID (e.g., `U0AQFJV9B32`). NOT the display name.
- `message_text`: the raw message body. Strip Slack-mrkdwn formatting if needed but otherwise preserve verbatim — the classifier needs the original wording to detect task verbs, T-N references, etc.
- `thread_ts`: pass NULL if it's a top-level message; pass the parent `ts` if it's a thread reply.

### When to ingest

- Whenever a skill fetches new messages from a channel (via Slack `conversations.history` or similar), ingest them.
- It's OK to ingest the same message twice; the `(channel_id, message_ts)` unique constraint deduplicates silently.
- DMs to Alaska bypass this table — they're handled synchronously by the intent-classifier when slack-commands invokes it.

### Edge cases

- **Bot messages:** still ingest them. The intent-classifier has a pre-filter that skips Alaska's own bot messages (`U0ANY9YTNUR`, `U0ANFSYAH29`).
- **Message edits:** Slack edits keep the same `ts`, so `INSERT OR IGNORE` keeps the original text. If we ever want to re-classify edited messages, add a separate column later; for Phase A, original wording is what we evaluate.
- **Empty / system messages** (e.g., "X joined the channel"): still ingest. The pre-filter in intent-classifier marks them `NON_WORK_CHAT` without an LLM call.

### Why ingestion is decoupled from classification

Two separate concerns:
- **Ingestion** = grab Slack reality and persist it (this section).
- **Classification** = interpret the persisted messages (intent-classifier skill).

Different skills can ingest at different cadences (Thinker reads hourly, future skills might pull more often). The classifier runs on a fixed 5-min cron and processes whatever's accumulated. The `INSERT OR IGNORE` constraint means concurrent ingestion is safe.

**Phase A latency tolerance.** Freshness lag between ingestion (Thinker hourly) and classification (5-min cron) is bounded at ~65 minutes worst case. This is acceptable in Phase A because the classifier only writes to `classifier_audit` — no agent acts on the classifications. Phases B+ may add more frequent ingesters once latency becomes user-visible.

---

## 1.7 Task Write Contract — v2 task model

The canonical operations for the v2 task model. Every skill that creates, updates, or queries tasks uses these patterns. Schema lives in `migrations/0001_v2_task_model.sql`; the live tables are on `/data/queue/alaska.db`.

**Always include `PRAGMA foreign_keys=ON;` per Section 1.5.** Without it, the FK relationships between `tasks`, `task_events`, `task_mentions`, and `blockers` are advisory only and orphan writes can silently corrupt the audit log.

### Generate the next T-N ID

```bash
NEXT_ID=$(sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; SELECT 'T-' || COALESCE(MAX(CAST(SUBSTR(task_id, 3) AS INTEGER)) + 1, 1) FROM tasks;")
```

Same pattern for `blocker_id` (`B-N`), `action_id` (`SA-N`), `proposal_id` (`RP-N`) — substitute the table name and prefix.

### Create a new task

```bash
# Escape any apostrophes in title/description per Section 1.6 pattern
q="'"; qq="''"
title_esc="${title//$q/$qq}"
desc_esc="${description//$q/$qq}"

sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO tasks ( \
    task_id, title, description, status, priority, effort, \
    owner_slack_id, additional_owners, creator_slack_id, assigner_slack_id, \
    visibility, category, source, source_ref, due_at \
  ) VALUES ( \
    '$NEXT_ID', '$title_esc', '$desc_esc', 'active', $priority_or_NULL, $effort_or_NULL, \
    '$owner_slack_id', $additional_owners_json_or_NULL, \
    '$creator_slack_id', $assigner_or_NULL, \
    '$visibility', $category_or_NULL, '$source', '$source_ref', \
    $due_at_or_NULL \
  ); \
  INSERT INTO task_events (task_id, event_type, actor_slack_id, new_value, context) \
  VALUES ('$NEXT_ID', 'created', '$actor_slack_id', \
          '{\"status\":\"active\",\"owner\":\"$owner_slack_id\"}', \
          'Source: $source, ref: $source_ref');"
```

**Compute `visibility` at INSERT time:**

```bash
if [ "$owner_slack_id" = "$creator_slack_id" ] && [ -z "$additional_owners_json" -o "$additional_owners_json" = "null" ]; then
  visibility="personal"
else
  visibility="team"
fi
# Override: meetings are always team-visible
if [ "$source" = "meeting" ]; then
  visibility="team"
fi
```

**Required fields** (any INSERT missing these will fail the CHECK constraints):

- `task_id` (unique, format `T-N`)
- `title` (NOT NULL)
- `status` (default `active`, must be in `{active, blocked, pending_acceptance, done, dropped, snoozed}`)
- `owner_slack_id` (NOT NULL)
- `creator_slack_id` (NOT NULL)
- `visibility` (default `personal`, must be `personal` or `team`)
- `source` (NOT NULL, must be in `{meeting, slack_dm, slack_channel, standup_reply, manual}`)

### Update task status (e.g., from "T-42 done")

`tasks.updated_at` auto-bumps via the `trg_tasks_updated_at` trigger (set up in migration 0001), so you don't need to set it manually — but you DO need to write the corresponding `task_events` row.

```bash
# Capture old value for the audit log
OLD_STATUS=$(sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; SELECT status FROM tasks WHERE task_id='$task_id';")

sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE tasks SET \
    status = '$new_status', \
    done_at = CASE WHEN '$new_status' = 'done' THEN CURRENT_TIMESTAMP ELSE done_at END \
  WHERE task_id = '$task_id'; \
  INSERT INTO task_events (task_id, event_type, actor_slack_id, old_value, new_value, context) \
  VALUES ('$task_id', 'status_changed', '$actor_slack_id', \
          '{\"status\":\"$OLD_STATUS\"}', '{\"status\":\"$new_status\"}', '$context');"
```

The trigger handles `updated_at`. Setting `done_at` is conditional on transitioning into `done` state.

### Log a mention without status change

When a task is discussed but no state change happens (e.g., someone references T-42 in a meeting summary, or the classifier sees TASK_UPDATE on a task that's already in that status):

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO task_mentions ( \
    task_id, surface, actor_slack_id, excerpt, source_ref, mention_type \
  ) VALUES ( \
    '$task_id', '$surface', '$actor_slack_id', '$excerpt_esc', '$source_ref', '$mention_type' \
  );"
```

`mention_type` is one of `{status_update, discussion, assignment, commitment, reference}` (or NULL). `surface` is one of `{meeting, slack_dm, slack_channel, standup_reply}`.

### Query: active tasks for a person (pre-call brief, daily pulse)

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, status, priority, due_at, updated_at, source \
  FROM tasks \
  WHERE owner_slack_id = '$owner_slack_id' \
    AND status IN ('active', 'blocked', 'pending_acceptance') \
  ORDER BY \
    CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, \
    due_at ASC NULLS LAST, \
    updated_at DESC;"
```

Add `additional_owners` filtering if you also want to surface tasks where the person is a secondary owner:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, status, priority, due_at, owner_slack_id \
  FROM tasks \
  WHERE (owner_slack_id = '$slack_id' OR additional_owners LIKE '%\"$slack_id\"%') \
    AND status IN ('active', 'blocked', 'pending_acceptance') \
  ORDER BY priority ASC, due_at ASC;"
```

### Query: tasks done in last N hours (changelog / daily pulse shipped)

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, owner_slack_id, done_at, category \
  FROM tasks \
  WHERE status = 'done' \
    AND done_at > datetime('now', '-24 hours') \
  ORDER BY done_at DESC;"
```

### Query: all events for a task (audit log)

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT created_at, event_type, actor_slack_id, old_value, new_value, context \
  FROM task_events \
  WHERE task_id = '$task_id' \
  ORDER BY created_at ASC;"
```

### Create a blocker row (when a task transitions to blocked)

When a task's status changes to `blocked`, the task-handler also writes a `blockers` row so the blocker is queryable independently of the task. One blocker row can block multiple tasks via the `blocking_task_ids` JSON array — that's the link back from blocker to task(s).

Schema reference (migration 0001, table 5): columns are `blocker_id, title, description, blocking_task_ids, owner_slack_id, raised_by_slack_id, status, raised_at, resolved_at, resolution, source, source_ref`. There is no `blocked_task_id` column — the link is the JSON array.

**Dedup guard — reaffirm, don't duplicate (run BEFORE the INSERT).** A blocked task gets re-reported constantly — the same impediment resurfaces across standups and meetings on different days. Inserting unconditionally spawns duplicate active rows (inflated Active-Blockers counts, double-counting in Daily Pulse/Risk Radar, and resolution that closes only one). First check whether this task already carries an active blocker:

```bash
# blocking_task_ids is a JSON array; the quotes delimit each id, so '%"T-42"%'
# matches ["T-42"] and ["T-1","T-42"] but NOT ["T-420"].
EXISTING=$(sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT blocker_id, title FROM blockers \
  WHERE status='active' AND blocking_task_ids LIKE '%\"$primary_blocked_task_id\"%';")
```

Decide from `$EXISTING`:
- **Empty** → no active blocker on this task. INSERT a fresh row (canonical pattern below).
- **Same thing already tracked** (an existing active blocker's title is the same impediment — the common re-report case) → do NOT insert a duplicate. Refresh that row and log the reaffirmation, keeping its original `blocker_id` and `raised_at`:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE blockers SET description='$desc_esc', source_ref='$source_ref' \
    WHERE blocker_id='$matched_blocker_id' AND status='active'; \
  INSERT INTO task_events (task_id, event_type, actor_slack_id, context) \
  VALUES ('$primary_blocked_task_id', 'comment', '$raised_by_slack_id', \
          'blocker $matched_blocker_id reaffirmed from $source');"
```

- **Genuinely different impediment** (a different dependency / thing-being-waited-on than the existing active blocker[s]) → INSERT a new row — a task can hold several distinct active blockers at once.

For an **unowned/standalone blocker** (`blocking_task_ids='[]'`, no task link), key the dedup on subject instead of task: skip the INSERT if an `active` blocker with the same subject already exists; otherwise insert fresh.

The canonical fresh-INSERT pattern:

```bash
# Generate next blocker_id using the canonical MAX/CAST/SUBSTR pattern from above.
B_NEXT_ID=$(sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; SELECT 'B-' || COALESCE(MAX(CAST(SUBSTR(blocker_id, 3) AS INTEGER)) + 1, 1) FROM blockers;")

# Escape apostrophes in free-text fields per Section 1.5.
q="'"; qq="''"
title_esc="${blocker_title//$q/$qq}"
desc_esc="${blocker_description//$q/$qq}"

# blocking_task_ids is a JSON array string like '["T-42","T-43"]'. Use '[]' not NULL when external.
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO blockers ( \
    blocker_id, title, description, blocking_task_ids, \
    owner_slack_id, raised_by_slack_id, status, source, source_ref \
  ) VALUES ( \
    '$B_NEXT_ID', '$title_esc', '$desc_esc', '$blocking_task_ids_json', \
    '$owner_slack_id', '$raised_by_slack_id', 'active', '$source', '$source_ref' \
  ); \
  INSERT INTO task_events (task_id, event_type, actor_slack_id, new_value, context) \
  VALUES ('$primary_blocked_task_id', 'linked_to_blocker', '$raised_by_slack_id', \
          '$B_NEXT_ID', '$title_esc');"
```

Field rules:
- `title` — short summary of the blocker (e.g., "Plaid docs", "Waiting on Sandeep's review"). NOT NULL.
- `description` — optional longer detail. Use the verbatim extraction if you have one.
- `blocking_task_ids` — JSON array of the task IDs this blocker is preventing (e.g., `'["T-42","T-43"]'`). Use `'[]'` (not NULL) when the blocker is external and not yet linked to any task.
- `owner_slack_id` — who owns the blocked work (usually the primary blocked task's owner).
- `raised_by_slack_id` — who reported the blocker (the actor/speaker, or `agent:meeting-intelligence`).
- `status` — at INSERT always `'active'`. Resolution flows UPDATE to `'resolved'` and set `resolved_at`.

After INSERT, append a `task_events` row on each blocked task with `event_type='linked_to_blocker'`, `new_value=$B_NEXT_ID`, `context` = the blocker title so each task's audit log carries the blocker pointer. If you're linking to multiple tasks, write one row per task.

### Match-or-create logic (delegated to task-handler skill)

When the intent-classifier surfaces a possible new task, do NOT write to `tasks` directly. Invoke the `task-handler` skill (at `/data/skills/task-handler/SKILL.md`) which encapsulates the match-or-create dedup logic.

The handler's procedure:

1. Pull candidate tasks for the same owner where status IN ('active', 'blocked', 'pending_acceptance') AND updated_at > NOW - 14 days, limit 20.
2. Pass the new extraction + candidates to Claude Sonnet 4.6 with a focused dedup prompt.
3. If `confidence >= 0.8` AND `match != null` → UPDATE the existing task per "Update task status" pattern above, append a `task_events` row with `event_type='matched'`, log a `task_mentions` row.
4. Else → INSERT new task per "Create a new task" pattern above.
5. Always log the decision to `task_events` with `event_type='dedup_decision'` and the full reasoning in `context`.

### Common anti-patterns

- **Never modify `task_id` after creation.** It's the stable identity that humans reference ("T-42 done"). Renaming or reassigning breaks every prior mention.
- **Never delete tasks.** Use `status = 'dropped'` for cancelled work. Preserves history and audit trail.
- **Always write a `task_events` row alongside every `tasks` UPDATE.** The events table is the audit log; updates without events are invisible to downstream readers.
- **Always log `task_mentions` on non-action discussions** (e.g., task referenced in a meeting but no status change). Needed for dedup signal and Thinker's pattern detection.
- **Default to NEW task when unsure.** When the match-or-create LLM call has confidence < 0.8, create a new task with a `[NEEDS LINK?]` note in description. Easier to merge later than to lose context.
- **Never set `updated_at` manually** unless you're intentionally back-dating (the trigger handles it).
- **Never bypass `task-handler` for INSERT/UPDATE from inbound message classification.** Direct writes skip the dedup logic and pollute the dataset with duplicates.

---

## 2. slackSend — Queue-First Slack Messages

### For Routine Messages (channel posts, summaries, proposals)
Send via OpenClaw's native Slack plugin directly. If the send fails, queue to outbox:
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO outbox (target, payload, status) VALUES ('slack', '{\"channel\": \"<channel_id>\", \"message\": \"<text>\", \"thread_ts\": \"<optional>\"}', 'pending');"
```

### For Critical Messages (alerts, escalations, P0 DMs)
Queue to SQLite outbox FIRST, then send, then mark sent. Critical messages must never be silently lost.

### Retry
- Retry after 5 minutes, max 5 retries
- If Slack is down for 30+ minutes: use WhatsApp backup for P0 alerts only (see whatsapp-send skill)

### Channel Routing

| Channel | ID | Use For |
|---|---|---|
| #project-management | C0ANKDD664A | Proposals, sprint plans, Thinker observations, commands |
| #alaska-daily-pulse | C0APP7V6H8C | Daily Pulse, Weekly Digest |
| #alaska-alerts | C0APP7X4TMJ | Risk reports, critical escalations, budget alerts |
| DMs | per person | Nudges, private escalations, pre-call briefs |

Post to the correct channel. Never post nudges or individual performance data to public channels. DMs for private/sensitive content.

---

## 3. reportHealth — Agent Heartbeat Protocol

Every agent reports its status after completing each work cycle.

### How to Report

Write a heartbeat to the Agent Signals database in Notion:
- **Signal:** `<agent_name> heartbeat`
- **From Agent:** `<agent_name>`
- **To Agent:** (empty for heartbeats)
- **Type:** `status`
- **Status:** one of the health statuses below
- **Details:** what happened, what was produced, any errors, duration

Queue to outbox first (target: `notion`), then write via MCP.

### Health Statuses

| Status | Meaning |
|---|---|
| `healthy` | Completed successfully |
| `degraded` | Completed with warnings (partial data, skipped items) |
| `error` | Failed, needs investigation |
| `silent` | No heartbeat received (detected by monitor, not self-reported) |

### Alert Threshold

If any agent is silent for >30 minutes during business hours (9 AM – 7 PM IST), post to `#alaska-alerts`:
```
*Agent Health Alert*
[agent_name] has not reported in [X] minutes.
Last known status: [status] at [time]
Impact: [what this agent does that isn't happening]
```

---

## 4. logTokenUsage — Budget Tracking & Enforcement

### Monthly Budget: $800–1,200/month (~$30-40/day)

**Token usage is tracked at the OpenClaw platform level** (per-cron-run metrics in the gateway). Agents do not self-report token usage — the platform records `usage.input_tokens` and `usage.output_tokens` per run automatically.

When checking costs manually, query the token_usage table:
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO token_usage (agent, input_tokens, output_tokens, estimated_cost) VALUES ('<agent_name>', <input>, <output>, <cost>);"
```

### Cost Estimation

**Primary model: Claude Opus 4 (most agents)**
- Input: $15 per 1M tokens
- Output: $75 per 1M tokens

**Routine/lightweight agents (if switched to Sonnet):**
- Input: $3 per 1M tokens
- Output: $15 per 1M tokens
- Candidates for Sonnet: Doc Keeper (event-driven), Pre-Call Brief (mostly no-ops), Sprint Operator (weekly)

### Daily Budget Caps

| Agent | Daily Cap | Alert at 80% |
|---|---|---|
| Thinker | $12 | $9.60 |
| Meeting Intelligence | $8 | $6.40 |
| Follow-Through (3 runs) | $6 | $4.80 |
| Daily Pulse | $4 | $3.20 |
| Risk Radar | $4 | $3.20 |
| Slack Commands | $3 | $2.40 |
| Proposal Loop | $3 | $2.40 |
| Doc Keeper | $2 | $1.60 |
| Sprint Operator | $2 | $1.60 |
| Pre-Call Brief | $1 | $0.80 |
| **Total** | **$45** | **$36** |

### Budget Queries

**Today's usage by agent:**
```bash
sqlite3 /data/queue/alaska.db "SELECT agent, SUM(input_tokens) as input, SUM(output_tokens) as output, ROUND(SUM(estimated_cost), 4) as cost FROM token_usage WHERE date(created_at) = date('now') GROUP BY agent;"
```

**Today's total:**
```bash
sqlite3 /data/queue/alaska.db "SELECT ROUND(SUM(estimated_cost), 4) as total_cost FROM token_usage WHERE date(created_at) = date('now');"
```

**Monthly total:**
```bash
sqlite3 /data/queue/alaska.db "SELECT agent, ROUND(SUM(estimated_cost), 2) as cost FROM token_usage WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now') GROUP BY agent;"
```

### Enforcement Protocol

1. **At 80% of any cap:** Post warning to `#alaska-alerts`:
   ```
   *Budget Warning*
   [agent] has used $[X] of $[cap] daily budget ([%]).
   ```

2. **At 100% of per-agent cap:** Reduce that agent's activity:
   - Cron agents: skip non-critical runs for the rest of the day
   - Event-driven agents: process only P0/P1 priority items
   - Thinker: pause hourly batches, resume next day

3. **At 100% of total daily cap ($45):** Pause ALL non-critical agents. DM Abhinav:
   ```
   *Daily budget cap reached ($35)*
   Breakdown: [per-agent costs]
   Non-critical agents paused until tomorrow.
   Override? Reply "resume" to lift the cap for today.
   ```

### Reporting
- Include token usage summary in Daily Pulse report (Section: *System Costs*)
- Include weekly spend + projected monthly total in Weekly Digest
- Track month-over-month trends

---

## 5. Agent Signal Handoff Pattern

All agent-to-agent communication goes through the **Agent Signals** database in Notion. Never use direct messaging between agents.

### Sending a Signal

Write to Agent Signals:
- **Signal:** descriptive title (e.g., "Meeting processed: [name]", "Proposal #P-[id] confirmed")
- **From Agent:** sender agent name
- **To Agent:** target agent name (or "All" for broadcast)
- **Type:** `handoff` / `alert` / `query` / `status`
- **Status:** always start as `pending`
- **Details:** JSON with structured data relevant to the signal

Queue to outbox first (target: `notion`), then write via MCP.

### Signal Types

| Type | Meaning | Example |
|---|---|---|
| `handoff` | "I'm done, your turn" — includes work product | Meeting Intelligence → Proposal Loop |
| `alert` | "Something needs attention" — no work product | Risk Radar → Sprint Operator |
| `query` | "I need information from you" — expects response | Thinker → any agent |
| `status` | Heartbeat or status update — informational | Any agent → heartbeat |

### Receiving Signals

On each invocation, check for pending signals:
1. Read Agent Signals where `To Agent = <myName>` AND `Status = pending`
2. Process each signal
3. Update Status to `acknowledged`
4. After full resolution, update to `resolved`

### Rules
- Never process the same signal twice — check Status before processing
- Always include enough context in Details that the receiving agent can act without additional lookups
- Queue the signal write to outbox before sending via Notion MCP

---

## 6. Communication Standards

Every Slack message from Alaska must follow these rules. No exceptions.

### Formatting
- **Bold:** `*bold*` (single asterisks). NEVER `**double**` — that's Markdown, not Slack mrkdwn.
- **Italic:** `_italic_`
- **Code:** `` `inline` `` or ``` ```block``` ```
- **Sections:** separate with blank lines, not dividers

### Names
- **First names only.** Never email addresses.
- Map Fireflies speaker names / Slack IDs to Team Roster entries.
- If you can't resolve a name, use the name as-is — never show raw emails.

### Message Discipline
- **Never leak internal reasoning.** No "Let me check Notion..." or "Now I'll update the database..." — your Slack messages are clean, final outputs only.
- **Never truncate mid-sentence.** If a message is too long, shorten the content — don't cut it off.
- **Split messages over 3000 characters** into multiple clean messages. Never exceed 3000 chars per message.
- **No transcript timestamps** (like 27:06). Meaningless in Slack.
- **No emojis** except `✓` for shipped items.

### Urgency Formatting
- **Critical/P0:** prefix with `*CRITICAL:*`
- **Alerts:** prefix with `*Alert:*`
- **Routine:** no prefix

### Narration Ban

DO NOT post things like:
- "Let me find the proposal in Notion..."
- "Now I'll apply the modifications..."
- "Good, Notion is updated."
- "I've been monitoring and noticed..."

These are internal steps. Only post final outputs, questions, and actionable information.

---

## 7. Error Handling & Graceful Degradation

### Error Handling by Service

**Notion down:**
- Save writes to SQLite outbox. Continue with Slack posts and other work.
- On next run, retry failed writes from outbox.
- After 3 failures → DM Abhinav: "Notion API is failing. [X] writes queued locally."

**Slack down:**
- Save messages to SQLite outbox. Continue with Notion writes and data processing.
- Retry on next run. If down 30+ min → WhatsApp backup for P0 alerts only.

**Fireflies API error:**
- Log the error, skip this transcript. Mark as `failed` in `processed_meetings`.
- Retry next cron run. After 3 failures on same transcript → alert Abhinav.

**Bad/Empty transcript:**
- Empty or <1 minute → skip silently
- Corrupted JSON → log error, skip, alert Abhinav
- <3 sentences → skip with note "Transcript too short"

**LLM extraction failure:**
- Retry once with simplified prompt
- If still fails → save raw transcript to Notion with note "Automated extraction failed — manual review needed"
- Never silently drop a meeting

### Retry Strategy

| Failure | Retry After | Max Retries | Fallback |
|---|---|---|---|
| Notion API | Next agent run (~30 min) | 3 | Alert Abhinav, keep in queue |
| Slack API | 5 minutes | 5 | WhatsApp backup for critical |
| Fireflies API | Next cron (~30 min) | 3 | Skip transcript, alert |
| LLM extraction | Immediate | 1 | Save raw, flag for manual review |

### Graceful Degradation Matrix

| Service Down | What Still Works |
|---|---|
| Notion | Slack posts, SQLite queue, Fireflies polling, all data processing |
| Slack | Notion writes, SQLite queue, all data processing |
| Fireflies | Everything except new transcript processing |
| **SQLite** | **NOTHING — this is critical. Alert immediately through any available channel.** |

### System Health Checks (Every 30 Minutes)

```bash
# Check Notion
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer ${NOTION_API_KEY}" "https://api.notion.com/v1/users/me" -H "Notion-Version: 2022-06-28"

# Check Fireflies
curl -s -o /dev/null -w "%{http_code}" -X POST "https://api.fireflies.ai/graphql" -H "Authorization: Bearer ${FIREFLIES_API_KEY}" -H "Content-Type: application/json" -d '{"query": "{ user { email } }"}'
```

Log health status:
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO system_health (service, status, response_code) VALUES ('<service>', '<ok|error>', <code>);"
```

If any service has 3+ consecutive failures (90 minutes), DM Abhinav:
```
*System Health Alert*
[Service] has been unresponsive for [X] minutes.
Last error: [error code/message]
Impact: [what's affected]
Queued writes: [X] pending in local queue
```

### Agent Silence Detection

If Alaska hasn't posted to Slack or written to Notion for 30+ minutes during business hours AND active crons should have fired → likely gateway crash. Railway's HEALTHCHECK should catch this. On gateway restart, process queued outbox items first.

---

## 8. Anti-Hallucination Checklist

Every agent must verify data before writing or posting. This is the final gate before any external action.

### Before Writing to Notion
- [ ] All extracted data was **explicitly stated** (not inferred from context)
- [ ] Select field values match existing options **exactly** (see Section 1)
- [ ] Required fields are populated (Due Date on any task entry; Owner set via roster Notion ID per "Owner field — enabled" above, fallback to first-name-in-Notes only if no ID)
- [ ] No duplicate entries — check for existing similar entries first
- [ ] Page/database IDs are real, not fabricated

### Before Posting to Slack
- [ ] Names resolve to real team members in Team Roster
- [ ] No fabricated dates, metrics, or status information
- [ ] No raw email addresses — first names only
- [ ] If uncertain about any detail, flagged as `[NEEDS CLARIFICATION]`

### Before Creating Tasks
- [ ] Owner exists in Team Roster and is Available
- [ ] Due date was stated OR flagged as `[NEEDS DUE DATE]`
- [ ] Effort estimate has reasoning (not just guessed)
- [ ] Task is actionable and specific (not vague like "finalize the flow")
- [ ] No duplicate of an existing item in DAILY_STATE.md per-person sections or recent Meeting Notes

### Before Logging Decisions
- [ ] Decision was explicitly made ("Let's go with X"), not just discussed
- [ ] Decision-maker is identified
- [ ] Context/reasoning is captured
- [ ] Check for contradictions with existing decisions — if found, flag

### Universal Rule

**If you are uncertain about ANY extracted information, flag it as `[NEEDS CLARIFICATION]` and ask the team to confirm. Never invent details that weren't explicitly stated.**

Distinguish "someone mentioned it" from "someone committed to it." Only commitments become tasks.

---

## Toolkit Compliance (For Thinker Agent)

When quality-checking other agents, verify they follow these patterns:
- Are writes going through the outbox queue first?
- Are Slack messages using correct mrkdwn formatting?
- Are Agent Signals following the standard handoff pattern?
- Are select field values using exact existing options?
- Is token usage being logged after LLM calls?
- Are budget caps being respected?

Flag deviations to Abhinav via DM. Don't block the pipeline — advise.
