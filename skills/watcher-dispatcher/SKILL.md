---
name: watcher-dispatcher
description: Executes ONE watcher when its per-watcher cron fires (or the event-poller dispatches it). Loads the watcher row, applies cooldown + strict-entity memory dedup, runs the action_chain DSL, handles per-fire approval (rung 0), logs every run to watcher_fires, updates stats, and retires expired watchers. The WHAT engine — creation lives in watcher-creator.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3, python3]
      env: [ANTHROPIC_API_KEY]
    emoji: "👁️"
---

# Watcher Dispatcher

Read `/data/skills/shared-toolkit/SKILL.md` for queue/outbox patterns, Slack routing, Section 1.5 SQL-escape rules, Section 1.7 ID-generation, and Communication Standards (mrkdwn, first-names-only, no internal narration). Read `/data/skills/task-handler/SKILL.md` only if the chain contains a `create_task` step, and `/data/skills/user-profile-360/SKILL.md` only if it resolves identity/email. Roster, Slack IDs, and Notion User IDs come from `/root/.openclaw/workspace/MEMORY.md` → Team Roster — never embed your own copy. Abhinav's Slack ID is `U07GKLVA9FE`.

You are the Watcher Dispatcher. When a watcher fires, you run its `action_chain`. You are pure execution: the watcher already exists (created + approved by watcher-creator), the cron already decided it's time. Your only job is to run this one watcher correctly, dedup it, act, and audit it.

## When you're invoked

- **Cron-type watcher:** its per-watcher OpenClaw cron fires with the message `Run /data/skills/watcher-dispatcher/SKILL.md procedure for watcher_id=W-N.` Extract the id with a `W-\d+` regex.
- **Event-type watcher:** the shared **event-poller** (one cron per event type) matched an event and invokes you with the `watcher_id` AND the event payload, which you expose to the chain as `{{event}}` / `{{event.field}}`.

If no `W-\d+` is present in the message, exit silently — the payload is malformed (nothing to audit, no watcher to blame).

## Procedure

### Step 1: Load the watcher; bail unless it's active

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT status, trigger_type, action_chain, recipient, per_fire_approval, per_fire_approver, \
         autonomy_rung, volume_cap, memory_strategy, memory_state, cool_down_seconds, \
         created_by_slack_id, expires_at, openclaw_cron_id, knowledge_sources \
  FROM watchers WHERE watcher_id = '$WATCHER_ID';"
```

If 0 rows OR `status != 'active'`: **exit silently, write nothing.** A row that is `paused`/`expired`/`cancelled`/`pending_*` should not fire; an orphan cron firing a missing/non-active watcher is the janitor's problem, not a fire to audit. (Do NOT log a `watcher_fires` row here — there was no legitimate fire.)

Resolve the standard variables now so every later step can use them: `{{creator}}` = `created_by_slack_id`, `{{authority}}` = that person's authority from the Team Roster, `{{volume_cap}}` = `volume_cap`.

### Step 2: Expiry check (before doing any work)

If `expires_at IS NOT NULL` AND `now >= expires_at`:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE watchers SET status='expired' WHERE watcher_id='$WATCHER_ID';"
```

Then, for a cron-type watcher with a non-NULL `openclaw_cron_id`, call the in-session **`cron.remove`** OpenClaw tool on that cron id (only Alaska can; external HTTP callers are denied). Event watchers have no per-watcher cron — just the status flip. This is idempotent with the `kind:"at"` one-shot the creator may also have scheduled. Then exit (no fire).

### Step 3: Cooldown gate (cheapest short-circuit — no query needed)

If `cool_down_seconds > 0` AND `last_fired_at` (from `memory_state`) is set AND `(now - last_fired_at) < cool_down_seconds`:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO watcher_fires (watcher_id, outcome) VALUES ('$WATCHER_ID', 'skipped_cooldown');"
```

Exit. (Cooldown is purely time-based, so checking it before the sensing steps avoids a wasted query. This is the one place this skill's order differs from the plan's listed order — same correctness, cheaper.)

### Step 4: Per-fire approval double-prompt guard (rung 0 only)

If `per_fire_approval = 1`, check for an already-pending draft:

```bash
sqlite3 /data/queue/alaska.db \
  "SELECT id FROM watcher_fires WHERE watcher_id='$WATCHER_ID' AND outcome='awaiting_approval' \
   ORDER BY fired_at DESC LIMIT 1;"
```

If a row exists, a previous fire is still waiting on the creator's yes. **Do not draft again** (no second DM, no stacked drafts):

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO watcher_fires (watcher_id, outcome) VALUES ('$WATCHER_ID', 'skipped_pending_approval');"
```

Exit. New fires resume only after the creator approves/declines the pending one (slack-commands per-fire approval flow).

### Step 5: Run the SENSING steps and compute the fact_key

The `action_chain` (JSON array) splits into **sensing** then **acting**. Sensing = every step before the first step with an external effect (`send_dm`, `send_channel`, `send_email_cio`, `attach_chart`, `create_task`, or `draft_for_approval`): i.e. `load_knowledge`, query `invoke_skill`s, and `format`. Run them in order, capturing each `output_var`. This is a SINGLE pass — sensing outputs are reused by the acting steps; never query twice.

- **load_knowledge** → read the listed `kb_files` (under `/root/.openclaw/workspace/knowledge/`) into context.
- **invoke_skill** (query) → run the skill with `args`, capture `output_var`. (DSL detail in "Action-chain step execution" below.)
- **format** → render `template` with `args` → `output_var` (Slack mrkdwn).

**Empty result → `skipped_empty`.** If the sensing produced nothing to act on (no entities, query returned 0 rows, the would-be message is empty), log `skipped_empty` and exit — never send an empty alert. (This is what every template's `skip_if_empty: true` means at the chain level.)

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO watcher_fires (watcher_id, outcome) VALUES ('$WATCHER_ID', 'skipped_empty');"
```

**Compute `fact_key`** (only if `memory_strategy='strict_entity_set'`): a deterministic, canonical signature of the salient entities this fire would act on — e.g. the sorted, comma-joined set of signup `user_id`s, bug-cluster topic IDs, or stale `task_id`s (spec §"Memory"). Sort first so ordering never changes the key; for large sets store a `sha256` of the canonical string. `memory_strategy='none'` → no fact_key (periodic reports always proceed).

### Step 6: Memory gate (strict_entity_set only)

Compare the computed `fact_key` to `memory_state.last_fact_key`. If **equal**, this fire would repeat the last action on the same facts:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO watcher_fires (watcher_id, fact_key, outcome) \
  VALUES ('$WATCHER_ID', '$fact_key_esc', 'skipped_memory');"
```

Exit. (Escape `fact_key` per §1.5.) Otherwise proceed — but do NOT update `last_fact_key` yet; it is updated only when an action actually happens (Step 8 / the approval resume). A skipped, declined, or failed fire must never suppress the next legitimate one.

### Step 7: Branch on per-fire approval

**Rung 0 (`per_fire_approval = 1`): pause for the creator.** Run the chain up to `draft_for_approval`, then:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO watcher_fires (watcher_id, fact_key, outcome, action_summary) \
  VALUES ('$WATCHER_ID', '$fact_key_esc', 'awaiting_approval', '$summary_esc');"
```

`action_summary` (JSON) must capture the rendered draft AND enough to resume — which acting steps remain and their resolved args — so the slack-commands resume runs the exact same send. DM the **`per_fire_approver`** (the creator — locked decision #14) the draft plus the reply grammar:

> `Watcher W-N is ready to send (your approval needed):`
> `<the rendered draft>`
> `Reply 'approve W-N fire' to send, 'decline W-N fire <reason>' to skip, or 'modify W-N fire: <change>'.`

Then **exit** — the action does not run now and `last_fact_key` is NOT updated (it updates on approval). The resume is owned by slack-commands; this skill never sends a rung-0 external action without the yes.

**Rung 1 (`per_fire_approval = 0`): act now.** Continue to Step 8.

### Step 8: Execute the ACTING steps, then record (execute-first ordering)

Run the remaining (acting) steps in order, substituting variables (see "Variable substitution"), applying `volume_cap` (truncate any entity list to the cap; note it in the message, e.g. `showing 50 of 120`), and honoring per-step `skip_if_empty`.

**Ordering & idempotency.** Unlike reminder-dispatcher (which flips a queue row to `fired` *before* its side effect to survive overlapping ticks re-reading the queue), this dispatcher is a single per-watcher invocation with no queue to re-scan — so it executes the side effect FIRST, then records. This biases to **never-miss**: if a send fails we do NOT advance `last_fact_key`, so the next scheduled fire retries the same fact. The cost is a rare duplicate if the container dies between send and record — acceptable for internal/read-only actions (rung 1 is reports/alerts/nudges/`create_task` only; external sends are rung 0 and human-gated). `strict_entity_set` further self-heals: once `last_fact_key` is written, a re-fire on the same facts hits Step 6 and skips.

**On success:**

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE watchers \
  SET fire_count = fire_count + 1, \
      last_fired_at = CURRENT_TIMESTAMP, \
      memory_state = '$memory_state_esc', \
      last_action_summary = '$action_summary_esc' \
  WHERE watcher_id = '$WATCHER_ID';"
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO watcher_fires (watcher_id, fact_key, outcome, action_summary) \
  VALUES ('$WATCHER_ID', '$fact_key_esc', 'acted', '$action_summary_esc');"
```

`memory_state` JSON = `{"last_fact_key": "<fact_key or null>", "last_fired_at": "<now ISO>"}`. For `memory_strategy='none'`, still bump `last_fired_at`/`fire_count`; `last_fact_key` stays null.

**On failure** (a step errored — skill timeout, Slack/Notion down, bad data): log it and alert Abhinav once; do NOT advance `last_fact_key` (so the next fire retries):

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE watchers SET fire_count = fire_count + 1, last_fired_at = CURRENT_TIMESTAMP \
  WHERE watcher_id = '$WATCHER_ID'; \
  INSERT INTO watcher_fires (watcher_id, fact_key, outcome, error) \
  VALUES ('$WATCHER_ID', '$fact_key_esc', 'failed', '$short_error_esc');"
```

Then DM Abhinav (`U07GKLVA9FE`): `Watcher W-N failed this fire: <short error>. Won't retry until its next scheduled run.` If you see the same service erroring across a batch, follow shared-toolkit Section 7 graceful-degradation before continuing.

### Step 9: Post-fire expiry sweep

If `expires_at` was set and this run pushed past it (or it lapsed during the run), apply Step 2's expiry (flip `status='expired'` + `cron.remove`). Belt-and-suspenders with the creator's `kind:"at"` one-shot — both are idempotent.

## Action-chain step execution (the 9 step types)

| Step | Execution |
|---|---|
| `load_knowledge` | Read each `kb_files` path under `/root/.openclaw/workspace/knowledge/` into context. Free. |
| `invoke_skill` | Run `skill` with `args`; capture stdout/result into `output_var`. **Identity/email/profile = `user-profile-360`** (`python3 /data/skills/user-profile-360/lookup.py --query {{user_id}} --query-type <user_id\|email\|name\|phone> --intent <narrowest> --requester-slack-id {{creator}} --requester-authority {{authority}} --channel-type dm`). Pick the **narrowest `--intent`** (`user_summary` for email-only; `credit_health`/`debt_situation`/`full_picture` only when the alert needs enrichment) — repeated enrichment of the same user hits `user_profile_cache`, so per-fire cost stays low. NEVER use a phantom "identity-resolver". |
| `format` | Render the named `template` (e.g. `funnel_delta_alert`, `bug_cluster_report`, `stale_task_nudge`) from `args` into Slack mrkdwn → `output_var`. In Gen 1 these template names document intent; you produce the mrkdwn directly — no separate template file. |
| `draft_for_approval` | Boundary marker for rung-0 watchers (Step 7). Everything before it is the draft; everything after runs only on approval. A no-op for rung 1. |
| `send_dm` | DM via the shared-toolkit outbox. `to` resolves `{{creator}}`/`{{var}}`; `content` is the rendered text. `skip_if_empty:true` → skip if content is empty. |
| `send_channel` | Channel post via the outbox. Public-channel sends are external-ish — only on rung-0/approved chains (watcher-creator gates this at creation). **PII enforcement (belt-and-suspenders):** if the rendered content contains individual PII (names, phone numbers, emails, individual credit scores) and the `recipient` is a channel WITHOUT a `pii_override_by` stamp, do NOT post — log `failed` and alert Abhinav (`Blocked W-N: would post customer PII to an unauthorized channel`). The stamp (set by watcher-creator only after Abhinav authorized a *private* channel) is the authorization token; absent it, PII never reaches a channel even if the recipient were mis-set. |
| `send_email_cio` | Customer.io send — a real external write ($$$). **Only ever runs on a rung-0 watcher after approval.** If you reach this step with `per_fire_approval=0`, the watcher is misconfigured: do NOT send — log `failed` + alert Abhinav (anti-pattern 9). |
| `attach_chart` | Fetch + attach a chart image (e.g. Amplitude saved-chart export) to the pending send. |
| `create_task` | Invoke **task-handler** (never write `tasks`/`task_events` directly). When the task surfaces to Notion, set **Owner (people)** from the roster **Notion User ID** (`{"people":[{"id":"<uuid>"}]}`) — Owner writes are ENABLED (MEMORY.md); fall back to first-name-in-Notes only if the person has no Notion ID. **NEVER target the retired Sprint Board** (`4494fedd-…`). |

**Note — invoke_skill steps that sense and return a digest.** A few chains (e.g. `cross-person-task-assign` → `follow-through.escalate_unacked_assignments`) invoke a skill that SENSES read-only and returns a digest — it writes nothing and does NOT send. The watcher's own `send_dm` step sends that digest, and the watcher's `strict_entity_set` dedups on the digest signature, so an unchanged set of unacked assignments doesn't re-nudge. (Dedup + delivery are the watcher's job, not the invoked skill's.)

## Variable substitution

Resolve `{{…}}` against, in order: the standard vars (`{{creator}}` → `created_by_slack_id`, `{{authority}}`, `{{volume_cap}}`); the event payload for event watchers (`{{event}}`, `{{event.timestamp}}`, `{{event.repo}}`, …); and prior step outputs (`{{var_name}}` for an `output_var`, `{{step_N.field}}` for the Nth step's structured result). The `recipient` column's `{type,id}` is the default send target when a `send_*` step doesn't override `to`. An unresolved `{{…}}` at send time is a failure — log `failed`, do not send a message containing a literal `{{…}}`.

## Anti-patterns

1. **Never re-act on a memory hit.** `strict_entity_set` means: same `fact_key` as `last_fact_key` → `skipped_memory`, no send. Ever.
2. **Never skip the audit row.** Every fire writes exactly one `watcher_fires` row — `acted` / `skipped_memory` / `skipped_cooldown` / `skipped_empty` / `skipped_pending_approval` / `awaiting_approval` / `failed`. The only no-row exits are a missing/non-active watcher (Step 1) and a malformed payload. Silence on a real fire breaks the audit trail.
3. **Never write `tasks`/`blockers`/`task_events` directly.** Task writes route through `create_task` → task-handler.
4. **Never touch `scheduled_actions`.** Phase C is being deprecated — this skill makes no writes there.
5. **Never bypass per-fire approval (rung 0).** Pause at `draft_for_approval`, log `awaiting_approval`, DM the creator, exit. Never run the external send without the creator's yes — and never double-prompt (Step 4 guard → `skipped_pending_approval`).
6. **Never leave a cron firing a dead watcher.** When status flips to `expired` (or you observe `cancelled`), `cron.remove` the `openclaw_cron_id` (cron-type only).
7. **Never advance `last_fact_key` except on a real action** (`acted`, or `approved` via the resume). Skipped/declined/failed fires must leave memory untouched so the next fire still works.
8. **Never send to the wrong recipient or narrate internals.** `{{creator}}` = the watcher's creator, resolved at fire time from the row. Reply text is the final output — no "Let me query…" / "the dispatcher ran…" (shared-toolkit Communication Standards). Cost values never appear in any fire output (those live only in Abhinav's creation-time approval DM). The report itself is **plain English** — never raw event/property/file names (`add_card_successful`, `exit_step`, `amplitude.md`); and any date/weekday in the output is computed with `python3` in the watcher's timezone, never reasoned by hand (a Tuesday mislabeled "Monday" is the classic failure).
9. **Never run `send_email_cio` (or a public `send_channel`) from a rung-1 watcher.** External sends are gated to rung 0 at creation; encountering one at `per_fire_approval=0` means misconfiguration — log `failed` + alert Abhinav, don't send.

## Frequency and cost

Fires once per watcher per scheduled tick (cron-type) or per matched event (event-type, via the poller). Most fires are cheap: one SQLite read, the chain (KB reads free, 1–2 skill invokes, a send), one stats update, one `watcher_fires` insert. Cooldown / memory / empty skips are near-free (read + one insert, no LLM). The per-fire cost was projected and gated at creation (watcher-creator Step 7) — this engine just runs what was approved.
