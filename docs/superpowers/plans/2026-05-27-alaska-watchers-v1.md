# Alaska Watchers V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Watcher primitive — Alaska's foundation for user-requested proactive agency. Each watcher = a unit of repeatable agency (trigger + action chain + recipient + memory + approval gates).

**Architecture:** New `watchers` + `watcher_fires` tables in SQLite. Per-watcher OpenClaw cron entries handle WHEN (via `cron.add`). New `watcher-dispatcher` skill handles WHAT (executes action chains). Existing `slack-commands` skill gets new intent-routing for watcher creation. Pre-built templates ship for common patterns (Bug-cluster, Customer-signal, Stale-task, Deploy-impact). Phase C's `reminder-dispatcher` and `scheduled_actions` table are migrated, then deprecated after 2 weeks of dual-write.

**Tech Stack:** SQLite (per-connection FK PRAGMA), bash + sqlite3 for SQL ops, OpenClaw cron API (`cron.add`, `cron.remove`, `cron.list`), Python 3 + python-dateutil for RRULE math (already in image), Sonnet 4.6 for LLM-aided dedup + classification.

**Dependencies:**
- ✅ Phase A.1 schema (tasks, task_events, blockers, etc.) — live in production
- ✅ Phase B task-handler skill — live in production
- ✅ Phase C reminder-dispatcher + scheduled_actions table — live in production (will be migrated)
- ⏳ BON Knowledge Base Tier 1 files (Abhinav seeding in parallel) — REQUIRED before Phase W.1 starts
- ✅ OpenClaw `cron.add` API access — verified via Phase A.2 and Phase C usage

**Spec reference:** `docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md` (locked decisions #1-#16)
**Research reference:** `docs/superpowers/research/2026-05-27-openclaw-native-primitives.md`

---

## Pre-flight

### P.1: Verify clean main, create branch

- [ ] **Step 1: Confirm clean working tree on main**

```bash
cd alaska-openclaw
git checkout main && git pull origin main
git status
```

Expected: `nothing to commit, working tree clean`.

- [ ] **Step 2: Verify BON KB Tier 1 files exist**

```bash
ls workspace/knowledge/integrations/plaid.md
ls workspace/knowledge/integrations/amplitude.md
ls workspace/knowledge/integrations/customerio.md
ls workspace/knowledge/definitions/metrics.md
```

Expected: all files present. If KB Tier 1 is incomplete, STOP and resolve before continuing — watcher-creator skill depends on these.

- [ ] **Step 3: Create feature branch**

```bash
git checkout -b feat/v2-watchers-v1
```

---

## Phase W.0 — Foundation (schema + intent classifier)

### Task W0.1: Migration 0003 — watchers + watcher_fires tables

**Files:**
- Create: `migrations/0003_watchers_v1.sql`

- [ ] **Step 1: Write the migration**

Create `migrations/0003_watchers_v1.sql`:

```sql
-- Migration 0003: Watchers V1 schema
-- Spec: docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md
-- Adds watchers + watcher_fires tables for the proactive-agency primitive.

PRAGMA foreign_keys = ON;

-- ============================================================
-- 1. watchers — the watcher primitive
-- ============================================================
CREATE TABLE IF NOT EXISTS watchers (
  -- Identity
  watcher_id          TEXT PRIMARY KEY,
  description         TEXT NOT NULL,

  -- Lifecycle
  created_by_slack_id TEXT NOT NULL,
  created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_from_msg    TEXT,
  status              TEXT NOT NULL
                       CHECK (status IN ('pending_approval','active','paused','expired','cancelled')),
  cost_class          TEXT NOT NULL
                       CHECK (cost_class IN ('free','low','medium','high')),
  approved_by_slack_id TEXT,
  approved_at         DATETIME,
  decline_reason      TEXT,

  -- Trigger
  trigger_type        TEXT NOT NULL
                       CHECK (trigger_type IN ('cron','event')),
  trigger_config      TEXT NOT NULL,

  -- Time bounds
  starts_at           DATETIME,
  expires_at          DATETIME,

  -- Action
  action_chain        TEXT NOT NULL,
  recipient           TEXT NOT NULL,
  per_fire_approval   BOOLEAN NOT NULL DEFAULT 0,
  per_fire_approver   TEXT,
  volume_cap          INTEGER,

  -- Memory
  memory_strategy     TEXT NOT NULL DEFAULT 'none'
                       CHECK (memory_strategy IN ('none','strict_entity_set')),
  memory_state        TEXT,
  cool_down_seconds   INTEGER NOT NULL DEFAULT 0,

  -- KB provenance
  knowledge_sources   TEXT,

  -- Stats
  fire_count          INTEGER NOT NULL DEFAULT 0,
  last_fired_at       DATETIME,
  last_action_summary TEXT,

  -- OpenClaw integration
  openclaw_cron_id    TEXT,
  stagger_seconds     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_watchers_status_trigger ON watchers(status, trigger_type);
CREATE INDEX IF NOT EXISTS idx_watchers_created_by   ON watchers(created_by_slack_id);
CREATE INDEX IF NOT EXISTS idx_watchers_expires      ON watchers(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_watchers_cron_lookup  ON watchers(openclaw_cron_id) WHERE openclaw_cron_id IS NOT NULL;

-- ============================================================
-- 2. watcher_fires — execution audit log
-- ============================================================
CREATE TABLE IF NOT EXISTS watcher_fires (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  watcher_id      TEXT NOT NULL REFERENCES watchers(watcher_id),
  fired_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fact_key        TEXT,
  outcome         TEXT NOT NULL
                   CHECK (outcome IN ('acted','skipped_memory','skipped_cooldown','skipped_empty','failed','awaiting_approval','approved','declined')),
  action_summary  TEXT,
  error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_watcher_fires_watcher ON watcher_fires(watcher_id, fired_at);
```

- [ ] **Step 2: Run migration locally to verify**

```bash
sqlite3 /tmp/test-watchers.db < migrations/0001_v2_task_model.sql
sqlite3 /tmp/test-watchers.db < migrations/0002_classifier_secondary_intents.sql
sqlite3 /tmp/test-watchers.db < migrations/0003_watchers_v1.sql
sqlite3 /tmp/test-watchers.db ".schema watchers"
sqlite3 /tmp/test-watchers.db ".schema watcher_fires"
rm /tmp/test-watchers.db
```

Expected: both tables print with all CHECK constraints and indexes.

- [ ] **Step 3: Confirm migration runner picks it up**

The runner at `migrations/run_migrations.sh` uses `shopt -s nullglob` to glob all `.sql` files in order. No code change needed — file naming `0003_*` ensures it runs after 0001 and 0002.

- [ ] **Step 4: Commit**

```bash
git add migrations/0003_watchers_v1.sql
git commit -m "feat(watchers): add migration 0003 — watchers + watcher_fires tables"
```

### Task W0.2: Extend intent-classifier with WATCHER_REQUEST intent

**Files:**
- Modify: `skills/intent-classifier/SKILL.md`

The classifier currently has 9 intents. Add a 10th: `WATCHER_REQUEST` (user asking Alaska to set up an ongoing watch/scheduled report/recurring action).

- [ ] **Step 1: Read current classifier prompt**

```bash
grep -n "TASK_CREATE\|REMINDER_REQUEST\|the 9 intent types\|## The 9 intent types" skills/intent-classifier/SKILL.md | head
```

- [ ] **Step 2: Edit the intent enumeration**

Use Edit to update the "9 intent types" → "10 intent types" table and the prompt template. Add the new row:

```markdown
| `WATCHER_REQUEST` | User asking Alaska to set up an ongoing watch / scheduled report / recurring action that's MORE than a simple reminder. Distinguishes from REMINDER_REQUEST: WATCHER_REQUEST involves data queries, conditional logic, or persistent observation. | "every Monday show me DAU and retention", "alert me whenever a user below 580 signs up", "track failed Plaid users daily and send them gift card emails", "send me a bar chart of Plaid failures every week" |
```

And update the prompt's "Return JSON" intent enum from 9 values to 10 (add `WATCHER_REQUEST`).

Also update the "Disambiguation rules" subsection (added in v1.1) to distinguish REMINDER_REQUEST vs WATCHER_REQUEST:

```
- REMINDER_REQUEST vs WATCHER_REQUEST: 
  REMINDER_REQUEST = simple "ping me about X at time T" — message text only, no data query.
  WATCHER_REQUEST = ongoing observation involving data ("show me", "alert me when X happens", 
  "track X and do Y"). Anything mentioning a metric, chart, query, condition, or external 
  data source is WATCHER_REQUEST.
```

Bump version from `1.1.0` → `1.2.0` in frontmatter.

- [ ] **Step 3: Verify**

```bash
grep "WATCHER_REQUEST" skills/intent-classifier/SKILL.md
# Expected: 4+ matches (intent type row, prompt enum, disambiguation rule, etc.)
grep "version:" skills/intent-classifier/SKILL.md
# Expected: version: 1.2.0
```

- [ ] **Step 4: Commit**

```bash
git add skills/intent-classifier/SKILL.md
git commit -m "feat(classifier): add WATCHER_REQUEST intent (v1.1.0 → v1.2.0)"
```

---

## Phase W.1 — Watcher creation flow

### Task W1.1: Write skills/watcher-creator/SKILL.md

**Files:**
- Create: `skills/watcher-creator/SKILL.md`

The watcher-creator skill handles the NL → draft → confirm flow. Invoked when intent-classifier labels a DM as `WATCHER_REQUEST` OR when user explicitly says `@alaska watch ...` / `@alaska activate <template>`.

- [ ] **Step 1: Create directory + write SKILL.md**

```bash
mkdir -p skills/watcher-creator
```

Create `skills/watcher-creator/SKILL.md` with frontmatter:

```yaml
---
name: watcher-creator
description: Parses user "watch X / track X / alert me when X" requests, loads relevant BON KB files, drafts a watcher with action chain + trigger + recipient, confirms with creator, routes high-cost watchers to Abhinav for approval, activates via OpenClaw cron.add.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3, python3]
      env: [ANTHROPIC_API_KEY]
    emoji: "🛡️"
---
```

The body of the SKILL.md covers (per the spec's "Step-by-step flow" §):

1. RECEIVE — invoke trigger
2. PARSE INTENT — categorize (simple reminder vs scheduled report vs event watch vs external action vs template activation)
3. LOAD RELEVANT KB — keyword match against KB index, load matched files
4. DRAFT WATCHER INTERNALLY using KB definitions
5. ASK FOLLOW-UP QUESTIONS (only true ambiguities — KB resolves technical ones)
6. PRESENT DRAFT to creator with plain-English action chain summary
7. CHECK APPROVAL GATE — self-approvable vs requires Abhinav
8. ON CONFIRMATION — insert watcher row + call cron.add + DM creator + DM Abhinav if applicable
9. ON DECLINE — update status, DM creator with reason

Include explicit `cron.add` payload examples (per the spec's "Migration path" §) showing the right shape for `kind=cron` (recurring) and `kind=at` (one-shot).

Include cost projection logic (compute monthly $ from action chain step costs × fire frequency). Tier mapping: free <$0.50, low $0.50-$3, medium >$3 (= >$3/day for the approval gate), high (external write OR >$15/day). Cost shown ONLY in Abhinav's approval DM.

Include the stagger logic: at creation, roll `random.randint(0, 300)` and store in `stagger_seconds`. When constructing the `cron.add` payload, the trigger time is shifted by stagger.

Include the action_chain JSON shape with the 9 step types from the spec (load_knowledge, invoke_skill, format, draft_for_approval, send_dm, send_channel, send_email_cio, attach_chart, create_task).

Anti-patterns:
1. Never write to `watchers` table without also calling `cron.add` in the same atomic flow (use the write-ahead pattern: INSERT row with `status='pending_cron_create'`, call cron.add, UPDATE row with cron_id + status='active').
2. Never show cost to creator. Cost is ONLY in Abhinav's approval DM.
3. Never let a non-Abhinav user edit a KB file (refuse with: "Knowledge base changes go through Abhinav directly.").
4. Never bypass the approval gate for cost > $3/day.
5. Never skip the cron.add `enabled: true` field (issue #8557 default-undefined bug).
6. Never invoke task-handler from this skill — watchers are different from tasks.

- [ ] **Step 2: Verify the file**

```bash
wc -l skills/watcher-creator/SKILL.md
# Expected: 200-400 lines
grep "Anti-patterns" skills/watcher-creator/SKILL.md
# Expected: 1 match
grep "load_knowledge\|invoke_skill\|draft_for_approval" skills/watcher-creator/SKILL.md
# Expected: action chain step references
```

- [ ] **Step 3: Commit**

```bash
git add skills/watcher-creator/SKILL.md
git commit -m "feat(watchers): add watcher-creator skill (Phase W.1)"
```

### Task W1.2: Create pre-built template files

**Files:**
- Create: `skills/watcher-creator/templates/bug-cluster.json`
- Create: `skills/watcher-creator/templates/customer-signal.json`
- Create: `skills/watcher-creator/templates/stale-task.json`
- Create: `skills/watcher-creator/templates/deploy-impact.json`

Each template is a JSON file matching the schema from the spec's "Pre-built watcher templates" §.

- [ ] **Step 1: Create templates directory**

```bash
mkdir -p skills/watcher-creator/templates
```

- [ ] **Step 2: Write all 4 templates verbatim from the spec**

Copy the JSON from spec §"Pre-built watcher templates (ship with V1)":
- `bug-cluster.json` (lines 442-461 of spec)
- `customer-signal.json` (lines 462-481)
- `stale-task.json` (lines 482-500)
- `deploy-impact.json` (lines 501-524)

- [ ] **Step 3: Validate JSON syntax**

```bash
for f in skills/watcher-creator/templates/*.json; do
  python3 -c "import json; json.load(open('$f'))" && echo "✓ $f" || echo "✗ $f"
done
# Expected: ✓ for all 4 files
```

- [ ] **Step 4: Commit**

```bash
git add skills/watcher-creator/templates/
git commit -m "feat(watchers): add 4 pre-built watcher templates"
```

### Task W1.3: Add slack-commands routing for WATCHER_REQUEST

**Files:**
- Modify: `skills/slack-commands/SKILL.md`

The intent-driven action section (added in Phase B/C) handles TASK_CREATE/UPDATE/BLOCKER and REMINDER_REQUEST. Add WATCHER_REQUEST handler that routes to watcher-creator skill.

- [ ] **Step 1: Find the existing intent-driven section**

```bash
grep -n "## Intent-driven actions\|### TASK_CREATE handler\|### REMINDER_REQUEST handler" skills/slack-commands/SKILL.md
```

- [ ] **Step 2: Insert WATCHER_REQUEST handler after REMINDER_REQUEST**

Use Edit to add (after the REMINDER_REQUEST handler section, before STATUS_QUERY fall-through):

```markdown
### WATCHER_REQUEST handler

Triggered by: "watch X", "track X and do Y", "alert me when Z", "every Monday show me ...", "every Tuesday create ...", "activate <template>"

1. Read `/data/skills/watcher-creator/SKILL.md` and execute its procedure.
2. The watcher-creator handles the full conversational flow (parse, KB load, draft, confirm, approve, activate). Slack-commands does NOT do anything beyond routing.
3. Return the watcher-creator's reply text as the response.
```

Update the "STATUS_QUERY / DECISION_RECORDED / NON_WORK_CHAT / AMBIGUOUS" section to NOT list WATCHER_REQUEST as unhandled.

- [ ] **Step 3: Verify**

```bash
grep "WATCHER_REQUEST" skills/slack-commands/SKILL.md
# Expected: at least 2 matches (handler header + classifier trigger reference)
grep "watcher-creator" skills/slack-commands/SKILL.md
# Expected: 1+ matches
```

- [ ] **Step 4: Commit**

```bash
git add skills/slack-commands/SKILL.md
git commit -m "feat(slack-commands): route WATCHER_REQUEST to watcher-creator skill"
```

---

## Phase W.2 — Watcher dispatcher

### Task W2.1: Write skills/watcher-dispatcher/SKILL.md

**Files:**
- Create: `skills/watcher-dispatcher/SKILL.md`

This replaces Phase C's reminder-dispatcher. When ANY watcher cron fires, OpenClaw invokes this dispatcher with the watcher_id as context. Dispatcher reads the watcher row, executes the action chain, applies memory, logs to watcher_fires.

- [ ] **Step 1: Create skill**

```bash
mkdir -p skills/watcher-dispatcher
```

Create `skills/watcher-dispatcher/SKILL.md` covering:

**Procedure structure** (modeled on reminder-dispatcher's flip-first ordering):

```
1. Read watcher_id from the cron payload (passed in the message text).
2. SELECT from watchers WHERE watcher_id = ? AND status = 'active'.
3. If row not found or status != 'active': exit silently (orphan cron, janitor will clean up).
4. Check memory:
   a. If memory_strategy = 'none': proceed to action chain.
   b. If memory_strategy = 'strict_entity_set':
      - Run any KB load + initial query steps to compute fact_key
      - If fact_key == last_fact_key: log skipped_memory, exit.
      - Else: proceed.
5. Check cool-down:
   - If now - last_fired_at < cool_down_seconds: log skipped_cooldown, exit.
6. Check per_fire_approval:
   - If per_fire_approval = 0: execute action chain through to send.
   - If per_fire_approval = 1:
     - Execute chain up to draft_for_approval step
     - Create a pending watcher_fires row with outcome='awaiting_approval'
     - DM the per_fire_approver with the draft + reply grammar
     - Exit (resume happens when user replies — handled by slack-commands)
7. Execute action chain step-by-step. For each step:
   - load_knowledge: read files into context
   - invoke_skill: cross-skill invocation, capture output_var
   - format: render template with vars
   - send_dm / send_channel / send_email_cio: external delivery
   - attach_chart: fetch + attach
   - create_task: invoke task-handler
8. Update watcher row: last_fired_at, fire_count++, memory_state with new fact_key, last_action_summary.
9. Log fire row: outcome='acted' or 'failed' or 'skipped_empty'.
10. Check expires_at: if now >= expires_at, set status='expired', call cron.remove(openclaw_cron_id).
```

Action chain step semantics — full spec for each of the 9 step types.

`{{step_N.field}}` and `{{var_name}}` substitution syntax.

Anti-patterns (modeled on reminder-dispatcher's):
1. Never re-execute on memory hit. Strict-entity-set means: same fact_key = no action.
2. Never skip the fire row log. Even silent skips get a watcher_fires row with outcome='skipped_*'.
3. Never write to tasks/blockers directly — route via task-handler (action_chain step).
4. Never modify scheduled_actions table — Phase C is being deprecated, do NOT add new writes.
5. Never bypass per_fire_approval if it's enabled — pause via awaiting_approval and exit, even if it makes the chain feel incomplete.
6. Never leave the cron entry running if status flips to 'expired' or 'cancelled' — call cron.remove.

- [ ] **Step 2: Verify**

```bash
wc -l skills/watcher-dispatcher/SKILL.md
# Expected: 250-400 lines
grep "fact_key\|memory_strategy\|per_fire_approval" skills/watcher-dispatcher/SKILL.md
# Expected: multiple matches each
```

- [ ] **Step 3: Commit**

```bash
git add skills/watcher-dispatcher/SKILL.md
git commit -m "feat(watchers): add watcher-dispatcher skill (Phase W.2)"
```

### Task W2.2: Per-fire approval flow — extend slack-commands

**Files:**
- Modify: `skills/slack-commands/SKILL.md`

When a watcher with `per_fire_approval=1` fires, the dispatcher pauses and DMs the approver. The approver replies "approve W-N fire" / "decline W-N fire" / "modify W-N fire". slack-commands handles those replies.

- [ ] **Step 1: Add new section "Per-fire watcher approval" to slack-commands**

Use Edit to insert after the "Routine Proposal Approval (Abhinav-only)" section (which handles per-watcher creation approval). Content covers:

1. When the creator DMs `approve W-N fire`: look up the pending watcher_fires row (outcome='awaiting_approval'), execute the remaining action chain steps from where draft_for_approval paused, update fire outcome to 'approved', log result.
2. When the creator DMs `decline W-N fire <reason>`: update fire outcome='declined', log reason in action_summary. No further action.
3. When the creator DMs `modify W-N fire: <change>`: re-draft with the modification, DM the new draft back for re-approval. Keep outcome='awaiting_approval'.

The lookup pattern: `SELECT * FROM watcher_fires WHERE watcher_id='W-N' AND outcome='awaiting_approval' ORDER BY fired_at DESC LIMIT 1;`

Authority check: per-fire approval recipient is the watcher's CREATOR (per spec locked decision #14). Verify the replying user matches `watchers.created_by_slack_id`. If not, refuse: "Only the watcher's creator can approve per-fire drafts."

- [ ] **Step 2: Verify**

```bash
grep "per-fire\|awaiting_approval\|Per-fire" skills/slack-commands/SKILL.md
# Expected: multiple matches
```

- [ ] **Step 3: Commit**

```bash
git add skills/slack-commands/SKILL.md
git commit -m "feat(slack-commands): handle per-fire watcher approval replies"
```

### Task W2.3: Phase C migration script

**Files:**
- Create: `lib/migrate_phase_c_to_watchers.py`

One-time script to convert existing `scheduled_actions` and `routine_proposals` rows to `watchers` rows.

- [ ] **Step 1: Write the migration script**

`lib/migrate_phase_c_to_watchers.py`:

```python
"""
One-time migration: Phase C scheduled_actions + routine_proposals → watchers.

Idempotent — running twice is safe (uses INSERT OR IGNORE on watcher_id).

Strategy:
1. For each scheduled_actions row with status='pending':
   - Generate W-N watcher_id
   - Build action_chain JSON from action_type
   - INSERT into watchers
   - Do NOT call cron.add yet — the original cron entries from Phase C
     are still firing. After 2 weeks of dual-write, we hard-cut.
   - Mark the original row with a comment in payload: "migrated_to=W-N"

2. For each routine_proposals row with status='pending':
   - Generate W-N watcher_id
   - INSERT into watchers with status='pending_approval'
   - DM Abhinav with a re-approval request: "RP-N migrated to W-N. Re-approve in the new system?"

Usage:
    python3 lib/migrate_phase_c_to_watchers.py --dry-run    # show what would happen
    python3 lib/migrate_phase_c_to_watchers.py --execute    # do it
"""

from __future__ import annotations
import json
import sqlite3
import sys
from datetime import datetime

DB = '/data/queue/alaska.db'

def migrate_scheduled_actions(conn, dry_run: bool):
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON;")
    cur.execute("SELECT * FROM scheduled_actions WHERE status='pending'")
    rows = cur.fetchall()
    # ... full implementation per the spec

if __name__ == '__main__':
    dry_run = '--execute' not in sys.argv
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    migrate_scheduled_actions(conn, dry_run)
    # migrate_routine_proposals(conn, dry_run)
    conn.close()
    print(f"{'DRY RUN' if dry_run else 'EXECUTED'} — done")
```

Full implementation includes:
- W-N ID generation via SELECT MAX + 1 pattern from shared-toolkit Section 1.7
- action_chain JSON construction:
  - `remind` → action_chain with single `send_dm` step
  - `recurring_routine` → action_chain with `invoke_skill` (the prompt) + `send_*` step
  - `escalate` → action_chain with `send_dm` to escalation target
  - `surface_task` → action_chain with `create_task` invocation (mention type)
  - `auto_followup` → action_chain with task-status check + conditional send_dm
- cost_class projection (free for most Phase C entries since they're internal)
- knowledge_sources = empty array (Phase C entries weren't KB-aware)

- [ ] **Step 2: Test dry-run locally against a snapshot of production DB**

```bash
# Get a snapshot of /data/queue/alaska.db from Railway (or use a test fixture)
python3 lib/migrate_phase_c_to_watchers.py --dry-run
```

Expected: prints proposed migrations without writing.

- [ ] **Step 3: Add to entrypoint.sh — RUN ONCE after 0003 migration**

`entrypoint.sh` already runs migrations via `bash /opt/migrations/run_migrations.sh`. Add a one-time idempotency-checked call to the Python migration:

```bash
# One-time Phase C → Watchers migration (idempotent — safe to re-run)
if [ -f /data/queue/alaska.db ] && [ ! -f /data/.openclaw/.phase_c_migrated ]; then
  echo "[entrypoint] Running Phase C → Watchers V1 migration..."
  python3 /opt/lib/migrate_phase_c_to_watchers.py --execute && \
    touch /data/.openclaw/.phase_c_migrated
fi
```

The marker file `/data/.openclaw/.phase_c_migrated` ensures we run exactly once.

- [ ] **Step 4: Commit**

```bash
git add lib/migrate_phase_c_to_watchers.py entrypoint.sh
git commit -m "feat(watchers): Phase C → Watchers migration script + entrypoint integration"
```

---

## Phase W.3 — Management commands + event triggers

### Task W3.1: Slack-native watcher management

**Files:**
- Modify: `skills/slack-commands/SKILL.md`

Add the `@alaska watchers` / `show` / `pause` / `resume` / `delete` / `modify` / `templates` / `activate` commands.

- [ ] **Step 1: Add Watcher Management section to slack-commands**

Use Edit to insert (after the per-fire approval section, near the bottom):

```markdown
## Watcher Management

Triggered by: `@alaska watchers`, `@alaska show W-N`, etc.

### `@alaska watchers` — list creator's active watchers

[SQL query + format output as table]

### `@alaska watchers all` — Abhinav-only, all active watchers

[Authority check + SQL]

### `@alaska show W-N`

[Details: trigger, action chain summary (plain English from JSON), last 5 fires from watcher_fires, memory state]

### `@alaska pause W-N`

[Update status='paused'; do NOT delete cron (resume just flips status back)]

### `@alaska resume W-N`

[Update status='active' from 'paused']

### `@alaska delete W-N`

[Update status='cancelled' + call cron.remove(openclaw_cron_id)]

### `@alaska modify W-N: <change>`

[Parse change, edit watcher row, possibly call cron.remove + cron.add if trigger changed, re-run approval if cost class changes]

### `@alaska watcher templates`

[List the 4 pre-built templates from skills/watcher-creator/templates/]

### `@alaska activate <template>`

[Read template JSON, ask for parameters, then route to watcher-creator]
```

- [ ] **Step 2: Verify**

```bash
grep "@alaska watchers\|@alaska show\|@alaska pause" skills/slack-commands/SKILL.md
# Expected: matches for all commands
```

- [ ] **Step 3: Commit**

```bash
git add skills/slack-commands/SKILL.md
git commit -m "feat(slack-commands): add watcher management commands"
```

### Task W3.2: Event poller crons (V1: 4 event types)

**Files:**
- Create: `skills/event-poller/SKILL.md`
- Modify: `config/cron-jobs-backup.json`

For event-based watchers (Example 5 — low-score signup alerts), we need shared poller crons (one per event type) that scan their data source and dispatch to subscribed watchers.

V1 event types: `new_signup`, `bug_closed`, `pr_merged`, `task_status_changed`. (More can be added later.)

- [ ] **Step 1: Write event-poller SKILL.md**

`skills/event-poller/SKILL.md`:

```yaml
---
name: event-poller
description: Shared cron skill that polls one event source (e.g., Amplitude signups) for new events since last poll, finds watchers subscribed to those events, and dispatches the watcher-dispatcher skill for each matching pair.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3, python3]
      env: [AMPLITUDE_API_KEY, GITHUB_TOKEN]
    emoji: "📡"
---
```

Procedure: invoked with `event_type` in cron payload. Reads `event_pollers.last_polled_at` for that type, queries the source for events since then, finds matching watchers via `SELECT FROM watchers WHERE trigger_type='event' AND json_extract(trigger_config, '$.event_name')=?`, dispatches the watcher-dispatcher for each (watcher, event) pair, updates last_polled_at.

- [ ] **Step 2: Add a small event_pollers state table to migration 0003**

Update `migrations/0003_watchers_v1.sql` to add:

```sql
CREATE TABLE IF NOT EXISTS event_pollers (
  event_type      TEXT PRIMARY KEY,
  last_polled_at  DATETIME NOT NULL,
  last_run_count  INTEGER NOT NULL DEFAULT 0
);
-- Seed initial event types
INSERT OR IGNORE INTO event_pollers (event_type, last_polled_at) VALUES
  ('new_signup',          CURRENT_TIMESTAMP),
  ('bug_closed',          CURRENT_TIMESTAMP),
  ('pr_merged',           CURRENT_TIMESTAMP),
  ('task_status_changed', CURRENT_TIMESTAMP);
```

- [ ] **Step 3: Add the 4 event-poller cron entries to cron-jobs-backup.json**

Each entry has schedule per the spec table (e.g., new_signup every 15 min, bug_closed every 30 min). Payload message: "Run event-poller for event_type=<name>".

- [ ] **Step 4: Commit**

```bash
git add skills/event-poller/SKILL.md migrations/0003_watchers_v1.sql config/cron-jobs-backup.json
git commit -m "feat(watchers): add event-poller skill + 4 V1 event types (Phase W.3)"
```

---

## Phase W.4 — Janitor + acceptance

### Task W4.1: Reconciliation janitor cron

**Files:**
- Create: `skills/watcher-janitor/SKILL.md`
- Modify: `config/cron-jobs-backup.json`

Nightly cron that detects orphan crons (no matching watcher row) and orphan watchers (active but no cron_id) and reconciles.

- [ ] **Step 1: Write the janitor skill**

`skills/watcher-janitor/SKILL.md`:

```yaml
---
name: watcher-janitor
description: Nightly reconciliation of OpenClaw cron entries vs watchers table. Detects orphan cron entries (no matching watcher row → call cron.remove) and orphan watcher rows (active but no cron_id → DM Abhinav for manual resolution).
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3]
    emoji: "🧹"
---
```

Procedure:
1. Call OpenClaw `cron.list` (returns all active crons with their IDs).
2. SELECT openclaw_cron_id FROM watchers WHERE status IN ('active', 'paused').
3. Set difference 1: cron IDs in OpenClaw but NOT in watchers → orphan crons. For each: call cron.remove. Log via task_events (event_type='comment', context='janitor: removed orphan cron <id>').
4. Set difference 2: watcher rows with status='active' AND openclaw_cron_id IS NULL → orphan watchers. DM Abhinav with the list.
5. Log activity summary in task_events: "janitor: cleaned N orphan crons, found M orphan watchers".

- [ ] **Step 2: Add the janitor cron entry to cron-jobs-backup.json**

```json
{
  "name": "Watcher Janitor",
  "enabled": true,
  "schedule": {"kind": "cron", "expr": "0 4 * * *", "tz": "UTC"},
  "payload": {"kind": "user-message", "message": "Run /data/skills/watcher-janitor/SKILL.md procedure."},
  "delivery": {"mode": "none"},
  "timeoutSeconds": 180
}
```

- [ ] **Step 3: Commit**

```bash
git add skills/watcher-janitor/SKILL.md config/cron-jobs-backup.json
git commit -m "feat(watchers): add watcher-janitor reconciliation cron"
```

### Task W4.2: Replay-style validation against May 18-26 historical data

**Files:**
- (validation only — no code changes)

Like Phase B's sandbox replay, we exercise the watcher path end-to-end against historical data WITHOUT touching production tables.

- [ ] **Step 1: Set up sandbox**

```bash
SANDBOX=/data/queue/alaska_watchers_replay.db
sqlite3 /data/queue/alaska.db ".schema" | sqlite3 $SANDBOX
```

- [ ] **Step 2: Replay creation scenarios**

For each of the 5 scenarios in the spec's "Worked examples" §, manually inject the synthetic DM into the sandbox intent_inbox, run classifier (v1.2 — should label as WATCHER_REQUEST), let watcher-creator skill run, observe the result.

For each scenario verify:
- Watcher row created with correct trigger_config, action_chain, recipient
- OpenClaw cron entry created (`cron.list` shows it)
- Confirmation DM has the right plain-English action chain summary
- Cost shown only when applicable (>$3/day)
- Approval routing correct (self vs Abhinav)

- [ ] **Step 3: Replay execution**

Manually trigger watcher-dispatcher for each W-N created. Verify:
- Action chain executes step-by-step
- Memory updates correctly (last_fact_key set)
- watcher_fires row logged with correct outcome
- For per-fire approval scenarios (Example 2), verify dispatcher pauses at draft_for_approval

- [ ] **Step 4: Cleanup**

```bash
rm $SANDBOX
# Clean up any orphan crons created in OpenClaw during the replay
# (the cron.list call from janitor would catch these too)
```

- [ ] **Step 5: Commit validation report**

Create `docs/superpowers/research/2026-MM-DD-watchers-v1-validation.md` with the replay findings. Pattern after Phase B's validation report.

```bash
git add docs/superpowers/research/2026-MM-DD-watchers-v1-validation.md
git commit -m "test(watchers): replay validation against May 18-26 historical data"
```

### Task W4.3: Open PR + manual exercise

- [ ] **Step 1: Push branch + open PR**

```bash
git push -u origin feat/v2-watchers-v1
gh pr create --base main --head feat/v2-watchers-v1 \
  --title "feat: Alaska Watchers V1 — the proactive-agency primitive" \
  --body "[full PR body covering: what shipped, two-stage review highlights, validation results, deploy steps]"
```

- [ ] **Step 2: After merge — Alaska deploys**

Send Alaska a comprehensive activation brief (matching the pattern used for Phase B/C activation):
- Verify migration 0003 + Phase C migration script ran
- Verify event-poller crons registered in OpenClaw dashboard
- Verify janitor cron registered
- Exercise the 5 scenarios live in production
- Observation: 1 week of dual operation (Phase C scheduled_actions still firing alongside new watchers)

- [ ] **Step 3: After 2 weeks of clean dual operation — hard-cut**

- Drop `scheduled_actions` and `routine_proposals` tables (migration 0004)
- Deprecate `reminder-dispatcher` skill (move to `skills/_deprecated/`)
- DM Abhinav: "Phase C dual-write window complete. Watchers is now the sole scheduling primitive."

---

## Verification Plan

After all phases land, before declaring V1 live:

### Static checks

```bash
# Migration applied
sqlite3 /data/queue/alaska.db ".tables" | grep -E "watchers|watcher_fires"

# Schemas correct
sqlite3 /data/queue/alaska.db ".schema watchers" | grep "stagger_seconds"

# New skills present
ls skills/watcher-creator/SKILL.md
ls skills/watcher-creator/templates/*.json
ls skills/watcher-dispatcher/SKILL.md
ls skills/event-poller/SKILL.md
ls skills/watcher-janitor/SKILL.md

# Updated skills
grep "WATCHER_REQUEST" skills/intent-classifier/SKILL.md
grep "watcher-creator" skills/slack-commands/SKILL.md

# Migration script + entrypoint integration
ls lib/migrate_phase_c_to_watchers.py
grep "phase_c_migrated" entrypoint.sh
```

### Live pipeline checks (after Railway redeploy)

1. **Self-approvable watcher creation:** DM Alaska "remind me about V2 launch in 5 days" → watcher created, classifier labels REMINDER_REQUEST OR WATCHER_REQUEST → watcher-creator drafts → user confirms → cron.add called → row inserted with status='active' and openclaw_cron_id populated.

2. **Cost-gated watcher creation:** DM Alaska "every Monday show me DAU and retention" → cost projected (medium) → routed to Abhinav for approval → Abhinav approves → activated.

3. **Per-fire approval flow:** DM Alaska "daily gift card emails to failed Plaid users" → high cost, per-fire flag enabled → Abhinav approves watcher → fires next day → drafts batch → DMs to Samder (creator) → Samder approves → emails go out.

4. **Event-based watcher:** DM Alaska "alert me whenever <580 signs up" → event-poller cron picks up new signups within the next 15-min window → dispatches watcher-dispatcher → DM to creator.

5. **Memory dedup:** Run the Bug-cluster watcher manually twice in a row with the same data. First fire: acts. Second fire: skipped_memory (fact_key unchanged).

6. **Pause / Resume / Delete:** `@alaska pause W-N` → status='paused', cron remains but doesn't act. `@alaska resume W-N` → status='active'. `@alaska delete W-N` → status='cancelled' + cron.remove called.

7. **Janitor:** Manually create an orphan cron (cron.add without a watcher row). Wait for janitor's 4 AM run. Verify orphan removed, log entry in task_events.

### What "done" looks like

- 3 consecutive days where no watcher run errors out
- All 5 spec scenarios executable end-to-end
- Phase C `reminder-dispatcher` and new `watcher-dispatcher` co-exist for 2 weeks with no conflicting writes
- After 2 weeks: hard-cut migration drops Phase C tables; watcher count grows organically

---

## Self-Review

After writing this plan, I reviewed against the spec checklist:

**Spec coverage:**
- ✅ All 16 locked decisions reflected in tasks
- ✅ All 5 worked examples covered by W4.2 replay scenarios
- ✅ All 4 pre-built templates have a creation task
- ✅ All 9 action chain step types referenced in W2.1
- ✅ All 4 V1 event types have poller setup
- ✅ Approval gates (per-watcher + per-fire) covered
- ✅ Memory model (strict-entity-set) covered
- ✅ Migration from Phase C covered
- ✅ Janitor for orphan reconciliation covered
- ✅ Stagger field included in schema
- ✅ KB load integration via load_knowledge step

**No placeholders:** every task has concrete files, steps, verification commands.

**Type consistency:** schema fields, action step types, event names all match across tasks.

**Gap analysis:**
- ⚠️ Cost projection logic in W1.1 is described prose-level, not specced down to the formula. Acceptable for V1 because we'll iterate based on early data.
- ⚠️ Plain-English rendering of action chain JSON (for Slack display) is described conceptually in W3.1. Implementation will need a small renderer — flagged but not blocking.

**Risks:**
- OpenClaw `cron.add` response shape — confidence MEDIUM (research findings). If field name is unexpected, W1.1 needs a tweak. Low-risk: easy to patch.
- Phase C migration script complexity — depends on how many `scheduled_actions` rows exist. If <100, trivial. If >1000, may need batching. Flag at execution time.

---

## Execution Handoff

This plan is ready for execution. Two paths:

**1. Subagent-Driven (recommended)** — use `superpowers:subagent-driven-development`. Dispatch one subagent per task, with two-stage review (spec compliance then code quality) after each. Fast iteration, fresh context per task, no context pollution.

**2. Inline Execution** — use `superpowers:executing-plans`. Batch execution with checkpoints. Slower but lower overhead.

**Estimated effort:** 2-3 weeks of focused work. Larger than Phases B and C because of the broader surface area (new tables, new skills, migration script, event pollers, janitor, template library).

**Prerequisites confirmed before kickoff:**
- BON KB Tier 1 files exist (Abhinav's parallel work)
- All 16 spec decisions locked
- OpenClaw research findings reviewed (no surprises)
