# Alaska v2 Task Model — Design Spec

**Status:** Draft for review
**Date:** 2026-05-23
**Author:** Brainstormed with Abhinav (Head of Product & Design, BON Credit)
**Plan:** `~/.claude/plans/lazy-bubbling-clarke.md` (v2.2 stabilization — Phase 2.3)

---

## Context

The Notion Sprint Board was retired in v2.2 stabilization (2026-05-23). The current backing store for "what each person is working on" is `DAILY_STATE.md` — per-person markdown sections (NOW / LAST COMMITTED / DONE RECENTLY / BLOCKED) rewritten after each team call by Meeting Intelligence.

`DAILY_STATE.md` works as a narrative dashboard but has four structural gaps:

1. **No persistent task identity.** Items live as narrative bullets. When Meeting Intelligence rewrites the file, items can vanish, merge, or re-extract with different wording. The pre-call standup brief (8:30 PM IST) often shows stale or repeated items because Alaska can't tell yesterday's "chart UI" from today's "chart UI in V2".
2. **No async capture from Slack.** Tasks only enter the system via meetings. DMs to Alaska, channel messages where work gets discussed, and cross-person assignments live in Slack scrollback and get lost.
3. **No history or audit trail.** `DAILY_STATE.md` is point-in-time. "When did Pankaj start the chart UI?" or "what did Sandeep ship last month?" can't be answered.
4. **No scheduled/proactive surfacing.** "Remind me about X in 5 days" or "follow up with Sandeep in 48 hours" have no primitive. Alaska is purely reactive.

This spec defines the replacement: an event-sourced task graph in SQLite, with a universal Slack/meeting capture layer, a scheduling engine, and projections to Slack + Notion for visibility. The model is designed for a 6–9 person pre-PMF startup where the team interacts entirely through Slack and rarely opens Notion.

## Goals (success criteria)

1. **Stable task identity** — every committed work item has a T-N ID that survives across sessions, meetings, and file rewrites.
2. **Universal capture** — tasks created from meetings, DMs, standup replies, and channel messages all land in one place with a stable ID and full provenance.
3. **Cross-person workflow that closes the loop** — when one person assigns another (in any surface), the assignee is DM'd, the public channel is notified, the assignee can `ack` or `pass`, and the task surfaces in the assignee's standup brief.
4. **Scheduled and recurring actions** — "remind me in N days", "follow up if not done by Friday", "every Monday at 9 AM run X" — all expressible as scheduled actions with a single dispatcher.
5. **Dedup across surfaces** — same task discussed in DM + standup reply + meeting becomes one task with three logged mentions, not three confused entries.
6. **Pre-call brief that's actually useful** — surfaces active tasks by stable ID, separates new-since-yesterday from carryover, shows reminders due today, calls out tasks awaiting ack.
7. **No regression in current capability** — DAILY_STATE.md narrative output still works, Meeting Intelligence still drives meeting comprehension, Decision Log / Blockers / Changelog Notion DBs unchanged.

---

## Architecture overview

Four layers. Each layer does one thing.

```
═══════════════════════════════════════════════════════════════════════════════
LAYER 1: HUMAN INTERACTION SURFACES
═══════════════════════════════════════════════════════════════════════════════

  HIGH TRUST (autonomous task action)
  ┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
  │ Meetings           │ │ DMs to Alaska      │ │ Standup replies    │
  │ (Fireflies)        │ │                    │ │ (#daily-standup    │
  │ 9 PM team call     │ │ ad-hoc, anytime    │ │  thread 8:30 PM)   │
  │ + ad-hoc + 1:1s    │ │                    │ │                    │
  │ + external calls   │ │                    │ │                    │
  └─────────┬──────────┘ └─────────┬──────────┘ └─────────┬──────────┘
            │                      │                       │
  MEDIUM TRUST (acts with confirmation loop)               │
  ┌─────────────────────────────────────────┐              │
  │ Slack channel messages with @-mention   │              │
  │ or task-shaped language                 │              │
  └─────────────┬───────────────────────────┘              │
                │                                          │
  LOW TRUST (proposes to Abhinav only)                     │
  ┌─────────────────────────────────────────┐              │
  │ All other channel chatter (Thinker)     │              │
  └─────────────┬───────────────────────────┘              │
                │                                          │
═══════════════════════════════════════════════════════════════════════════════
LAYER 2: INTERPRETATION (classify intent + route)
═══════════════════════════════════════════════════════════════════════════════
                ▼                                          ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ Intent Classifier (always-on, batched 5-min for channel/observation,   │
  │ synchronous for DMs)                                                   │
  │                                                                        │
  │ Classifies each non-trivial message into one of:                       │
  │   TASK_CREATE  TASK_UPDATE  TASK_ASSIGN  TASK_BLOCKER                  │
  │   REMINDER_REQUEST  DECISION_RECORDED  STATUS_QUERY                    │
  │   NON_WORK_CHAT (ignore)  AMBIGUOUS (DM Abhinav)                       │
  │                                                                        │
  │ Routes to the appropriate handler skill below.                         │
  └─────────────────────────────────┬──────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼────────────────────────────┐
        ▼                           ▼                            ▼
  Meeting Intelligence       Slack Commands              Pre-Call Brief
  (existing — extended)      (existing — extended)       (existing — extended)
        │                           │                            │
        │ + intent-based task       │ + cross-person workflow    │ + structured
        │   match-or-create         │   + reminder parsing       │   T-ID replies
        │                                                        │
═══════════════════════════════════════════════════════════════════════════════
LAYER 3: SOURCE OF TRUTH (SQLite at /data/queue/alaska.db)
═══════════════════════════════════════════════════════════════════════════════
                                    │ all writes land here
                                    ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │  tasks ─────┬──── task_events (audit log of every state change)        │
  │             ├──── task_mentions (every reference, any surface)         │
  │             ├──── task_categories (V2, MoneyLine, Marketing, etc.)     │
  │             └──── blockers (linked)                                    │
  │                                                                        │
  │  scheduled_actions (one-shot reminders + recurring routines)           │
  │             │                                                          │
  │             └──── linked to task OR standalone                         │
  │                                                                        │
  │  routine_proposals (team-wide routine requests pending Abhinav ack)    │
  └─────────────────────────────────┬──────────────────────────────────────┘
                                    │
═══════════════════════════════════════════════════════════════════════════════
LAYER 4: OUTPUT (project SQLite state back to humans)
═══════════════════════════════════════════════════════════════════════════════
                                    │
       ┌────────────────────────────┼─────────────────────────────┐
       ▼                            ▼                             ▼
  Reminder Dispatcher          Pre-Call Brief              Daily Pulse
  (new — every 15 min)         (8:30 PM IST)               (9 AM IST)
  Fires due scheduled_actions  Personalized per-person     Team-board snapshot
                                                            → #project-management

  Notion Projection            Follow-Through              Sprint Operator
  (4 UTC daily)                Doc Keeper                  (Monday DM helper)
  → read-only Active Work DB   Risk Radar
                               Thinker
                               (all read from SQLite)
```

**Three trust tiers for input:**

| Tier | Surfaces | Behavior |
|---|---|---|
| **High** | Meeting transcripts, DMs to Alaska, standup thread replies | Autonomous task creation/update. Items extracted here become tasks immediately. |
| **Medium** | Channel messages with @-mention OR task-shaped language with assignee | Tasks created with status `pending_acceptance`. Auto-DM the proposed assignee for ack. |
| **Low** | All other channel chatter | Thinker observes for pattern detection only. Surfaces *proposals* to Abhinav DM; never creates tasks autonomously. |

---

## Layer-by-layer detail

### Layer 1 — Surfaces

No change to the surfaces themselves. The change is *what Alaska does with them*:

| Surface | Today | New |
|---|---|---|
| Meeting transcript (Fireflies) | Read by Meeting Intelligence every 30 min, extracts commitments into DAILY_STATE.md per-person sections | Same + match-or-create against tasks table with stable T-IDs |
| Slack DMs to Alaska | Handled by slack-commands skill for queries; tasks discussed in DMs don't get tracked | Tasks/blockers/reminders extracted by intent classifier and written to tasks/scheduled_actions |
| Standup thread replies | Parsed loosely; no structured task linkage | Parsed against pre-call brief T-IDs; replies like "T-42 done" update SQLite cleanly |
| Channel messages (#project-management, #agentic-ai, etc.) | Thinker observes for high-confidence signals only | Intent classifier processes all messages; task-shaped language with @-mentions triggers `pending_acceptance` task creation flow |

### Layer 2 — Intent Classifier (new always-on skill)

A new skill `intent-classifier` that runs on every Slack message Alaska sees. Two modes:

| Mode | Trigger | Latency |
|---|---|---|
| **Synchronous** | DMs to Alaska | Immediate (within seconds) |
| **Batched** | All channel messages | Every 5 min via cron (messages queue to SQLite intent_inbox table) |

**Intent types (9):**

| Intent | Example | Routes to |
|---|---|---|
| `TASK_CREATE` | "starting on chart UI", "I'll fix this profile bug" | Task handler — create new task with creator=speaker, owner=speaker |
| `TASK_UPDATE` | "T-42 done", "still working on it", "merged the PR" | Task handler — match T-ID or fuzzy-match by owner+title; update status |
| `TASK_ASSIGN` | "@Shailesh @Tarun look at users 2854, 2891, 2894 in 48h" | Cross-person workflow (Section: Cross-person assignment) |
| `TASK_BLOCKER` | "blocked on Plaid docs", "can't proceed until X" | Create blocker, link to active tasks for speaker, update task status |
| `REMINDER_REQUEST` | "remind me about X in 5 days", "every Friday at 5 PM..." | Scheduling engine — create scheduled_action |
| `DECISION_RECORDED` | "let's go with approach A", "we're cancelling X" | Decision Log Notion DB (existing flow, unchanged) |
| `STATUS_QUERY` | "what's on my plate?", "any blockers?", "what shipped this week?" | Slack Commands — query SQLite, respond in same thread/DM |
| `NON_WORK_CHAT` | greetings, banter, lunch plans | Ignore |
| `AMBIGUOUS` | unclear intent or low confidence | Log to intent_inbox with flag; DM Abhinav daily digest of ambiguous items |

**Classifier prompt** runs against the small fast model (Sonnet, ~300 input tokens per message). Output is a JSON object: `{intent, confidence, entities: {task_ids, owners, dates, ...}, reasoning}`. Confidence below 0.7 → AMBIGUOUS.

**Token budget:** estimated ~50 channel messages/day × $0.003/1K input × ~600 tokens avg = ~$0.10/day. Negligible. DMs add maybe 10/day = ~$0.02/day.

### Layer 3 — SQLite schema

Database: `/data/queue/alaska.db` (existing, on Railway persistent volume).

#### Table: `tasks`

```sql
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT UNIQUE NOT NULL,            -- 'T-1', 'T-2', ...
  title TEXT NOT NULL,                     -- short, scannable
  description TEXT,                        -- longer context
  status TEXT NOT NULL DEFAULT 'active',   -- active | blocked | pending_acceptance | done | dropped
  priority TEXT,                           -- P0 | P1 | P2 | P3 | NULL
  effort TEXT,                             -- XS | S | M | L | XL | NULL
  owner_slack_id TEXT NOT NULL,            -- primary assignee
  additional_owners TEXT,                  -- JSON array of Slack IDs
  creator_slack_id TEXT NOT NULL,          -- who created the task (or 'agent:meeting-intelligence')
  assigner_slack_id TEXT,                  -- who assigned (when different from creator)
  visibility TEXT NOT NULL DEFAULT 'personal',  -- personal | team (computed at create time)
  category TEXT,                           -- 'V2' | 'MoneyLine' | 'Marketing' | 'Infra' | NULL
  source TEXT NOT NULL,                    -- meeting | slack_dm | slack_channel | standup_reply | manual
  source_ref TEXT,                         -- Fireflies ID+timestamp, or Slack message URL
  due_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  done_at DATETIME,
  parent_task_id TEXT REFERENCES tasks(task_id)
);

CREATE INDEX idx_tasks_owner_status ON tasks(owner_slack_id, status);
CREATE INDEX idx_tasks_created ON tasks(created_at);
CREATE INDEX idx_tasks_status_due ON tasks(status, due_at);
```

**Computed fields:**

- `visibility` is computed at creation time:
  - `personal` if `owner_slack_id == creator_slack_id` AND `additional_owners is empty/null`
  - `team` otherwise
  - **Exception:** all tasks with `source = 'meeting'` get `visibility = team` (meetings are public by nature)
- `task_id` is generated as `'T-' || (max(id) + 1)`.

#### Table: `task_events`

Append-only audit log of every state change.

```sql
CREATE TABLE task_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES tasks(task_id),
  event_type TEXT NOT NULL,
    -- created | status_changed | owner_changed | due_changed |
    -- priority_changed | ack | pass | reassigned | dedup_decision |
    -- comment | mention | linked_to_blocker | scheduled_action_linked
  actor_slack_id TEXT,                     -- who triggered (or 'agent:<name>')
  old_value TEXT,                          -- JSON for the before state
  new_value TEXT,                          -- JSON for the after state
  context TEXT,                            -- free-text reasoning (e.g., dedup match reasoning)
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_task_events_task ON task_events(task_id, created_at);
```

#### Table: `task_mentions`

Every reference to a task across any surface — even discussion without state change.

```sql
CREATE TABLE task_mentions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES tasks(task_id),
  surface TEXT NOT NULL,                   -- meeting | slack_dm | slack_channel | standup_reply
  mention_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actor_slack_id TEXT,
  excerpt TEXT,                            -- the quoted text
  source_ref TEXT,                         -- Fireflies ID+timestamp or Slack message URL
  mention_type TEXT                        -- status_update | discussion | assignment | commitment | reference
);

CREATE INDEX idx_task_mentions_task ON task_mentions(task_id, mention_at);
```

#### Table: `task_categories`

Lightweight grouping for cross-task queries ("what shipped in V2 last sprint?").

```sql
CREATE TABLE task_categories (
  name TEXT PRIMARY KEY,                   -- 'V2', 'MoneyLine', 'Marketing', 'Infra', ...
  description TEXT,
  active BOOLEAN NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Seed with a few categories pulled from DAILY_STATE.md `This Week's Goals` patterns. Anyone can add new categories via Alaska DM.

#### Table: `blockers` (extends existing pattern, links to tasks)

```sql
CREATE TABLE blockers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  blocker_id TEXT UNIQUE NOT NULL,         -- 'B-1', 'B-2', ...
  title TEXT NOT NULL,
  description TEXT,
  blocking_task_ids TEXT,                  -- JSON array of T-N IDs
  owner_slack_id TEXT,                     -- who's resolving
  raised_by_slack_id TEXT,                 -- who raised
  status TEXT NOT NULL DEFAULT 'active',   -- active | resolved
  raised_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at DATETIME,
  resolution TEXT,
  source TEXT,                             -- same enum as tasks.source
  source_ref TEXT
);
```

The existing Notion Blockers DB stays in sync (cron projects from SQLite to Notion). Old workflow preserved; new SQLite becomes source of truth.

#### Table: `scheduled_actions`

The scheduling engine table. Handles one-shot reminders + recurring routines + auto-followups.

```sql
CREATE TABLE scheduled_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action_id TEXT UNIQUE NOT NULL,          -- 'SA-1', 'SA-2', ...
  action_type TEXT NOT NULL,
    -- remind | surface_task | escalate | recurring_routine | auto_followup
  fire_at DATETIME NOT NULL,
  recurrence_rule TEXT,                    -- RRULE string (e.g., 'FREQ=WEEKLY;BYDAY=FR;BYHOUR=17')
                                           -- NULL for one-shot
  recipient_slack_id TEXT,                 -- person to ping (NULL if channel-targeted)
  recipient_channel_id TEXT,               -- channel to post to (NULL if person-targeted)
  linked_task_id TEXT REFERENCES tasks(task_id),
  payload TEXT NOT NULL,                   -- JSON: message, options, links, etc.
  scope TEXT NOT NULL DEFAULT 'personal',  -- personal | team
  created_by_slack_id TEXT NOT NULL,
  approved_by_slack_id TEXT,               -- for team-scope; references Abhinav's Slack ID
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | fired | cancelled | snoozed
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  next_fire_at DATETIME,                   -- for recurring, computed after each fire
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fired_at DATETIME
);

CREATE INDEX idx_scheduled_pending ON scheduled_actions(status, fire_at);
```

**Action types:**

| Type | Use | Example |
|---|---|---|
| `remind` | One-shot personal reminder | "Remind me about the deck on Friday" |
| `surface_task` | Re-surface a specific task in standup brief | Internal — Alaska schedules this when a task is snoozed |
| `escalate` | Notify Abhinav + assigner if no action by time T | Auto-attached to TASK_ASSIGN, fires if no ack in 2 hours |
| `recurring_routine` | RRULE-based, fires repeatedly | "Every Monday 9 AM, DM Abhinav the sprint planning agenda" |
| `auto_followup` | Conditional: fire only if task hasn't transitioned | "Follow up with Sandeep on T-42 in 48h" → fires only if T-42 still active |

#### Table: `routine_proposals`

Team-scope routines proposed by non-admins; require Abhinav approval.

```sql
CREATE TABLE routine_proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proposal_id TEXT UNIQUE NOT NULL,
  proposed_by_slack_id TEXT NOT NULL,
  description TEXT NOT NULL,
  proposed_payload TEXT NOT NULL,          -- JSON: same shape as scheduled_actions.payload
  proposed_recurrence_rule TEXT NOT NULL,
  proposed_recipient TEXT,
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | declined | expired
  abhinav_response TEXT,                   -- optional notes
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  responded_at DATETIME,
  expires_at DATETIME                      -- auto-expires 7 days after creation
);
```

On approval, creates the corresponding `scheduled_actions` row and notifies the proposer.

#### Table: `intent_inbox`

Stores incoming Slack channel messages awaiting batched intent classification.

```sql
CREATE TABLE intent_inbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_ts TEXT NOT NULL,                -- Slack timestamp
  channel_id TEXT NOT NULL,
  author_slack_id TEXT NOT NULL,
  message_text TEXT NOT NULL,
  thread_ts TEXT,                          -- if in a thread
  processed BOOLEAN NOT NULL DEFAULT 0,
  intent TEXT,                             -- filled in by classifier
  confidence REAL,                         -- 0.0 to 1.0
  classifier_output TEXT,                  -- full JSON response for debugging
  processed_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_intent_unprocessed ON intent_inbox(processed, created_at);
```

The 5-min classifier cron processes unprocessed rows. DMs to Alaska bypass this table (handled synchronously).

---

### Layer 4 — Output layer

#### 4.1 Reminder Dispatcher (new cron, every 15 min)

```python
# Pseudo-code
due_actions = sqlite("""
  SELECT * FROM scheduled_actions
  WHERE status = 'pending' AND fire_at <= datetime('now')
  ORDER BY fire_at ASC LIMIT 20
""")

for action in due_actions:
    try:
        execute_action(action)  # DM / post / surface / escalate
        sqlite("UPDATE scheduled_actions SET status='fired', fired_at=now WHERE id=?", action.id)
        if action.recurrence_rule:
            next_fire = compute_next_rrule(action.recurrence_rule, after=now)
            sqlite("INSERT INTO scheduled_actions ... fire_at=?, ...", next_fire)
    except Exception as e:
        sqlite("UPDATE scheduled_actions SET attempts=attempts+1 WHERE id=?", action.id)
        if action.attempts + 1 >= action.max_attempts:
            sqlite("UPDATE scheduled_actions SET status='cancelled' WHERE id=?", action.id)
            dm_abhinav(f"Scheduled action {action.action_id} failed after {action.max_attempts} attempts: {e}")
```

Cron schedule: `*/15 * * * *` UTC (every 15 min, 24/7). Adds 96 invocations/day; most return quickly with no due actions.

#### 4.2 Pre-Call Brief (8:30 PM IST — existing cron, new content)

Pre-call brief is generated per person from SQLite. Format:

```
Shailesh — Wednesday, May 24

ACTIVE (3):
• T-67  Audit users 2854, 2891, 2894 — Darwin assigned Wed 8:50 PM, due Fri
        [you ack'd Wed 9:12 PM]
• T-65  Validate V2 PRs 82-86 — committed in Tue meeting
        [last activity: 2 commits to bon_app yesterday]
• T-58  Card linking RCA — ongoing since May 19, no update in 48h ⚠

REMINDERS DUE TODAY (1):
• Check status of MoneyLine sandbox question to Kathleen
  [you set this reminder Mon for today]

NEW SINCE YESTERDAY (1):
• T-67 Audit users (Darwin → you + Tarun, Wed 8:50 PM in #project-management)

NEEDS YOUR ACK (0): none pending

BLOCKED (0): none

Reply format:
  T-N done             — mark complete
  T-N blocked by X     — log blocker, pause nudges
  T-N active           — confirm still working
  new: <description>   — capture new task right now
  remind me in N days about X   — schedule a future surface
  reassign T-N to <name>        — push to someone else (needs ack)
  on leave             — pause all today

Team call in 30 min.
```

**Query:**

```sql
-- Active tasks
SELECT task_id, title, status, due_at, updated_at,
       (SELECT MAX(mention_at) FROM task_mentions WHERE task_id = t.task_id) AS last_mention
FROM tasks t
WHERE owner_slack_id = ? AND status IN ('active', 'blocked', 'pending_acceptance')
ORDER BY priority ASC, due_at ASC NULLS LAST;

-- Reminders due today
SELECT * FROM scheduled_actions
WHERE recipient_slack_id = ? AND status = 'pending'
  AND fire_at BETWEEN date('now') AND date('now', '+1 day');

-- New since yesterday
SELECT task_id, title, created_at FROM tasks
WHERE owner_slack_id = ? AND created_at > date('now', '-1 day');

-- Awaiting ack
SELECT task_id, title FROM tasks
WHERE owner_slack_id = ? AND status = 'pending_acceptance';
```

Reply parsing: regex + LLM fallback. Stable T-IDs make this near-deterministic for the common cases.

#### 4.3 Daily Team-Board Snapshot (9 AM IST — replaces some Daily Pulse content)

Posted to #project-management as part of Daily Pulse. Format:

```
*Team Board — Thursday, May 24*

Active tasks: 23 across 7 people | Done overnight: 4 | Blocked: 2

*By person:*
• Sandeep (5 active, 1 blocked): V2 API dev, card matching fix, T-58 RCA…
• Pankaj (3 active): TestFlight build, chart UI animation fix, T-65 PR review…
• Shailesh (3 active, ack-pending T-67): V2 PR validation, card linking RCA…
• …

*New since yesterday:* T-67 (Darwin → Shailesh+Tarun), T-68 (Sandeep self), …
*Done overnight:* T-60, T-61, T-62, T-63 (see Changelog)
*Blocked >24h:* T-58 (Shailesh, card linking) — investigation continuing

Full picture in Notion: <link to Active Work projection>
Reply 'team status' to me for live snapshot anytime.
```

#### 4.4 Notion Projection (read-only Active Work DB)

Cron: 4 UTC daily (after Meeting Intelligence overnight processing finishes).

A new Notion DB `Active Work` (separate from the retired Sprint Board). Schema mirrors SQLite tasks:

- `Task ID` (title) — "T-67"
- `Title` (rich text)
- `Owner` (people — uses Notion User IDs from MEMORY.md)
- `Additional Owners` (people, multi)
- `Status` (select: Active / Blocked / Pending Acceptance / Done / Dropped)
- `Priority` (select: P0/P1/P2/P3 or empty)
- `Effort` (select: XS/S/M/L/XL or empty)
- `Category` (select: V2 / MoneyLine / Marketing / Infra / Other)
- `Created From` (select: Meeting / Slack DM / Slack Channel / Standup Reply / Manual)
- `Source Message` (URL — links back to Fireflies meeting or Slack message)
- `Created` (date)
- `Due` (date)
- `Done At` (date)
- `Notes` (rich text)

Cron behavior:

1. Query SQLite for all tasks updated in the last 24h.
2. For each: upsert into Notion (search by `Task ID` field, create or update).
3. Mark `Done` tasks but don't delete (history).
4. Log every write to `task_events` with `event_type='notion_synced'`.

**Read-only is enforced socially, not technically.** The Notion DB allows edits, but the team is told: "Edits in Notion don't sync back to Alaska — change status via Slack." A weekly Thinker check flags drift.

---

## Cross-person assignment workflow (full sequence)

Example: Darwin posts in #project-management:

> "@Shailesh @Tarun please look at users 2854, 2891, 2894 in the next 48 hours"

**Step 1.** Slack message event → queued to `intent_inbox`.

**Step 2.** Intent classifier (next 5-min cron) → classifies as `TASK_ASSIGN` with entities: `{owners: ['U0AQ1UZHZ8D', '<Tarun-ID>'], assigner: 'U0APK8VTT62', deadline_text: '48 hours', topic: 'Audit users 2854, 2891, 2894'}`.

**Step 3.** Task handler:

```sql
INSERT INTO tasks (
  task_id, title, owner_slack_id, additional_owners,
  creator_slack_id, assigner_slack_id, status, visibility,
  source, source_ref, due_at, ...
) VALUES (
  'T-67', 'Audit users 2854, 2891, 2894',
  'U0AQ1UZHZ8D', '["<Tarun-ID>"]',
  'U0APK8VTT62', 'U0APK8VTT62',
  'pending_acceptance', 'team',
  'slack_channel', 'https://slack.com/archives/C0ANKDD664A/p<ts>',
  datetime('now', '+48 hours'), ...
);

INSERT INTO task_events (task_id, event_type, actor_slack_id, new_value, context)
VALUES ('T-67', 'created', 'agent:intent-classifier', '{...}',
        'Extracted from Slack channel message, intent confidence 0.94');
```

**Step 4.** Public reply in the original Slack thread (where Darwin posted):

> "Tracking as *T-67* for Shailesh + Tarun, due Friday 8:50 PM. DMing each of you for ack."

**Step 5.** DM Shailesh and DM Tarun in parallel:

> "Hey Shailesh, Darwin just assigned you *T-67* in #project-management:
> 'Audit users 2854, 2891, 2894' — due Fri 8:50 PM.
>
> Reply:
> • `ack` to accept
> • `pass with reason: <why>` to decline
> • `reassign to <name>` to redirect (needs the new person's ack)"

**Step 6.** Public-channel announcement (in addition to thread reply):

> "*New team task:* T-67 — Audit users 2854, 2891, 2894
> Owner: Shailesh + Tarun | Assigned by: Darwin | Due: Fri 8:50 PM"

(Posted as a separate message to #project-management for the running log.)

**Step 7.** Schedule auto-escalation:

```sql
-- 2-hour acceptance watch
INSERT INTO scheduled_actions (action_id, action_type, fire_at,
  recipient_slack_id, linked_task_id, payload, ...)
VALUES ('SA-101', 'escalate', datetime('now', '+2 hours'),
  'U07GKLVA9FE',  -- Abhinav
  'T-67',
  '{"reason": "no_ack_after_2h", "task": "T-67"}', ...);

-- 4-hours-before-due reminder for owner
INSERT INTO scheduled_actions (action_id, action_type, fire_at, ...)
VALUES ('SA-102', 'escalate', datetime('<due_at>', '-4 hours'), ...);
```

**Step 8.** Shailesh DMs Alaska: `ack`.

```sql
UPDATE tasks SET status='active', updated_at=now WHERE task_id='T-67';
INSERT INTO task_events (task_id, event_type, actor_slack_id, ...)
VALUES ('T-67', 'ack', '<Shailesh-ID>', ...);
UPDATE scheduled_actions SET status='cancelled' WHERE action_id='SA-101';
```

Alaska DMs back: "Got it, T-67 is yours. I'll surface it in your standup brief tonight."

**Step 9.** Tarun is silent for 2 hours. SA-101 fires:

> *(DM to Abhinav)*: "T-67 has not been ack'd by Tarun (Darwin assigned 2h ago). Shailesh did ack. Want me to proceed with Shailesh as sole owner, or chase Tarun?"

Abhinav responds → Alaska acts → audit log captures.

**Step 10.** Standup brief Wednesday 8:30 PM: T-67 appears in both Shailesh's NEW SINCE YESTERDAY and ACTIVE sections.

---

## Channel visibility rules

**Personal task** (`visibility = personal`):
- Created silently
- DM to owner only on create
- Status updates: DM to owner
- No public channel involvement

**Team task** (`visibility = team`):
- Created with public announcement in #project-management
- DM to each owner + additional_owner on create
- Status transitions (active → blocked, → done, reassignment) get a one-line update to #project-management
- The original creation thread (if applicable) gets a final "Closed: <reason>" reply when status → done or dropped

**Meeting-extracted tasks** are always `team` (overrides the auto-compute) since meetings are public by nature.

---

## Scheduling engine — examples by intent

| User message | Created scheduled_action |
|---|---|
| "Remind me about the budget deck on Friday" | `{type:'remind', fire_at:'2026-05-30T14:00:00Z', payload:{message:'Reminder you set Mon: budget deck'}, recipient:<asker>}` |
| "Follow up with Sandeep on T-42 in 48h" | `{type:'auto_followup', fire_at:'+48h', linked_task_id:'T-42', payload:{check_status_first:true, message_if_active:'Following up: T-42 — Sandeep, any update?'}}` |
| "Every Friday at 5 PM, DM me my open P0/P1 tasks" | `{type:'recurring_routine', fire_at:'<next Friday 5pm>', recurrence_rule:'FREQ=WEEKLY;BYDAY=FR;BYHOUR=17', payload:{query:'open_p0_p1_for_user', recipient:<asker>}, scope:'personal'}` |
| (Engineer) "Every Wednesday 3 PM post midweek check-in in #project-management" | Creates `routine_proposals` row (scope:'team'), DMs Abhinav for approval |
| "Snooze T-67 until Monday" | Updates T-67 status to 'snoozed', creates `surface_task` action for Monday |

---

## Migration — 5 phases

Each phase is an independent PR with its own rollout window.

### Phase A — Schema + intent classifier (logging only)

**Goal:** Get data flowing into the new tables without changing any behavior.

- Create all 7 new SQLite tables.
- Build `intent-classifier` skill — runs as 5-min cron + sync DM handler.
- Classifier writes intent + confidence to `intent_inbox` and logs to a new `classifier_audit` table.
- **No downstream action.** No tasks created, no DMs sent, no Slack posts. Pure observation.
- Run for 1 week.
- Verify accuracy by spot-checking 50-100 classifications: was the intent correct? Were entities extracted?

**Risk:** Zero. Pure addition.

### Phase B — Basic task lifecycle (Meeting Intelligence + DMs)

**Goal:** Tasks start landing in SQLite from the two high-trust surfaces.

- Meeting Intelligence: extend match-or-create to write tasks to SQLite alongside its existing DAILY_STATE.md updates.
- Slack Commands: DM-to-Alaska TASK_CREATE/TASK_UPDATE/TASK_BLOCKER intents become real writes.
- Pre-Call Brief: read from SQLite, show T-IDs, support T-N reply parsing.
- DAILY_STATE.md keeps being authoritative for narrative output in parallel — both systems run side by side.
- Run for 1-2 weeks. Compare pre-call brief quality before/after.

**Risk:** Low. Old system still primary.

### Phase C — Scheduling engine

**Goal:** "Remind me", "follow up", and recurring routines come online.

- Build dispatcher cron (every 15 min).
- Wire REMINDER_REQUEST intent → scheduled_actions writes.
- Personal routines work immediately. Team routines go to routine_proposals.
- Test with self-set reminders by Abhinav and 1-2 engineers first.

**Risk:** Low. New feature, no replacement.

### Phase D — Cross-person workflow

**Goal:** TASK_ASSIGN intent triggers the full ack loop.

- Build cross-person handler.
- Public channel announcements on team tasks.
- DM-to-owner with ack/pass/reassign reply options.
- Auto-escalation scheduling.
- 2-hour acceptance watch.
- Run for 1 week.

**Risk:** Medium — new public surface area for confusion. Land with clear visible behavior ("I'm tracking this as T-N").

### Phase E — Cutover

**Goal:** DAILY_STATE.md per-person sections become generated from SQLite. Notion projection live.

- Meeting Intelligence stops writing per-person sections directly.
- New "render DAILY_STATE.md from SQLite" pass runs after every Meeting Intelligence cycle.
- Notion projection cron live.
- Old narrative path retired (but committed in git for rollback).
- Universal channel observation (Thinker reads all channels).

**Risk:** Medium — but by now everything has been running in parallel for ~4 weeks.

---

## Authority model (simplified)

| Action | Who can do it |
|---|---|
| Create task for self | Anyone (engineer, founder, admin) |
| Create task for another person | Anyone — but assignee can `pass` |
| Update task status (own task) | Owner, additional_owner |
| Update task status (someone else's) | Anyone — but logs to task_events with `actor_slack_id`; flagged in audit |
| Reassign task | Current owner OR creator OR Abhinav — assignee must ack |
| Drop task | Owner, creator, or Abhinav |
| Create personal reminder/routine | Anyone (recipient = self only) |
| Create team-wide routine (channel post or multi-recipient) | Abhinav only; others can propose via `routine_proposals` |
| Approve team-wide routine proposal | Abhinav only |
| Sprint approval | Abhinav only (unchanged from existing alaska-core) |
| Change Alaska behavior, prompts, agent pipeline | Abhinav only (unchanged) |

---

## Open implementation questions

For the writing-plans phase to address:

1. **Channel allowlist for intent classifier.** Default: all channels Alaska is in. Should we add a quick exclude-list for `#random` or `#offtopic` channels if/when they exist?
2. **Intent classifier model choice.** Sonnet is the default fast/cheap option ($3/1M input). Should AMBIGUOUS items be retried with Opus before flagging to Abhinav?
3. **Notion projection conflict policy.** If a human edits the Notion projection (despite "read-only" social rule), should the next sync overwrite their edit silently, or flag it? Default: overwrite + log to task_events with `event_type='notion_drift_overwritten'`.
4. **task_id format.** `T-1, T-2, ...` is fine. Should we ever reset (e.g., per quarter) or just keep ascending forever? Recommend: ascending forever; reaches T-10000 in ~5 years at current pace.
5. **Recurring routine timezone handling.** Today everything is UTC internally. Should RRULE be stored in user's local TZ or UTC? Recommend: store in UTC, render in IST for display.
6. **What happens to T-IDs when task is hard-deleted (vs marked `dropped`)?** Recommend: never hard-delete tasks. `dropped` status keeps the ID alive for history.
7. **Bulk operations.** "Mark all my P3 tasks as dropped" — useful sometimes. Should we support bulk reply syntax in Phase B or defer to a later phase?
8. **Engineer-self-set vs Abhinav-approved boundary for routines.** What if an engineer wants a recurring DM to themselves that includes summary of *another person's* work ("every Monday, send me Sandeep's last week's commits"). That's still personal-recipient but touches another person's data. Recommend: still treat as personal if recipient is self, but warn the proposer that the content is about another person.
9. **What does Meeting Intelligence do if it sees a TASK_UPDATE for a task it can't find?** Recommend: create a new task with status='done' if the update was "done", source noted as 'meeting' with reference. Log to task_events with `event_type='retroactive_create'`.
10. **Channel observation by Thinker — what if a channel has 100+ messages/hour?** Current Thinker filters ruthlessly. Should we add a hard cap (e.g., max 50 messages processed per batch per channel)? Recommend: yes, with overflow logged and Abhinav notified if cap hit repeatedly.

---

## What changes in existing skills

| Skill | Change |
|---|---|
| `meeting-intelligence` | Extend Step 6 to write to SQLite tasks (match-or-create); Step 5 (extract actions) uses intent classifier output; DAILY_STATE.md update happens as in Phase B/E migration. |
| `slack-commands` | Add TASK_CREATE/UPDATE/BLOCKER/ASSIGN/REMINDER handling for DMs; status queries read SQLite first. |
| `pre-call-brief` | Read from SQLite (active + reminders + new + needs-ack + blocked). New T-ID reply parser. |
| `daily-pulse` | Add team-board snapshot section sourced from SQLite. |
| `follow-through` | Read from SQLite per-person sections instead of DAILY_STATE.md; nudges still go via DM; cross-person reassignment supported. |
| `risk-radar` | Add data sources: task_events for "stale tasks", task_mentions for "discussed but no action", scheduled_actions for "reminders being snoozed too often". |
| `thinker` | Universal channel observation (all channels Alaska is in); still 60-min batches; still proposes-to-Abhinav for medium-confidence signals. |
| `doc-keeper` | Changelog now triggered by `task_events.event_type='status_changed' AND new_status='done'`. |
| `sprint-operator` | Already revised in v2.2 (planning helper, DM-only). Now also has SQLite as source for carryover/velocity calculations. |
| `alaska-core` | Add authority section for cross-person assignment + routine proposals. Document `task_id` and `scheduled_action_id` formats. |
| `shared-toolkit` | Add a new "Task Write Contract" section similar to the Notion Write Contract — exact SQLite queries for common task operations. |

**New skills introduced:**

- `intent-classifier` — always-on, classifies Slack messages into 9 intent types. Sync for DMs, batched for channels.
- `task-handler` — write path for tasks (insert/update/dedup logic).
- `reminder-dispatcher` — cron handler that fires due scheduled_actions.

---

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Intent classifier mis-classifies and creates wrong tasks | Medium | Phase A is observation-only; tune for 1 week. Confidence threshold 0.7. Below threshold → AMBIGUOUS → Abhinav digest. |
| Cross-person assignment spams channels | Medium | Public announcement is one line per task. If volume becomes high, batch announcements (e.g., hourly digest instead of per-task) — design supports this. |
| SQLite becomes a bottleneck at scale | Low | At BON Credit's size (~50 tasks active, ~100 events/day), SQLite WAL handles this trivially. Re-evaluate at 10x scale. |
| Notion projection drift confuses team | Low | One-way write only. Documented "Slack is source." Drift detection alerts Abhinav weekly. |
| Recurring routines spam Slack | Medium | Team routines require Abhinav approval. Personal routines can be paused via "snooze routine SA-N". |
| Engineers don't adopt T-IDs in replies | Medium | Pre-call brief shows T-IDs prominently. Reply parser tolerates fuzzy match as fallback. Track adoption via task_events. |
| `intent_inbox` grows unbounded | Low | Cleanup cron prunes processed=1 rows older than 30 days. |

---

## Success metrics (re-evaluate after Phase E lands)

1. **Pre-call brief accuracy.** % of brief items that the recipient acknowledges as correct (no "I don't know what this is" replies). Target: >90% (vs current ~60%).
2. **Task identity stability.** % of multi-mention tasks (same task discussed >2x) that have a single T-ID. Target: >85%.
3. **Cross-person assignment closure.** % of TASK_ASSIGN events that get ack within 4 hours. Target: >80%.
4. **Reminder usage.** Number of `remind` and `auto_followup` scheduled_actions per week. Indicates adoption of the new capability.
5. **Daily standup reply quality.** Reduction in repeated items week-over-week. Measured by: count of tasks appearing in 3+ consecutive briefs without status update.

---

## Decisions log (from brainstorming session 2026-05-23)

- Storage: SQLite primary + Slack snapshot + read-only Notion projection (Abhinav)
- Multi-owner via `additional_owners` field, not split tasks (Abhinav)
- Cross-person assignment open to anyone, no authority gating (Abhinav)
- Personal routines free, team-wide routines need Abhinav approval (Abhinav)
- Thinker watches all channels Alaska is in (Abhinav)
- Public channel announcement for all team-visible tasks (Abhinav)
- Meeting-extracted tasks default to team visibility (Abhinav)
- Intent classifier batched every 5 min for channels (Abhinav)

---

## Appendix: glossary

- **Task** — A piece of committed work with stable T-N identity, owner, status. Lives in SQLite `tasks` table.
- **Task event** — Append-only audit log row capturing any state change.
- **Task mention** — Reference to a task in any surface (even discussion without state change).
- **Scheduled action** — Future-fire event in `scheduled_actions` table. One-shot or recurring.
- **Surface** — A place where humans communicate (meeting, DM, channel, standup thread reply).
- **Intent** — The classified purpose of a Slack message (TASK_CREATE, TASK_UPDATE, etc.).
- **Trust tier** — High/Medium/Low based on the surface. Determines whether Alaska acts autonomously, with confirmation, or only proposes to Abhinav.
- **Visibility** — `personal` (silent) or `team` (public channel announcement). Computed at task creation from owner/creator relationship.
- **Routine** — A recurring scheduled_action. Personal (anyone) or team-scope (Abhinav-approved).
- **Source ref** — The original Fireflies meeting ID + timestamp, or Slack message URL, that produced a task or mention. Enables click-back-to-source.
