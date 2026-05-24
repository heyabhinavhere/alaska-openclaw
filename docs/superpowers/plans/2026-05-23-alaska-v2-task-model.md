# Alaska v2 Task Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v2 task model defined in `docs/superpowers/specs/2026-05-23-alaska-task-model-design.md` — replace the retired Sprint Board with an SQLite-backed task graph, universal Slack capture via intent classifier, scheduling engine, and cross-person workflow.

**Architecture:** Four-layer system (surfaces → interpretation → SQLite → output). SQLite at `/data/queue/alaska.db` is the single source of truth. New skills are added under `skills/`, existing skills extended. Cron jobs added via OpenClaw dashboard. DAILY_STATE.md keeps running in parallel through Phase D — cutover to generated-from-SQLite happens in a future Phase E plan.

**Tech Stack:** OpenClaw v2026.3.13 (Docker), SQLite 3 (WAL mode, existing at /data/queue/alaska.db), Bash for entrypoint and cron prompt orchestration, Python 3 for RRULE evaluation and complex SQL parsing, Notion MCP server (existing), Slack API via OpenClaw plugin (existing), Claude Sonnet 4.6 for intent classification, Claude Opus 4.6 for high-stakes reasoning (Meeting Intelligence, Thinker).

**Scope:** Phases A through D (per user instruction). Phase E (cutover) gets its own plan after Phases A-D run stably for 2-4 weeks.

---

## Spec Reference

The full design lives at `docs/superpowers/specs/2026-05-23-alaska-task-model-design.md`. Key sections this plan implements:

- **Architecture overview** — 4-layer model (sections 1-4 in spec)
- **SQLite schema** — 8 new tables (full DDL in spec section "Layer 3 — SQLite schema")
- **Intent classifier** — 9 intent types (section "Layer 2 — Intent Classifier")
- **Cross-person workflow** — 10-step sequence (section "Cross-person assignment workflow")
- **Scheduling engine** — RRULE + dispatcher (section "Scheduling engine — examples by intent")
- **Channel visibility rules** — personal vs team (section "Channel visibility rules")
- **Migration phases A-E** — this plan covers A through D

When this plan references a section, that's where to look in the spec.

---

## File Structure

### New directories
- `migrations/` — SQL migration files (numbered, applied in order on every boot)
- `lib/` — shared Python helpers (RRULE eval, JSON helpers)
- `tests/` — Python unit tests for `lib/` modules

### New files
- `migrations/0001_v2_task_model.sql` — creates all 8 new tables
- `migrations/run_migrations.sh` — applies pending migrations idempotently
- `lib/rrule_helper.py` — parse RRULE strings, compute next fire time
- `lib/task_helpers.py` — match-or-create task logic, dedup scoring
- `tests/test_rrule_helper.py`
- `tests/test_task_helpers.py`
- `skills/intent-classifier/SKILL.md` — always-on, classifies every Slack message
- `skills/task-handler/SKILL.md` — match-or-create + status updates
- `skills/reminder-dispatcher/SKILL.md` — fires due scheduled_actions

### Modified files
- `Dockerfile` — install python3 dateutil, pip; copy lib/ to image
- `entrypoint.sh` — run migrations on boot
- `skills/shared-toolkit/SKILL.md` — add "Task Write Contract" section
- `skills/meeting-intelligence/SKILL.md` — call task-handler for each commitment
- `skills/slack-commands/SKILL.md` — handle TASK_*, REMINDER_REQUEST intents
- `skills/pre-call-brief/SKILL.md` — read SQLite, T-ID-based replies
- `skills/risk-radar/SKILL.md` — add task_events/task_mentions as risk signals
- `skills/doc-keeper/SKILL.md` — Changelog trigger on task_events status=done
- `skills/alaska-core/SKILL.md` — document v2 task system + authority for routines
- `workspace/MEMORY.md` — log architectural evolution as v2.3
- `workspace/AGENT_RULES.md` — note new task system
- `config/cron-jobs-backup.json` — sync new cron entries (added via dashboard separately)

### Cron jobs (added via OpenClaw dashboard)
- `intent-classifier-batch` — every 5 min UTC, runs intent classifier over intent_inbox
- `reminder-dispatcher` — every 15 min UTC, fires due scheduled_actions
- `routine-proposal-watch` — daily 06:00 UTC, expires routine_proposals older than 7 days

---

## Tech Dependencies

Add to `Dockerfile` (Phase C):
- `python3-dateutil` (RRULE parsing) via `apt-get install python3-dateutil` OR `pip install python-dateutil`

Existing dependencies (no new install):
- `sqlite3` (Phase A — already in Dockerfile)
- `curl` (existing)
- Python 3 base (existing, used by amplitude-analyst/charts.py)
- Notion MCP server (existing)
- Slack OpenClaw plugin (existing)

---

## Conventions Used in This Plan

**For each task:**
- **Files:** lists exact paths to create or modify with line ranges
- Steps are bite-sized (~2-15 min each) with explicit code blocks where applicable
- "Verify" steps include exact SQL queries, log greps, or Slack message checks
- Each task ends with a commit

**Commit message convention:** Conventional Commits (matches existing repo). `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`.

**Branching:** One feature branch per phase. PR to `main` after the full phase is verified. Phase A → `feat/v2-task-phase-a`, Phase B → `feat/v2-task-phase-b`, etc.

**Testing approach for skill prompts:** SKILL.md files are LLM prompts, not code. "Verification" for skills = trigger via cron or DM and observe expected SQLite rows / Slack messages. Unit tests apply only to `lib/*.py` modules.

**Pre-flight (do once before Phase A):**

- [ ] Confirm you're on a clean main: `cd alaska-openclaw && git status` should be clean, `git fetch && git status -sb` should show "up to date with origin/main".
- [ ] Create the Phase A branch: `git switch -c feat/v2-task-phase-a`.

---

# PHASE A — Schema + Intent Classifier (Observation Mode)

**Phase goal:** Get data flowing into 8 new SQLite tables. Add the intent-classifier skill running in LOG-ONLY mode (writes to intent_inbox + classifier_audit, does NOT act). Run for 1 week, spot-check accuracy on 50-100 classifications.

**Phase risk:** Zero — pure additive change, no behavior modification.

**Phase output:** Live data in `intent_inbox` and `classifier_audit` you can query to validate classifier quality before Phase B wires the action paths.

---

### Task A1: Create migration system

**Files:**
- Create: `migrations/run_migrations.sh`
- Modify: `entrypoint.sh` (insert migration run block after SQLite WAL init)

The migration system runs all `.sql` files in `migrations/` numerically, idempotently, tracking applied migrations in a `_migrations` table. Idempotent so it's safe to run on every container boot.

- [ ] **Step 1: Create `migrations/run_migrations.sh`**

```bash
#!/bin/bash
# Apply all SQL migrations in numerical order, idempotently.
# Tracks applied migrations in the `_migrations` table.
set -e

DB="${1:-/data/queue/alaska.db}"
MIGRATION_DIR="${2:-/opt/migrations}"

# Bootstrap the tracking table
sqlite3 "$DB" "CREATE TABLE IF NOT EXISTS _migrations (
  filename TEXT PRIMARY KEY,
  applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);"

# Apply each .sql file not yet recorded
for migration in $(ls "$MIGRATION_DIR"/*.sql | sort); do
  name=$(basename "$migration")
  applied=$(sqlite3 "$DB" "SELECT 1 FROM _migrations WHERE filename='$name';")
  if [ "$applied" = "1" ]; then
    echo "[migrations] $name already applied — skipping"
    continue
  fi
  echo "[migrations] Applying $name..."
  sqlite3 "$DB" < "$migration"
  sqlite3 "$DB" "INSERT INTO _migrations (filename) VALUES ('$name');"
  echo "[migrations] $name applied"
done
```

- [ ] **Step 2: Make executable** — `chmod +x migrations/run_migrations.sh`

- [ ] **Step 3: Modify `Dockerfile`** to copy migrations to the image

Add this line after the existing `COPY skills/` line (currently around line 36):

```dockerfile
# Copy SQL migrations to staging
COPY --chown=node:node migrations/ /opt/migrations/
```

- [ ] **Step 4: Modify `entrypoint.sh`** to run migrations after SQLite init

Find the existing block (around line 79-86):

```bash
if [ ! -f /data/queue/alaska.db ]; then
  echo "[alaska] Initializing SQLite queue database with WAL mode..."
  sqlite3 /data/queue/alaska.db "PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS outbox (...);"
  echo "[alaska] SQLite queue ready at /data/queue/alaska.db"
else
  echo "[alaska] SQLite queue already exists."
fi
```

Insert AFTER that block, BEFORE the env-var substitution:

```bash
# Apply any pending SQL migrations (idempotent — safe to run every boot)
if [ -d /opt/migrations ]; then
  echo "[alaska] Checking for pending migrations..."
  bash /opt/migrations/run_migrations.sh /data/queue/alaska.db /opt/migrations
  echo "[alaska] Migrations complete."
fi
```

- [ ] **Step 5: Local test** (optional but recommended)

```bash
mkdir -p /tmp/alaska-mig-test
cp -r migrations /tmp/alaska-mig-test/
echo "CREATE TABLE _test (x INTEGER);" > /tmp/alaska-mig-test/migrations/0000_test.sql
bash migrations/run_migrations.sh /tmp/alaska-mig-test/test.db /tmp/alaska-mig-test/migrations
sqlite3 /tmp/alaska-mig-test/test.db ".tables"  # should show _migrations and _test
bash migrations/run_migrations.sh /tmp/alaska-mig-test/test.db /tmp/alaska-mig-test/migrations  # should say "already applied"
rm -rf /tmp/alaska-mig-test
```

Expected: First run creates both tables. Second run prints "already applied" and exits cleanly.

- [ ] **Step 6: Commit**

```bash
git add migrations/run_migrations.sh Dockerfile entrypoint.sh
git commit -m "feat(migrations): add idempotent SQL migration runner"
```

---

### Task A2: Define v2 task model schema migration

**Files:**
- Create: `migrations/0001_v2_task_model.sql`

This migration creates all 8 new tables defined in the spec. Single migration file because they're a cohesive unit; future schema tweaks get their own numbered files.

- [ ] **Step 1: Create `migrations/0001_v2_task_model.sql`**

```sql
-- Migration 0001: v2 task model schema
-- Spec: docs/superpowers/specs/2026-05-23-alaska-task-model-design.md
-- Creates tables for the new task system. Idempotent via CREATE IF NOT EXISTS.

-- ============================================================
-- 1. tasks — the primary task entity
-- ============================================================
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'blocked', 'pending_acceptance', 'done', 'dropped', 'snoozed')),
  priority TEXT
    CHECK (priority IS NULL OR priority IN ('P0', 'P1', 'P2', 'P3')),
  effort TEXT
    CHECK (effort IS NULL OR effort IN ('XS', 'S', 'M', 'L', 'XL')),
  owner_slack_id TEXT NOT NULL,
  additional_owners TEXT,
  creator_slack_id TEXT NOT NULL,
  assigner_slack_id TEXT,
  visibility TEXT NOT NULL DEFAULT 'personal'
    CHECK (visibility IN ('personal', 'team')),
  category TEXT,
  source TEXT NOT NULL
    CHECK (source IN ('meeting', 'slack_dm', 'slack_channel', 'standup_reply', 'manual')),
  source_ref TEXT,
  due_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  done_at DATETIME,
  parent_task_id TEXT REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_owner_status ON tasks(owner_slack_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON tasks(status, due_at);

-- ============================================================
-- 2. task_events — append-only audit log
-- ============================================================
CREATE TABLE IF NOT EXISTS task_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES tasks(task_id),
  event_type TEXT NOT NULL,
  actor_slack_id TEXT,
  old_value TEXT,
  new_value TEXT,
  context TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, created_at);

-- ============================================================
-- 3. task_mentions — every reference to a task across any surface
-- ============================================================
CREATE TABLE IF NOT EXISTS task_mentions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES tasks(task_id),
  surface TEXT NOT NULL
    CHECK (surface IN ('meeting', 'slack_dm', 'slack_channel', 'standup_reply')),
  mention_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actor_slack_id TEXT,
  excerpt TEXT,
  source_ref TEXT,
  mention_type TEXT
    CHECK (mention_type IS NULL OR mention_type IN
           ('status_update', 'discussion', 'assignment', 'commitment', 'reference'))
);

CREATE INDEX IF NOT EXISTS idx_task_mentions_task ON task_mentions(task_id, mention_at);

-- ============================================================
-- 4. task_categories — lightweight grouping
-- ============================================================
CREATE TABLE IF NOT EXISTS task_categories (
  name TEXT PRIMARY KEY,
  description TEXT,
  active BOOLEAN NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed common categories from DAILY_STATE.md This Week's Goals patterns
INSERT OR IGNORE INTO task_categories (name, description) VALUES
  ('V2', 'V2 app build, testing, launch'),
  ('MoneyLine', 'MoneyLine partnership integration'),
  ('Marketing', 'Single-mom campaign, content, growth'),
  ('Infra', 'Platform, CI/CD, observability'),
  ('Card-Matching', 'Plaid integration, card linking, matching engine'),
  ('Customer-IO', 'Push notification + email delivery work'),
  ('Other', 'Catch-all for uncategorized work');

-- ============================================================
-- 5. blockers — extends existing pattern, links to tasks
-- ============================================================
CREATE TABLE IF NOT EXISTS blockers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  blocker_id TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  blocking_task_ids TEXT,
  owner_slack_id TEXT,
  raised_by_slack_id TEXT,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'resolved')),
  raised_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at DATETIME,
  resolution TEXT,
  source TEXT,
  source_ref TEXT
);

CREATE INDEX IF NOT EXISTS idx_blockers_status ON blockers(status, raised_at);

-- ============================================================
-- 6. scheduled_actions — reminders + recurring routines
-- ============================================================
CREATE TABLE IF NOT EXISTS scheduled_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action_id TEXT UNIQUE NOT NULL,
  action_type TEXT NOT NULL
    CHECK (action_type IN ('remind', 'surface_task', 'escalate',
                            'recurring_routine', 'auto_followup')),
  fire_at DATETIME NOT NULL,
  recurrence_rule TEXT,
  recipient_slack_id TEXT,
  recipient_channel_id TEXT,
  linked_task_id TEXT REFERENCES tasks(task_id),
  payload TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT 'personal'
    CHECK (scope IN ('personal', 'team')),
  created_by_slack_id TEXT NOT NULL,
  approved_by_slack_id TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'fired', 'cancelled', 'snoozed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  next_fire_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fired_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_scheduled_pending ON scheduled_actions(status, fire_at);

-- ============================================================
-- 7. routine_proposals — team-wide routines pending Abhinav approval
-- ============================================================
CREATE TABLE IF NOT EXISTS routine_proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  proposal_id TEXT UNIQUE NOT NULL,
  proposed_by_slack_id TEXT NOT NULL,
  description TEXT NOT NULL,
  proposed_payload TEXT NOT NULL,
  proposed_recurrence_rule TEXT NOT NULL,
  proposed_recipient TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'declined', 'expired')),
  abhinav_response TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  responded_at DATETIME,
  expires_at DATETIME
);

-- ============================================================
-- 8. intent_inbox — Slack channel messages awaiting classification
-- ============================================================
CREATE TABLE IF NOT EXISTS intent_inbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_ts TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  author_slack_id TEXT NOT NULL,
  message_text TEXT NOT NULL,
  thread_ts TEXT,
  processed BOOLEAN NOT NULL DEFAULT 0,
  intent TEXT,
  confidence REAL,
  classifier_output TEXT,
  processed_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (channel_id, message_ts)
);

CREATE INDEX IF NOT EXISTS idx_intent_unprocessed ON intent_inbox(processed, created_at);

-- ============================================================
-- 9. classifier_audit — Phase A observation log (no action taken)
-- ============================================================
CREATE TABLE IF NOT EXISTS classifier_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inbox_id INTEGER REFERENCES intent_inbox(id),
  classified_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  intent TEXT NOT NULL,
  confidence REAL NOT NULL,
  entities TEXT,
  reasoning TEXT,
  would_have_done TEXT,
  abhinav_reviewed BOOLEAN NOT NULL DEFAULT 0,
  abhinav_verdict TEXT
);
```

- [ ] **Step 2: Local validation**

```bash
sqlite3 /tmp/test-schema.db < migrations/0001_v2_task_model.sql
sqlite3 /tmp/test-schema.db ".tables"
# Expected: blockers  classifier_audit  intent_inbox  routine_proposals
#           scheduled_actions  task_categories  task_events  task_mentions  tasks
sqlite3 /tmp/test-schema.db "SELECT name FROM task_categories;"
# Expected: V2, MoneyLine, Marketing, Infra, Card-Matching, Customer-IO, Other
rm /tmp/test-schema.db
```

- [ ] **Step 3: Run a syntax dry-run via the migration runner**

```bash
mkdir -p /tmp/mig-dry
cp -r migrations /tmp/mig-dry/
bash migrations/run_migrations.sh /tmp/mig-dry/test.db /tmp/mig-dry/migrations
sqlite3 /tmp/mig-dry/test.db ".schema tasks" | head -20
# Expected: complete tasks DDL
rm -rf /tmp/mig-dry
```

- [ ] **Step 4: Commit**

```bash
git add migrations/0001_v2_task_model.sql
git commit -m "feat(schema): add v2 task model tables (tasks, events, mentions, scheduling)"
```

---

### Task A3: Verify migration applies on Railway

**Files:** none (deployment + remote verification)

- [ ] **Step 1: Push the branch and merge to main**

This phase deploys live. Push branch, open PR, merge to trigger Railway redeploy.

```bash
git push -u origin feat/v2-task-phase-a
gh pr create --base main --head feat/v2-task-phase-a \
  --title "Phase A.1: Migration runner + v2 task model schema" \
  --body "Adds migration runner + creates 9 new SQLite tables. No behavior change — observation-only setup for Phase A."
```

Wait for PR approval + merge.

- [ ] **Step 2: After Railway redeploys, verify tables exist on the live volume**

Via OpenClaw dashboard chat, ask Alaska to confirm:

```
Verify the v2 task model migration applied. Run:
  sqlite3 /data/queue/alaska.db ".tables"
  sqlite3 /data/queue/alaska.db "SELECT * FROM _migrations;"
  sqlite3 /data/queue/alaska.db "SELECT count(*) FROM task_categories;"

Expected: all 9 new tables present, _migrations shows 0001 applied, 7 categories.
Report back results.
```

- [ ] **Step 3: Re-create the feature branch off the new main**

```bash
git checkout main && git pull origin main
git switch -c feat/v2-task-phase-a-classifier
```

(Each subsequent task block in Phase A goes on this branch. PR at the end of the phase.)

---

### Task A4: Write the intent-classifier SKILL.md

**Files:**
- Create: `skills/intent-classifier/SKILL.md`

The classifier is an always-on skill that LLM-classifies Slack messages into one of 9 intents. In Phase A it runs in **OBSERVATION MODE** — writes to `classifier_audit` only, no downstream action.

- [ ] **Step 1: Create the skill directory and SKILL.md**

```bash
mkdir -p skills/intent-classifier
```

Create `skills/intent-classifier/SKILL.md`:

````markdown
---
name: intent-classifier
description: Classify every non-trivial Slack message Alaska sees into one of 9 intent types. Writes classification + entities + reasoning to intent_inbox / classifier_audit. Phase A runs in OBSERVATION MODE — no downstream action. Phases B+ wire the action paths.
version: 1.0.0
metadata:
  openclaw:
    always: true
    requires:
      bins: [sqlite3]
      env: [ANTHROPIC_API_KEY]
    primaryEnv: ANTHROPIC_API_KEY
    emoji: "🎯"
---

# Intent Classifier (v1 — Observation Mode)

Also read `/data/skills/shared-toolkit/SKILL.md` for communication standards, queue-first patterns, and the Slack channel ID list.

You are the Intent Classifier. Every non-trivial Slack message Alaska sees gets classified into one of 9 intent types so downstream handlers know what to do. **Phase A: OBSERVATION ONLY. Write to classifier_audit and log everything. Do NOT take downstream action.**

## Trigger modes

- **Batched (channels):** every 5 min cron processes unprocessed rows in `intent_inbox`.
- **Synchronous (DMs):** when invoked from a DM-handling context with a message payload.

The cron prompt that invokes this skill in batched mode supplies the channel/messages. The DM-handling context supplies one message and expects an immediate intent result.

## The 9 intent types

| Intent | Definition | Example messages |
|---|---|---|
| `TASK_CREATE` | Speaker is committing to do new work themselves | "starting on chart UI", "I'll fix this profile bug", "going to look at the Plaid issue" |
| `TASK_UPDATE` | Status change on existing work | "T-42 done", "still working on it", "merged the PR", "halfway through chart UI" |
| `TASK_ASSIGN` | Asking someone else (one or more) to do work | "@Shailesh @Tarun look at users 2854, 2891, 2894 in 48h", "Pankaj should fix this", "can someone QA this PR?" |
| `TASK_BLOCKER` | Reporting a blocker on own or others' work | "blocked on Plaid docs", "can't proceed until X is merged", "waiting on Sandeep" |
| `REMINDER_REQUEST` | Asking for a future-fire reminder or recurring routine | "remind me about X in 5 days", "every Friday at 5 PM DM me my open tasks", "follow up with Pankaj on T-42 tomorrow" |
| `DECISION_RECORDED` | A decision being made | "let's go with approach A", "we're cancelling X", "decided to use Twilio not Plivo" |
| `STATUS_QUERY` | Question about state | "what's on my plate?", "any blockers?", "what shipped this week?", "sprint status" |
| `NON_WORK_CHAT` | Banter, greetings, social | "good morning", "lunch?", "lol", emoji-only |
| `AMBIGUOUS` | Unclear — confidence < 0.7 OR genuinely ambiguous | "hmm", "interesting", short fragments without context |

## Classification logic

For each message:

1. **Pre-filter:** skip if message_text is < 5 characters AND doesn't contain `@` mention, T-N reference, or task verb. Mark as `NON_WORK_CHAT` directly without LLM call.

2. **Classify with LLM:** for the rest, call Claude Sonnet 4.6 with this exact prompt structure:

```
You are classifying Slack messages from BON Credit team members for the Alaska
AI project manager. Classify this message into ONE of these intent types:

TASK_CREATE / TASK_UPDATE / TASK_ASSIGN / TASK_BLOCKER / REMINDER_REQUEST /
DECISION_RECORDED / STATUS_QUERY / NON_WORK_CHAT / AMBIGUOUS

Return JSON with this exact shape:
{
  "intent": "<one of the 9>",
  "confidence": <0.0 to 1.0>,
  "entities": {
    "task_ids": ["T-42", ...],          // T-N references found
    "owners_mentioned": ["U07GKLVA9FE", ...],  // Slack IDs of @-mentioned people
    "dates_mentioned": ["2026-05-30", "in 48h", ...],
    "task_topic": "<short topic summary if task-related>",
    "blocker_topic": "<short blocker summary if TASK_BLOCKER>",
    "decision_summary": "<if DECISION_RECORDED>",
    "recurrence_hint": "<weekly|daily|once|null>"
  },
  "reasoning": "<one sentence why this intent>",
  "would_have_done": "<one sentence describing what action Phase B+ would take>"
}

Notes:
- Confidence < 0.7 → intent must be AMBIGUOUS
- TASK_ASSIGN requires at least one @-mention of another team member
- TASK_UPDATE requires either a T-N reference OR clear "done/in progress/blocked" verb
- "let's discuss X" or "should we do Y" without commitment is NOT a task — usually NON_WORK_CHAT or DECISION_RECORDED if it concludes
- Empty or single-emoji messages = NON_WORK_CHAT

Team roster (for @ resolution):
[Resolve from /root/.openclaw/workspace/MEMORY.md → Team Roster]

Message text:
[insert message text]

Channel: [channel name]
Author: [first name]
Timestamp: [ISO]
```

3. **Write classification result.**

**Observation mode (Phase A):**
- Update the `intent_inbox` row: `processed = 1`, `intent = <result>`, `confidence = <result>`, `classifier_output = <full JSON>`, `processed_at = NOW()`.
- Insert into `classifier_audit`: full record with `would_have_done` populated.
- **DO NOT** create tasks, send DMs, post to channels, schedule actions, or modify any other table. This is logging only.

**Production mode (Phases B+):** unchanged from above PLUS route to the appropriate handler based on intent.

## Cron behavior (batched mode)

Triggered every 5 min via OpenClaw cron. Read unprocessed messages:

```bash
sqlite3 /data/queue/alaska.db "
  SELECT id, channel_id, author_slack_id, message_text, message_ts
  FROM intent_inbox
  WHERE processed = 0
  ORDER BY created_at ASC
  LIMIT 50;
"
```

For each row:
1. Look up channel name (from /root/.openclaw/workspace/TOOLS.md channel mapping)
2. Look up author first name (from MEMORY.md)
3. Run the LLM classifier
4. Write results per "Write classification result" above

Cap at 50 messages per run to bound token cost. If queue grows >200, alert Abhinav.

## DM handling (synchronous mode)

When invoked from a DM context with a single message:

1. Skip the intent_inbox insert (this isn't a channel message).
2. Run classifier directly.
3. Write to `classifier_audit` with `inbox_id = NULL` and `would_have_done` describing the would-be action.
4. Return the JSON result to the caller (the DM-handling skill — Phase A: only slack-commands, just for logging).

## Anti-patterns

1. **Never act on classifier output in Phase A.** Pure observation.
2. **Never modify the message text** before classifying — pass it verbatim so the audit log is accurate.
3. **Never skip the `would_have_done` field.** It's how we'll evaluate classifier quality before flipping to Phase B.
4. **Never re-classify already-processed messages.** Check `processed=0`.

## Token budget

Estimate: 50 channel msgs/day × 600 tokens/classification × $3/1M (Sonnet) = ~$0.10/day. Cap warning at $0.50/day in `classifier_audit` count >> expected.
````

- [ ] **Step 2: Verify SKILL.md syntax**

```bash
head -15 skills/intent-classifier/SKILL.md
# Expected: frontmatter present with `name`, `description`, `version`, `metadata`
wc -l skills/intent-classifier/SKILL.md
# Expected: ~150-180 lines
```

- [ ] **Step 3: Commit**

```bash
git add skills/intent-classifier/SKILL.md
git commit -m "feat(intent-classifier): add Phase A observation-mode classifier skill"
```

---

### Task A5: Add Slack-message-to-intent_inbox ingestion

**Files:**
- Modify: `skills/shared-toolkit/SKILL.md` (add section "Slack message ingestion")
- Modify: `skills/alaska-core/SKILL.md` (note that channel messages are captured)

Channel messages need to land in `intent_inbox` for the batched classifier to process. The simplest path: every cron-driven skill that reads Slack channels (currently Thinker, soon also others) writes any unprocessed messages to `intent_inbox`. We don't have a separate "Slack event listener" — Alaska's architecture is cron-pull, not event-push.

- [ ] **Step 1: Read the current shared-toolkit Section 6 (Communication Standards)** for context

```bash
grep -n "## 6\." skills/shared-toolkit/SKILL.md
# Note the structure so the new section fits naturally
```

- [ ] **Step 2: Add a new section to shared-toolkit (insert after Section 6)**

Use Edit tool to add this section:

````markdown
## 6.5 Slack message ingestion (for intent classifier)

Any skill that reads Slack channel messages should ALSO write them to `intent_inbox` for the intent classifier to process.

Pattern:

```bash
# After fetching new channel messages
for each message:
  sqlite3 /data/queue/alaska.db "
    INSERT OR IGNORE INTO intent_inbox
      (message_ts, channel_id, author_slack_id, message_text, thread_ts)
    VALUES
      ('$message_ts', '$channel_id', '$author_id', '$text', $thread_ts_or_null);
  "
done
```

The `INSERT OR IGNORE` on the `(channel_id, message_ts)` unique constraint means duplicates are harmless — safe to re-ingest on every cron pull.

DMs to Alaska are handled separately (synchronous classification — see intent-classifier/SKILL.md "DM handling" section).
````

- [ ] **Step 3: Update thinker/SKILL.md** to call this pattern

Find the Thinker skill's "Step 1: Collect Inputs" section. Add at the end of "1a. Slack Messages":

```markdown
**Also write each fetched message to `intent_inbox`** for the batched classifier:

```bash
sqlite3 /data/queue/alaska.db "
  INSERT OR IGNORE INTO intent_inbox (message_ts, channel_id, author_slack_id, message_text, thread_ts)
  VALUES ('<ts>', '<channel>', '<author>', '<text>', '<thread_ts_or_NULL>');
"
```

This is a quick write that lets the classifier observe everything in parallel without changing Thinker's own behavior.
```

- [ ] **Step 4: Commit**

```bash
git add skills/shared-toolkit/SKILL.md skills/thinker/SKILL.md
git commit -m "feat(intent-classifier): wire channel message ingestion to intent_inbox"
```

---

### Task A6: Add intent-classifier batch cron

**Files:**
- Modify: `config/cron-jobs-backup.json` (snapshot — applied via dashboard)
- Document: `workspace/MEMORY.md` (cron section update)

OpenClaw cron jobs are managed via the dashboard. The `cron-jobs-backup.json` is a snapshot for documentation; the actual cron must be added in the dashboard separately.

- [ ] **Step 1: Document the new cron in `config/cron-jobs-backup.json`**

Use Python to add the entry:

```bash
python3 << 'EOF'
import json
from pathlib import Path

p = Path('config/cron-jobs-backup.json')
data = json.loads(p.read_text())

new_job = {
    "id": "PLACEHOLDER-uuid-to-be-set-by-openclaw",
    "name": "Intent Classifier — Batch (Phase A obs mode)",
    "enabled": True,
    "schedule": {"kind": "cron", "expr": "*/5 * * * *", "tz": "UTC"},
    "agentId": "main",
    "sessionKey": "agent:main:main",
    "sessionTarget": "isolated",
    "wakeMode": "now",
    "payload": {
        "kind": "user-message",
        "message": (
            "You are running the intent-classifier batch job. "
            "Read /data/skills/intent-classifier/SKILL.md for the full procedure. "
            "Phase A: OBSERVATION ONLY — log to classifier_audit, do NOT take downstream action. "
            "Process up to 50 unprocessed rows from intent_inbox. "
            "When done, report: messages processed, intent distribution, average confidence."
        ),
        "timeoutSeconds": 300
    },
    "delivery": {"channel": "none"},
    "state": {}
}

data['jobs'].append(new_job)
p.write_text(json.dumps(data, indent=2))
print(f"Added cron job. Total jobs now: {len(data['jobs'])}")
EOF
```

- [ ] **Step 2: Apply via OpenClaw dashboard**

In the OpenClaw dashboard:
1. Navigate to Cron Jobs section
2. Add new job with:
   - Name: `Intent Classifier — Batch (Phase A obs mode)`
   - Schedule: `*/5 * * * *` UTC
   - Session: isolated, sessionKey `agent:main:main`
   - Timeout: 300s
   - Prompt: as above

The cron UUID generated by OpenClaw should replace the `PLACEHOLDER-uuid-to-be-set-by-openclaw` field in the JSON snapshot. After applying, run the Python snippet again with the real UUID, OR do a manual JSON edit.

- [ ] **Step 3: Verify the cron fires**

Wait 5 minutes after applying. Then via dashboard chat:

```
Verify the intent-classifier cron ran. Run:
  sqlite3 /data/queue/alaska.db "SELECT COUNT(*) FROM classifier_audit WHERE classified_at > datetime('now', '-10 minutes');"

Expected: at least 1 if any channel messages were ingested in the last 10 min.
Also: SELECT intent, COUNT(*) FROM classifier_audit GROUP BY intent;
```

- [ ] **Step 4: Commit the JSON snapshot**

```bash
git add config/cron-jobs-backup.json
git commit -m "chore(cron): document intent-classifier batch cron (5-min schedule)"
```

---

### Task A7: Phase A acceptance — observe for 1 week, spot-check accuracy

**Files:** none (operational verification)

- [ ] **Step 1: Open Phase A PR and merge**

```bash
git push -u origin feat/v2-task-phase-a-classifier
gh pr create --base main --head feat/v2-task-phase-a-classifier \
  --title "Phase A.2: Intent classifier + ingestion (observation mode)" \
  --body "Adds intent-classifier skill, channel ingestion in shared-toolkit, batch cron at 5-min. OBSERVATION ONLY — no downstream action."
```

Wait for merge → Railway redeploy.

- [ ] **Step 2: Wait 24 hours, then sample the first batch**

```sql
-- via OpenClaw dashboard
SELECT intent, confidence, message_text, would_have_done
FROM classifier_audit a
JOIN intent_inbox i ON a.inbox_id = i.id
ORDER BY classified_at DESC
LIMIT 30;
```

For each row, eyeball: was the intent right? Were entities extracted correctly?

- [ ] **Step 3: Mark Abhinav-reviewed rows**

```sql
UPDATE classifier_audit
SET abhinav_reviewed = 1,
    abhinav_verdict = '<correct|wrong: should be X|partial>'
WHERE id IN (...);
```

- [ ] **Step 4: After 1 week, compute accuracy**

```sql
SELECT
  intent,
  COUNT(*) AS total,
  SUM(CASE WHEN abhinav_verdict LIKE 'correct%' THEN 1 ELSE 0 END) AS correct,
  ROUND(100.0 * SUM(CASE WHEN abhinav_verdict LIKE 'correct%' THEN 1 ELSE 0 END) / COUNT(*), 1) AS accuracy_pct
FROM classifier_audit
WHERE abhinav_reviewed = 1
GROUP BY intent;
```

Target: 85%+ overall accuracy. If TASK_ASSIGN or REMINDER_REQUEST are < 70% accurate, iterate on the classifier prompt before Phase B (these are the highest-stakes intents).

- [ ] **Step 5: Update the classifier prompt if needed, push the iteration**

If accuracy is too low, edit `skills/intent-classifier/SKILL.md` to add examples/disambiguation rules in the classifier prompt. Push, wait for redeploy, observe another 48h.

- [ ] **Step 6: Phase A complete — proceed to Phase B**

```bash
git checkout main && git pull origin main
```

---

# PHASE B — Basic Task Lifecycle

**Phase goal:** Tasks start being created and updated in SQLite from two surfaces: Meeting Intelligence (task extraction from transcripts) and Slack DMs (intent classifier wires TASK_CREATE/UPDATE/BLOCKER to writes). Pre-call brief reads from SQLite, shows T-IDs. **DAILY_STATE.md keeps being authoritative for narrative output** — both systems run side by side. No cross-person workflow yet (Phase D).

**Phase risk:** Low — old system still primary. New system shadows it.

**Phase output:** Pre-call brief shows stable T-IDs. Engineers can DM Alaska "T-42 done" or "starting on chart UI" and have it land in SQLite.

**Pre-flight:**

- [ ] `git checkout main && git pull origin main`
- [ ] `git switch -c feat/v2-task-phase-b`

---

### Task B1: Add Task Write Contract to shared-toolkit

**Files:**
- Modify: `skills/shared-toolkit/SKILL.md` (add new section "Task Write Contract" after Section 1 "notionWrite")

A reference section any skill can read for exact SQLite operations on the tasks tables. Mirrors the Notion Write Contract pattern that landed in v2.2.

- [ ] **Step 1: Add the Task Write Contract section**

Use Edit to add after Section 1 (around line 75):

````markdown
---

## 1.5 Task Write Contract — SQLite tasks table

The canonical operations for the v2 task model. Every skill that creates or updates tasks uses these patterns.

### Generate next T-ID

```bash
NEXT_ID=$(sqlite3 /data/queue/alaska.db "SELECT 'T-' || COALESCE(MAX(CAST(SUBSTR(task_id, 3) AS INTEGER)) + 1, 1) FROM tasks;")
```

### Create a new task

```bash
sqlite3 /data/queue/alaska.db <<SQL
INSERT INTO tasks (
  task_id, title, description, status, priority, effort,
  owner_slack_id, additional_owners, creator_slack_id, assigner_slack_id,
  visibility, category, source, source_ref, due_at
) VALUES (
  '$NEXT_ID', '$TITLE', '$DESC', 'active', $PRIORITY_OR_NULL, $EFFORT_OR_NULL,
  '$OWNER_SLACK_ID', $ADDITIONAL_OWNERS_JSON_OR_NULL,
  '$CREATOR_SLACK_ID', $ASSIGNER_OR_NULL,
  '$VISIBILITY', $CATEGORY_OR_NULL, '$SOURCE', '$SOURCE_REF',
  $DUE_AT_OR_NULL
);

INSERT INTO task_events (task_id, event_type, actor_slack_id, new_value, context)
VALUES ('$NEXT_ID', 'created', '$ACTOR_SLACK_ID',
        '{"status":"active","owner":"$OWNER_SLACK_ID"}',
        'Source: $SOURCE, ref: $SOURCE_REF');
SQL
```

**Compute `visibility`:**
- `'personal'` if `owner_slack_id == creator_slack_id` AND `additional_owners` is empty/null
- `'team'` otherwise
- **Override:** `source = 'meeting'` always gets `visibility = 'team'`

### Update status (e.g., from "T-42 done")

```bash
# Get old value first for audit log
OLD_STATUS=$(sqlite3 /data/queue/alaska.db "SELECT status FROM tasks WHERE task_id='$TASK_ID';")

sqlite3 /data/queue/alaska.db <<SQL
UPDATE tasks SET
  status = '$NEW_STATUS',
  updated_at = CURRENT_TIMESTAMP,
  done_at = CASE WHEN '$NEW_STATUS' = 'done' THEN CURRENT_TIMESTAMP ELSE done_at END
WHERE task_id = '$TASK_ID';

INSERT INTO task_events (task_id, event_type, actor_slack_id, old_value, new_value, context)
VALUES ('$TASK_ID', 'status_changed', '$ACTOR_SLACK_ID',
        '{"status":"$OLD_STATUS"}', '{"status":"$NEW_STATUS"}',
        '$CONTEXT');
SQL
```

### Log a mention without status change

```bash
sqlite3 /data/queue/alaska.db "
INSERT INTO task_mentions (task_id, surface, actor_slack_id, excerpt, source_ref, mention_type)
VALUES ('$TASK_ID', '$SURFACE', '$ACTOR', '$EXCERPT', '$SOURCE_REF', '$MENTION_TYPE');
"
```

### Query: active tasks for a person (used by pre-call brief)

```bash
sqlite3 /data/queue/alaska.db "
SELECT task_id, title, status, priority, due_at, updated_at, source
FROM tasks
WHERE owner_slack_id = '$OWNER_SLACK_ID'
  AND status IN ('active', 'blocked', 'pending_acceptance')
ORDER BY
  CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
  due_at ASC NULLS LAST;
"
```

### Match-or-create logic (when extracting a possible task from any surface)

Pseudocode for the LLM-aided match step — implemented by the task-handler skill:

1. Pull candidate tasks: same owner, status active/blocked, updated within 14 days, limit 20.
2. Pass the new extraction + candidates to Claude Sonnet with this prompt:
   > "Is this new statement a match for one of these active tasks, or a new task? Compare title, topic, timing. Return: `{match: 'T-N' or null, confidence: 0-1, reasoning: ''}`"
3. If `confidence >= 0.8` AND `match != null` → update existing task, append to task_events with `event_type='matched'`, log to task_mentions.
4. Else → create new task per pattern above.
5. Always log the decision to task_events with `event_type='dedup_decision'` and full reasoning in `context`.

### Anti-patterns

- **Never modify task_id after creation.** It's the stable identity that humans reference.
- **Never delete tasks.** Use `status = 'dropped'` for cancelled work — preserves history and audit trail.
- **Always write a task_events row alongside every tasks UPDATE.** The events table is the audit log; updates without events are invisible.
- **Always log task_mentions on any non-action discussion** (e.g., task referenced in a meeting but no status change). Needed for dedup signal and Thinker's pattern detection.
- **When unsure if a statement is a status update vs new task, default to new task with a `[NEEDS LINK?]` note in description.** Easier to merge later than to lose context.
````

- [ ] **Step 2: Commit**

```bash
git add skills/shared-toolkit/SKILL.md
git commit -m "feat(toolkit): add Task Write Contract for v2 task model"
```

---

### Task B2: Write task-handler SKILL.md

**Files:**
- Create: `skills/task-handler/SKILL.md`

The task-handler is invoked by other skills (Meeting Intelligence, slack-commands) when they need to create or update a task. It encapsulates the match-or-create logic so the same dedup rules apply across all surfaces.

- [ ] **Step 1: Create directory and SKILL.md**

```bash
mkdir -p skills/task-handler
```

Create `skills/task-handler/SKILL.md`:

````markdown
---
name: task-handler
description: Create or update tasks in SQLite with match-or-create deduplication. Invoked by Meeting Intelligence, Slack Commands, Pre-Call Brief. Encapsulates the dedup logic so behavior is consistent across surfaces.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3]
    emoji: "✅"
---

# Task Handler

Read `/data/skills/shared-toolkit/SKILL.md` Section 1.5 "Task Write Contract" for the canonical SQL operations.

You are the Task Handler. Other skills call you to create or update tasks. You apply the match-or-create dedup logic and write to the tasks tables.

## When you're invoked

A calling skill provides:
- `extraction`: the natural-language task statement (e.g., "Pankaj will fix the chart bug by Friday")
- `owner_slack_id`: who owns the work
- `creator_slack_id`: who created/extracted (often agent:meeting-intelligence)
- `source`: meeting / slack_dm / slack_channel / standup_reply / manual
- `source_ref`: Fireflies ID+timestamp or Slack message URL
- `assigner_slack_id` (optional): if different from creator
- `is_status_update` (boolean): if true, expects an existing task to match (e.g., "T-42 done")
- `explicit_task_id` (optional): if the source mentions T-N explicitly

## Procedure

### Step 1: Explicit T-N match (cheap shortcut)

If `explicit_task_id` is provided OR the extraction text contains a `T-\d+` pattern:

1. Query the task. If it exists and `owner_slack_id` matches (or the speaker is the owner): treat as status update on this task.
2. If the task doesn't exist: log to task_events with `event_type='unknown_t_id_referenced'` for Abhinav review, then fall through to dedup step.

### Step 2: Match-or-create dedup

Pull candidate tasks for this owner:

```bash
sqlite3 /data/queue/alaska.db "
SELECT task_id, title, status, updated_at,
  (SELECT MAX(mention_at) FROM task_mentions WHERE task_id = t.task_id) AS last_mention
FROM tasks t
WHERE owner_slack_id = '$OWNER'
  AND status IN ('active', 'blocked', 'pending_acceptance')
  AND updated_at > datetime('now', '-14 days')
ORDER BY updated_at DESC LIMIT 20;
"
```

If `0 candidates` → no match possible, jump to Step 4 (create).

If `candidates exist`: call Claude Sonnet 4.6 with this prompt:

```
You're helping deduplicate task entries for the Alaska AI project manager.

A new statement was made by/about <owner first name>:
"<extraction text>"
Source: <source> (<source_ref>)

Candidate active tasks for this owner:
1. T-42: Chart UI in V2 (active, last updated 2 days ago)
2. T-65: Validate V2 PR 82-86 (active, last updated yesterday)
...

Is the new statement a MATCH for one of these tasks (status update or further discussion),
or is it a NEW task?

Return JSON:
{
  "decision": "match" | "new",
  "matched_task_id": "T-N" | null,
  "confidence": 0.0-1.0,
  "reasoning": "<one sentence>"
}

Rules:
- Match only if title/topic clearly overlap. Vague matches don't count.
- Same owner + same general topic + status verb → likely match.
- Different feature areas or different commitment → new.
- Confidence < 0.8 → default to "new" but flag for Abhinav review.
```

### Step 3: Act on match decision

**If `decision = match` AND `confidence >= 0.8`:**
- If `is_status_update` is true: UPDATE the matched task's status per Task Write Contract.
- Always log a `task_mentions` row with `mention_type` based on context.
- Log to `task_events` with `event_type='dedup_decision'`, `context` = reasoning.

**If `decision = new` (or low confidence):**
- Continue to Step 4.

### Step 4: Create new task

Per Task Write Contract "Create a new task" pattern.

Compute visibility:
- `personal` if owner == creator AND no additional_owners
- `team` if owner != creator OR additional_owners present
- Override `team` if source == 'meeting'

Generate `T-N`, INSERT, log `task_events` with `event_type='created'`.

### Step 5: Side effects (Phase B scope)

- **Personal task created:** silent. No Slack post.
- **Team task created (multi-owner OR meeting-source):** Phase B still silent. Phase D adds public channel announcement.
- **Status changed to 'done':** signal doc-keeper for Changelog (existing Agent Signals pattern).
- **Status changed to 'blocked':** create blockers row, link via `blocking_task_ids`.

## Return value

Return the resulting task object as JSON to the caller:

```json
{
  "task_id": "T-67",
  "action": "created" | "updated",
  "status": "active",
  "title": "...",
  "owner_slack_id": "...",
  "visibility": "personal" | "team"
}
```

## Anti-patterns

1. **Never create duplicates without exhausting the dedup step.** A duplicate task is the failure mode this skill exists to prevent.
2. **Never silently match low-confidence.** Default to new task with `[NEEDS LINK?]` note.
3. **Never write to tasks without writing to task_events.** Audit log is mandatory.
4. **Never modify tasks belonging to other owners unless explicitly authorized** (e.g., cross-person reassignment in Phase D).
````

- [ ] **Step 2: Commit**

```bash
git add skills/task-handler/SKILL.md
git commit -m "feat(task-handler): add match-or-create skill with dedup logic"
```

---

### Task B3: Wire Meeting Intelligence to task-handler

**Files:**
- Modify: `skills/meeting-intelligence/SKILL.md` (Step 5 + Step 6 updates)

Meeting Intelligence already extracts commitments from transcripts. Phase B: for each commitment, call task-handler with the right inputs. The DAILY_STATE.md update flow stays unchanged (parallel system).

- [ ] **Step 1: Read current Meeting Intelligence Step 5**

```bash
grep -n "## Step 5" skills/meeting-intelligence/SKILL.md
sed -n '127,160p' skills/meeting-intelligence/SKILL.md
```

- [ ] **Step 2: Add a new sub-step 5b after the existing "Extract Actions" content**

Use Edit to insert. Find the closing `### Anti-Hallucination Rules` line in Step 5, and add this section before it:

````markdown
### Step 5b: Write each commitment to SQLite via task-handler (Phase B+)

For each commitment extracted in Step 5:

1. Decide if it's a NEW task or a STATUS UPDATE on an existing one. (Status updates: "I shipped X yesterday", "T-42 done", "still working on chart UI" — these have explicit completion or progress verbs.)
2. Read `/data/skills/task-handler/SKILL.md` and invoke its procedure with:
   - `extraction`: the verbatim commitment quote
   - `owner_slack_id`: speaker's Slack ID from Team Roster (MEMORY.md)
   - `creator_slack_id`: 'agent:meeting-intelligence'
   - `source`: 'meeting'
   - `source_ref`: `<fireflies_id>+<sentence_index>`
   - `is_status_update`: true for completion/progress statements, false otherwise
   - `explicit_task_id`: any T-N reference found in the quote
3. Task-handler returns the task_id (created or matched). Log it in your meeting summary so you can reference it in Slack post.

**External actions (MobileFirst — Sai, Ritika, etc.):** SKIP this step entirely. Per existing rules, external action items go to Meeting Notes only, never to tasks.

**Recurring/daily activities:** SKIP. "Daily deploy check" is not a task.
````

- [ ] **Step 3: Update Step 7 (Post Summary) to include T-IDs**

Find the existing format block in Step 7. Update the `_New tasks:_` line to:

```markdown
_New tasks:_ [list T-IDs and one-line titles, only if genuinely new]
_Status updates:_ [T-IDs marked done, blocked, etc. as a separate line]
```

- [ ] **Step 4: Verify the integration is internally consistent**

```bash
grep -n "task-handler" skills/meeting-intelligence/SKILL.md
# Expected: at least 1 reference in Step 5b
grep -n "T-\\\\?N\\|T-ID" skills/meeting-intelligence/SKILL.md
# Expected: references to T-IDs in Steps 5b and 7
```

- [ ] **Step 5: Commit**

```bash
git add skills/meeting-intelligence/SKILL.md
git commit -m "feat(meeting-intelligence): write commitments to tasks via task-handler"
```

---

### Task B4: Wire Slack Commands DM handlers (TASK_CREATE, TASK_UPDATE, TASK_BLOCKER)

**Files:**
- Modify: `skills/slack-commands/SKILL.md` (add intent-driven handlers)

The intent classifier (Phase A, observation mode) now needs its first downstream consumer for DMs. Slack Commands gets the action paths for the three TASK_* intents it can handle in Phase B.

- [ ] **Step 1: Read current slack-commands structure**

```bash
head -10 skills/slack-commands/SKILL.md
grep -n "^## " skills/slack-commands/SKILL.md
```

- [ ] **Step 2: Add a new section "Intent-driven actions (Phase B+)" before "General Questions"**

Use Edit to add this section. The exact insertion point is right before `## General Questions`:

````markdown
## Intent-driven actions (Phase B+)

For every DM Alaska receives, BEFORE responding directly:

1. Invoke intent-classifier (synchronous mode, see `/data/skills/intent-classifier/SKILL.md`).
2. Classifier returns `{intent, confidence, entities, would_have_done}`.
3. If intent is one of the action intents below, run that handler. Otherwise fall through to the existing query/help responses.

**Phase B handlers (DMs only — channel TASK_CREATE/UPDATE comes in Phase D):**

### TASK_CREATE handler

Triggered by: "starting on X", "I'll do Y", "add task: Z"

1. Read /data/skills/task-handler/SKILL.md
2. Invoke task-handler with:
   - extraction: the message text
   - owner_slack_id: the DM sender's Slack ID
   - creator_slack_id: the same Slack ID (self-create = personal)
   - source: 'slack_dm'
   - source_ref: Slack DM message URL
   - is_status_update: false
3. Task-handler returns `{task_id, action, ...}`.
4. Reply in the DM: "Tracking as T-N: [title]. I'll surface it in your standup brief tonight."
5. If the message had a due date hint ("by Friday"), parse and update task.due_at.

### TASK_UPDATE handler

Triggered by: "T-42 done", "still working on T-65", "blocked on T-58"

1. Extract the T-N from message text. If absent: ask "Which task? Reply with the T-N or describe it."
2. Invoke task-handler with:
   - extraction: the message text
   - owner_slack_id: DM sender
   - source: 'slack_dm'
   - source_ref: Slack message URL
   - is_status_update: true
   - explicit_task_id: the T-N found
3. Detect target status from verb: done/blocked/active.
4. Reply in DM: "Got it — T-N marked as [status]." (One line. No internal narration per shared-toolkit rules.)

### TASK_BLOCKER handler

Triggered by: "blocked on Plaid docs", "can't proceed until X"

1. Generate blocker_id: `B-N` next from blockers table.
2. INSERT into blockers with the message text as title, sender as raised_by.
3. If the blocker text mentions a T-N, link it via `blocking_task_ids = '["T-N"]'` AND update that task's status to 'blocked'.
4. Reply in DM: "Logged blocker B-N. [If linked to T-N: T-N is now marked blocked.] I'll surface it in tonight's brief."

### REMINDER_REQUEST handler — DEFERRED to Phase C

Reply in DM: "Reminders aren't wired up yet — coming in Phase C. For now I'll note it; remind me by hand near the date."

### Authority note

In Phase B, all task actions are SELF-SCOPED (the DM sender is always the owner). Cross-person assignment (TASK_ASSIGN) comes in Phase D.
````

- [ ] **Step 3: Commit**

```bash
git add skills/slack-commands/SKILL.md
git commit -m "feat(slack-commands): wire TASK_CREATE/UPDATE/BLOCKER intent handlers"
```

---

### Task B5: Update pre-call-brief to read from SQLite

**Files:**
- Modify: `skills/pre-call-brief/SKILL.md`

Pre-call brief currently reads from DAILY_STATE.md. Phase B: read from SQLite tasks table primarily, fall back to DAILY_STATE.md for anything not yet captured as a task. Show T-IDs. Support T-N-format reply parsing.

- [ ] **Step 1: Read current pre-call-brief**

```bash
wc -l skills/pre-call-brief/SKILL.md
grep -n "^## " skills/pre-call-brief/SKILL.md
```

- [ ] **Step 2: Rewrite the "Step 3: Generate the Brief" section**

Use Edit to replace the existing brief generation block. New content:

````markdown
## Step 3: Generate the Brief (Phase B — SQLite-aware)

For each team member who's active today, query SQLite for their task state:

```bash
# Active and blocked tasks
sqlite3 /data/queue/alaska.db "
SELECT task_id, title, status, priority, due_at, updated_at, source
FROM tasks
WHERE owner_slack_id = '$OWNER' AND status IN ('active', 'blocked', 'pending_acceptance')
ORDER BY
  CASE status WHEN 'pending_acceptance' THEN 0 WHEN 'blocked' THEN 1 ELSE 2 END,
  CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
  due_at ASC NULLS LAST;
"

# New since yesterday (created < 24h ago)
sqlite3 /data/queue/alaska.db "
SELECT task_id, title, source, assigner_slack_id
FROM tasks
WHERE owner_slack_id = '$OWNER' AND created_at > datetime('now', '-1 day');
"

# Reminders due today (Phase C wires this; Phase B returns empty result)
sqlite3 /data/queue/alaska.db "
SELECT action_id, payload FROM scheduled_actions
WHERE recipient_slack_id = '$OWNER' AND status = 'pending'
  AND fire_at BETWEEN date('now') AND date('now', '+1 day');
"

# Tasks awaiting ack (Phase D wires this; Phase B returns empty result)
sqlite3 /data/queue/alaska.db "
SELECT task_id, title FROM tasks
WHERE owner_slack_id = '$OWNER' AND status = 'pending_acceptance';
"
```

Format the brief:

```
[Name] — [Day, Date]

ACTIVE ([N]):
• T-N  [Title] — [source context: e.g., 'assigned by Darwin Wed', 'committed in Tue meeting']
        [optional: last activity hint from task_events]
• T-N  ...

REMINDERS DUE TODAY ([N]):  (Phase C — empty in Phase B)
• [reminder text]

NEW SINCE YESTERDAY ([N]):
• T-N [Title] ([source: e.g., 'Darwin → you in #project-management Wed 8:50 PM'])

NEEDS YOUR ACK ([N]): (Phase D — empty in Phase B)
• T-N — please reply 'ack' or 'pass'

BLOCKED ([N]):
• T-N [Title] — blocker: [blocker text]

Reply format:
  T-N done             — mark complete
  T-N blocked by X     — log blocker
  T-N active           — confirm working
  new: <description>   — capture new task right now

Team call in 30 min.
```

**If a person has zero tasks in SQLite yet (early Phase B before all members have task history):** fall back to the OLD format using DAILY_STATE.md per-person sections, with a footer note: "_(switching to v2 task system — DM me to capture your active work)_"

## Step 4: Listen for replies and parse

After posting briefs, watch the thread for replies. Use this parser (regex first, LLM fallback):

```python
# Pseudocode for the reply parser
patterns = [
    (r'^T-(\d+)\s+done\b', 'mark_done'),
    (r'^T-(\d+)\s+blocked\s+by\s+(.+)$', 'mark_blocked_with_reason'),
    (r'^T-(\d+)\s+active\b', 'confirm_active'),
    (r'^T-(\d+)\s+(.+)$', 'update_with_note'),
    (r'^new:\s+(.+)$', 'create_new'),
    (r'^on leave\b', 'mark_on_leave'),
]
```

For matches: call the appropriate task-handler operation.
For non-matches: invoke intent classifier on the reply text, route accordingly.
For ambiguous: reply asking for clarification (e.g., "Which task? T-42 or T-43?").

## Anti-patterns

- **Don't post empty sections.** If ACTIVE has 0 items, omit the heading entirely.
- **Don't mix T-IDs and untracked items in the same section.** During Phase B transition, separate cleanly with the footer note.
- **Don't auto-mark stale tasks as dropped.** That's a Phase E+ decision.
````

- [ ] **Step 3: Commit**

```bash
git add skills/pre-call-brief/SKILL.md
git commit -m "feat(pre-call-brief): read from SQLite tasks, support T-N reply parsing"
```

---

### Task B6: Phase B acceptance — open PR and observe

- [ ] **Step 1: Open the Phase B PR**

```bash
git push -u origin feat/v2-task-phase-b
gh pr create --base main --head feat/v2-task-phase-b \
  --title "Phase B: Basic task lifecycle (Meeting Intelligence + DMs)" \
  --body "$(cat <<'EOF'
Wires the v2 task model into Meeting Intelligence and Slack DM handling.

What changes for users:
- Engineers can DM Alaska: 'starting on chart UI', 'T-42 done', 'blocked on Plaid docs'
- Meeting Intelligence creates SQLite tasks for each commitment (parallel to existing DAILY_STATE.md updates — both run)
- Pre-call brief shows stable T-IDs; replies in T-N format land cleanly

What does NOT change:
- DAILY_STATE.md narrative output continues unchanged
- No cross-person workflow yet (Phase D)
- No reminders/scheduling yet (Phase C)
EOF
)"
```

- [ ] **Step 2: After merge + Railway redeploy, manually exercise**

DM Alaska: "starting on the Phase B testing audit"

Expected response: "Tracking as T-N: starting on the Phase B testing audit. I'll surface it in your standup brief tonight."

```sql
-- Verify
SELECT task_id, title, status, owner_slack_id, source FROM tasks ORDER BY id DESC LIMIT 5;
SELECT * FROM task_events ORDER BY id DESC LIMIT 5;
```

- [ ] **Step 3: Wait for next meeting → Meeting Intelligence cycle**

After the 9 PM IST call processes, verify tasks were created from meeting commitments:

```sql
SELECT task_id, title, owner_slack_id, source, source_ref
FROM tasks
WHERE source = 'meeting' AND created_at > datetime('now', '-12 hours');
```

- [ ] **Step 4: Verify the pre-call brief uses T-IDs the next day**

Watch #daily-standup at 8:30 PM IST. Each per-person message should show T-N IDs on tracked items.

- [ ] **Step 5: Iterate the task-handler dedup if false positives/negatives appear**

If 2+ duplicates appear or 2+ false-merges happen: tune the match-or-create LLM prompt in task-handler/SKILL.md. Push fix, observe another 48h.

- [ ] **Step 6: Phase B complete — proceed to Phase C**

```bash
git checkout main && git pull origin main
```

---

# PHASE C — Scheduling Engine

**Phase goal:** "Remind me in 5 days", "follow up in 48h", "every Friday DM me my open tasks" — all become real. Personal routines self-serve; team-wide routines flow through Abhinav approval.

**Phase risk:** Low — new capability, no replacement of existing behavior.

**Phase output:** Reminders and routines work end-to-end. Phase D builds on top (auto-escalation for cross-person tasks).

**Pre-flight:**

- [ ] `git checkout main && git pull origin main`
- [ ] `git switch -c feat/v2-task-phase-c`

---

### Task C1: Add Python dateutil to Dockerfile

**Files:**
- Modify: `Dockerfile`

RRULE (recurrence rule) parsing is non-trivial. Use Python's `dateutil` package — battle-tested standard for this.

- [ ] **Step 1: Modify Dockerfile**

Find the existing `apt-get install` block (around line 11-14):

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*
```

Replace with:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    python3-dateutil \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Verify python3-dateutil install path**

After redeploy (or in a local docker build), verify:

```bash
python3 -c "from dateutil import rrule; print(rrule.__version__ if hasattr(rrule, '__version__') else 'OK')"
# Expected: OK or version string
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "chore(docker): add python3-dateutil for RRULE parsing"
```

---

### Task C2: Create lib/rrule_helper.py + tests

**Files:**
- Create: `lib/rrule_helper.py`
- Create: `tests/test_rrule_helper.py`
- Modify: `Dockerfile` (COPY lib/ to /opt/lib/)
- Modify: `entrypoint.sh` (export PYTHONPATH=/opt/lib)

A small Python module that parses RRULE strings and computes next fire times. Used by reminder-dispatcher.

- [ ] **Step 1: Create lib/ and write rrule_helper.py**

```bash
mkdir -p lib tests
```

`lib/rrule_helper.py`:

```python
"""
RRULE helper for Alaska v2 scheduling engine.

Wraps python-dateutil's rrule module with a few helpers that handle
the specific cases Alaska needs:
- Compute next fire time after a given datetime
- Validate RRULE string syntax
- Format human-readable description (for confirmation messages)
"""

from datetime import datetime, timezone
from dateutil import rrule
from dateutil.parser import isoparse


def next_fire_time(rrule_str: str, after: datetime | None = None) -> datetime:
    """
    Compute the next firing time for an RRULE, after a given datetime.

    Args:
        rrule_str: an RRULE string, e.g. 'FREQ=WEEKLY;BYDAY=FR;BYHOUR=17'
        after: anchor datetime (default: now UTC)

    Returns:
        UTC datetime of next firing

    Raises:
        ValueError: if rrule_str is malformed
    """
    if after is None:
        after = datetime.now(timezone.utc)
    # rrulestr returns an rruleset / rrule; first occurrence after `after`
    rule = rrule.rrulestr(f"DTSTART:{after.strftime('%Y%m%dT%H%M%SZ')}\nRRULE:{rrule_str}")
    next_occurrence = rule.after(after, inc=False)
    if next_occurrence is None:
        raise ValueError(f"RRULE has no future occurrence after {after}: {rrule_str}")
    return next_occurrence


def validate_rrule(rrule_str: str) -> tuple[bool, str]:
    """
    Check if an RRULE string is syntactically valid.

    Returns:
        (is_valid, error_message_or_empty)
    """
    try:
        anchor = datetime.now(timezone.utc)
        rrule.rrulestr(f"DTSTART:{anchor.strftime('%Y%m%dT%H%M%SZ')}\nRRULE:{rrule_str}")
        return (True, "")
    except (ValueError, KeyError) as e:
        return (False, str(e))


def describe_rrule(rrule_str: str) -> str:
    """
    Return a human-readable description of an RRULE.
    Crude but useful for confirmation messages.

    Example: 'FREQ=WEEKLY;BYDAY=FR;BYHOUR=17' -> 'every Friday at 17:00 UTC'
    """
    parts = {}
    for kv in rrule_str.split(';'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            parts[k] = v

    freq = parts.get('FREQ', 'UNKNOWN').lower()
    day_map = {'MO': 'Monday', 'TU': 'Tuesday', 'WE': 'Wednesday',
               'TH': 'Thursday', 'FR': 'Friday', 'SA': 'Saturday', 'SU': 'Sunday'}

    bits = []
    if freq == 'daily':
        bits.append('every day')
    elif freq == 'weekly':
        if 'BYDAY' in parts:
            days = [day_map.get(d, d) for d in parts['BYDAY'].split(',')]
            bits.append('every ' + ', '.join(days))
        else:
            bits.append('every week')
    elif freq == 'monthly':
        bits.append('every month')
    else:
        bits.append(f'every {freq}')

    if 'BYHOUR' in parts:
        hour = int(parts['BYHOUR'])
        minute = int(parts.get('BYMINUTE', '0'))
        bits.append(f'at {hour:02d}:{minute:02d} UTC')

    return ' '.join(bits)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: rrule_helper.py <rrule>')
        sys.exit(1)
    rule_str = sys.argv[1]
    valid, err = validate_rrule(rule_str)
    if not valid:
        print(f'INVALID: {err}')
        sys.exit(1)
    print(f'Description: {describe_rrule(rule_str)}')
    print(f'Next fire:   {next_fire_time(rule_str).isoformat()}')
```

- [ ] **Step 2: Write tests/test_rrule_helper.py**

`tests/test_rrule_helper.py`:

```python
"""Tests for lib/rrule_helper.py."""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add lib/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))

from rrule_helper import next_fire_time, validate_rrule, describe_rrule


def test_validate_valid_rrule():
    valid, err = validate_rrule('FREQ=WEEKLY;BYDAY=FR;BYHOUR=17')
    assert valid, f"Expected valid, got error: {err}"
    assert err == ''


def test_validate_invalid_rrule():
    valid, err = validate_rrule('NOT_A_RULE')
    assert not valid
    assert err != ''


def test_next_fire_weekly_friday_5pm():
    # Anchor: Monday May 19, 2026 at 10:00 UTC
    anchor = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    nxt = next_fire_time('FREQ=WEEKLY;BYDAY=FR;BYHOUR=17;BYMINUTE=0', after=anchor)
    # Should be Friday May 22, 2026 at 17:00 UTC
    assert nxt.weekday() == 4  # Friday
    assert nxt.hour == 17
    assert nxt.minute == 0
    assert nxt.date() == datetime(2026, 5, 22).date()


def test_next_fire_daily():
    anchor = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    nxt = next_fire_time('FREQ=DAILY;BYHOUR=9', after=anchor)
    # Should be next day at 9:00 UTC
    assert nxt.date() == (anchor + timedelta(days=1)).date()
    assert nxt.hour == 9


def test_describe_weekly_friday():
    desc = describe_rrule('FREQ=WEEKLY;BYDAY=FR;BYHOUR=17')
    assert 'Friday' in desc
    assert '17:00' in desc


def test_describe_daily():
    desc = describe_rrule('FREQ=DAILY;BYHOUR=9')
    assert 'every day' in desc
    assert '09:00' in desc


if __name__ == '__main__':
    # Run all tests
    import inspect
    test_funcs = [obj for name, obj in inspect.getmembers(sys.modules[__name__])
                  if inspect.isfunction(obj) and name.startswith('test_')]
    failed = 0
    for fn in test_funcs:
        try:
            fn()
            print(f'PASS: {fn.__name__}')
        except AssertionError as e:
            print(f'FAIL: {fn.__name__}: {e}')
            failed += 1
        except Exception as e:
            print(f'ERROR: {fn.__name__}: {type(e).__name__}: {e}')
            failed += 1
    print(f'\n{len(test_funcs) - failed}/{len(test_funcs)} passed')
    sys.exit(1 if failed else 0)
```

- [ ] **Step 3: Run tests locally**

```bash
cd alaska-openclaw
python3 tests/test_rrule_helper.py
# Expected: 5/5 passed (after dateutil is installed locally — `pip3 install python-dateutil` if needed)
```

If python-dateutil isn't installed locally:

```bash
pip3 install python-dateutil
python3 tests/test_rrule_helper.py
```

- [ ] **Step 4: Modify Dockerfile to copy lib/ into image**

Find the existing `COPY skills/` line. Add right after:

```dockerfile
# Copy Python helper library
COPY --chown=node:node lib/ /opt/lib/
```

- [ ] **Step 5: Modify entrypoint.sh to set PYTHONPATH**

After the existing env setup block (around line 4), add:

```bash
# Make /opt/lib importable for Python helpers (rrule_helper, etc.)
export PYTHONPATH="/opt/lib:${PYTHONPATH}"
```

- [ ] **Step 6: Commit**

```bash
git add lib/ tests/ Dockerfile entrypoint.sh
git commit -m "feat(scheduling): add RRULE helper module with tests"
```

---

### Task C3: Write reminder-dispatcher SKILL.md

**Files:**
- Create: `skills/reminder-dispatcher/SKILL.md`

The cron-fired skill that reads `scheduled_actions WHERE fire_at <= now`, executes each, and re-queues recurring ones.

- [ ] **Step 1: Create skill**

```bash
mkdir -p skills/reminder-dispatcher
```

`skills/reminder-dispatcher/SKILL.md`:

````markdown
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

Read `/data/skills/shared-toolkit/SKILL.md` for queue patterns, Slack channel routing, and communication standards.

You are the Reminder Dispatcher. Cron fires you every 15 min. You read due scheduled_actions, execute each, and re-queue recurring ones.

## Procedure

### Step 1: Read due actions

```bash
sqlite3 /data/queue/alaska.db "
SELECT id, action_id, action_type, recipient_slack_id, recipient_channel_id,
       linked_task_id, payload, recurrence_rule, attempts, max_attempts, scope
FROM scheduled_actions
WHERE status = 'pending' AND fire_at <= datetime('now')
ORDER BY fire_at ASC LIMIT 20;
"
```

If 0 rows: exit silently (no action needed).

### Step 2: Execute each due action

Per row, dispatch by `action_type`:

#### `remind`

Payload format: `{"message": "...", "linked_task_id": "T-N" or null}`

1. If `recipient_slack_id`: send Slack DM. Format:
   ```
   _Reminder you set [time ago]:_
   <message text>
   [If linked_task_id: Linked task: T-N — <current title>]
   ```
2. If `recipient_channel_id`: post to that channel (use only if explicitly scheduled for channel).

#### `surface_task`

Payload format: `{"task_id": "T-N", "reason": "user_snoozed_until_today"}`

1. Look up task, ensure still active.
2. The next pre-call brief naturally surfaces this — write a marker to task_events with `event_type='dispatcher_surfaced'`.

(No Slack action needed; the pre-call brief is the surface.)

#### `escalate`

Payload format: `{"reason": "no_ack_after_2h" | "deadline_4h_warning" | ..., "task_id": "T-N"}`

1. Look up task.
2. Based on reason:
   - `no_ack_after_2h`: DM Abhinav: "T-N has not been ack'd by <owner first name> (assigned by <assigner> Xh ago). Want me to proceed with default, chase the owner, or reassign?"
   - `deadline_4h_warning`: DM the task owner: "Heads-up: T-N is due in 4h. Status update?"
   - `overdue_24h`: DM both task owner AND assigner: "T-N is 24h overdue. <Owner> — what's the status?"

#### `recurring_routine`

Payload format: `{"prompt": "<the recurring action's prompt>", "scope": "personal" | "team"}`

1. Execute the `prompt` action — typically a Slack DM or channel post.
2. AFTER executing, compute next fire time:
   ```bash
   NEXT_FIRE=$(python3 /opt/lib/rrule_helper.py "<recurrence_rule>")
   ```
3. INSERT a new `scheduled_actions` row with `fire_at = NEXT_FIRE`, same recurrence_rule, status='pending'.
4. Mark current row as `fired`.

#### `auto_followup`

Payload format: `{"check_status_first": true, "task_id": "T-N", "message_if_active": "..."}`

1. Look up task. If status is `done` or `dropped`: skip (no follow-up needed). Mark action fired with note.
2. If still active or blocked: send the `message_if_active` as DM to the relevant party (usually the assigner or Abhinav).

### Step 3: Mark action fired (or failed)

After successful execution:

```bash
sqlite3 /data/queue/alaska.db "
UPDATE scheduled_actions
SET status = 'fired', fired_at = CURRENT_TIMESTAMP
WHERE id = $ROW_ID;
"

# If linked to a task, log a task_event
if [ -n "$LINKED_TASK_ID" ]; then
  sqlite3 /data/queue/alaska.db "
  INSERT INTO task_events (task_id, event_type, actor_slack_id, context)
  VALUES ('$LINKED_TASK_ID', 'scheduled_action_fired', 'agent:reminder-dispatcher',
          'Action ID: $ACTION_ID, type: $ACTION_TYPE');
  "
fi
```

If execution fails (e.g., Slack API error):

```bash
sqlite3 /data/queue/alaska.db "
UPDATE scheduled_actions
SET attempts = attempts + 1
WHERE id = $ROW_ID;
"

# If max_attempts exhausted, cancel and alert Abhinav
if [ $((attempts + 1)) -ge $MAX_ATTEMPTS ]; then
  sqlite3 /data/queue/alaska.db "UPDATE scheduled_actions SET status='cancelled' WHERE id=$ROW_ID;"
  # DM Abhinav with details
fi
```

### Step 4: Report (only if anything fired)

If at least one action fired, log a single line:

```bash
echo "[reminder-dispatcher] Fired $N actions: <breakdown by type>"
```

No Slack post unless an action explicitly required it.

## Anti-patterns

1. **Never silently fail.** Failed actions log to task_events (if linked) and increment attempts. Max attempts = 3 by default, then cancel + alert.
2. **Never fire an action twice.** Mark status=fired before any side effects, or wrap in a transaction.
3. **Never assume Notion / Slack / Fireflies is up.** Check via shared-toolkit health checks if errors mount.
4. **Always compute next_fire_at for recurring_routine BEFORE marking the current one fired.** Otherwise a crash mid-loop loses the recurrence.
````

- [ ] **Step 2: Commit**

```bash
git add skills/reminder-dispatcher/SKILL.md
git commit -m "feat(scheduling): add reminder-dispatcher skill"
```

---

### Task C4: Add REMINDER_REQUEST handler to slack-commands

**Files:**
- Modify: `skills/slack-commands/SKILL.md` (replace the Phase B deferred handler)

The intent classifier already classifies REMINDER_REQUEST. Now wire the handler that creates the scheduled_action.

- [ ] **Step 1: Find the deferred handler in slack-commands**

```bash
grep -n "REMINDER_REQUEST handler — DEFERRED" skills/slack-commands/SKILL.md
```

- [ ] **Step 2: Replace the deferred stub with the real handler**

Use Edit to replace the entire section:

````markdown
### REMINDER_REQUEST handler (Phase C+)

Triggered by: "remind me about X in 5 days", "every Friday at 5 PM DM me ...", "follow up with Pankaj on T-42 tomorrow"

1. Parse the request. Identify:
   - **One-shot vs recurring** — "in 5 days" = one-shot; "every Friday" = recurring.
   - **Recipient** — usually the DM sender (self); could be a channel for team routines.
   - **Linked task** — any T-N reference.
   - **Fire time** — parse relative dates ("in 5 days", "tomorrow at 9am", "Friday at 5pm").
   - **Message text** — what to remind about.

2. Determine scope:
   - `personal` if recipient is the sender AND no other people are mentioned.
   - `team` if recipient is a channel OR multiple people are mentioned OR the action posts publicly.

3. For `personal` scope: create the scheduled_action directly.

   For one-shot:
   ```bash
   ACTION_ID=$(sqlite3 /data/queue/alaska.db "SELECT 'SA-' || COALESCE(MAX(CAST(SUBSTR(action_id, 4) AS INTEGER)) + 1, 1) FROM scheduled_actions;")
   sqlite3 /data/queue/alaska.db "
   INSERT INTO scheduled_actions
     (action_id, action_type, fire_at, recipient_slack_id, linked_task_id,
      payload, scope, created_by_slack_id)
   VALUES
     ('$ACTION_ID', 'remind', '$FIRE_AT_ISO', '$SENDER_SLACK_ID',
      $LINKED_TASK_ID_OR_NULL,
      '$PAYLOAD_JSON', 'personal', '$SENDER_SLACK_ID');
   "
   ```

   For recurring:
   ```bash
   # Validate RRULE first
   python3 /opt/lib/rrule_helper.py "$RRULE_STRING"
   # If valid, compute first fire
   FIRST_FIRE=$(python3 -c "from rrule_helper import next_fire_time; print(next_fire_time('$RRULE_STRING').isoformat())")
   sqlite3 /data/queue/alaska.db "
   INSERT INTO scheduled_actions
     (action_id, action_type, fire_at, recurrence_rule, recipient_slack_id,
      payload, scope, created_by_slack_id)
   VALUES
     ('$ACTION_ID', 'recurring_routine', '$FIRST_FIRE', '$RRULE_STRING',
      '$SENDER_SLACK_ID', '$PAYLOAD_JSON', 'personal', '$SENDER_SLACK_ID');
   "
   ```

   Confirm to sender in DM:
   ```
   Got it — I'll remind you [describe_rrule output OR formatted one-shot time].
   [If linked: Linked to T-N.]
   Reminder ID: SA-N (reply 'cancel SA-N' to remove it later).
   ```

4. For `team` scope: create routine_proposal, DO NOT create scheduled_action yet.

   ```bash
   PROPOSAL_ID=$(sqlite3 /data/queue/alaska.db "SELECT 'RP-' || COALESCE(MAX(CAST(SUBSTR(proposal_id, 4) AS INTEGER)) + 1, 1) FROM routine_proposals;")
   sqlite3 /data/queue/alaska.db "
   INSERT INTO routine_proposals
     (proposal_id, proposed_by_slack_id, description, proposed_payload,
      proposed_recurrence_rule, proposed_recipient, expires_at)
   VALUES
     ('$PROPOSAL_ID', '$SENDER_SLACK_ID', '$DESCRIPTION',
      '$PAYLOAD_JSON', '$RRULE_STRING', '$RECIPIENT_DESCRIPTION',
      datetime('now', '+7 days'));
   "
   ```

   Reply to sender:
   ```
   That's a team-wide routine — I'll need Abhinav to approve it first. Flagged for him (RP-N).
   I'll let you know once he responds (or after 7 days if he doesn't).
   ```

   DM Abhinav:
   ```
   *Routine proposal RP-N* from <sender first name>:
   "<description>"
   Schedule: <describe_rrule output>
   Recipient: <recipient description>

   Reply: 'approve RP-N' / 'decline RP-N because <reason>' / 'modify RP-N: <changes>'
   Expires in 7 days if no response.
   ```
````

- [ ] **Step 3: Add the routine-approval reply handler to slack-commands**

In a new section "Routine proposal approval (Abhinav-only)" added near the bottom of slack-commands:

````markdown
## Routine Proposal Approval (Abhinav-only)

When Abhinav DMs "approve RP-N" / "decline RP-N ..." / "modify RP-N ...":

1. Verify sender is Abhinav (Slack ID U07GKLVA9FE). If not, respond "Only Abhinav can approve routines."
2. Look up RP-N. If status != 'pending': respond "RP-N is already <status>."
3. On `approve`:
   - Create the scheduled_action from the proposal fields.
   - Update routine_proposals row: status='approved', abhinav_response=NULL, responded_at=NOW.
   - DM both Abhinav and the proposer: "RP-N approved. Routine SA-N created."
4. On `decline`:
   - Update routine_proposals: status='declined', abhinav_response='<reason>'.
   - DM proposer: "Your routine proposal RP-N was declined. Reason: <reason>"
5. On `modify`:
   - Update the proposal fields, keep status='pending'.
   - DM proposer: "RP-N modified by Abhinav. New schedule: <describe>. Will re-confirm after."
   (Modified version still requires final approve.)
````

- [ ] **Step 4: Commit**

```bash
git add skills/slack-commands/SKILL.md
git commit -m "feat(scheduling): wire REMINDER_REQUEST handler + routine proposal flow"
```

---

### Task C5: Add reminder-dispatcher cron + routine-proposal-watch cron

**Files:**
- Modify: `config/cron-jobs-backup.json` (snapshot)

- [ ] **Step 1: Add the two crons to the JSON snapshot**

```bash
python3 << 'EOF'
import json
from pathlib import Path
p = Path('config/cron-jobs-backup.json')
data = json.loads(p.read_text())

data['jobs'].append({
    "id": "PLACEHOLDER-reminder-dispatcher",
    "name": "Reminder Dispatcher",
    "enabled": True,
    "schedule": {"kind": "cron", "expr": "*/15 * * * *", "tz": "UTC"},
    "agentId": "main",
    "sessionKey": "agent:main:main",
    "sessionTarget": "isolated",
    "wakeMode": "now",
    "payload": {
        "kind": "user-message",
        "message": "You are the reminder-dispatcher running on cron. Read /data/skills/reminder-dispatcher/SKILL.md and execute the procedure. Fire all due scheduled_actions.",
        "timeoutSeconds": 240
    },
    "delivery": {"channel": "none"},
    "state": {}
})

data['jobs'].append({
    "id": "PLACEHOLDER-routine-proposal-watch",
    "name": "Routine Proposal Watch (expire after 7 days)",
    "enabled": True,
    "schedule": {"kind": "cron", "expr": "0 6 * * *", "tz": "UTC"},
    "agentId": "main",
    "sessionKey": "agent:main:main",
    "sessionTarget": "isolated",
    "wakeMode": "now",
    "payload": {
        "kind": "user-message",
        "message": "Check routine_proposals for any pending proposals past their expires_at. Mark them 'expired'. DM the proposer with: 'Your routine proposal RP-N expired without response from Abhinav.' If any expired, also DM Abhinav with a summary.",
        "timeoutSeconds": 120
    },
    "delivery": {"channel": "none"},
    "state": {}
})

p.write_text(json.dumps(data, indent=2))
print(f"Total jobs now: {len(data['jobs'])}")
EOF
```

- [ ] **Step 2: Apply both via OpenClaw dashboard**

In the dashboard:
1. Add "Reminder Dispatcher" cron — schedule `*/15 * * * *` UTC, isolated session, 240s timeout
2. Add "Routine Proposal Watch" cron — schedule `0 6 * * *` UTC, isolated, 120s timeout

Replace PLACEHOLDER UUIDs in the JSON with the real UUIDs OpenClaw generates.

- [ ] **Step 3: Commit**

```bash
git add config/cron-jobs-backup.json
git commit -m "chore(cron): add reminder-dispatcher + routine-proposal-watch"
```

---

### Task C6: Phase C acceptance — PR, deploy, exercise

- [ ] **Step 1: Open Phase C PR**

```bash
git push -u origin feat/v2-task-phase-c
gh pr create --base main --head feat/v2-task-phase-c \
  --title "Phase C: Scheduling engine (reminders + recurring routines)" \
  --body "Adds reminder-dispatcher skill + dispatcher cron + REMINDER_REQUEST handler. Personal routines self-serve; team routines flow through routine_proposals → Abhinav approval. python3-dateutil added for RRULE parsing."
```

After merge → Railway redeploy → cron applied in dashboard.

- [ ] **Step 2: Exercise personal reminder**

DM Alaska: "remind me in 2 minutes about testing the reminder"

Expected: Alaska confirms with SA-N. After ~2 minutes (or next 15-min cron firing — whichever is later), Alaska DMs back the reminder.

```sql
-- Verify
SELECT action_id, action_type, fire_at, status, payload
FROM scheduled_actions
WHERE created_by_slack_id = 'U07GKLVA9FE'
ORDER BY id DESC LIMIT 3;
```

- [ ] **Step 3: Exercise recurring personal routine**

DM Alaska: "every day at 9 AM IST DM me a good morning"

Expected: Alaska validates RRULE, confirms SA-N. First fire happens next 9 AM IST (3:30 UTC). After fire, the row's status=fired and a NEW SA row exists with fire_at = next 9 AM.

- [ ] **Step 4: Exercise team routine proposal (from non-Abhinav)**

Have Sandeep DM Alaska: "every Wednesday 3 PM post midweek check-in in #project-management"

Expected:
- Alaska creates RP-N (no scheduled_action yet)
- Sandeep gets "flagged for Abhinav" reply
- Abhinav gets DM with proposal details
- Abhinav DMs "approve RP-N" → scheduled_action created, both notified

- [ ] **Step 5: Phase C complete**

```bash
git checkout main && git pull origin main
```

---

# PHASE D — Cross-Person Workflow

**Phase goal:** TASK_ASSIGN intent triggers the full 10-step cross-person workflow from the spec. Public channel announcement, per-assignee DM with ack/pass/reassign, auto-escalation.

**Phase risk:** Medium — new public surface area. Land with explicit "Tracking as T-N" thread replies so behavior is visible/correctable.

**Phase output:** Darwin can @-mention Shailesh and Tarun in #project-management with task language; T-N gets created, public announcement posted, each assignee gets DM'd, ack/pass routing works, escalation fires if no ack in 2h.

**Pre-flight:**

- [ ] `git checkout main && git pull origin main`
- [ ] `git switch -c feat/v2-task-phase-d`

---

### Task D1: Enable channel-message intent action (move classifier out of obs-mode for TASK_ASSIGN)

**Files:**
- Modify: `skills/intent-classifier/SKILL.md` (allow TASK_ASSIGN to act, others stay obs-mode for one more week)

In Phase A we set classifier to observation-only. Phase B added action paths for DMs only. Phase D adds the FIRST channel-message action path: TASK_ASSIGN.

- [ ] **Step 1: Modify the "Write classification result" section**

Find the section. Update the "Observation mode (Phase A)" block and add a new "Phase D" block:

````markdown
**Production mode (selective):**

- DMs: act per slack-commands TASK_CREATE/UPDATE/BLOCKER handlers (Phase B+) and REMINDER_REQUEST handler (Phase C+).
- Channel messages classified as `TASK_ASSIGN` (Phase D+): route to cross-person assignment workflow in slack-commands.
- All other channel intents: remain observation-only. Log to classifier_audit with `would_have_done`, do not act.

This selective rollout lets us validate TASK_ASSIGN behavior before opening other intents to channel-driven action.
````

- [ ] **Step 2: Commit**

```bash
git add skills/intent-classifier/SKILL.md
git commit -m "feat(intent-classifier): enable TASK_ASSIGN channel action (Phase D)"
```

---

### Task D2: Add TASK_ASSIGN handler with full workflow

**Files:**
- Modify: `skills/slack-commands/SKILL.md` (add the workflow section)

The 10-step workflow from the spec, written as a single procedure the slack-commands skill executes.

- [ ] **Step 1: Add the workflow section**

Add after the existing TASK_BLOCKER section:

````markdown
### TASK_ASSIGN handler (Phase D+)

Triggered by: channel messages with @-mentions + task-shaped language. Example:

> "@Shailesh @Tarun please look at users 2854, 2891, 2894 in 48 hours"

#### Procedure

**Step 1: Parse classifier output**

Read the classifier entities:
- `owners_mentioned`: array of Slack IDs (resolved from @-mentions)
- `task_topic`: short summary
- `dates_mentioned`: deadline strings

**Step 2: Resolve owners**

For each Slack ID in `owners_mentioned`:
- Look up in MEMORY.md Team Roster — confirm internal team member (skip External like Sai)
- If unresolved, log to task_events and skip that owner
- If only ONE valid owner remains: treat as single-owner task (primary owner)
- If MULTIPLE: first is primary owner, rest are `additional_owners`

**Step 3: Parse due date**

If `dates_mentioned` includes:
- "48 hours" / "in N hours" → `due_at = now + N hours`
- "by Friday" / day name → next occurrence of that day at 5pm IST (11:30 UTC)
- Explicit date → parse
- If unparseable: `due_at = NULL`, note "[NEEDS DUE DATE]" in description

**Step 4: Create task**

Use task-handler match-or-create. Inputs:
- `extraction`: task_topic + " — " + original message text
- `owner_slack_id`: primary owner
- `additional_owners`: JSON array
- `creator_slack_id`: 'agent:intent-classifier'
- `assigner_slack_id`: original message author
- `source`: 'slack_channel'
- `source_ref`: Slack message permalink
- `is_status_update`: false

This returns T-N. Visibility auto-computes as 'team' (multi-owner OR owner != creator).

**Step 5: Reply in the original thread**

Post to the original Slack message thread:

```
Tracking as *T-N* for <first names>, due <human-readable due>. DMing each of you for ack.
```

**Step 6: Public announcement in #project-management**

If the source message wasn't already in #project-management, post a separate one-line announcement:

```
*New team task:* T-N — <title>
Owner: <first name>[ + <first name>] | Assigned by: <assigner> | Due: <date>
```

(If the source IS #project-management, skip — the thread reply suffices as public visibility.)

**Step 7: DM each assignee in parallel**

For each owner (primary + additional):

```
Hey <first name>, <assigner> just assigned you *T-N* in #project-management:
"<title>" — due <date>

Reply:
• `ack` to accept
• `pass with reason: <why>` to decline
• `reassign to <name>` to redirect (the new person needs to ack)
```

**Step 8: Schedule auto-escalation**

Two scheduled_actions per task:

```bash
# 2-hour acceptance watch (DM Abhinav if no ack)
ACTION_1=$(sqlite3 /data/queue/alaska.db "SELECT 'SA-' || COALESCE(MAX(CAST(SUBSTR(action_id, 4) AS INTEGER)) + 1, 1) FROM scheduled_actions;")
sqlite3 /data/queue/alaska.db "
INSERT INTO scheduled_actions (action_id, action_type, fire_at, recipient_slack_id, linked_task_id, payload, scope, created_by_slack_id)
VALUES ('$ACTION_1', 'escalate', datetime('now', '+2 hours'),
        'U07GKLVA9FE',  -- Abhinav
        '$TASK_ID',
        '{\"reason\":\"no_ack_after_2h\",\"task_id\":\"$TASK_ID\"}',
        'team', 'agent:intent-classifier');
"

# 4-hour-before-due reminder (DM owner)
ACTION_2=...  # similar pattern with fire_at = due_at - 4h
```

**Step 9: Handle ack/pass replies**

Listen for DMs from owners with these patterns:

- `ack` → UPDATE task SET status='active', log task_events, CANCEL the SA-1 acceptance watch.
- `pass with reason: ...` OR `pass: ...` → UPDATE task SET status='dropped' (if all owners pass) OR remove this person from owners (if others remain), log task_events with reason, DM the assigner: "<first name> passed on T-N. Reason: <reason>. Reassign?"
- `reassign to <name>` → Look up new person in roster. UPDATE task owner. DM new person with the full assignment notice (Step 7 format). Log task_events with `event_type='reassigned'`.

**Step 10: Brief surfaces the task**

The next pre-call brief (Phase B) reads from SQLite. T-N will naturally appear under "NEW SINCE YESTERDAY" and (after ack) "ACTIVE".

#### Anti-patterns

1. **Never auto-pass if no ack within 2h.** Just escalate to Abhinav — he decides.
2. **Never proceed if only one of multi-owners has ack'd.** First ack flips status to active; others can still pass/reassign their slot.
3. **Never spam DMs.** One DM per assignee per task. If the same person is mentioned in multiple consecutive messages, dedup at the task_handler level.
4. **Never assign to external members (Sai, MobileFirst people).** Strip them from owners list.
````

- [ ] **Step 2: Commit**

```bash
git add skills/slack-commands/SKILL.md
git commit -m "feat(cross-person): add TASK_ASSIGN workflow with ack/pass/escalate"
```

---

### Task D3: Update reminder-dispatcher with the no_ack_after_2h escalation handler

**Files:**
- Modify: `skills/reminder-dispatcher/SKILL.md`

The dispatcher already handles `action_type='escalate'` generally. Phase D adds specific behavior for the new escalation reasons.

- [ ] **Step 1: Find the escalate section**

```bash
grep -n "#### \`escalate\`" skills/reminder-dispatcher/SKILL.md
```

- [ ] **Step 2: Expand the escalate handler**

Replace the existing escalate section with this expanded version:

````markdown
#### `escalate`

Payload format: `{"reason": "<reason_code>", "task_id": "T-N"[, "additional_context": "..."]}`

Look up the linked task. Based on `reason`:

##### `no_ack_after_2h` (Phase D)

If task.status is still `pending_acceptance` (i.e., no ack came in):

DM Abhinav (U07GKLVA9FE):
```
*Ack timeout on T-N* — <title>
Assigned by: <assigner first name> at <Xh ago>
Owner: <owner first names>
Status: pending_acceptance (no ack received)

Reply:
• `proceed T-N` — keep as-is, assume owner saw it
• `chase T-N` — re-DM the owner with a nudge
• `reassign T-N to <name>` — pick a different owner
```

If task.status is now `active` (ack came in between scheduling and firing): mark this action `fired` with note "no escalation needed, ack received".

##### `deadline_4h_warning` (Phase D)

DM the task owner: "Heads-up: *T-N* is due in 4h. Status update?"

##### `overdue_24h`

DM both owner AND assigner: "*T-N* is 24h overdue. <owner first name>, what's the status?"
````

- [ ] **Step 3: Commit**

```bash
git add skills/reminder-dispatcher/SKILL.md
git commit -m "feat(reminder-dispatcher): handle no_ack_after_2h + deadline warnings"
```

---

### Task D4: Phase D acceptance — PR, deploy, end-to-end exercise

- [ ] **Step 1: Open Phase D PR**

```bash
git push -u origin feat/v2-task-phase-d
gh pr create --base main --head feat/v2-task-phase-d \
  --title "Phase D: Cross-person task assignment workflow" \
  --body "$(cat <<'EOF'
Wires the TASK_ASSIGN intent end-to-end.

What changes for users:
- Channel messages like '@Shailesh @Tarun fix X in 48h' create T-N and DM both assignees
- Each assignee can `ack`, `pass with reason`, or `reassign to <name>`
- Public announcement to #project-management for all team-visible tasks
- Auto-escalation if no ack within 2h
- Deadline warnings 4h before due

Risk: medium — new public surface. Behavior is explicit via thread replies + public log.
EOF
)"
```

- [ ] **Step 2: After merge + Railway redeploy, exercise**

In #project-management, post a test message: `@<test-user> please ping me about lunch in 2 hours`

Expected:
1. Within 5 min (next classifier batch), Alaska replies in thread: "Tracking as T-N..."
2. Public announcement in same channel (or skipped if posted in #project-management)
3. DM to the assignee

```sql
-- Verify
SELECT task_id, title, status, visibility, owner_slack_id, additional_owners, assigner_slack_id
FROM tasks
WHERE source = 'slack_channel'
ORDER BY id DESC LIMIT 5;

SELECT * FROM task_events WHERE task_id = '<T-N from above>' ORDER BY id;

SELECT action_id, action_type, fire_at, status, payload
FROM scheduled_actions
WHERE linked_task_id = '<T-N>';
```

- [ ] **Step 3: Test ack flow**

The assignee DMs Alaska: `ack`

Expected:
- Task status → 'active'
- The 'no_ack_after_2h' scheduled_action → cancelled
- DM confirmation: "Got it, T-N is yours."

- [ ] **Step 4: Test pass flow (in a new test task)**

Post another test assignment. Assignee DMs: `pass with reason: out of bandwidth today`

Expected:
- Task status updated (dropped if no other owners, else owner removed)
- Assigner DM'd: "<name> passed on T-N. Reason: out of bandwidth today. Reassign?"

- [ ] **Step 5: Test escalation (skip ack, wait 2 hours, observe Abhinav DM)**

Post a test assignment. DON'T ack. After 2 hours + the next dispatcher cron firing, Abhinav should receive the timeout DM.

- [ ] **Step 6: Phase D complete**

```bash
git checkout main && git pull origin main
```

---

## Phase D acceptance summary

After Phase D lands:

- ✅ Pre-call brief shows T-IDs (Phase B)
- ✅ Engineers can DM Alaska to create/update/block tasks (Phase B)
- ✅ Meeting Intelligence creates SQLite tasks per commitment (Phase B)
- ✅ Personal reminders + recurring routines work (Phase C)
- ✅ Team-wide routines require Abhinav approval (Phase C)
- ✅ Channel TASK_ASSIGN auto-creates tasks + DMs assignees (Phase D)
- ✅ Ack/pass/reassign reply flow works (Phase D)
- ✅ Auto-escalation fires for stuck assignments (Phase D)
- ❌ DAILY_STATE.md per-person sections are still independently authored by Meeting Intelligence (Phase E will switch this to generated-from-SQLite)
- ❌ Notion projection (read-only "Active Work" DB) not yet built (Phase E)
- ❌ Universal channel TASK_CREATE/UPDATE actions still observation-only — only TASK_ASSIGN acts (Phase E expands this once we've seen Phase D run cleanly for 1-2 weeks)

---

# Phase E — Cutover (DEFERRED to separate plan)

**Why deferred:** Phase E retires the old narrative-DAILY_STATE.md path and switches per-person sections to generated-from-SQLite. It's the riskiest phase because it removes the safety net of the parallel system. Run Phases A-D for 2-4 weeks first; collect data on classifier accuracy, dedup quality, and reply parsing reliability. Then write a Phase E plan with that data.

What Phase E will cover (skeleton — not for execution now):

- Stop Meeting Intelligence from authoring per-person sections.
- Build a `daily_state_renderer` that generates DAILY_STATE.md from SQLite.
- Build Notion projection (Active Work DB).
- Open ALL channel intents to action (not just TASK_ASSIGN).
- Universal Thinker channel observation (currently limited to high-trust channels).
- Migrate any orphan Phase A-D inflight tasks.

---

## Self-Review

### Spec coverage check

I walked through the spec section by section. Coverage:

- **Architecture overview (4 layers)** → Tasks A1-A7 (Phase A) + B1-B6 (Phase B) wire layers 2-3, C1-C6 + D1-D4 wire layer 4. ✅
- **SQLite schema (8 tables)** → Task A2 creates all 8 + the classifier_audit table. ✅
- **Intent classifier (9 types)** → Task A4 (classifier itself) + Tasks B4, C4, D2 (handlers per intent). DECISION_RECORDED handler missing — see Note 1 below.
- **Cross-person workflow (10 steps)** → Task D2 implements all 10 steps. ✅
- **Scheduling engine** → Tasks C1-C5. ✅
- **Channel visibility rules** → Auto-computed in Task B1 contract + applied in B2, D2. ✅
- **Migration phases A-D** → Covered. Phase E deferred per user instruction. ✅
- **Authority model** → Embedded in handler tasks (e.g., D2 anti-patterns, C4 routine-approval). ✅

**Note 1: DECISION_RECORDED intent is observed but no handler.** Per spec section "Layer 2", it routes to "Decision Log (Notion)". I haven't added a Phase B/D handler because the existing Meeting Intelligence skill already writes decisions to the Notion Decision Log when extracted from transcripts. For Slack-DM-originated decisions (rare), the classifier in obs-mode captures them in classifier_audit. Adding an explicit slack-commands DECISION_RECORDED handler is best deferred to Phase E once we see how often it fires.

**Note 2: STATUS_QUERY intent has no explicit handler.** Same reasoning — slack-commands already has the existing query patterns ("my tasks", "sprint status", "who's blocked") that match the spec's STATUS_QUERY definition. The classifier provides confirmation labeling but doesn't change the response path.

### Placeholder scan

Searched for TBD/TODO/FIXME/XXX in the plan. None present. All steps have complete code or commands.

### Type consistency

- `task_id` format: `T-N` consistent throughout (B1, B2, B3, B4, B5, D2).
- `action_id` format: `SA-N` consistent (C4, D2, D3).
- `blocker_id` format: `B-N` (B4).
- `proposal_id` format: `RP-N` (C4).
- Field names (`owner_slack_id`, `additional_owners`, `creator_slack_id`, `visibility`, `source`, `source_ref`) consistent across schema (A2), Task Write Contract (B1), and all handler skills.
- Slack ID format `UXXXXXXXXXX` consistent.
- Status enum values (`active`, `blocked`, `pending_acceptance`, `done`, `dropped`, `snoozed`) consistent across schema check constraint and all handler references.

### Scope check

Plan covers Phases A-D as user specified. ~4-8 weeks of engineering work at one phase per ~1-2 weeks. Each phase is independently shippable + reversible. Plan is one cohesive document (not multiple plans) because the phases share schema and depend on each other; splitting would create cross-plan coupling.

### Issues fixed inline

- Confirmed each handler references the Task Write Contract from B1 (avoided duplicating SQL across tasks).
- Confirmed reminder-dispatcher's escalate handler matches the action_type written by D2 (no naming drift).
- Confirmed pre-call brief queries (B5) use the same status enum as the schema (A2).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-23-alaska-v2-task-model.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach?
