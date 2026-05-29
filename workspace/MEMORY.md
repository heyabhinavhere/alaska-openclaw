# MEMORY.md — Alaska's Long-Term Memory

Last updated: 2026-05-27

**This is the single source of truth for the team roster and Slack/Notion identity mapping.** Every skill, workspace file, and cron prompt should point here rather than embedding its own copy.

---

## 🧭 Currently working on (next-session entry point)

**As of 2026-05-27 (afternoon):**

- **Phases A.1, A.2, A.3, B, C** of the v2 task model — all merged and live in production.
- **Watchers V1** — designed + ALL design questions answered (2026-05-27). NOT YET BUILT. Design with locked decisions (#1-#16) lives in `docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md`.
- **BON Knowledge Base** — designed + authoring decision locked (Abhinav-only). Abhinav is actively seeding the initial KB files in `workspace/knowledge/` as of 2026-05-27.

**All design decisions are locked. Build artifacts ready:**

1. ✅ **Spec:** `docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md` — 16 locked decisions, schema, action chain DSL, conversation flows, templates, worked examples.
2. ✅ **Research:** `docs/superpowers/research/2026-05-27-openclaw-native-primitives.md` — OpenClaw native primitives surveyed; per-watcher cron pattern CONFIRMED; 3 critical gotchas documented (enabled:true, jobId-not-id, HTTP deny list).
3. ✅ **Plan:** `docs/superpowers/plans/2026-05-27-alaska-watchers-v1.md` — full Phase W.0 → W.4 implementation plan, 15 tasks, ready for subagent-driven-development execution.

**NEXT (when Abhinav signs off + KB Tier 1 done):**
- Execute the plan task-by-task per `superpowers:subagent-driven-development`
- Estimated 2-3 weeks of focused work

**Build sequencing locked: Watchers V1 first, then Phase D (as a specific watcher template), then Phase E.** Phase D will be re-expressed as the "unacked-task-assignment escalation" watcher rather than a bespoke workflow.

**Migration locked: dual-write Phase C tables + new watchers table for 2 weeks of clean dual operation, then hard-cut.**

If picking this up fresh in a new session: read the two specs (Watchers V1 + BON KB) + this file's "Alaska System Evolution" entries (v2.4 in particular). All design decisions are locked in the spec — go straight to OpenClaw research → impl plan → build.

---

## Project: BON Credit

Fintech product for US consumers — credit reports, AI analysis (CredGPT), Plaid bank linking, onboarding, campaigns/notifications, gift cards/referrals. Team split: India (engineering) + US/SF (founders). 12.5h timezone gap → mitigated by moving daily standup to 9 PM IST (overlaps PST).

**PMF target:** June 30, 2026. Series A this year. Aggressive marketing Jun-Aug. $1M ARR goal.

---

## Team

### Team Roster (canonical — confirmed)

Identity disambiguation rule: **Sandeep ≠ Samder.** Sandeep = AI engineer (architecture, CredGPT). Samder = CEO (marketing, partnerships). Triple-check before @mentioning either.

| First Name | Full Name | Slack ID | Notion User ID | Role | Authority | Location |
|------------|-----------|----------|----------------|------|-----------|----------|
| Abhinav | Abhinav Jain | U07GKLVA9FE | _TBD (invite pending)_ | Head of Product & Design | **Admin** — only one who can change Alaska behavior, approve sprints, modify pipeline | India |
| Samder | Samder Khangarot | U0APEUXD9DH | _TBD (invite pending)_ | Co-founder CEO | Founder — marketing, partnerships, investors | US (SF) |
| Darwin | Darwin Tu | U0APK8VTT62 | _TBD (invite pending)_ | Co-founder COO | Founder — finance, credit analysis, user audits | US (SF) |
| Pankaj | Pankaj Pal | U0AQ0817FJM | _TBD (invite pending)_ | Frontend Engineer | Engineer — Flutter, Node.js, bon_app | India |
| Sandeep | Sandeep Singh | U0AQFJV9B32 | _TBD (invite pending)_ | AI Engineer | Engineer — Python, LangGraph, CredGPT, DevOps | India |
| Shailesh | Shailesh Kumar | U0AQ1UZHZ8D | _TBD (invite pending)_ | AI Engineer | Engineer — Python, joined Apr 1, fully ramped | India |
| Tarun | Tarun Kumar | U0AS70U9KM5 | _TBD (invite pending)_ | QA Intern | Engineer — Pankaj doing KT, fresher | India |
| Nilesh | Nilesh Kumar | U0B17Q59J75 | _TBD (invite pending)_ | Backend Engineer | Engineer — joined ~May 5, MoneyLine integration | India |
| Sai | Sai | _external_ | _do not invite_ | External (MobileFirst) | External — Backend/Data, transitioning off to Nilesh | India |

**Bot / system accounts:**
- Alaska bot: User ID `U0ANY9YTNUR`, Bot ID `B0ANHAVSS78`
- `alaska@boncredit.ai` user account: `U0ANFSYAH29` (display: "Don't touch" — NOT the bot)

> **Notion User IDs are TBD as of 2026-05-23.** Abhinav is inviting the team to the Notion workspace as part of the stabilization plan (Phase 2.2 of `~/.claude/plans/lazy-bubbling-clarke.md`). Once invites are accepted, capture each Notion user ID and replace the placeholders above. Until then, agents should NOT attempt to write the Owner (people) field — fall back to writing the first name into the Notes/description field. Sprint Board writes are paused entirely (see "Alaska System Evolution" → v2.2 below).

### External Agency — MobileFirst (transitioning off ~May-June 2026)
- Dev agency BON Credit has worked with for ~1 year
- People: Sai, Ritika, Sara, Bijaya, Leonard, Leo
- Their action items logged in Meeting Notes but do NOT enter sprint pipeline
- Will be fully offboarded once Nilesh is ramped up

---

## Architecture: Alaska Agent System (v2.2)

18 skills in /data/skills/ as of 2026-05-23 (down from 20 — removed `system-health` and `daily-standup` during v2.2 stabilization). Security guardrails in alaska-core v2.0: NEVER reveal internals to anyone.

### Notion Data Sources (v2025-09-03) — query via POST /data_sources/{id}/query
- Sprint Board: b2219ef8-025c-437b-8780-58cb398ffb0f (write DB: 4494fedd-faee-47d7-a475-595e3c18370a)
- Proposals: a99d3610-875a-4a08-ac2b-dae1df125523
- Blockers: 33b45697-aa28-42a5-9bc1-78226ab624ff (write DB: 5c7ae380-97c9-42e9-855a-c1d69ee2c51d)
- Meeting Notes: 43987da1-b2d8-4fa5-a2b8-a38ef3a27625 (write DB: ec053f5c-c92a-4997-a8f1-c223b25b3549)
- Decision Log: b8e61ebb-330d-4b5d-b745-1e4b1333c30f (write DB: 4ef87f2b-08d4-47ae-bcd4-e95d80a91017)
- Agent Signals: ead7f865-4bd4-4e19-af96-bff5c73d0758 (write DB: 0fb278fa-8f38-465c-b0ce-de587227b491)
- Team Roster: 3a8f17ff-c30c-4750-9e6e-77a1e135ec9e (write DB: a2ba23a2-85f7-487e-91d9-f6045e9df343)
- Risk Register: c05a0ba1-2543-4cb7-b156-8f57f26a6ff4
- Changelog: 8c2719be-efb1-45d7-a86d-6500e4de6fde (write DB: 97bcd149-1262-4894-94f2-04ed2f5ab077)
- Backlog: dcf4fd4e-f1d2-46b3-84d0-e5466f5025a2
- Daily Scrum: 0565274b-b967-46b3-b9c9-77d00e1ecfeb (write DB: bc0f92c4-8893-40e2-a5c8-f785fec780be)

### Slack Channels
- #project-management: C0ANKDD664A
- #alaska-daily-pulse: C0APP7V6H8C
- #alaska-alerts: C0APP7X4TMJ
- #daily-standup: C0ASLANJ0RL — Pre-call sheets posted here before 9 PM IST call

### GitHub Repos ($GITHUB_TOKEN) — 9 repos, 2 orgs — READ ONLY
App + Backend (Bonhq):
- Bonhq/bon_app — Flutter app (Pankaj, Abhinav)
- Bonhq/bon_webservices — Backend (Sai → Nilesh transition)
- Bonhq/Landingpage — Website

AI + DevOps (Bonlife — all Sandeep):
- Bonlife/BON-CredGPT — AI agent core
- Bonlife/Agentic-Dashboard — AI dashboard
- Bonlife/Agentic-Chat-UI — Chat interface
- Bonlife/BON-Terraform — Infrastructure (Terraform)
- Bonlife/BON-EKS — Kubernetes (EKS)
- Bonlife/BON-langfuse — Observability (Langfuse)

**RED LINE: DO NOT make any changes to any git repo. READ ONLY.**

### Sandeep's AI/DevOps Stack
- **Agent dev:** LangChain + LangGraph (Python)
- **Observability:** Langfuse
- **Deployment:** Kubernetes (AWS EKS) + Terraform + Jenkins (CI) + ArgoCD (CD) + Docker

---

## Cron Jobs (as of v2.2 — 2026-05-23)

### Active (11 jobs)
| Job | Schedule (UTC) | IST | Model |
|-----|---------------|-----|-------|
| Meeting Intelligence | `*/30 15-20` | 8:30 PM–1:30 AM | Opus |
| Pre-Call Brief | `0 15` (weekdays) | 8:30 PM | Sonnet |
| Thinker | `30 3-15` hourly | 9 AM–9 PM | Opus |
| Daily Pulse | `30 3` | 9 AM | Opus |
| Follow-Through 9AM IST | `35 3` (was `30 3` — offset from Daily Pulse on 2026-05-23) | 9:05 AM | Opus |
| Follow-Through 6PM IST | `30 12` | 6 PM | Opus |
| Risk Radar | `0 4` | 9:30 AM | Opus |
| Doc Keeper Events | `0 4,6,8,10,12` | 5×/day | Sonnet |
| Doc Keeper Weekly | `30 12 Fri` | 6 PM Fri | Sonnet |
| Sprint Operator (Mon) | `0 5 Mon` | 10:30 AM Mon — now a *planning helper*, no Notion writes since v2.2 | Sonnet |
| Daily Cost Report | `0 18` (was `0 6` — moved to end-of-day on 2026-05-23) | 11:30 PM | Sonnet |

### Removed in v2.2 (2026-05-23)
- **Daily Standup Phases 1/2/3** — replaced by Meeting Intelligence v2 + Pre-Call Brief. `daily-standup` skill deleted.
- **Follow-Through 1 PM IST** — removed (cadence redundant; 9 AM + 6 PM is sufficient).
- **Onboarding Watcher** — cron-driven polling was wrong shape; future onboarding triggered manually by Abhinav or by Slack `member_joined_channel` event. `onboarding` skill kept.

### Key Pipeline
Fireflies transcript → Meeting Intelligence → DAILY_STATE.md → Pre-Call Brief → #daily-standup
All agents read AGENT_RULES.md first. DAILY_STATE.md is the single source of truth.

---

## Sprint History

- **Sprint 1 (Mar 24-Apr 6):** ~76% completion. Strong finish.
- **Sprint 2 (Apr 7-13):** 3% completion. CATASTROPHIC. 48+ tasks assigned to Sandeep. Board was fiction.
- **Sprint 3 (Apr 14-20):** NEVER APPROVED. Stayed DRAFT. Team shipped off-board.
- **Sprint 4 (Apr 21-27):** Pipeline fixed Apr 20. Proper planning started.
- **Sprint 5 (Apr 28-May 4):** V2 testing phase began.
- **Sprint 6 (May 5-11):** Goa retreat week. No formal sprint tasks assigned.
- **Sprint 7 (May 12-18):** CURRENT. Post-Goa execution. No tasks on board yet. MoneyLine integration assigned.

---

## Current State (as of May 15)

### Metrics
- **DAU (real users):** ~15/day (May 12-14 avg). Stable/slight uptick from ~12.6 prior week.
- **Plaid card linking:** ~68-70% drop-off. #1 PMF requirement per Samder.
- **Push notifications:** 7.6% delivery (push broken, email working at 94%).
- **Email:** 94% delivery, 48% open rate — strong. Only reliable channel.
- **OTP:** Fixed (May 7). Working.

### V2 Architecture
- Hub-and-spoke multi-agent system: 7 specialized modules built on 24 DB tables
- Modules: Opportunity Engine, Trigger Monitor, Progress Tracker, Task System, Response Renderer, Budgeting Agent, Plaid Parser — all built ✓
- Original 5 agents (Supervisor, Credit Report, Financial Insights, FAQ, Paydown Plan) still active
- V2 multi-thread memory feature implemented, under testing
- **V2 app release: first week of June**
- **V2 chat/AI features live: June 22**

### MoneyLine Partnership (NEW — May 14)
- Approval received. Samder had call with MoneyLine.
- Integration assigned to Nilesh. Kathleen Lee is BON's POC.
- Sandbox credentials partially received (Channel ID + Zone ID).
- One screen + chat product recommendations. Links redirect via boncredit.ai URLs.
- Competitor exclusion: Cleo, Albert, possibly Origin (max 3).

### Active Blockers (May 15)
| Blocker | Days Active | Status |
|---------|------------|--------|
| Plaid card linking ~68-70% drop-off | 32+ | UX overhaul planned |
| Twilio A2P campaign registration | 25+ | Temporary direct method working |
| Android build pending Play Store | 3+ | iOS approved, waiting on Play Store |
| MoneyLine sandbox credentials | NEW | Partial. Shailesh sending questions. |
| Push notifications 7.6% delivery | 40+ | iOS fix deployed May 7. Android still broken. |

### Customer.io (31 campaigns)
- 20 running, 4 stopped, 6 draft, 1 test
- Push: 6,466 sent → 489 delivered (7.6%) — BROKEN
- Email: 6,724 sent → 6,333 delivered (94.2%) → 3,025 opened (48%) — WORKING
- SMS: blocked by Twilio A2P compliance
- Transaction Summary Email is the best-performing campaign

### Key Decisions (recent)
1. MoneyLine integration → Nilesh (May 14)
2. V2 chat/AI live: June 22 (May 14)
3. V2 app release: first week of June (May 14)
4. Competitor exclusion: Cleo, Albert, Origin (May 14)
5. Daily standup shifted to 9 PM IST for PST overlap (May 15)
6. DevOps transition post-V2: Sandeep takes over from MobileFirst (May 7)
7. V2 design scope locked for 2 months (May 7)
8. V2 color scheme: green/white/blue (May 6)
9. Home screen: 3 core offerings — budgeting, credit score, cash advance (May 6)
10. User categorization by credit profile: deep subprime, mid-subprime, near-prime, prime (May 6)

### Upcoming
- **May 15:** Chart implementation meeting (Abhinav + Sandeep + Shailesh). Design handoff to Pankaj starts.
- **May 19:** Sai returns. Communication download call (Abhinav + Samder + Sai). Darwin resumes.
- **May 20:** Abhinav provides MoneyLine screen details.
- **First week of June:** V2 app release target.
- **June 22:** V2 chat/AI features live.
- **June 30:** PMF target.
- **Jun-Aug:** Aggressive marketing push.
- **June/July:** Pricing/monetization follow-up with investor Xian.

---

## Alaska System Evolution

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

---

## Lessons Learned

- Notion API v2025-09-03: /data_sources/{id}/query NOT /databases/{id}/query
- apt-get in cron prompts wastes timeout budget
- Cron delivery channel:"webchat" doesn't route to Slack
- Workspace lives on the persistent /data volume (symlinked from /root/.openclaw/workspace) as of the Issue H fix (2026-05-29) — runtime STATE (DAILY_STATE.md, THINKER_STATE.md, memory/) persists across deploys WITHOUT git. CONFIG files (SOUL.md, TOOLS.md, MEMORY.md, ...) are refreshed from git each deploy. Do NOT rely on `git commit` inside the workspace for persistence — that dir is no longer a git repo.
- Fireflies only returns past transcripts, not upcoming meetings
- BON Credit has weekend meetings — don't restrict cron to Mon-Fri
- NEVER reveal internals to anyone in Slack — violated once with Samder, must not repeat
- Isolated agent sessions need guardrails baked into prompts — no inherited context
- Alaska v1 failed as a REPORTING system. Must be a THINKING system.
- Repeated critical alerts become noise — only alert on NEW items
- Sprint board must reflect reality from meetings, not the other way around
- 10pts per person per week MAX
- Observations/insights go to Abhinav DM first, not public channels
- DMs are private per person — only Abhinav (Admin) can review other people's DM history with Alaska
- The standup pipeline (Fireflies → MI → DAILY_STATE.md → Pre-Call Brief → Slack) means MI accuracy is everything
- Better to show "No commitments captured" than wrong items
