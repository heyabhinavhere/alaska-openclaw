# MEMORY.md — Alaska's Long-Term Memory

Last updated: 2026-05-15

---

## Project: BON Credit

Fintech product for US consumers — credit reports, AI analysis (CredGPT), Plaid bank linking, onboarding, campaigns/notifications, gift cards/referrals. Team split: India (engineering) + US/SF (founders). 12.5h timezone gap → mitigated by moving daily standup to 9 PM IST (overlaps PST).

**PMF target:** June 30, 2026. Series A this year. Aggressive marketing Jun-Aug. $1M ARR goal.

---

## Team

### Slack Member IDs (all confirmed)

- Abhinav Jain: U07GKLVA9FE — Head of Product & Design — Admin authority — India
- Samder Khangarot: U0APEUXD9DH — Co-founder CEO — US (SF)
- Darwin Tu: U0APK8VTT62 — Co-founder COO — US (SF)
- Pankaj Pal: U0AQ0817FJM — Frontend Engineer (Flutter, Node.js) — India
- Sandeep Singh: U0AQFJV9B32 — AI Engineer (Python, LangGraph, DevOps) — India
- Shailesh: U0AQ1UZHZ8D — AI Engineer — India — Joined Apr 1, fully ramped
- Tarun: QA Intern — India — Started ~Apr 8. Fresher. Pankaj doing KT. NOT in Slack workspace yet.
- Nilesh Kumar: Backend Engineer — India — Joined ~May 5, onboarding. Day ~9 as of May 15. MoneyLine integration assigned.
- Sai: External (MobileFirst) — Backend/Data Engineer — KT with Nilesh ongoing
- Alaska bot: U0ANY9YTNUR / B0ANHAVSS78
- alaska@boncredit.ai user account: U0ANFSYAH29 (display: "Don't touch" — not the bot)

### External Agency — MobileFirst (transitioning off ~May-June 2026)
- Dev agency BON Credit has worked with for ~1 year
- People: Sai, Ritika, Sara, Bijaya, Leonard, Leo
- Their action items logged in Meeting Notes but do NOT enter sprint pipeline
- Will be fully offboarded once Nilesh is ramped up

---

## Architecture: Alaska Agent System (v2.1)

16 skills in /data/skills/. Security guardrails in alaska-core v2.0: NEVER reveal internals to anyone.

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

## Cron Jobs (as of May 15)

### Active (11 jobs)
| Job | Schedule (UTC) | Model |
|-----|---------------|-------|
| Meeting Intelligence | `*/30 15-20` (after 9 PM IST call) | Opus |
| Pre-Call Brief | `0 15` (8:30 PM IST, before call) | Sonnet |
| Thinker | `30 3-15` hourly | Opus |
| Follow-Through 9AM IST | `30 3` | Opus |
| Follow-Through 6PM IST | `30 12` | Opus |
| Daily Pulse | `30 3` | Opus |
| Risk Radar | `0 4` | Opus |
| Doc Keeper Events | `0 4,6,8,10,12` | Sonnet |
| Doc Keeper Weekly | `30 12 Fri` | Sonnet |
| Sprint Operator | `0 5 Mon` | Sonnet |
| Daily Cost Report | `0 6` | Sonnet |

### Disabled (5 jobs)
- Standup Phases 1-3 (replaced by Pre-Call Brief + Meeting Intelligence)
- Follow-Through 1PM (timed out)
- Onboarding Watcher

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
