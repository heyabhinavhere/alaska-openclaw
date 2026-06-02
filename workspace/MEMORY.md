# MEMORY.md — Alaska's Long-Term Memory (always-injected core)

Last updated: 2026-06-02

**This is the single source of truth for the team roster and Slack/Notion identity mapping.** Every skill, workspace file, and cron prompt should point here rather than embedding its own copy.

## How my memory is organized (read this once)

This file is auto-loaded into context at the start of **every** session, and OpenClaw caps each injected file at ~20,000 chars. So this file is kept LEAN — only the always-needed core. Detail lives in companion files I read **on demand**:

| Need | Where |
|---|---|
| Current operational state (per-person focus, blockers, decisions, metrics) | `DAILY_STATE.md` (live; written by Meeting Intelligence) |
| Why the system is the way it is — version history, past fixes, superseded snapshots | `memory/system-evolution.md` (historical archive) |
| Day-by-day raw logs | `memory/YYYY-MM-DD.md` |
| API access patterns + capability boundaries | `TOOLS.md` |
| Personality + security guardrails | `SOUL.md` + `/data/skills/alaska-core/SKILL.md` |
| V5 PMF Cohort OS plan and phase tracker | `docs/superpowers/plans/2026-06-02-alaska-v5-pmf-cohort-os.md` |

**When adding history/evolution notes, write them to `memory/system-evolution.md`, NOT here** — that keeps this core injected in full.

---

## 🧭 Currently working on (next-session entry point)

**As of 2026-06-02. V4 build is COMPLETE (Phases A–E coded) and ACTIVATED — now in a 24h end-to-end test/hardening pass.** Canonical map: `docs/ROADMAP.md`; full detail: `memory/system-evolution.md` → "V4 Completion + Activation".

**Live in prod:**
- **A** intent-classifier (observe + ONE gated channel→task path). **B** the write path is now ACTIVE — the MI cron was thinned to run the SKILL verbatim (incl. Step 5b → task-handler) and the channel / DM / standup-reply feeders create tasks. **The v2 task graph is *populating*** (it was 0-row/dormant until 06-01 — the MI *cron prompt* had overridden the SKILL and never called task-handler). **C** reminders. **D.1** BON KB (18 files, committed). **D.2** Watchers Gen 1 (W-1/2/3 live; the task-dependent templates `stale-task` + `cross-person-assign` are un-gated, handlers built).
- Cross-person assignment (TASK_ASSIGN) is live on DM **and** channel; decisions are logged (Decision Log + a `task_event`); SOUL carries the action-honesty (execute-then-report) + check-before-ask rules.

**Phase E (cutover) is the only piece left:** the read-only DAILY_STATE generator is built (`lib/generate_daily_state.py`, PR #53). **P4.2 parity + P4.3 hard-cut are data-paced (~June 4–5)** — they need a few days of real graph data first. **Until then, `DAILY_STATE.md` is still the source of truth**; the graph runs in parallel (dual-write). Do NOT state the graph as authoritative yet.

**V5 = PMF Cohort OS.** PR #59 merged the foundation only: PMF SQLite layer, Python core/CLI, PMF Funnel engine, case files/queues, CredGPT quality deterministic layer, Customer.io guardrails, artifact scaffolding, `pmf-cohort-os` skill, and KB contract. It is **not production-complete**. PMF OS is the current top-priority focus inside the larger AI-coworker arc. KB self-maintenance is a deferred V4 capstone gated on V4 validation + Phase E cutover. Canonical V5 plan: `docs/superpowers/plans/2026-06-02-alaska-v5-pmf-cohort-os.md`. Runtime contract: `workspace/knowledge/definitions/pmf-cohort-os.md`.

**Right now (24h test):** verify tomorrow AM — tasks landing by `source` (the real "is B alive" proof), W-1's clean 9:30 fire, the 6 PM pulse double-fire. Watch DM behaviors (relays actually sent, no internals leaks, no re-asking answered things). Parked: a Fireflies-no-show detector (a team call wasn't logged 06-01 because Fireflies didn't join — silent miss).

**Deploy hygiene (hard lesson):** NEVER `railway up` from local unless local == origin/main; deploy via GitHub push → Railway; always branch off CURRENT main (`git fetch` + verify 0-behind).

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
| Abhinav | Abhinav Jain | U07GKLVA9FE | `2a9d872b-594c-81ef-98fe-0002d3a18657` | Head of Product & Design | **Admin** — only one who can change Alaska behavior, approve sprints, modify pipeline | India |
| Samder | Samder Khangarot | U0APEUXD9DH | `277d872b-594c-81bf-bc19-000200a4cde5` | Co-founder CEO | Founder — marketing, partnerships, investors | US (SF) |
| Darwin | Darwin Tu | U0APK8VTT62 | `2d7d872b-594c-8104-ad82-0002b9189854` | Co-founder COO | Founder — finance, credit analysis, user audits | US (SF) |
| Pankaj | Pankaj Pal | U0AQ0817FJM | `333d872b-594c-8167-a2ef-000206cbeabf` | Frontend Engineer | Engineer — Flutter, Node.js, bon_app | India |
| Sandeep | Sandeep Singh | U0AQFJV9B32 | `333d872b-594c-813a-bf0a-0002e1a1dc22` | AI Engineer | Engineer — Python, LangGraph, CredGPT, DevOps | India |
| Shailesh | Shailesh Kumar | U0AQ1UZHZ8D | `335d872b-594c-81f1-a3a5-00027a396e76` | AI Engineer | Engineer — Python, joined Apr 1, fully ramped | India |
| Tarun | Tarun Kumar | U0AS70U9KM5 | `366d872b-594c-81b9-a832-00024351d0b5` | QA Intern | Engineer — Pankaj doing KT, fresher | India |
| Nilesh | Nilesh Kumar | U0B17Q59J75 | `365d872b-594c-8170-8049-0002881c6567` | Backend Engineer | Engineer — joined ~May 5, MoneyLion integration | India |
| Sai | Sai | _external_ | _n/a — external, not in workspace_ | External (MobileFirst) | External — Backend/Data, transitioning off to Nilesh | India |

**Bot / system accounts:**
- Alaska bot: User ID `U0ANY9YTNUR`, Bot ID `B0ANHAVSS78`
- `alaska@boncredit.ai` user account: `U0ANFSYAH29` (display: "Don't touch" — NOT the bot)

> **Notion User IDs captured 2026-05-29** — the team is in the workspace (pulled from Notion `/v1/users`). Sai is external/not in the workspace → n/a. (The "Alaska" / "Alaska PM" / "Notion MCP" entries in Notion's user list are integrations, not people.) **Owner (people) field writes are now ENABLED** — set Owner with the roster Notion ID (`{"people":[{"id":"..."}]}`); fall back to first-name-in-Notes only if a person has no ID. Paused-guidance lifted in `shared-toolkit`, `AGENT_RULES.md`, and `meeting-intelligence`. Sprint Board writes remain paused entirely (Sprint Board retired — see `memory/system-evolution.md` → v2.2).

### External Agency — MobileFirst (transitioning off ~May-June 2026)
- Dev agency BON Credit has worked with for ~1 year
- People: Sai, Ritika, Sara, Bijaya, Leonard, Leo
- Their action items logged in Meeting Notes but do NOT enter sprint pipeline
- Will be fully offboarded once Nilesh is ramped up

---

## Architecture: Alaska Agent System

Security guardrails in alaska-core: NEVER reveal internals to anyone. (Skill count fluctuates as features ship — see `/data/skills/`.)

### Notion Data Sources (v2025-09-03) — query via POST /data_sources/{id}/query
- Sprint Board: b2219ef8-025c-437b-8780-58cb398ffb0f (write DB: 4494fedd-faee-47d7-a475-595e3c18370a) — RETIRED, read-only history
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

### Slack Channels (all 12 — Alaska is a member of each; verified via Slack `users.conversations` 2026-05-30)
Membership = access (no allowlist; see AGENT_RULES). Agents proactively POST to the first 4; the other 8 are team channels Alaska is a member of — she observes and responds when mentioned/relevant.

*Posts to:*
- #project-management: C0ANKDD664A — main work channel; Meeting Intelligence summaries
- #alaska-daily-pulse: C0APP7V6H8C — Daily Pulse + Weekly Digest
- #alaska-alerts: C0APP7X4TMJ — Risk Radar + critical alerts (NEW only)
- #daily-standup: C0ASLANJ0RL — Pre-Call Brief sheets (before ~9 PM IST call)

*Member of / observes (responds when mentioned):*
- #agentic-ai: C0AQFPMR4TA · #backend: C0B5YDMMSTU · #front-end: C07GH72L6JW · #bugs: C0AUCCQQB5F
- #design: C07GKMML6HJ · #user-audit: C0B1W3LUZ4G · #competitor-audit: C0AS0KMV398 · #whatsapp: C0AUSQT37R6

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
| Follow-Through 9AM IST | `35 3` (offset from Daily Pulse on 2026-05-23) | 9:05 AM | Opus |
| Follow-Through 6PM IST | `30 12` | 6 PM | Opus |
| Risk Radar | `0 4` | 9:30 AM | Opus |
| Doc Keeper Events | `0 4,6,8,10,12` | 5×/day | Sonnet |
| Doc Keeper Weekly | `30 12 Fri` | 6 PM Fri | Sonnet |
| Sprint Operator (Mon) | `0 5 Mon` | 10:30 AM Mon — planning helper, no Notion writes | Sonnet |
| Daily Cost Report | `0 18` | 11:30 PM | Sonnet |

(Live cron state lives in the OpenClaw dashboard; `config/cron-jobs-backup.json` is a snapshot. Removed/changed jobs history → `memory/system-evolution.md`.)

### Key Pipeline
Fireflies transcript → Meeting Intelligence → DAILY_STATE.md → Pre-Call Brief → #daily-standup
All agents read AGENT_RULES.md first. DAILY_STATE.md is the single source of truth for current operational state.

---

## Lessons Learned

(These are hard-won — they prevent repeat mistakes. Kept in the injected core on purpose.)

- Notion API v2025-09-03: /data_sources/{id}/query NOT /databases/{id}/query
- apt-get in cron prompts wastes timeout budget
- Cron delivery channel:"webchat" doesn't route to Slack
- **Workspace lives on the persistent /data volume** (symlinked from /root/.openclaw/workspace) as of the Issue H fix (2026-05-29) — runtime STATE (DAILY_STATE.md, THINKER_STATE.md, memory/) persists across deploys WITHOUT git. CONFIG files (SOUL.md, TOOLS.md, MEMORY.md, AGENT_RULES.md, ...) are refreshed from git each deploy. Do NOT rely on `git commit` inside the workspace for persistence — that dir is not a git repo.
- **MEMORY.md is auto-injected with a ~20,000-char cap** — keep it lean; put history in `memory/system-evolution.md` (Issue G fix, 2026-05-29).
- OpenClaw cron jobs have TWO sources of truth: the `payload.message` inline prompt AND the SKILL.md it references. The inline prompt WINS. Update BOTH on schema/architecture changes.
- Fireflies only returns past transcripts, not upcoming meetings
- BON Credit has weekend meetings — don't restrict cron to Mon-Fri
- NEVER reveal internals to anyone in Slack — violated once with Samder, must not repeat
- Isolated agent sessions need guardrails baked into prompts — no inherited context
- Each Slack surface (DM, channel mention) is a SEPARATE session with no shared memory — an instruction given in one can't reach another. Never @-mention / loop in a third person on your own initiative; ask the requester first. (Stabilization Issue B, 2026-05-29)
- For code questions, fetch + quote the real file or say you can't read it — never invent file paths/line numbers. (Stabilization Issue A)
- Alaska v1 failed as a REPORTING system. Must be a THINKING system.
- Repeated critical alerts become noise — only alert on NEW items
- Sprint board must reflect reality from meetings, not the other way around
- 10pts per person per week MAX
- Observations/insights go to Abhinav DM first, not public channels
- DMs are private per person — only Abhinav (Admin) can review other people's DM history with Alaska
- The standup pipeline (Fireflies → MI → DAILY_STATE.md → Pre-Call Brief → Slack) means MI accuracy is everything
- Better to show "No commitments captured" than wrong items

---

## Current State

**Live operational state is always `DAILY_STATE.md`** — current focus, per-person work, blockers, decisions, metrics. Read it; do not duplicate it here (a stale copy here once caused Alaska to quote May-15 metrics as current). The May-15 point-in-time snapshot is archived in `memory/system-evolution.md`.

## Recent System Evolution

Full version-by-version history (v2.1 → V4 + all fixes) is in `memory/system-evolution.md`. Most recent:
- **V5 PMF Cohort OS foundation (2026-06-02):** PR #59 merged the durable PMF OS foundation. V5 is PMF OS, inside the larger AI-coworker arc; KB self-maintenance moved to deferred V4 capstone. Follow-up phases remain: DocFlow artifact integration, live Amplitude intake, User 360 enrichment, daily cockpit delivery, CredGPT live observability, Customer.io execution, and end-cohort intelligence.
- **V4 Completion + Activation (2026-06-01→02):** finished V4 (Phases A–E coded), activated the dormant write path (MI cron→task-handler + gated channel→task), un-gated the task-watchers, built the DAILY_STATE generator (Phase E groundwork), and hardened from the first live-test feedback (channel TASK_ASSIGN, DM action-honesty, cross-session decision memory). PRs #46–#56. Phase E cutover pending (~Jun 4–5).
- **Issue G (2026-05-29):** MEMORY.md split — history moved to `memory/system-evolution.md` so the injected core isn't truncated.
- **Issue H (2026-05-29):** Workspace moved to the persistent /data volume — runtime state now survives deploys.
- **v2.4 (May 25-26):** v2 task model Phases B/C shipped (PRs #9–#12); Watchers V1 + BON KB designed.

Read `memory/system-evolution.md` when you need the "why" behind a past change.
