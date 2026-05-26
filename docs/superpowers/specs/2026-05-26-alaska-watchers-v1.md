# Alaska Watchers V1 — Design Spec

> **Status:** Design — awaiting Abhinav's answers on open questions before implementation.
> **Date:** 2026-05-26
> **Author:** Abhinav (product direction) + Claude (architecture synthesis)
> **Supersedes:** the implicit "reminders + scheduling" framing of Phase C
> **Related docs:**
> - `docs/superpowers/specs/2026-05-26-bon-knowledge-base.md` — the BON Knowledge Base design (foundational dependency)
> - `docs/superpowers/specs/2026-05-23-alaska-task-model-design.md` — the v2 task model (Phases A-E)
> - `workspace/MEMORY.md` — current operational state

---

## Strategic framing

Alaska's V1 (Phases A-C as just deployed) made her a **reactive PM**: she classifies messages, tracks tasks, reminds about commitments, posts daily summaries. Good but not differentiated. Many tools do this.

V2 is **the smartest teammate BON has** — a proactive, ambient coworker who watches everything, finds patterns, drafts the work, never misses what a human would catch. This is the [Alaska v2 thesis](`~/.claude/projects/-Users-abhinavjain-Downloads-My-Mac-BON-code-agents-alaska/memory/alaska-v2-thesis.md`). It's foundational because BON has a hard deadline (PMF target: June 30) and operational velocity is the differentiator.

The Watchers primitive is the substrate that makes proactivity possible. Without it, every "proactive" behavior would be a one-off hack. With it, Alaska's intelligence is composable — each new use case is a new Watcher, not a new code path.

**V1 scope deliberately stays narrow:** Watchers fire ONLY on explicit user requests. Autonomous "Alaska decides what's worth watching" stays with the Thinker agent (separate, improved later). This keeps V1 testable and predictable while still unlocking the full breadth of user-requested patterns.

---

## The Watcher primitive

A **Watcher** is a unit of repeatable agency with five properties:

1. **Trigger** — when to evaluate (time-based cron OR event-based polling)
2. **Action chain** — what to do (sequence of skill invocations, formatting, sends)
3. **Recipient** — where to deliver
4. **Memory** — what's already been done (so it doesn't repeat on the same fact)
5. **Approval gates** — what humans must say yes to before it can run / send

Every example below maps to one Watcher with these five properties filled in.

### V1 in vs. out

| In V1 | Out of V1 (later versions) |
|---|---|
| User-requested watchers via Slack: "watch X and do Y" | Alaska autonomously deciding what to watch (Thinker handles that) |
| Pre-built watcher templates (Bug-cluster, Customer-signal, Stale-task, Deploy-impact) | Calibration/sensitivity tuning UX (user just deletes if too noisy) |
| Cost-gated approval (medium/high → Abhinav DM) | Cross-watcher aggregation / digest mode |
| Per-watcher memory (strict-entity-set) | Per-user context (quiet hours, on-leave, timezone resolution) |
| Skill invocation as action type | Watcher chaining (one fires another) |
| Slack-native management (list/pause/delete) | Full multi-turn watcher-creation negotiation (V1 is single-clarifier-round) |
| BON Knowledge Base referenced during creation | KB freshness enforcement (V1 warns; V2 might refuse) |
| Time-bounded watchers (expires_at) | Approval recipient configuration per-watcher |

The **Thinker** agent stays as the autonomous-pattern-finder layer. Watchers handle deterministic, user-instructed observations and actions. Clean separation.

---

## Locked design decisions

These are settled. Don't re-litigate without explicit reason:

1. **Cost display is private.** Only shown in DMs to Abhinav, only when watcher creation needs his approval. Never shown to creator or anyone else.
2. **Per-watcher cron** for time triggers (each watcher gets its own OpenClaw cron entry). Reason: timing accuracy, lifecycle isolation, OpenClaw native support.
3. **Reminders ARE Watchers.** Phase C's `scheduled_actions` table will be subsumed by the new `watchers` table. Phase C migrates as part of V1 build.
4. **Per-fire approval only for high cost variance.** Default off. Enabled when daily cost variance is wide (e.g., gift-card emails: $0 to $100 depending on user count).
5. **No approval needed for watching other team members.** Trust within team. (Privacy revisit possible later but not in V1.)
6. **Memory: strict-entity-set.** Each Watcher tracks the exact set of entities (IDs, hashes) that triggered the last action. Dedup resets only when that set changes. No time-based reset.
7. **Volume caps decided by user at creation.** Alaska asks in the follow-up question round if not specified.
8. **Build fresh.** New `watchers` table. Migrate Phase C's `scheduled_actions` rows to it during V1 build. Don't run them in parallel.
9. **Thinker stays autonomous.** Watchers are user-driven only.
10. **Watcher approval threshold = $3/day.** Watchers with projected cost ≤$3/day auto-approve (creator self-approves via confirm). Watchers >$3/day require Abhinav approval. This replaces the earlier 4-tier free/low/medium/high cost class with a simple binary at creation time. External writes (Customer.io campaigns, etc.) under $3/day still auto-approve in V1 — we'll tighten if it goes sideways. *Confirmed 2026-05-27.*
11. **Cost display privacy locked.** Cost values appear ONLY in DMs to Abhinav, during approval gate. Never to creator. Never in confirmation messages. Never in `@alaska show W-N` output for non-Abhinav callers. *Confirmed 2026-05-27.*
12. **KB-driven query templates: YES.** `workspace/knowledge/playbooks/common-queries.md` holds reusable query specs (Amplitude funnel queries, CIO segment queries, etc.). Watchers reference queries by name (e.g., `query: "plaid_funnel"`) — DRY across watchers. *Confirmed 2026-05-27.*
13. **Action chain DSL: JSON in DB, plain English in Slack.** Engineering implementation detail — users never see the JSON. Slack drafts and `@alaska show W-N` output render the action chain as a numbered prose summary ("Step 1: Query Amplitude for X. Step 2: Format as table. Step 3: DM to you."). Great UX is non-negotiable. *Confirmed 2026-05-27.*
14. **Per-fire approval recipient: ALWAYS Abhinav, creator gets CC.** When a watcher has per-fire approval enabled (Example 2 pattern — high cost variance external send), every fire's draft routes to Abhinav for approval. The original watcher creator is CC'd ("FYI Samder, W-23's batch is awaiting Abhinav's approve") so they're informed, not surprised. *Confirmed 2026-05-27 — see "Per-fire approval flow" below.*

### Knowledge base authoring authority — Abhinav-only

**Confirmed 2026-05-27.** Earlier proposal of domain-distributed authoring (engineers PR their own KB files) is RESCINDED. The Knowledge Base is Abhinav's responsibility alone — he writes and maintains every file in `workspace/knowledge/`. Engineers do NOT submit PRs to KB files.

Reasoning: KB content drives Alaska's behavior across many skills. Inconsistencies, drift, or honest mistakes by individual engineers would cascade into watcher misbehavior. Abhinav-as-sole-author ensures the KB stays a coherent single voice and reflects his canonical understanding of how BON works.

Alaska MUST refuse any apparent "edit KB" request from anyone other than Abhinav (Slack ID `U07GKLVA9FE`). Reply with: "Knowledge base changes go through Abhinav directly." Do not engage further.

### Freshness handling — warn but don't refuse

**Confirmed 2026-05-27.** When Alaska uses a KB file that's been untouched >60 days, she:
- Loads and uses it normally
- In the watcher creation flow, includes a 1-liner in her draft: *"⚠️ Sources include `integrations/plaid.md` — last updated 73 days ago. Definitions may have drifted. Want to flag this with Abhinav for refresh, or proceed?"*
- The creator can proceed (default behavior) or pause to ask Abhinav for a KB refresh

Alaska does NOT refuse to use stale KB. Better stale knowledge than no knowledge.

---

## Architecture

Three layers + one cross-cutting concern. Each layer has its own concrete primitives.

### Layer 1 — Triggers (when to evaluate)

Two trigger types in V1:

**`cron`** — Time-based.
- RRULE or cron expression with timezone
- Most user requests ("every Monday 9 AM", "daily at 5 PM PST", "in 5 days at 10am")
- Each watcher gets its own OpenClaw cron entry via `cron.add` API
- Watcher row stores `openclaw_cron_id` for lifecycle (delete on cancel)

**`event`** — Event-based, V1 implemented as polling.
- Pre-defined event types with optional filters
- A single shared poller-cron per event type runs every N minutes
- The poller dispatches matching events to all subscribed watchers
- V2 may replace polling with webhooks where available (Amplitude, etc.)

**V1 event types (initial set):**

| Event | Source | Filter shape | Poll interval |
|---|---|---|---|
| `new_signup` | Amplitude | `{credit_score: {op: "<", value: 580}}` (any user property) | 15 min |
| `bug_closed` | Notion bugs DB | `{closed_by_slack_id: [...]}` | 30 min |
| `pr_merged` | GitHub | `{author_slack_id: [...], repo: [...]}` | 15 min |
| `meeting_processed` | Meeting Intelligence (task_events table) | `{attendee_slack_id: [...]}` | event-driven (no polling needed) |
| `task_status_changed` | task_events table | `{to_status: "done", owner_slack_id: [...]}` | event-driven (no polling needed) |
| `deploy_succeeded` | (TBD — Sandeep's domain to wire) | `{repo: [...]}` | TBD |

More event types can be added later by extending the event poller registry.

### Layer 2 — Action chain (what to do when triggered)

A watcher's `action_chain` is an ordered JSON array of steps. Each step is one of:

| Step | Purpose | Output |
|---|---|---|
| `load_knowledge` | Pre-load BON KB files into working context | None (side effect) |
| `invoke_skill` | Run a skill with args, capture output | Whatever the skill returns (JSON, text, structured data) |
| `format` | Format previous step's output via template | Formatted string / structured object |
| `draft_for_approval` | Pause chain, DM the draft to per_fire_approver | Resumes on approve; stops on decline |
| `send_dm` | Slack DM to a user | None |
| `send_channel` | Slack channel post | None |
| `send_email_cio` | Customer.io transactional or campaign send | None |
| `attach_chart` | Fetch chart from external (Amplitude saved chart, etc.) | URL / image |
| `create_task` | Invoke task-handler skill | task_id |

Steps reference each other's outputs via Mustache-like `{{step_N.field}}` or `{{var_name}}` syntax. Examples in the worked-examples section below.

**Cost annotations per step:**
- `load_knowledge`: free (just file reads)
- `invoke_skill`: varies by skill — skill metadata declares its `cost_class`
- `format`: free if template-only, low if LLM-formatted
- `draft_for_approval`: low (one Slack DM)
- `send_dm` / `send_channel`: free (Slack API is free)
- `send_email_cio`: HIGH (external write, $$$ implications)
- `attach_chart`: low
- `create_task`: free (just SQLite write + LLM dedup call which is already costed in task-handler)

The watcher's `cost_class` (free/low/medium/high) is computed at creation time by summing per-step cost classes × expected fire frequency. Watcher-creator skill projects monthly cost from this and shows it to Abhinav in the approval DM if cost_class >= medium.

### Layer 3 — Memory & approval (cross-cutting)

**Memory (strict-entity-set):**

Each watcher tracks `last_fact_key` — a deterministic ID for the thing that triggered the last action. On each fire:

1. Compute current `fact_key`
2. If `current_fact_key == last_fact_key`: don't repeat. Log fire with `outcome='skipped_memory'`. Exit.
3. If different: take action, update `last_fact_key`, log fire with `outcome='acted'`.

Examples:
- **Bug-cluster Watcher:** `fact_key` = sorted set of bug-cluster topic IDs
- **Stale-task Watcher:** `fact_key` = sorted set of stale task IDs
- **Low-score signup Watcher:** `fact_key` = sorted set of new user_ids in this poll

Watchers explicitly opting out of memory (e.g., periodic reports that should always fire — "weekly card linkage report") set `memory_strategy='none'`. Their fact_key is never compared.

**Approval (two levels):**

*Per-watcher approval* — creation-time gate, single decision.
- Triggered when: cost_class >= medium, OR action chain contains external write (email, channel post), OR recipient is anyone other than creator.
- Flow: Watcher created with `status='pending_approval'`. DM sent to Abhinav with full draft + cost projection + approve/decline/modify reply grammar. On approve: status→active, OpenClaw cron created. On decline: status→cancelled, DM creator with reason.

*Per-fire approval* — execution-time gate, fires every run.
- Enabled when: action chain produces external sends with VARIABLE cost (e.g., gift card emails — 5 some days, 50 others), or skill metadata declares `requires_per_fire_approval: true`.
- Flow: At fire time, dispatcher runs the action chain up to the `draft_for_approval` step. Then pauses. Drafts the planned action (recipients, content, cost) and DMs it to `per_fire_approver` (always Abhinav for variable-cost external sends; creator gets a CC). Approval = continue chain. Decline = stop, log decision in watcher_fires.
- **All `per_fire_approver` defaults to Abhinav for variable-cost external sends.** Creator gets a "this is going to Abhinav for sign-off" CC.

---

## Schema

### `watchers` table (new in V1)

```sql
CREATE TABLE watchers (
  -- Identity
  watcher_id          TEXT PRIMARY KEY,             -- W-1, W-2, ... (generated like T-N per shared-toolkit Section 1.7)
  description         TEXT NOT NULL,                 -- short NL summary for display

  -- Lifecycle status
  created_by_slack_id TEXT NOT NULL,
  created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_from_msg    TEXT,                          -- Slack permalink to the original request
  status              TEXT NOT NULL
                       CHECK (status IN ('pending_approval','active','paused','expired','cancelled')),
  cost_class          TEXT NOT NULL
                       CHECK (cost_class IN ('free','low','medium','high')),
  approved_by_slack_id TEXT,                         -- NULL if self-approved
  approved_at         DATETIME,
  decline_reason      TEXT,                          -- populated if status='cancelled' via decline

  -- Trigger
  trigger_type        TEXT NOT NULL
                       CHECK (trigger_type IN ('cron','event')),
  trigger_config      TEXT NOT NULL,                 -- JSON: {expr, tz} or {event_name, filter}

  -- Time bounds
  starts_at           DATETIME,                      -- NULL = immediately
  expires_at          DATETIME,                      -- NULL = forever

  -- Action chain
  action_chain        TEXT NOT NULL,                 -- JSON array of steps (see below)
  recipient           TEXT NOT NULL,                 -- JSON: {type: 'slack_dm'|'slack_channel'|'email', id: '...'}
  per_fire_approval   BOOLEAN NOT NULL DEFAULT 0,
  per_fire_approver   TEXT,                          -- Slack ID
  volume_cap          INTEGER,                       -- max items per fire (e.g., 50 users); NULL = no cap

  -- Memory
  memory_strategy     TEXT NOT NULL DEFAULT 'none'
                       CHECK (memory_strategy IN ('none','strict_entity_set')),
  memory_state        TEXT,                          -- JSON: {last_fact_key, last_fired_at}
  cool_down_seconds   INTEGER NOT NULL DEFAULT 0,    -- minimum gap between fires

  -- Knowledge base provenance
  knowledge_sources   TEXT,                          -- JSON array of KB file paths used at creation

  -- Stats
  fire_count          INTEGER NOT NULL DEFAULT 0,
  last_fired_at       DATETIME,
  last_action_summary TEXT,                          -- JSON of last fire's outcome

  -- OpenClaw integration
  openclaw_cron_id    TEXT                           -- the cron ID OpenClaw assigned (cron-type only)
);

CREATE INDEX idx_watchers_status_trigger ON watchers(status, trigger_type);
CREATE INDEX idx_watchers_created_by   ON watchers(created_by_slack_id);
CREATE INDEX idx_watchers_expires      ON watchers(expires_at) WHERE expires_at IS NOT NULL;
```

### `watcher_fires` table (audit log)

```sql
CREATE TABLE watcher_fires (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  watcher_id        TEXT NOT NULL REFERENCES watchers(watcher_id),
  fired_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fact_key          TEXT,                              -- the fact that triggered this fire
  outcome           TEXT NOT NULL
                     CHECK (outcome IN ('acted','skipped_memory','skipped_cooldown','skipped_empty','failed','awaiting_approval','approved','declined')),
  action_summary    TEXT,                               -- JSON of what was done
  error             TEXT                                -- populated if outcome=failed
);

CREATE INDEX idx_watcher_fires_watcher ON watcher_fires(watcher_id, fired_at);
```

### Action chain DSL example

```json
[
  {
    "step": "load_knowledge",
    "kb_files": ["integrations/plaid.md", "integrations/amplitude.md", "definitions/metrics.md"]
  },
  {
    "step": "invoke_skill",
    "skill": "amplitude-analyst",
    "args": {
      "query": "users_with_event_without_followup",
      "trigger_event": "plaid_link_initiated",
      "no_followup_event": "plaid_link_success",
      "window_hours": 168,
      "filters": "real_users"
    },
    "output_var": "failed_users"
  },
  {
    "step": "invoke_skill",
    "skill": "identity-resolver",
    "args": {
      "user_ids": "{{failed_users.user_ids}}"
    },
    "output_var": "users_with_emails"
  },
  {
    "step": "format",
    "template": "weekly_funnel_report",
    "args": {
      "users": "{{users_with_emails}}",
      "max_users": "{{volume_cap}}",
      "include_email": true
    },
    "output_var": "report"
  },
  {
    "step": "send_dm",
    "to": "U07GKLVA9FE",
    "content": "{{report}}"
  }
]
```

### Migration from Phase C

Phase C's `scheduled_actions` and `routine_proposals` tables don't disappear immediately. Migration plan during V1 build:

1. Add the new `watchers` + `watcher_fires` tables (migration 0003).
2. Write a one-time migration script that converts existing `scheduled_actions` rows (action_type='remind' / 'recurring_routine') to `watchers` rows. Most fields map directly.
3. Routine_proposals migrate to watchers with `status='pending_approval'`.
4. Reminder-dispatcher gets rewritten as the Watcher dispatcher (or replaced — see "OpenClaw research" below).
5. After 2 weeks of dual operation (both tables populated, only watchers actively executing), drop `scheduled_actions` and `routine_proposals`.

---

## The watcher-creator skill — conversation flow

This is a new skill at `skills/watcher-creator/SKILL.md`. It's invoked when the intent-classifier labels a DM as **WATCHER_REQUEST** (a new intent type to add) OR when a user explicitly says `@alaska watch ...` / `@alaska deploy watcher for ...` / `@alaska activate <template>`.

Note: WATCHER_REQUEST becomes a new intent in the classifier. Phase C already added REMINDER_REQUEST — many simple reminders will continue to flow through that path. WATCHER_REQUEST captures the more general "I want you to do X periodically / conditionally" pattern. Update intent-classifier prompt to distinguish.

### Step-by-step flow

```
1. RECEIVE
   User Slack message contains "watch", "track", "alert me", "every Monday", "whenever X happens", etc.
   Or explicit @alaska watch / deploy watcher / activate <template>.

2. PARSE INTENT
   Categorize: simple reminder | scheduled report | event watch | external action | template activation
   If template activation → jump to step 6 with template defaults pre-filled.

3. LOAD RELEVANT KB FILES
   Keyword match against the BON KB index:
   - "Plaid" / "card linkage" → integrations/plaid.md
   - "credit score" → data-models/credit-profile.md + definitions/metrics.md
   - "email" / "campaign" → integrations/customerio.md
   - "Amplitude" / "DAU" / "retention" → integrations/amplitude.md
   - "deploy" / "PR" / "commit" → integrations/github.md
   - "user" without other qualifier → data-models/user.md
   - Plus always load: definitions/metrics.md, definitions/lifecycle-events.md
   Load all matched files as working context for the LLM.

4. DRAFT WATCHER INTERNALLY
   Use KB definitions to fill in:
   - Event definitions (what counts as "failed", "stale", "success")
   - Filter syntax (Real Users filter, etc.)
   - Available data sources (which skill to invoke, what args)
   - Output formats (table, chart, list, summary)
   Identify remaining gaps — these are HUMAN INTENT ambiguities, not technical ones.

5. ASK FOLLOW-UP QUESTIONS (only for true ambiguities)
   Common categories:
   - Timezone (if not specified): "IST or PST?"
   - Volume cap (if listing things): "Cap at how many users?"
   - Format preference (if multiple sensible): "Table or list?"
   - Time bounds (if not specified): "Run forever or expire after N weeks?"
   - Recipient (if not obviously "me"): "DM you only, or also post somewhere?"
   - Things the KB CAN'T know

   Limit to 3 questions max. Bundle into one message.
   Wait for user reply.

6. PRESENT DRAFT
   "Watcher W-X (draft, pending your confirm):

    What: <NL description>
    Trigger: <schedule + timezone, OR event + filter>
    Action: <plain-English summary of action chain>
    Recipient: <where output goes>
    Memory: <strict — won't repeat on same fact / or 'none' for periodic reports>
    Expires: <date or 'never'>
    Sources: <KB files I used>

    Confirm 'yes' or edit:
    - 'change time to 10 AM'
    - 'expire after Dec 31'
    - 'cap at 30 instead of 50'"

7. CHECK APPROVAL GATE
   Decide:
   - Self-approvable (cost free/low, self-scope, no external writes) → wait for creator's "yes"
   - Requires Abhinav approval (cost medium/high, external writes, recipient ≠ creator) →
       a) Reply to creator: "I'll need Abhinav to sign off — flagged as W-X pending."
       b) DM Abhinav with full draft + cost projection + per-fire approval flag + approve/decline/modify grammar.

8. ON CONFIRMATION
   - Insert watcher row, status='active'
   - For cron triggers: call OpenClaw cron.add → store openclaw_cron_id in the row
   - For event triggers: add watcher_id to event poller's subscription registry
   - DM creator: "Watcher W-X active. Reply '@alaska pause W-X' anytime to pause."
   - DM Abhinav (if he approved): "Activated W-X for <creator first name>."

9. ON DECLINE (from Abhinav)
   - Update status='cancelled', decline_reason='...'
   - DM creator: "<Abhinav decided not to activate W-X. Reason: ...>"
```

### Reply grammar for management

```
@alaska watchers              → list MY active watchers (W-N, description, last fired)
@alaska watchers all          → list ALL active watchers (Abhinav-only)
@alaska watchers paused       → list paused (mine)
@alaska watchers expired      → list expired (mine, past 30 days)
@alaska show W-N              → details: trigger, action chain summary, last 5 fires, memory state
@alaska pause W-N             → status='paused' (cron stays registered but doesn't act)
@alaska resume W-N            → status='active'
@alaska delete W-N            → cancel + remove OpenClaw cron entry
@alaska modify W-N: <change>  → edit (re-runs approval if cost class crosses threshold)
@alaska watcher templates     → list pre-built templates available
@alaska activate <template>   → set up from template (asks for parameters)
```

---

## Pre-built watcher templates (ship with V1)

Stored at `skills/watcher-creator/templates/`. Each is a JSON file with placeholders.

### `bug-cluster.json`

```json
{
  "id": "bug-cluster",
  "display_name": "Bug Cluster Watcher",
  "description": "Weekly bug topic clustering — alerts if any topic has 3+ reports in past 7 days",
  "trigger": {"type": "cron", "expr": "0 16 * * 5", "tz": "Asia/Kolkata"},
  "action_chain": [
    {"step": "load_knowledge", "kb_files": ["integrations/notion.md", "playbooks/common-queries.md"]},
    {"step": "invoke_skill", "skill": "thinker", "args": {"action": "cluster_bugs_by_topic", "window_days": 7}, "output_var": "clusters"},
    {"step": "format", "template": "bug_cluster_report", "args": {"clusters": "{{clusters}}", "threshold": 3}, "output_var": "report"},
    {"step": "send_dm", "to": "{{creator_slack_id}}", "content": "{{report}}", "skip_if_empty": true}
  ],
  "memory_strategy": "strict_entity_set",
  "cost_class": "free",
  "parameters_to_ask": []
}
```

### `customer-signal.json`

```json
{
  "id": "customer-signal",
  "display_name": "Customer Signal Watcher",
  "description": "Daily Amplitude funnel deltas — alerts on ≥15% drop at any step vs 14-day baseline",
  "trigger": {"type": "cron", "expr": "0 3 * * *", "tz": "Asia/Kolkata"},
  "action_chain": [
    {"step": "load_knowledge", "kb_files": ["integrations/amplitude.md", "definitions/metrics.md", "data-models/card-linkage.md"]},
    {"step": "invoke_skill", "skill": "amplitude-analyst", "args": {"query": "funnel_with_baseline", "funnel_id": "{{funnel_id}}", "baseline_days": 14}, "output_var": "funnel"},
    {"step": "format", "template": "funnel_delta_alert", "args": {"funnel": "{{funnel}}", "threshold_pct": 15}, "output_var": "alert"},
    {"step": "send_dm", "to": "{{creator_slack_id}}", "content": "{{alert}}", "skip_if_empty": true}
  ],
  "memory_strategy": "strict_entity_set",
  "cost_class": "low",
  "parameters_to_ask": ["Which funnel? (card_linkage / signup / activation)"]
}
```

### `stale-task.json`

```json
{
  "id": "stale-task",
  "display_name": "Stale Task Watcher",
  "description": "Daily check for your active tasks unchanged >7 days",
  "trigger": {"type": "cron", "expr": "0 4 * * *", "tz": "Asia/Kolkata"},
  "action_chain": [
    {"step": "invoke_skill", "skill": "task-handler", "args": {"action": "query_stale", "owner_slack_id": "{{creator_slack_id}}", "days_stale": 7}, "output_var": "stale_tasks"},
    {"step": "format", "template": "stale_task_nudge", "args": {"tasks": "{{stale_tasks}}"}, "output_var": "nudge"},
    {"step": "send_dm", "to": "{{creator_slack_id}}", "content": "{{nudge}}", "skip_if_empty": true}
  ],
  "memory_strategy": "strict_entity_set",
  "cost_class": "free",
  "parameters_to_ask": []
}
```

### `deploy-impact.json`

```json
{
  "id": "deploy-impact",
  "display_name": "Deploy Impact Watcher",
  "description": "On every deploy event, snapshot key metrics before/after and report delta",
  "trigger": {"type": "event", "event_name": "deploy_succeeded", "filter": {"repo": "{{repos}}"}},
  "action_chain": [
    {"step": "load_knowledge", "kb_files": ["integrations/amplitude.md", "definitions/metrics.md"]},
    {"step": "invoke_skill", "skill": "amplitude-analyst", "args": {"query": "metric_snapshot", "metrics": ["DAU", "card_linkage_rate", "session_length"], "window": "24h", "anchor": "{{event.timestamp}}"}, "output_var": "snapshot"},
    {"step": "format", "template": "deploy_impact_report", "args": {"snapshot": "{{snapshot}}", "deploy_meta": "{{event}}"}, "output_var": "report"},
    {"step": "send_dm", "to": "{{creator_slack_id}}", "content": "{{report}}"}
  ],
  "memory_strategy": "none",
  "cost_class": "low",
  "parameters_to_ask": ["Which repos to watch? (default: all 9 BON repos)"]
}
```

Skipping `silent-engineer` per Abhinav's explicit feedback — covered by manual asks if needed.

---

## Worked examples (with BON KB in play)

These are the 5 scenarios from the design conversation. They drove the architecture.

### Example 1 — Abhinav, weekly card linkage report

> "Hey @Alaska deploy watcher for me, I want to see card linkage rate every Monday for previous week. Also include the unique users who tried and succeeded and failed. Also list the details of these users who failed and share me their email id who failed."

**Without KB:** ~5 clarifying questions (timezone, format, "what's failed", etc.)

**With KB:** Alaska reads `integrations/plaid.md` (failed-user definition), `integrations/amplitude.md` (Real Users filter), `definitions/metrics.md` (card linkage rate formula). Only HUMAN INTENT questions remain.

Conversation:

```
Alaska: "Two questions before I draft:
1. Monday morning IST (9 AM IST) or end-of-Sunday PST?
2. Max failed users to list? You may get 50-100+ some weeks — pick a cap or say 'all'."

Abhinav: "9 AM IST. Cap at 50."

Alaska: "Drafted W-15:
What: Weekly card linkage report for previous Mon-Sun
Trigger: Every Monday 9 AM IST (3:30 AM UTC)
Action chain:
  1. Query Amplitude for plaid funnel (initiated/success/failed) past 7 days, real users only
  2. Resolve failed users' emails via Customer.io
  3. Format report: rate %, counts, top 50 failed users with emails
  4. DM to you
Memory: none (each week's report stands alone)
Expires: never
Sources: plaid.md, amplitude.md, customerio.md, metrics.md

Confirm 'yes' or edit?"

Abhinav: "yes"

Alaska: "Watcher W-15 active. First fire: Monday 9 AM IST."
```

### Example 2 — Samder, daily failed-users + gift card emails (HIGH STAKES)

> "Hey @Alaska, I want you to track the failed card linkage users every day and at the end of day PST at 5 PM craft a mail for these users proposing them $5 gift card for a call so that we can help them to link their cards to talk to them. And send them the email."

**This is the most architecturally important example.** Reveals per-fire approval gate as a real primitive.

Conversation:

```
Alaska: "Three things before drafting:
1. Max emails per day? If 100 users fail in a day, sending all = 100 × $5 = $500 in gift cards.
2. Personalized email per user (more compelling, slightly more $$$) or one shared template?
3. Same user might fail multiple times — don't re-email within how many days? 30-day cool-off?

Also flagging: I don't see a gift_card_offer template in customerio.md. Has the marketing template been created, or do you want me to draft one in the watcher?"

Samder: "1. Cap at 20. 2. Personalized. 3. 30 days. 4. Yes draft the template, run it past me first."

Alaska: "Drafted W-23:
What: Daily gift card outreach to failed Plaid users
Trigger: Every day 5 PM PST
Action chain:
  1. Query Amplitude for failed Plaid users today (per plaid.md definition)
  2. Filter out users emailed in last 30 days (CIO check)
  3. Top 20 by signup recency
  4. LLM-personalize gift card offer email per user
  5. DRAFT_FOR_APPROVAL → DM Abhinav with batch preview
  6. On approve: send via Customer.io transactional
  7. Mark emailed users in memory
Memory: track emailed user IDs (30-day window)
Expires: 60 days from activation
Per-fire approval: YES (variable cost up to $100/day)
Sources: plaid.md, customerio.md, metrics.md

Because this sends external emails with variable cost, Abhinav needs to approve the watcher AND each day's batch. Sending the proposal to him now."

[DMs Abhinav privately:]
"Routine proposal W-23 from Samder (variable financial commitment):
Daily 5 PM PST gift card outreach to failed Plaid users.
- Max 20 emails/day, 30-day re-send cool-off
- Personalized via LLM
- Per-fire approval ON (you review each day's batch before send)
- 60-day campaign window

Cost projection: $0.50-2/day compute + $0-100/day gift cards (capped). Hard ceiling: $6,000 over 60 days max.

Marketing template gift_card_offer doesn't exist in CIO — Samder requested I draft one for your review first.

Approve / decline / modify W-23."
```

### Example 3 — Darwin, daily bug-fix tracking (time-bounded)

> "I want to notify me whenever Tarun or Shailesh completes the bugs, for what user, what bugs they fixed in detail, so I can continue the audit. Do this everyday at 6 PM PST for next two weeks maybe."

Reveals: time-bounded watchers (`expires_at`), multi-person tracking, cross-system joining.

```
Alaska: "Quick clarifying questions:
1. 'Bugs' — Notion bug DB, #bugs Slack channel, or both?
2. 'Completes' — PR merged, status flipped to Done, or just commit pushed?
3. Start the 2-week window today, or next Monday?"

Darwin: "1. Both. 2. PR merged AND status flipped to Done. 3. Today."

Alaska: "Drafted W-31:
What: Daily summary of bugs Tarun + Shailesh closed in past 24h
Trigger: Every day 6 PM PST
Expires: 2026-06-09 (14 days from today)
Action chain:
  1. Query GitHub for PRs merged in past 24h by Tarun OR Shailesh (across 9 BON repos)
  2. Query Notion bugs DB for status flips to Done in past 24h by either of them
  3. For each: resolve which user (BON end user) the bug affected
  4. Format report grouped by engineer
  5. DM to you
Memory: track bug IDs already reported (no duplicates across days)
Sources: github.md, notion.md, data-models/user.md

Confirm 'yes' or edit?"

Darwin: "yes"

Alaska: "Watcher W-31 active. First fire: today 6 PM PST. Expires 2026-06-09."
```

### Example 4 — Pankaj, weekly Plaid failure-step bar chart

> "Hey Alaska, I want you to send me a bar chart of failure step on plaid every week."

Reveals: artifact-producing watchers (charts as images).

```
Alaska: "Two quick things:
1. Image attachment or link to a saved Amplitude dashboard?
2. Which day/time?"

Pankaj: "Image. Monday 9 AM IST."

Alaska: "Drafted W-42:
What: Weekly bar chart of Plaid funnel failure steps
Trigger: Every Monday 9 AM IST
Action chain:
  1. Query Amplitude funnel: Plaid steps (initiated → opened → success/abandoned/errored)
  2. Compute failure counts per step, past 7 days, real users
  3. Fetch chart image from Amplitude saved-chart export API
  4. DM to you with chart attached + 1-line summary
Memory: none (each week's chart stands alone)
Sources: plaid.md, amplitude.md

Confirm 'yes'?"
```

### Example 5 — Darwin, real-time low-score signups (EVENT-BASED)

> "Whenever user below 580 signs up inform me."

Reveals: event-based triggers (V1 implemented as polling).

```
Alaska: "Two quick things:
1. Real-time-ish (each one as it happens, batched hourly), or end-of-day summary?
2. Run forever or time-bound?"

Darwin: "Hourly batches. Forever."

Alaska: "Drafted W-24:
What: Hourly alerts for new <580 signups
Trigger: Event subscription: new_signup, filter credit_score < 580
Action chain:
  1. Get new signups since last hour (Amplitude, with filter)
  2. Pull profile details (signup_time, credit_score)
  3. If 1+ new users: DM you with batch
  4. If 0 new users: silent
Memory: track alerted user IDs (no double-alerts across hours)
Expires: never
Sources: credit-profile.md, amplitude.md, lifecycle-events.md

Self-approved. Activating now."
```

---

## OpenClaw deeper research — to do before implementation

The earlier (lighter) research showed OpenClaw natively supports `cron.add` with `kind=at` for one-shot scheduling. Before building V1 we need answers to:

1. **Beyond cron** — does OpenClaw have native primitives for:
   - Event hooks (webhook receivers we could plug into Amplitude / GitHub / etc.)
   - Stateful long-running watchers (vs. our SQLite state model)
   - Per-cron-job state persistence (would replace our memory_state column)
   - Tool / skill chaining (would replace our action_chain DSL)
   - Approval workflows
   - Notification delivery batching

2. **Limits** — practical max number of cron entries OpenClaw can manage. With 50+ active watchers we shouldn't run into dashboard clutter or performance issues but want to confirm.

3. **API surface** — what's the exact `cron.add` shape, what fields are passable, can we set `delivery.channel="none"` and have the skill prompt drive its own Slack posts (the pattern we already use)?

4. **Migration path** — can we cleanly convert Phase C's `scheduled_actions` rows to OpenClaw cron entries during V1 build? Or do we keep our table as authoritative and use OpenClaw cron purely as the timer mechanism?

**The deliverable from this research:** a 1-page summary that informs:
- Whether V1's dispatcher is a thin wrapper on OpenClaw native, or a custom implementation
- Whether watcher state lives in our SQLite or OpenClaw-managed
- Whether per-watcher cron entries are sustainable at scale

Dispatched as a research subagent after Abhinav signs off on this design.

---

## Open questions — answered 2026-05-27

Resolved (see "Locked design decisions" #10-#14 above for full details):

1. ✅ **KB authoring:** Abhinav-only (not domain-distributed). Engineers don't touch knowledge files. — *Locked decision #14 / dedicated section above.*
2. ✅ **KB freshness:** Warn but don't refuse. — *Locked decision section above.*
3. ✅ **Watcher creation threshold:** >$3/day requires Abhinav approval; ≤$3/day auto-approves. — *Locked decision #10.*
4. ✅ **Per-fire approval recipient:** Always Abhinav, creator CC'd. — *Locked decision #14.*
5. ✅ **Action chain DSL:** JSON in DB, plain English in Slack. — *Locked decision #13.*
6. ✅ **Cost privacy:** Cost only visible to Abhinav, in approval DMs. — *Locked decision #11.*
7. ✅ **KB-driven query templates:** Yes. — *Locked decision #12.*

## Still open — sequencing decisions

These don't block the spec finalization but block kicking off the build:

**A. Build sequencing.**
- Option A: Phase D (cross-person TASK_ASSIGN) first, then Watchers V1
- Option B: Watchers V1 first (Phase D becomes a specific watcher pattern)
- Option C: Continue Phase B/C observation for ~1 week, then decide
- Recommendation: Option B — Watcher substrate makes everything else additive

**B. Migration window.** Phase C `scheduled_actions` → new `watchers` table.
- Dual-write both tables for ~2 weeks (safer)
- Hard-cut on V1 deploy (cleaner)
- Recommendation: dual-write — Phase C just deployed, too early to know what might break

---

## Implementation plan (to be written after design sign-off)

Once Abhinav answers the open questions and the OpenClaw research lands, the implementation plan goes in `docs/superpowers/plans/2026-MM-DD-alaska-watchers-v1.md` following the `superpowers:writing-plans` skill format.

High-level shape (subject to refinement):

**Phase W.0 — Foundation**
- W0.1: BON Knowledge Base scaffold (initial KB files seeded)
- W0.2: `watchers` + `watcher_fires` migration (0003)
- W0.3: Update intent-classifier with WATCHER_REQUEST intent

**Phase W.1 — Watcher creation flow**
- W1.1: `skills/watcher-creator/SKILL.md` (the NL → draft → confirm flow)
- W1.2: Watcher template loader + 4 pre-built templates
- W1.3: Approval flow (per-watcher creation gate)

**Phase W.2 — Dispatcher**
- W2.1: Watcher dispatcher (replaces Phase C reminder-dispatcher; reads watchers table; executes action chains)
- W2.2: OpenClaw cron integration (one cron per watcher; cleanup on delete)
- W2.3: Event poller crons (one per event type; subscription registry)
- W2.4: Per-fire approval flow (draft_for_approval step)
- W2.5: Phase C migration script (scheduled_actions → watchers)

**Phase W.3 — Management**
- W3.1: Slack-native management commands (list/show/pause/resume/delete/modify)
- W3.2: Slack template activation flow (`@alaska activate stale-task`)

**Phase W.4 — Acceptance**
- W4.1: Replay-style validation (against historical signal where applicable)
- W4.2: Exercise the 5 scenarios end-to-end
- W4.3: Deploy + observation

Roughly 2-3 weeks of focused work.

---

## Appendix — Architecture diagram (text)

```
                           ┌────────────────────────────┐
                           │   User Slack message       │
                           │   "@alaska watch X..."     │
                           └─────────────┬──────────────┘
                                         ▼
                           ┌────────────────────────────┐
                           │   intent-classifier        │
                           │   labels as WATCHER_REQUEST│
                           └─────────────┬──────────────┘
                                         ▼
                           ┌────────────────────────────┐
                           │   watcher-creator skill    │
                           │   1. Load BON KB           │◀── workspace/knowledge/
                           │   2. Draft watcher         │
                           │   3. Ask follow-ups        │
                           │   4. Present to user       │
                           │   5. Route approval        │
                           └─────────────┬──────────────┘
                                         ▼
                           ┌────────────────────────────┐
                           │   watchers table (SQLite)  │
                           │   status='pending_approval'│
                           │           or 'active'      │
                           └─────────────┬──────────────┘
                              activation │
                                         ▼
              ┌──────────────────────────┴──────────────────────────┐
              ▼                                                     ▼
   ┌─────────────────────┐                              ┌─────────────────────┐
   │  cron triggers:     │                              │  event triggers:    │
   │  one OpenClaw cron  │                              │  shared event-poller│
   │  per watcher        │                              │  cron per event-type│
   └──────────┬──────────┘                              └──────────┬──────────┘
              │                                                     │
              └────────────────────┬────────────────────────────────┘
                                   ▼
                       ┌────────────────────────┐
                       │   watcher-dispatcher   │
                       │   1. Check memory      │
                       │   2. Run action chain  │
                       │   3. Per-fire approval?│
                       │   4. Execute / pause   │
                       │   5. Update memory     │
                       │   6. Log to fires      │
                       └─────────┬──────────────┘
                                 ▼
                       ┌────────────────────────┐
                       │   Action outputs:      │
                       │   - Slack DMs/channels │
                       │   - Customer.io emails │
                       │   - SQLite writes      │
                       │   - Drafts to approver │
                       └────────────────────────┘
```

---

## Cross-references

- **BON Knowledge Base design:** `docs/superpowers/specs/2026-05-26-bon-knowledge-base.md`
- **v2 task model spec:** `docs/superpowers/specs/2026-05-23-alaska-task-model-design.md`
- **Current operational state:** `workspace/MEMORY.md` → "Alaska System Evolution" v2.4 entry
- **Phase C deployment artifacts:** PR #12, commits 48c13b5..05fb90a
- **Phase B deployment artifacts:** PR #9
- **Bridge fix:** PR #10

## Open thread for next session

If picking this up fresh:
1. Read `workspace/MEMORY.md` for current state
2. Read this doc + the BON KB doc
3. Check this section ("Open questions awaiting Abhinav's answers") for what's blocked
4. Once unblocked, dispatch the OpenClaw deeper-research agent
5. Then write the implementation plan
6. Then execute via subagent-driven-development

The Watcher primitive is the substrate. Get this right and every proactive behavior Abhinav imagines becomes additive.
