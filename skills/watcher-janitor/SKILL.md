---
name: watcher-janitor
description: Nightly reconciliation between OpenClaw's cron store and the watchers table. Removes orphan WATCHER crons (no live watcher row), self-heals watchers stuck mid-activation (write-ahead crashes), expires stale unapproved drafts, and reports anything it can't auto-fix to Abhinav. Never touches non-watcher (infrastructure) crons.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3]
    emoji: "🧹"
---

# Watcher Janitor

Read `/data/skills/shared-toolkit/SKILL.md` for SQL-escape rules, Slack routing, and Communication Standards. You are the nightly safety net for the watcher system: you reconcile the two sources of truth — OpenClaw's cron store and the `watchers` table — and heal the write-ahead lifecycle's crash edges. The one destructive action you take, `cron.remove`, is **tightly scoped to watcher crons**; an infrastructure cron is never in scope. Abhinav's Slack ID is `U07GKLVA9FE`.

## When you're invoked

A nightly cron (~4 AM UTC) fires: `Run /data/skills/watcher-janitor/SKILL.md procedure.`

## Procedure

### Step 1: Snapshot both sides

- **OpenClaw side:** call the in-session **`cron.list`** tool → every registered cron (`id`, `name`, `payload`).
- **Watchers side:**
  ```bash
  sqlite3 /data/queue/alaska.db \
    "SELECT watcher_id, status, trigger_type, openclaw_cron_id, trigger_config, stagger_seconds, created_at \
     FROM watchers WHERE status IN ('active','paused','pending_cron_create','pending_approval','expired');"
  ```

### Step 2: Classify the crons (this is the safety boundary)

A cron is a **watcher cron** ONLY if its `name` matches `^Watcher W-[0-9]+\b` (watcher-creator names them `Watcher W-N — <desc>`) OR its `payload.message` contains both `watcher-dispatcher` and `watcher_id=W-<digits>`. Extract the `W-N` it references. **Everything else is an INFRASTRUCTURE cron — Meeting Intelligence, Daily Pulse, Risk Radar, the event-pollers, this janitor itself ("Watcher Janitor" does NOT match `Watcher W-\d`) — and is NEVER touched.** When a cron's classification is ambiguous, treat it as infrastructure (leave it).

### Step 3: Remove orphan watcher crons

For each **watcher cron** whose `W-N` has NO row with `status IN ('active','paused')` (the watcher is cancelled/expired/missing, or the cron's id ≠ that row's `openclaw_cron_id`):

- call **`cron.remove`** on that cron id;
- log: `INSERT INTO task_events (task_id?, event_type, actor_slack_id, context)` — use `event_type='comment'`, `actor_slack_id='agent:watcher-janitor'`, `context='janitor: removed orphan watcher cron <id> for W-N (<reason>)'`. (No `task_id` — pass a sentinel if the column requires one, or log to stdout if task_events isn't the right home; the point is an audit trail.)

This is the steady-state cleanup for a deleted/expired watcher whose cron lingered.

### Step 4: Self-heal watchers stuck mid-activation (`pending_cron_create`)

These are write-ahead crashes from watcher-creator Step 8 (row reserved + flipped to `pending_cron_create`, but `cron.add`/the final flip didn't finish). Only act on rows `created_at < datetime('now','-10 minutes')` so you never race an in-flight creation.

For each such **cron-type** watcher:
- **`openclaw_cron_id` IS NOT NULL** → the cron exists and its id was stored; the only lost step was the flip. `UPDATE watchers SET status='active' WHERE watcher_id='W-N';`
- **`openclaw_cron_id` IS NULL** → first check the Step-1 cron.list snapshot for an existing `Watcher W-N` cron:
  - **found** → `cron.add` had actually succeeded; only id-storage was lost. Adopt it: `UPDATE watchers SET openclaw_cron_id='<that id>', status='active'`. (Prevents a duplicate cron.)
  - **not found** → re-run `cron.add` using watcher-creator Step 8c's canonical shape (built from this row's `trigger_config` + `stagger_seconds`), store the returned id, flip `status='active'`. If `cron.add` fails or the trigger is malformed → DM Abhinav: `W-N was stuck mid-activation and I couldn't auto-complete it (<error>). Reply 'delete W-N' to cancel, or fix it.` and leave it `pending_cron_create` for the next run.

For an **event-type** watcher somehow at `pending_cron_create` (shouldn't happen — event watchers go straight to active with no cron): just `UPDATE status='active'`.

This self-healing is the entire reason `pending_cron_create` is a distinct status.

### Step 5: Expire stale unapproved drafts (`pending_approval`)

For each watcher `status='pending_approval' AND created_at < datetime('now','-7 days')` (the creator self-approve or Abhinav's gate never came):

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE watchers SET status='cancelled', decline_reason='expired: no approval within 7 days' \
  WHERE watcher_id='W-N';"
```

DM the creator: `Your watcher draft W-N expired after 7 days with no approval. Recreate it when you're ready.` (Mirrors the routine_proposals 7-day expiry.)

### Step 6: Flag orphan watchers (active cron-type, no cron)

For each watcher `status='active' AND trigger_type='cron' AND openclaw_cron_id IS NULL` — a "silent dead watcher" (dispatcher anti-pattern #1) that Step 4 didn't cover. Do NOT auto-recreate (unexpected state deserves eyes): DM Abhinav the list: `Active cron-watcher(s) with no backing cron: W-N. Likely a lost cron — reply 'delete W-N' or ask me to recreate.` (Event watchers are exempt — NULL cron is correct for them.)

### Step 7: Expired-watcher cron sweep

For each watcher `status='expired' AND openclaw_cron_id IS NOT NULL` whose cron still appears in the snapshot: `cron.remove` it and `UPDATE watchers SET openclaw_cron_id=NULL`. (Belt-and-suspenders with dispatcher Step 2 / management `delete`.)

### Step 8: Summary

Log one audit line (task_events `comment` or stdout): `janitor: removed N orphan crons, healed P stuck activations, expired Q stale drafts, flagged R orphan watchers, swept S expired crons.` The Abhinav/creator DMs from Steps 4–6 are the only user-facing output; if nothing needed fixing, stay silent.

## Anti-patterns

1. **Never remove an infrastructure cron.** Only crons matching `^Watcher W-[0-9]+\b` / targeting watcher-dispatcher are in scope (Step 2). A wrongly-removed Meeting Intelligence or Daily Pulse cron is catastrophic — when unsure, leave it and (if truly suspicious) flag it to Abhinav.
2. **Never delete watcher ROWS.** Reconcile via status changes (`cancelled`/`expired`/`active`) and `cron.remove`; `watcher_fires` history stays referentially intact.
3. **Never auto-recreate an unexpected orphan.** Only the known mid-activation case (Step 4) self-heals; an active-with-NULL-cron (Step 6) gets human eyes, never a blind `cron.add`.
4. **Never duplicate a cron.** In Step 4, always check the cron.list snapshot for an existing `Watcher W-N` before adding a new one.
5. **Never reconcile against assumptions.** Operate on the actual `cron.list` snapshot taken in Step 1, not on what you expect to be there.
6. **Never narrate internals to users.** The only user-facing messages are the targeted Abhinav/creator DMs (shared-toolkit Communication Standards).

## Frequency and cost

Nightly (~4 AM UTC). One `cron.list` + a handful of SQLite reads + occasional `cron.remove`/`cron.add` + rare DMs. Near-free; pure deterministic reconciliation, no LLM in steady state.
