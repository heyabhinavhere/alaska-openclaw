---
name: watcher-janitor
description: Nightly reconciliation between OpenClaw's cron store and the watchers table. Removes orphan WATCHER crons (no live watcher row), self-heals watchers stuck mid-activation (write-ahead crashes), expires stale unapproved drafts, flags rogue off-pipeline crons (improvised instead of created via watcher-creator), and reports anything it can't auto-fix to Abhinav. Never auto-deletes anything outside the watcher pipeline.
version: 1.2.0
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

### Step 1.5: Snapshot integrity gate — validate BEFORE you reconcile

The single cause of past false alarms (the W-2/W-3 cried-wolf) was reconciling against a **partial `cron.list` read** — e.g. a freshly-restarted gateway that served an incomplete snapshot. Every step below trusts the Step-1 snapshot, so a bad read manufactures false orphans and rogues. Gate it first.

**The self-reference invariant (airtight):** this janitor is *running from* the `Watcher Janitor` cron, so a VALID snapshot MUST contain that **own cron**, and a healthy system shows many infra crons (Meeting Intelligence, Daily Pulse, the event-pollers, reminder-dispatcher, …). If the snapshot is empty, errored, **does NOT contain this janitor's own cron**, or is implausibly sparse (the infra crons you know fire daily are missing), the **READ is unreliable — not the cron store.** A real store wipe would have taken your own cron too, and then this session would not be running; *"only the Janitor in the list"* is a self-evident contradiction, never a real reset.

When the snapshot looks unreliable:
1. **Re-call `cron.list` once** — a transient partial read usually clears on retry.
2. Still unreliable → **ABORT this run.** Do NOT flag orphans (Step 6), do NOT `cron.remove` (Steps 3/7), do NOT `cron.add` (Step 4 — a present cron would look absent and you'd create a duplicate). Reconciling against a bad read can only do harm.
3. Journal one builder-scope line to `/data/workspace/workbench/journal/YYYY-MM-DD.md`: `HH:MM — cron.list snapshot unreliable (N crons, own cron <present|absent>) — skipped reconciliation`. Stay **silent** to the team — a transient blip is not worth a DM.
4. **Escalate to Abhinav ONLY if the snapshot has been unreliable on 3+ consecutive runs.** You run nightly, so the prior runs live in *earlier* day-files — read recent journal lines **across day boundaries** (today + the prior 2 days' `YYYY-MM-DD.md`), not just today's, to count consecutiveness correctly. A persistently unreadable cron store is worth a DM (`cron.list has returned an unreliable snapshot for N runs — the cron store may need attention.` + ⚙); a one-night blip is not.

Proceed to Step 2 only once the snapshot passes this gate.

### Step 2: Classify the crons (this is the safety boundary)

A cron is a **watcher cron** ONLY if its `name` matches `^Watcher W-[0-9]+\b` (watcher-creator names them `Watcher W-N — <desc>`) OR its `payload.message` contains both `watcher-dispatcher` and `watcher_id=W-<digits>`. Extract the `W-N` it references. **Everything else is an INFRASTRUCTURE cron — Meeting Intelligence, Daily Pulse, Risk Radar, the event-pollers, this janitor itself ("Watcher Janitor" does NOT match `Watcher W-\d`) — and is NEVER touched.** When a cron's classification is ambiguous, treat it as infrastructure (leave it).

### Step 3: Remove orphan watcher crons

For each **watcher cron** whose `W-N` has NO row with `status IN ('active','paused')` (the watcher is cancelled/expired/missing, or the cron's id ≠ that row's `openclaw_cron_id`):

- call **`cron.remove`** on that cron id;
- log: `INSERT INTO task_events (task_id?, event_type, actor_slack_id, context)` — use `event_type='comment'`, `actor_slack_id='agent:watcher-janitor'`, `context='janitor: removed orphan watcher cron <id> for W-N (<reason>)'`. (No `task_id` — pass a sentinel if the column requires one, or log to stdout if task_events isn't the right home; the point is an audit trail.)

This is the steady-state cleanup for a deleted/expired watcher whose cron lingered.

### Step 3b: Flag rogue (off-pipeline) crons — defense-in-depth

The rule that's supposed to stop a hand-built recurring cron (a "report/alert" that should have gone through watcher-creator) is a prompt instruction, so it can be skipped. This step catches that leak within 24h.

A recurring cron is **legitimate** (do NOT flag) if it is ANY of:
- a **watcher cron** (Step 2 — `Watcher W-N`, backed by a `watchers` row), OR
- a **skill-runner** infra cron — its `payload.message` references a skill path (`/data/skills/.../SKILL.md`). Most infra crons (Meeting Intelligence, Daily Pulse, Risk Radar, the event-pollers, this janitor, reminder-dispatcher, …) run a skill, so they carry that reference, OR
- a **known inline-prompt infra cron** — legit infra crons that use an inline prompt (no skill reference): **`Daily Cost Report — DM to Abhinav`** and **`Routine Proposal Watch`**. These are real, NOT rogues. (Maintain this short list: if a new infra cron is added with an inline prompt, add its exact name here — or better, give it a `/data/skills/` reference so it passes the rule above.)

**Check EVERY recurring cron, regardless of `payload.kind` or `sessionTarget`** — don't assume `agentTurn`. A `systemEvent` reminder (no `payload.message` to grep for a skill path) or a job on `sessionTarget:"main"` is still in scope. A recurring cron on the **MAIN session** and/or a `systemEvent` / `deleteAfterRun` reminder that isn't one of the legitimate kinds above is a *strong* rogue signal — exactly the "hand-built reminder injected into the main session" pattern SOUL forbids (the sanctioned path is REMINDER_REQUEST → `scheduled_actions`). This is the gap that let the "Nilesh refactor docs review reminder" cron sit unflagged.

**Flag any cron that is none of the legitimate kinds** — an ad-hoc inline-prompt cron, a `systemEvent`/main-session reminder, anything not in the allowlist with no matching watcher row. That's the signature of an improvised cron that should have been a watcher or a `scheduled_action`. **Do NOT remove it.** DM Abhinav: `Found a cron that isn't a watcher, a skill-runner, or a known infra cron: <name> (<id>), schedule <expr>, kind <payload.kind>, session <sessionTarget>. Is it legit infra (I'll add it to my allowlist) or improvised (should be a watcher/scheduled_action)? Your call — I won't touch it either way.`

Flag-only, always — never auto-delete a cron you don't fully understand; the worst case is a harmless question, and a wrongly-removed infra cron is catastrophic. (The allowlist exists because the skill-runner heuristic alone false-flagged `Daily Cost Report` + `Routine Proposal Watch` — both real infra crons with inline prompts.)

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

### Step 6: Orphan active watchers (active cron-type, no cron) — adopt BEFORE you alarm

For each watcher `status='active' AND trigger_type='cron' AND openclaw_cron_id IS NULL` — a "silent dead watcher" (dispatcher anti-pattern #1) Step 4 didn't cover. **Do NOT alarm first.** Check the validated Step-1 snapshot for a matching `Watcher W-N` cron, exactly like Step 4 does:

- **found** → the cron exists; only the DB linkage was lost. **Adopt / re-link it** silently: `UPDATE watchers SET openclaw_cron_id='<that id>' WHERE watcher_id='W-N';` (status stays `active`). No DM — a lost *linkage* is not a lost *cron*.
- **not found** → a genuine orphan. Do NOT auto-recreate (unexpected state deserves eyes). Collect it; after the loop, DM Abhinav the survivors: `Active cron-watcher(s) with no backing cron: W-N. Likely a lost cron — reply 'delete W-N' or ask me to recreate.` + ⚙

(Event watchers are exempt — NULL cron is correct for them.) **Sanity check before sending:** if this run would flag *multiple* watchers as orphaned at once, that is the signature of a bad read, not several simultaneous losses — re-run the Step 1.5 gate and suppress the alarm if the snapshot is suspect. Genuine, independent cron losses do not arrive in batches.

### Step 7: Expired-watcher cron sweep

For each watcher `status='expired' AND openclaw_cron_id IS NOT NULL` whose cron still appears in the snapshot: `cron.remove` it and `UPDATE watchers SET openclaw_cron_id=NULL`. (Belt-and-suspenders with dispatcher Step 2 / management `delete`.)

### Step 8: Summary

Log one audit line (task_events `comment` or stdout): `janitor: removed N orphan crons, healed P stuck activations, expired Q stale drafts, flagged R orphan watchers + T rogue crons, swept S expired crons.` The Abhinav/creator DMs from Steps 3b–6 are the only user-facing output; if nothing needed fixing, stay silent.

## Anti-patterns

1. **Never remove an infrastructure cron.** Only crons matching `^Watcher W-[0-9]+\b` / targeting watcher-dispatcher are in scope (Step 2). A wrongly-removed Meeting Intelligence or Daily Pulse cron is catastrophic — when unsure, leave it and (if truly suspicious) flag it to Abhinav.
2. **Never delete watcher ROWS.** Reconcile via status changes (`cancelled`/`expired`/`active`) and `cron.remove`; `watcher_fires` history stays referentially intact.
3. **Never auto-recreate an unexpected orphan.** Only the known mid-activation case (Step 4) self-heals; an active-with-NULL-cron (Step 6) gets human eyes, never a blind `cron.add`.
3b. **Never auto-delete a flagged rogue cron (Step 3b).** It's a heuristic catch on an off-pipeline cron you may not fully understand — flag it to Abhinav and let him decide. Auto-deleting risks killing a legitimate infra cron that merely lacked a skill reference.
4. **Never duplicate a cron.** In Step 4, always check the cron.list snapshot for an existing `Watcher W-N` before adding a new one.
5. **Validate the snapshot, THEN reconcile — never against assumptions, never against an unvalidated read.** Operate on the actual Step-1 `cron.list` snapshot, not on what you expect — but ONLY after it passes the Step 1.5 integrity gate. A snapshot missing this janitor's own cron or the infra crons is a bad READ, not reality; reconciling against it manufactures false orphans (the W-2/W-3 cried-wolf). The old rule "trust the snapshot" was the bug when the snapshot itself was partial.
6. **Never narrate internals to users.** The only user-facing messages are the targeted Abhinav/creator DMs (shared-toolkit Communication Standards).

## Workshop mode (agent-memory scope + ⚙ DM marker + journal)

You run as a system-health (workshop) session, so:
- **agent-memory writes use `scope='builder'`.** If you store anything via the agent-memory skill — e.g. a false-positive pattern worth remembering so you don't cry wolf about it again — set `scope='builder'` **explicitly** (never the `team` default). Coworker-mode sessions must never see your internals.
- **Mark your Abhinav DMs.** End every DM you send to Abhinav with a final line containing exactly `⚙` (the workshop-thread marker) — so when he replies in that thread, Alaska stays in workshop mode and can read/write your builder notes while digging in.
- **Journal flag-worthy findings.** When a run surfaces something worth a breadcrumb (a rogue cron, a stuck activation you couldn't auto-heal, a *recurring* false positive), append one line to `/data/workspace/workbench/journal/YYYY-MM-DD.md` (create the dir/file if missing): `HH:MM — <what>`. This is how next week's run stops repeating this week's false alarm.

## Frequency and cost

Nightly (~4 AM UTC). One `cron.list` + a handful of SQLite reads + occasional `cron.remove`/`cron.add` + rare DMs. Near-free; pure deterministic reconciliation, no LLM in steady state.
