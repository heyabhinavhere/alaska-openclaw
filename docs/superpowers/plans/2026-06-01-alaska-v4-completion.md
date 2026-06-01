# Alaska V4 Completion — Implementation Plan

> **For agentic workers:** use **superpowers:subagent-driven-development** to execute task-by-task. **Each Phase = one PR + STOP for Abhinav's review/merge/deploy before the next.** Never auto-merge.

**Goal:** Complete Alaska V4 — activate the dormant task graph, make Alaska graph-aware and proactive, and flip the source of truth to the graph — so Alaska is at full capability for the **June 10 BON V2 cohort launch**.

**Deadline:** V4 complete by **June 5** (5-day hardening buffer before June 10).

**Architecture:** `task-handler` is the **sole writer** to the SQLite task graph (`/data/queue/alaska.db`). Feeders (Meeting Intelligence, Slack DM, standup replies, channels) send it a structured intent. Readers (Daily Pulse, Follow-Through, Risk Radar, slack-commands) become graph-aware. Watchers act on task state. Phase E flips DAILY_STATE.md from MI-authored to generated-from-graph (per-person + blockers sections).

**Tech/verification:** prompt-driven SKILL.md + cron inline prompts + SQLite + a few `lib/` python helpers. **Live crons are edited in the OpenClaw dashboard, NOT the repo** (`config/cron-jobs-backup.json` is a non-loaded snapshot) → cron changes are **ops handoffs to Alaska/Abhinav** (+ update the snapshot for docs). Verification = SQL against the DB + observed Slack behavior; only `lib/` has unit tests.

## Critical context (research, 2026-06-01)
- Task graph is EMPTY in prod because cron inline prompts **override** SKILL.md and never call task-handler (the v2.3 "fat cron prompt wins" disease).
- MI SKILL self-contained EXCEPT the "SHARED DEVICE RULE" attribution heuristic (cron-prompt-only) → fold into Step 5c before thinning the cron.
- intent-classifier: working ≥0.7 action route for DMs; channel mode hard-barred observe-only in BOTH the SKILL ("Channel/batch mode", ~L128–131) and the cron's "PHASE A: OBSERVATION ONLY" block. `intent_inbox.confidence` (REAL) exists.
- `query_stale` (task-handler) + `escalate_unacked_assignments` (follow-through) are referenced by watcher templates but **unimplemented**. Cross-person assign (TASK_ASSIGN) is rejected today (slack-commands ~L357–361).
- No DAILY_STATE generator exists; MI dual-writes already (Step 4 prose + Step 5b graph).
- task-handler contract: `extraction, owner_slack_id, creator_slack_id, source, source_ref, is_status_update` (+ optional `explicit_task_id, assigner_slack_id, due_at_iso, priority, effort, category, additional_owners`) → returns `{task_id, action, status, dedup_decision}`. SQL patterns in shared-toolkit §1.7.
- Readers read DAILY_STATE.md prose today (zero graph queries). §1.7 has "active tasks for person" + "done last N hours" ready to drop in.

---

## Phase P1 — Activate the write path (THE GATE)  → PR + deploy

After P1 the graph starts filling from meetings, DMs, standup replies, and gated channels.

### P1.1 — Fold the attribution heuristic into MI SKILL (make it thin-cron-safe)
- **Files:** `skills/meeting-intelligence/SKILL.md`
- Move the cron prompt's "SHARED DEVICE RULE" speaker-attribution heuristic into **Step 5c** so the SKILL is the complete source of behavior. Confirm Step 5b (task-handler per commitment) + Step 5c are complete/standalone.
- **Verify:** grep SKILL for the shared-device heuristic; Step 5b inputs match the task-handler contract (`source='meeting'`, `creator_slack_id='agent:meeting-intelligence'`, `source_ref='<transcript_id>+<sentence_index>'`).

### P1.2 — Thin the MI cron prompt (ops + snapshot)
- **Files:** `config/cron-jobs-backup.json` (snapshot/docs) + **HANDOFF: Alaska updates the LIVE cron** (`Meeting Intelligence Pipeline`, `*/30 15-20 UTC`) via cron.remove+cron.add.
- New prompt: *"Run /data/skills/meeting-intelligence/SKILL.md procedure exactly — all steps 1→8, for unprocessed Fireflies meetings. Do NOT skip Step 5b (task-handler) or Step 5c."* Delivery `{mode:none}` (drop any `channel` key — #46 bug class).
- **Verify (post-deploy):** after next nightly run, `SELECT source,COUNT(*),MAX(created_at) FROM tasks WHERE source='meeting'` > 0; `task_events` has `created`.

### P1.3 — Activate gated channel→task in intent-classifier
- **Files:** `skills/intent-classifier/SKILL.md` ("Channel/batch mode") + the batch cron prompt (snapshot + **HANDOFF** live).
- After the `classifier_audit` write, for rows where `intent ∈ {TASK_CREATE,TASK_UPDATE,TASK_ASSIGN,TASK_BLOCKER}` AND `confidence ≥ 0.85` (higher than the 0.7 DM bar — channels are noisier) → invoke task-handler: `source='slack_channel'`, `source_ref='slack:channel:<channel_id>:<message_ts>'`, `is_status_update=(intent==TASK_UPDATE)`. TASK_ASSIGN cross-person reassignment stays gated until P3. Lift the cron's "PHASE A: OBSERVATION ONLY" bar for this gated call only.
- **Verify:** channel-sourced tasks appear post-deploy; task-handler dedup prevents doubles vs MI's Step 5b for the same standup utterance.

### P1.4 — Diagnose + fix Pre-Call Brief cron (broken since May 28, 8 consecutive errors)
- **HANDOFF: Alaska pulls the real error** for `Pre-Call Brief — Fireflies Check` (lastRunStatus/run history). Likely a bad channel/recipient ID, the all-items-filtered empty body, or the DAILY_STATE-driven cron vs SQLite-SKILL divergence.
- Fix from the actual error (align cron to the SKILL's SQLite path / fix the ID / delivery). **Files:** `skills/pre-call-brief/SKILL.md` and/or cron.
- **Verify:** cron runs clean (consecutiveErrors→0); standup sheet posts.

### P1.5 — Verify DM write path end-to-end
- **HANDOFF:** DM Alaska "create task: V4 wiring test" → expect a `slack_dm` task + "Tracking as T-N" reply.
- **Verify:** `SELECT * FROM tasks WHERE source='slack_dm'` shows the row.

**P1 PR** = code (P1.1, P1.3 SKILL, snapshot). Ops handoffs (live crons, P1.4 diagnosis, P1.5 test) after merge+deploy. **STOP for review.**

---

## Phase P2 — Graph-aware capabilities  → PR + review

The readers + Alaska's answers come from the graph, with DAILY_STATE fallback during the fill period.

### P2.1 — slack-commands STATUS_QUERY / My Tasks / Status Check → graph (NL queries)
- **Files:** `skills/slack-commands/SKILL.md` (Status Check ~L17–32, My Tasks ~L83–97; STATUS_QUERY currently falls through, ~L351–353).
- Swap DAILY_STATE-prose reads for §1.7 queries (active per person; overdue = `status!='done' AND due_at<now`; blocked from `blockers`). Fallback to DAILY_STATE if 0 rows. Delivers "what's Sandeep on / what's blocked / what's overdue".

### P2.2 — Daily Pulse → graph-aware (Step 1a, ~L51–63; overdue ~L110–124)
- **Files:** `skills/daily-pulse/SKILL.md`
- Shipped=`done_at>-24h`; In Progress=`active`; Overdue=`status!='done' AND due_at<now` (`due_at IS NULL`→not overdue, keep the awaiting-update distinction); Blocked=`blockers active`. Keep GitHub/Amplitude. Parallel-run + DAILY_STATE fallback while the graph fills.

### P2.3 — Follow-Through → graph-aware + re-key nudges/snoozes to task_id
- **Files:** `skills/follow-through/SKILL.md`
- Step 1 → §1.7 active-tasks/person. Tiers off `due_at` + `task_events` recency. **Re-key `nudges`/`snoozes` from `task_name` → `task_id`** (FK to tasks). Reply "done" routes through task-handler (TASK_UPDATE), never direct write.

### P2.4 — Risk Radar → graph-aware (5 dimensions)
- **Files:** `skills/risk-radar/SKILL.md`
- Overdue/critical-path from queries; dependencies from `parent_task_id` + `blockers.blocking_task_ids`; capacity from `GROUP BY owner_slack_id` + `effort` rollup. Risk Register "Related Tasks" by `task_id` (per the existing line-116 note). Preserve "only post when changed" + `risk_scores` history.

**P2 PR. STOP for review.**

---

## Phase P3 — Proactive watchers on tasks (#49)  → PR + review

### P3.1 — Implement `query_stale` in task-handler
- **Files:** `skills/task-handler/SKILL.md`
- New action: given `owner_slack_id` + `days_stale`, return active tasks with `updated_at < now-Nd` and no recent `task_events`. Returns a digest the `stale-task` watcher formats.

### P3.2 — Activate cross-person assign (Phase-D path) in slack-commands
- **Files:** `skills/slack-commands/SKILL.md` (TASK_ASSIGN currently rejected ~L357–361)
- TASK_ASSIGN → task with `owner=assignee`, `assigner_slack_id=requester`, `status='pending_acceptance'`; one-line confirm to the assignee. (These rows are what the cross-person watcher escalates.)

### P3.3 — Implement `escalate_unacked_assignments` in follow-through
- **Files:** `skills/follow-through/SKILL.md`
- New action: tasks `status='pending_acceptance'` where `assigner_slack_id != owner_slack_id`, bucketed by age (tiers 2/24/48h) → digest. Invoked by the `cross-person-task-assign` watcher.

### P3.4 — Un-gate the two watcher templates
- **Files:** `skills/watcher-creator/templates/stale-task.json`, `cross-person-task-assign.json`
- Remove/relax the `gated` flag now that handlers exist + tasks flow. **HANDOFF:** Alaska creates the watcher instances (or on request).
- **Verify:** stale-task returns real stale tasks; cross-person escalation fires on an unacked `pending_acceptance` task.

**P3 PR. STOP for review.**

---

## Phase P4 — Phase E cutover (source-of-truth flip)  → PR + review

### P4.1 — Build the DAILY_STATE generator (read-only)
- **Files:** `lib/generate_daily_state.py` (new) + `tests/test_generate_daily_state.py`
- Render `## Per Person` (group tasks by owner: done-recent→DONE RECENTLY, active→NOW/LAST COMMITTED, blocked→BLOCKED) + `## Active Blockers` table from the graph. **Preserve the `# Last compiled:` header exactly** (readers parse it for staleness). Leave Current Focus / Active Decisions / Metrics MI-authored (no clean graph source) — generator **splices** its two sections, never clobbers the rest. **Read-only** against the graph. Real Python → TDD.

### P4.2 — Prove dual-write parity (observation, June 2–4)
- MI already dual-writes. **HANDOFF:** Alaska runs the generator vs MI's authored per-person/blockers and reports diffs.
- **Verify:** generator output ≈ MI-authored sections (diffs explained/acceptable).

### P4.3 — Cut over
- **Files:** `skills/meeting-intelligence/SKILL.md` (Step 4) + a generator cron (post-MI) + `docs/alaska-operating-model.md` §2.
- MI stops hand-writing per-person/blockers; generator renders them from the graph post-MI; MI still authors Current Focus/Decisions/Metrics. Readers already graph-aware (P2). Update operating-model §2: **SQLite is now the source of truth.**
- **Verify:** DAILY_STATE per-person matches the graph; a task change reflects in the next generated file; readers unaffected.

**P4 PR.** Cutover (P4.3) happens once P4.2 parity is clean (~June 4–5).

---

## Sequence & dependencies
P1 (gate, today) → graph fills June 1–4. P2 + P3 build after P1 (turn on with fallback). P4.1 anytime; P4.2 needs 2–3 days of P1 data; P4.3 cutover ~June 4–5 after parity.

## Out of scope
#48 OpenClaw upgrade (post-launch). Self-Improvement Loop (separate executor track).
