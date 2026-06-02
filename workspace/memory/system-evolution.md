# Alaska System Evolution — Historical Archive (read on-demand)

> **Why this file exists:** This is the detailed history of how Alaska's system evolved
> (version-by-version changes, fixes, and superseded state snapshots). It was split out of
> `MEMORY.md` on 2026-05-29 (Issue G fix) because MEMORY.md is auto-injected into every
> session with a 20,000-char cap — and the growing history was pushing the cap, silently
> truncating the back of MEMORY.md (including the Lessons Learned). This archive is NOT
> auto-injected; **read it on demand** when you need to know *why* something is the way it
> is (e.g. "why was the Sprint Board retired?", "what changed in v2.3?").
>
> MEMORY.md keeps a short "recent changes" summary + a pointer here. New evolution entries
> go HERE, not in MEMORY.md, so the injected core stays lean.

---

## Sprint History

- **Sprint 1 (Mar 24-Apr 6):** ~76% completion. Strong finish.
- **Sprint 2 (Apr 7-13):** 3% completion. CATASTROPHIC. 48+ tasks assigned to Sandeep. Board was fiction.
- **Sprint 3 (Apr 14-20):** NEVER APPROVED. Stayed DRAFT. Team shipped off-board.
- **Sprint 4 (Apr 21-27):** Pipeline fixed Apr 20. Proper planning started.
- **Sprint 5 (Apr 28-May 4):** V2 testing phase began.
- **Sprint 6 (May 5-11):** Goa retreat week. No formal sprint tasks assigned.
- **Sprint 7 (May 12-18):** Post-Goa execution. No tasks on board yet. MoneyLion integration assigned.

---

## State Snapshot — May 15 (ARCHIVED — superseded by DAILY_STATE.md)

> This is a point-in-time snapshot from May 15. It is NOT current state — the live
> operational state is always `DAILY_STATE.md`. Kept here for historical reference only.
> Do not quote these metrics/blockers as current.

### Metrics (May 15)
- **DAU (real users):** ~15/day (May 12-14 avg). Stable/slight uptick from ~12.6 prior week.
- **Plaid card linking:** ~68-70% drop-off. #1 PMF requirement per Samder.
- **Push notifications:** 7.6% delivery (push broken, email working at 94%).
- **Email:** 94% delivery, 48% open rate — strong. Only reliable channel.
- **OTP:** Fixed (May 7). Working.

### V2 Architecture (as described May 15)
- Hub-and-spoke multi-agent system: 7 specialized modules built on 24 DB tables
- Modules: Opportunity Engine, Trigger Monitor, Progress Tracker, Task System, Response Renderer, Budgeting Agent, Plaid Parser — all built ✓
- Original 5 agents (Supervisor, Credit Report, Financial Insights, FAQ, Paydown Plan) still active
- V2 multi-thread memory feature implemented, under testing
- V2 app release: first week of June; V2 chat/AI features live: June 22

### MoneyLion Partnership (May 14)
- Approval received. Integration assigned to Nilesh. Kathleen Lee is BON's POC.
- Sandbox credentials partially received (Channel ID + Zone ID).
- One screen + chat product recommendations. Links redirect via boncredit.ai URLs.
- Competitor exclusion: Cleo, Albert, possibly Origin (max 3).
- (Later simplified to webview-only — Kathleen hosts the UI via static URL. See May 15 evening call.)

### Active Blockers (May 15)
| Blocker | Days Active | Status |
|---------|------------|--------|
| Plaid card linking ~68-70% drop-off | 32+ | UX overhaul planned |
| Twilio A2P campaign registration | 25+ | Temporary direct method working |
| Android build pending Play Store | 3+ | iOS approved, waiting on Play Store |
| MoneyLion sandbox credentials | NEW | Partial. Shailesh sending questions. |
| Push notifications 7.6% delivery | 40+ | iOS fix deployed May 7. Android still broken. |

### Customer.io (31 campaigns, May 15)
- 20 running, 4 stopped, 6 draft, 1 test
- Push: 6,466 sent → 489 delivered (7.6%) — BROKEN
- Email: 6,724 sent → 6,333 delivered (94.2%) → 3,025 opened (48%) — WORKING
- SMS: blocked by Twilio A2P compliance
- Transaction Summary Email is the best-performing campaign

### Key Decisions (as of May 15)
1. MoneyLion integration → Nilesh (May 14)
2. V2 chat/AI live: June 22 (May 14)
3. V2 app release: first week of June (May 14)
4. Competitor exclusion: Cleo, Albert, Origin (May 14)
5. Daily standup shifted to 9 PM IST for PST overlap (May 15)
6. DevOps transition post-V2: Sandeep takes over from MobileFirst (May 7)
7. V2 design scope locked for 2 months (May 7)
8. V2 color scheme: green/white/blue (May 6)
9. Home screen: 3 core offerings — budgeting, credit score, cash advance (May 6)
10. User categorization by credit profile: deep subprime, mid-subprime, near-prime, prime (May 6)

---

## Alaska System Evolution

### V5 Scope Decision + KB Self-Maintenance Reclassification (2026-06-02)

Abhinav clarified the V5 product framing:

- **Alaska V5 = PMF Cohort Operating System.** PMF OS is the headline/current focus of the V5 era and the most important thing to build now for BON's V2 PMF cohort.
- **PMF OS sits inside the bigger horizontal coworker arc.** The long-term Alaska direction is still an AI coworker / "the rest of your startup team." V5 does not mean Alaska is only ever a cohort tool; it means the current V5 teammate job is operating the PMF cohort end to end.
- **KB self-maintenance is not V5 anymore.** The watcher that keeps the BON Knowledge Base updated moves to the V4 track as a deferred V4 capstone.

The KB self-maintenance watcher is gated on both:

1. V4 validates in live end-to-end testing, including Ops-4 tasks-landing proof.
2. Phase E cutover is activated, with SQLite as source of truth and `DAILY_STATE.md` generated/read-only.

Owner note: this is a **V4 track** item because it rides directly on the V4 Watchers + KB substrate. Shape: scheduled watcher scans recent Slack, Meeting Intelligence, DMs, and product/system changes; diffs against `workspace/knowledge/`; drafts proposed KB edits; and asks Abhinav for approval before any write.

This supersedes the older May 30 note that put KB self-maintenance in the V5 bucket.

### V4 Completion + Activation (2026-06-01 → 06-02)

V4 went from "build-incomplete + dormant" to fully built (Phases A–E coded), activated in prod, and hardened against the first wave of live feedback. Map: `docs/ROADMAP.md`. Plan: `docs/superpowers/plans/2026-06-01-alaska-v4-completion.md`.

**The discovery that kicked it off:** the v2 task graph was **0-row in prod**. Phase B was "shipped" (#9) but the Meeting Intelligence *cron prompt* — the thing that runs nightly — overrode the SKILL and never called task-handler (the v2.3 "fat cron prompt wins" disease). Commitments were going to Notion/DAILY_STATE, never the graph. (Ops-4 = verify-B-fires; the "Ops-4" in #42/#43 commit messages is a mislabel — that work is Ops-5.)

**V4 completion (one PR per phase):**
- **P1 (#50) — activate the write path.** Thinned the MI cron to run the SKILL verbatim (incl. Step 5b task-handler + 5c attribution); first folded the cron's SHARED-DEVICE attribution rule into SKILL Step 5c so thinning lost nothing. Activated gated channel→task in the classifier (TASK_CREATE/UPDATE/BLOCKER ≥0.85, owner-resolve-or-skip). Diagnosed the Pre-Call Brief "8 errors" as a **phantom** — the job posts its sheets fine; OpenClaw mis-marks the `{mode:none}` delivery as failed.
- **P2 (#51) — graph-aware reads.** Daily Pulse / Follow-Through / Risk Radar + slack-commands NL queries answer from the graph with a DAILY_STATE fallback; one canonical overdue rule (null `due_at` ≠ overdue); follow-through `nudges`/`snoozes` re-keyed to `task_id`.
- **P3 (#52) — proactive watchers.** Built task-handler `query_stale`, the cross-person assign handshake (`pending_acceptance` + owner-only accept/decline) + follow-through `escalate_unacked_assignments`; un-gated the `stale-task` + `cross-person-assign` templates.
- **P4.1 (#53) — Phase E groundwork.** `lib/generate_daily_state.py` — a read-only generator rendering DAILY_STATE per-person + blockers from the graph (13 tests). **P4.2 parity + P4.3 hard-cut remain (data-paced ~Jun 4–5).** Until cutover, `DAILY_STATE.md` is still source of truth; the graph dual-writes in parallel.

**Live-test hardening (Abhinav's 24h E2E test):**
- **#54** — activated channel `TASK_ASSIGN` (I'd wrongly carved it out vs the agreed "activate channel→task" scope and buried it — corrected; now captures channel requests directed at a teammate). Made the classifier cron *defer to the SKILL* so the intent list can't drift again.
- **#55** — DM action-honesty: a *requested* relay to a named person is **authorized** and a do-it-this-turn commitment (Alaska had claimed "messaged Nilesh" without sending); + a 3-point pre-send self-check (also kills the "Note: I did not schedule a reminder…" internals leak — which L109 already forbade and Alaska violated anyway).
- **#56** — cross-session memory: log decisions (Decision Log + a `task_event`) + check-the-graph-before-asking (Alaska had re-asked an already-answered question across isolated sessions, and asked "is the gift card new?" when it was already in Pankaj's tasks).

**Earlier this window:** watcher timing/delivery/janitor fixes (#46 — first live fires exposed a UTC-conversion bug firing at 4 AM not 9:30, a delivery "Message failed", and a janitor false-flag); MI extraction hardening = **Ops-5** (#42/#43 — speaker attribution + implicit blockers + inferred-task + signal-weighting, validated on a May 25–29 replay); blocker-row dedup (#47).

**Lessons reinforced:** (1) the *cron inline prompt* overrides the SKILL — a "shipped" SKILL means nothing until the live cron runs it (thin the cron / defer to the SKILL). (2) Don't unilaterally narrow an explicit user decision and bury it — flag deviations loudly. (3) Rules already in SOUL.md still get violated in long sessions — forcing-function self-checks beat more prose; if recurrence continues, the lever is structural (shorten/prioritize SOUL). (4) "Solid" is earned by live observation, not asserted at build time.

### v2.5 (2026-05-28 → 05-29) — Stabilization Sweep

Triggered by the Nilesh ↔ Alaska debt-discrepancy conversation (BON user 2756, May 26-27), which exposed several trust/reliability problems. Full register + cross-agent coordination detail: `docs/superpowers/plans/2026-05-27-alaska-v1-v3-stabilization.md`.

**Shipped & live:**
- **A–E — behavioral guardrails (PR #16).** New "Honesty & Restraint" spine in `alaska-core`: *bold in thinking; honest about facts & limits; restrained about actions & disclosure.* (A) Grounded reading — for code questions, fetch + quote the real file or say you can't; never invent file paths/line numbers. (B) Third-person restraint — never @-mention or loop in someone other than the requester unprompted (root cause of the rogue Sandeep ping: each Slack surface is an isolated session with no shared memory). (C) Apologize without exposing internals (no "automated session"). (D) Warm, not a cheerleader; no over-claiming actions you can't verify. (E) Capability honesty — split the "never say I don't have access" overshoot (API hiccup = "unavailable"; genuine boundary = say so plainly) + a "what you can/cannot reach" manifest in TOOLS.md.
- **H — workspace persistence (PR #18).** THE fix for "memory keeps going stale / not updating." `/root/.openclaw/workspace` was on the ephemeral overlay fs and re-seeded from the git image on every deploy → all runtime state reverted (DAILY_STATE kept snapping back to the May-21 stub). Moved to the persistent `/data/workspace` (symlinked from the old path); `lib/sync_workspace.sh` refreshes CONFIG files from git each deploy and preserves STATE files. Verified across two real deploys.
- **G — MEMORY.md truncation (PR #20).** MEMORY.md split into the lean always-injected core + this on-demand archive (see the Issue G detail entry below).
- **Notion User IDs + Owner-field writes (PR #20).** All 8 internal members' Notion IDs captured into the roster; Owner (people) writes re-enabled with a first-name-in-Notes fallback for anyone without an ID.
- **Channel-scope policy (PR #22).** Alaska operates in any Slack channel she's added to (membership = the access control; no allowlist). MEMORY-in-channels guidance reconciled: memory is available everywhere (needed to function); the safeguard is non-disclosure, not withholding.

**Deferred (Abhinav's call):** Issue F — the GitHub token is over-scoped (full `repo` read+WRITE, not read-only); the "READ ONLY" rule is currently enforced only by instructions, not the key itself.

**Meta-lesson:** the two deepest issues (H, G) were NOT in the original report — they surfaced by grounding on the live system (session logs, file mtimes, the truncation log line) rather than trusting assumptions. Fitting, since the whole sweep was about Alaska not making ungrounded claims.

### v2.4 (May 25-26) — v2 Task Model Activation + Watchers Design

Big session. Three PRs merged, two foundational design docs written, one Slack-discipline regression caught and patched.

**Shipped (all merged + live in production):**

- **PR #9 — Phase B (v2 task model — task lifecycle).** Six commits, five skills touched. `task-handler` skill added (match-or-create dedup via Sonnet 4.6 against last-14-days candidates). Meeting Intelligence now writes commitments to SQLite via task-handler (Step 5b). Slack Commands gained DM intent handlers for `TASK_CREATE` / `TASK_UPDATE` / `TASK_BLOCKER`. Pre-Call Brief reads from SQLite tasks (with `additional_owners` filter for secondary owners) and parses thread-reply grammar (`T-N done`, `T-N blocked by X`, `T-N active`, `new:`, `on leave`). shared-toolkit Section 1.7 extended with canonical Task Write Contract patterns + blocker-row INSERT pattern.

  Two-stage review caught: 5 schema mismatches in B2 (non-existent columns, invalid CHECK enum values, ID-gen bug), 4 issues in B3 (source_ref drift, unresolved-owner fallback, SKIP precedence, status-update format), 4 in B4 (source_ref undefined, blocker promise broken, stale-task confirmation, Phase C/D leaks in user-facing replies), 9 in B5 (T-N active contract ambiguity, regex anchors, additional_owners filter missing, etc.). All closed before merge.

  Validation: Alaska ran replay against May 18-24 historical data in a sandbox database (10 meeting tasks, 1 DM task, dedup engaged, visibility computation clean). Blocker path then validated in a separate exercise — all 7 checks pass, including the C2 fix (Step 5 blocker-row creation on initial INSERT, not just status change).

  **Phase B follow-up tracked as Task #44:** dedupe blocker rows on already-blocked tasks (when T-1 is already blocked and someone says "T-1 blocked again", we currently create B-2 in addition to B-1 — non-blocking but spammy in steady state).

- **PR #10 — Bridge fix for Daily Pulse / Follow-Through staleness.** May 25's 6 PM Daily Pulse quoted "Sprint 8 closes today" and "V2 TestFlight scheduled May 22" from a DAILY_STATE.md last compiled May 21 (4 days stale). Two gaps caught: (a) v2.2 FU3 added staleness gate to Daily Pulse 9AM only, not Follow-Through; (b) v2.3 cron-prompt sweep missed two "sprint tasks" mentions in Follow-Through 9AM. Plus (c) DAILY_STATE.md itself was structurally Sprint-framed even after Sprint Board retirement.

  Fix: staleness gate added to both Follow-Through crons (same gate as Daily Pulse 9AM — skip post if state >96h stale). Sprint refs stripped from Follow-Through 9AM. DAILY_STATE.md restructured sprint-neutral ("Current Focus" not "Current Sprint", "BACKLOG:" not "SPRINT TASKS:", header banner explaining sprint-agnostic framing). Alaska deployed cron updates manually in OpenClaw dashboard + refreshed live DAILY_STATE.md after merge.

- **PR #11 — Phase A.3 (classifier prompt tuning).** Renamed from working title "v1.1" to slot cleanly into Phase A→E sequence. Four disambiguation rules added to the classifier prompt:
  1. META-COMMENT — "I think X is being assigned to Y" no longer classified as TASK_ASSIGN
  2. STANDUP CONTEXT — standup messages reporting completed work no longer tagged STATUS_QUERY
  3. SHARING vs ASSIGNING — `@Sandeep here's the doc` no longer tagged TASK_ASSIGN
  4. MULTI-INTENT — `today done X, tomorrow Y` records both via new `secondary_intents` JSON column (migration 0002)

  Validation against May 18-24 replay (Alaska ran the re-replay post-merge): 4/4 targets hit. META-COMMENT FPs dropped from 3 to 0. Standup miscategorization dropped from 15 to 2 (the 2 remaining are genuine queries — correct). SHARING→TASK_ASSIGN false positives dropped from 1-2 to 1 borderline (arguably correct). secondary_intents populated on 52% of TASK_UPDATE rows (exceeded 30-40% target). Phase A.3 fully validated.

- **PR #12 — Phase C (scheduling engine — reminders, RRULE, REMINDER_REQUEST handler).** Six commits, 8 files, +617/-7 lines. First Python in the codebase: `lib/rrule_helper.py` (RRULE parsing via python-dateutil) + `tests/test_rrule_helper.py` (11/11 passing). New `reminder-dispatcher` skill (cron-fired every 15 min, handles 5 action types: remind / surface_task / escalate / recurring_routine / auto_followup). slack-commands REMINDER_REQUEST handler replaces the Phase B deferred stub. New Routine Proposal Approval section (Abhinav-gated team routines).

  Code-quality review caught: PEP 604 syntax broke local-dev on Python 3.9 (fixed with `from __future__ import annotations`), `describe_rrule` rendered "every hourly" / "every unknown" for unusual inputs (tightened), 4 missing test cases (added). Final cross-skill review caught 1 critical: reminder-dispatcher Step 3 contradicted Anti-pattern #2 — "mark fired AFTER side effect" vs "BEFORE". Crash between Slack post and the UPDATE would cause duplicate reminders. Rewrote Step 3 with explicit 3a/3b/3c/3d ordering: deterministic prep → flip-with-lock → side effect → audit. No retry path on side-effect failure — we accept rare "one lost reminder" to prevent common "duplicate spam" failure.

**Designed but NOT YET BUILT — preserved in design docs:**

- **Watchers V1** (`docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md`). The big strategic conversation about turning Alaska from reactive to proactive. A **Watcher** is a unit of repeatable agency with five properties (trigger / action chain / recipient / memory / approval gates). Generalizes Phase C's `scheduled_actions` table — reminders ARE watchers, just with action=send_dm and no memory. Unlocks the wider use cases Abhinav articulated: "every Monday show me DAU + retention", "daily 5 PM send gift card emails to failed Plaid users with per-fire approval", "weekly bar chart of Plaid failure steps", "alert me whenever <580 user signs up". Five worked examples in the spec map directly to user-articulated needs.

  V1 deliberately stays narrow: **user-requested watchers only**, no autonomous "Alaska decides what's worth watching" (that turf stays with Thinker). Pre-built templates (Bug-cluster, Customer-signal, Stale-task, Deploy-impact) ship with V1 for fast activation.

  9 design decisions locked (cost display private to Abhinav; per-watcher cron; reminders ARE watchers; per-fire approval only for high cost variance; no approval for watching teammates in V1; strict memory; user-decided volume caps; build fresh table; Thinker stays autonomous). 7 open questions await Abhinav's answers before implementation.

- **BON Knowledge Base** (`docs/superpowers/specs/2026-05-26-bon-knowledge-base.md`). Abhinav's foundational insight — Alaska needs structured domain knowledge. Right now she asks "what counts as a failed Plaid user?" because the answer isn't anywhere; with KB she reads `knowledge/integrations/plaid.md` and uses the team-canonical definition.

  Structure: `workspace/knowledge/` with `integrations/` (one file per external system), `data-models/` (BON internal domain), `definitions/` (shared vocabulary), `playbooks/` (operational recipes). Per-file format template enforces grep-able predictability. Each KB file has an owner (engineer who works with that system).

  Tier 1 seed list = 13 files to write before Watchers V1 ships. Tier 2 (~10 more files) follows over 2 weeks of operation. Domain-distributed authoring via PR with Abhinav approval. Skills declare which KB files they consume via metadata; watchers store `knowledge_sources` for re-validation when KB updates.

**OpenClaw native scheduling research (May 26 — informed Phase C reflection):**

Dispatched a research subagent on whether OpenClaw has native primitives that overlap with our custom Phase C scheduling layer. Findings: yes, partially. OpenClaw natively supports runtime `cron.add` (we already used this for the classifier cron in Phase A.2), one-shot scheduling via `schedule.kind="at"` with auto-delete-after-fire, per-recipient routing via `delivery.channel="slack"` + `delivery.to=user:U...`, and cancellation via `cron.remove`. So Phase C's `remind` and `surface_task` action types could have been native OpenClaw cron entries — our 15-min polling dispatcher adds up to 14 min latency vs native cron's exact-second firing.

But our custom layer remains necessary for: RRULE recurrences (OpenClaw cron uses standard cron expressions without COUNT/UNTIL/EXDATE), `escalate` and `auto_followup` business logic, routine_proposals approval flow, local audit + cross-task linkage in `task_events`, and cross-system queries ("show Sandeep's pending reminders" requires a local index — OpenClaw cron list has no tag/owner filter).

Cleanest hybrid (for V1): use OpenClaw cron natively for time triggers (one cron per watcher via `cron.add`), keep local table for state/memory/approval/audit. Documented in the Watchers V1 spec.

**Two new tasks added to tracker:** Task #43 (Phase A.3 work — completed), Task #44 (Phase B blocker-dedup follow-up — pending).

### v2.3 — v2.2 Follow-Up (May 25)
- Message overload → reduced to ~5-7/day
- Meeting Intelligence v2: deep transcript comprehension
- Risk Radar: only posts changes

### v2.1 (Apr 20) — Pipeline Fix
- AGENT_RULES.md created — shared rules for all agents
- Thinker: OBSERVE + ACT — updates Sprint Board directly
- Meeting Intelligence writes Sprint Board from transcript data
- Sprint Operator reads meetings first, board is cross-reference
- Identity disambiguation: Samder (CEO) vs Sandeep (AI Eng) in every prompt
- DAILY_STATE.md became the single source of truth

### Standup Hallucination Fix (Apr 29)
- Meeting Intelligence was fabricating commitments from transcript context
- Added strict COMMITMENT EXTRACTION rules, attribution rules, staleness rules, confidence threshold (<80% = don't include)
- Pre-Call Brief: added QUALITY GATE (relevance, non-work filter, staleness, Frankenstein detection)
- Key lesson: MI accuracy is everything — one hallucinated commitment becomes a public standup item

### Customer.io Access Fix (Apr 28)
- Interactive sessions said "I don't have access" despite API keys existing
- Fix: Added data tools to AGENT_RULES.md and TOOLS.md

### Standup Time Change (May 15)
- Daily standup shifted from 9 AM IST → 9 PM IST (3:30 PM UTC / 8:30 AM PST)
- Reason: PST overlap for US founders
- Meeting Intelligence → `*/30 15-20 UTC`, Pre-Call Brief → `0 15 UTC`

### Goa Retreat (May 9-13)
- Team retreat. Standups paused. Pre-Call Brief disabled (re-enabled May 15).

### v2.3 — v2.2 Follow-Up (May 25)

v2.2 updated SKILL.md files but missed the *cron payload.message prompts* — and those are what agents actually execute on each cron firing. Result: skills said "Sprint Board retired, write to DAILY_STATE.md", but Thinker and Sprint Operator's cron prompts still said `PATCH /v1/pages` with the retired DB ID. Plus several silent-failure surfaces.

Caught by Alaska's audit after the May 25 Daily Pulse looked off:

- Follow-Through 6PM had **27 consecutive `Message failed` errors** since launch — silent because nobody saw them.
- Pre-Call Brief had 2 consecutive failures.
- 7 cron jobs had `delivery.channel: webchat` — outputs going to an unreachable surface.
- 6 cron prompts still wrote to or read from the retired Sprint Board.
- Daily Pulse had no staleness gate (would post 4-day-old DAILY_STATE.md as fresh).
- Daily Pulse counted "days since commitment" as overdue instead of "days past due date" — flagged Samder's May 21 Mon/Tue commitment as overdue on Sunday May 25.
- Pre-Call Brief had a contradictory line ("DAILY_STATE.md was retired — DAILY_STATE.md is the only operational state file") from a v2.2 over-replace bug.
- Main-session Slack discipline still leaking — Alaska replied to Sandeep in #agentic-ai with full internal narration despite the v2.2 SOUL.md rewrite.

**What v2.3 fixed:**

- Rewrote cron payload prompts for Meeting Intelligence, Sprint Operator, Doc Keeper Event-Driven, Thinker, Pre-Call Brief, Daily Pulse. All Sprint Board write paths removed. Daily Pulse got staleness gate + correct overdue logic.
- Sprint Operator cron is now a full v2.0 planning helper: reads DAILY_STATE.md + GitHub, DMs Abhinav a proposal, NO Notion writes. Matches the SKILL.md rewrite from v2.2.
- Thinker cron stopped querying Sprint Board entirely. Now observes DAILY_STATE.md vs recent Slack activity and proposes to Abhinav via DM. No Notion writes.
- 7 delivery configs changed from `{mode: none, channel: webchat}` → `{mode: none}`. Agents post to Slack via explicit `action=send,channel=slack,target=...` in their prompts — removing the webchat channel lets OpenClaw stop trying to route to the unreachable surface.
- SOUL.md "Slack Message Discipline" section turned into a hard forbidden-phrase list with self-check rule. Examples + categories: process narration, tool/API references, self-reference as AI. Alaska-core SKILL.md cross-references it.
- daily-pulse/SKILL.md now has a "Critical guard — staleness check" section matching the cron prompt. Plus an "Overdue logic" subsection with a verdict table covering the Mon/Tue case.

**Lesson:** OpenClaw cron jobs have TWO sources of truth for behavior — the `payload.message` inline prompt AND the SKILL.md file the prompt references. The inline prompt wins because that's the active task; the SKILL is background guidance. Future schema/architecture changes need to update BOTH. The cron-jobs-backup.json snapshot in the repo is just documentation — the live state lives in OpenClaw's dashboard.

**Deferred for post-merge observation:**

- Pre-Call Brief 2-error pattern — root cause needs live error logs after these fixes deploy. May resolve as a side effect of the cron prompt cleanup; if not, investigate then.

### v2.2 — Stabilization (May 23)
Big foundation cleanup. Plan: `~/.claude/plans/lazy-bubbling-clarke.md`.

**State files unified:**
- `PROJECT_STATE.md` retired entirely (was stale since Apr 27, talking about Sprint 4/MoneyLion/voice AI). `DAILY_STATE.md` is now the only operational state file.
- `MEETING_INTELLIGENCE_V2.md` replaced with a pointer to the live skill (the design doc was historical).
- `AGENT_RULES.md` fully rewritten — removed stale Sprint 5 references, embedded team roster (now points here), Available Data Tools section (now points to TOOLS.md). Shrunk from ~488 lines to ~180.

**Skills changes:**
- `system-health` skill deleted — content was 100% duplicated by `shared-toolkit` Section 7.
- `daily-standup` skill deleted — replaced by Meeting Intelligence v2 + Pre-Call Brief since May 15.
- `shared-toolkit` got a new "Notion Write Contract" subsection with exact JSON shapes for all field types.
- `whatsapp-send` marked as deprecated in frontmatter — kept as a backup path but not actively maintained. Slack has been rock-solid.

**Sprint Board retired:**
- Notion Sprint Board DB (`4494fedd-faee-47d7-a475-595e3c18370a`) is no longer written by any agent. 15 stale tasks (TSK-253 to TSK-269 from Sprint 6/7) to be archived manually.
- All skills updated to read DAILY_STATE.md per-person sections instead.
- Sprint Operator Monday cron is now a planning *helper* — proposes goals to Abhinav in DM, no Notion writes.
- New task model being designed separately (Phase 2.3 in the plan) — currently leaning Option B (clean new Notion DB called "Active Work" with Alaska-first schema).

**Notion identity:**
- Team being invited to Notion workspace as Guests. Notion User IDs pending capture.
- Owner (people) field writes paused until IDs are in place.
- Status field documented as `select` (not `status`) — earlier confusion fixed in `shared-toolkit`.

**Cron tweaks:**
- Daily Cost Report moved from 11:30 AM IST to 11:30 PM IST so it captures the full day.
- Follow-Through 9 AM IST offset to 9:05 AM IST so it doesn't fire same-second as Daily Pulse.
- 5 disabled jobs removed from `cron-jobs-backup.json` snapshot (still need to delete from OpenClaw dashboard on Railway).

**No action this round:**
- `alaska-railway-backup-2026-05-22/` — pre-Sprint-8-deploy snapshot. Keep through PMF (June 30), delete after.
- `whatsapp-send` skill — leave alone. Slack is the only path that matters now.

### Issue H — Workspace Persistence Fix (May 29) [stabilization]
Workspace moved from the ephemeral `/root/.openclaw/workspace` (re-seeded from the git image every deploy → all runtime state reverted) to the persistent `/data/volume`, with `/root/.openclaw/workspace` symlinked to it. `lib/sync_workspace.sh` refreshes CONFIG files from git each deploy and seeds STATE files only if absent (preserve-by-default). DAILY_STATE.md reconstructed from the May-28 call + Slack as the seed. PR #18. This is the fix behind "memory was going stale / not updating."

### Issue G — MEMORY.md truncation fix (May 29) [stabilization]
MEMORY.md (~30.5K chars) exceeded OpenClaw's 20,000-char workspace-bootstrap injection cap, silently truncating its back third (the whole Lessons Learned section + older evolution history). Fixed by splitting this historical log out to `memory/system-evolution.md` (this file, read on-demand), promoting Lessons Learned into the injected core, and replacing the stale May-15 state snapshot with a pointer to DAILY_STATE.md. MEMORY.md now ~12-14K — fully injected, with headroom that stays lean as history grows here.
