# MEMORY.md — Alaska's Long-Term Memory

Last updated: 2026-05-23

**This is the single source of truth for the team roster and Slack/Notion identity mapping.** Every skill, workspace file, and cron prompt should point here rather than embedding its own copy.

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
| Shailesh | Shailesh | U0AQ1UZHZ8D | _TBD (invite pending)_ | AI Engineer | Engineer — Python, joined Apr 1, fully ramped | India |
| Tarun | Tarun | _not in Slack_ | _TBD (invite pending)_ | QA Intern | Engineer — Pankaj doing KT, fresher | India |
| Nilesh | Nilesh Kumar | _TBD_ | _TBD (invite pending)_ | Backend Engineer | Engineer — joined ~May 5, MoneyLine integration | India |
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

### v2.0 (Apr 13) — First Reset
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
- Gateway restart wipes uncommitted workspace files — ALWAYS git commit immediately
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
