# DAILY_STATE.md — Single Source of Truth
# Written by Meeting Intelligence. Read by ALL agents before acting.
# Last compiled: 2026-05-21 16:30 UTC (Meeting Intelligence — Team call May 21 9 PM IST)

---

## Current Sprint
- **Sprint:** 8 (May 19 – May 25) — Sprint 7 ended May 18.
- **Status:** Day 3 (Thursday IST). V2 DEV IS LIVE — testing starts. TestFlight build going up tomorrow for 10-user validation. Sandeep shipped 31 fixes across 9 PRs earlier today. Shailesh doing card matching engine RCA/fix. MoneyLine UNBLOCKED (Kathleen responded).
- **Cadence:** Weekly (Monday–Sunday)
- **Capacity:** 10pts per person per week MAX
- **Note:** MoneyLine UNBLOCKED as of tonight. V2 on dev, TestFlight tomorrow. Simplified budgeting approach decided (minimum obligations first). Product recommendation engine identified as V3. Single mom marketing strategy crystallized — 100-day focus.

## This Week's Goals (updated from May 21 team call)
1. **V2 testing & validation** — V2 live on dev. TestFlight build tomorrow. 10-user QA (5 from Darwin's audits + 5 from Sandeep). Tarun leads QA, Darwin/Samder test from business angle.
2. **New API development** — Sandeep starts building APIs for new design screens. Internal morning tech calls this week. Parallel with V2 bug fixes.
3. **Card matching engine fix** — Shailesh found root causes. Last-4-digit priority implemented. Plaid event data integration for better AI responses planned.
4. **Simplified budgeting** — New approach: show minimum monthly obligations from tradelines FIRST, then offer detailed budgeting. EveryDollar-style categories.
5. **Abhinav: logic for progress + task screen** — Delivering to Sandeep and Shailesh tomorrow.
6. **MoneyLine integration UI** — 3 CTAs (cash advance, loans, credit cards) → redirect to MoneyLine webview. Minimal approach.
7. **Dave Ramsey transcripts** — 165 episodes downloaded. PII cleanup needed before use.
8. **Single mom marketing** — 100-day focus. YouTube shorts, influencer collabs, referral incentives, PR strategy.
9. **Ventures Lab Q1 metrics** — Darwin organizing and sharing with team.

---

## Per Person

### Abhinav (Head of Product & Design)
- **NOW:** Completed all V2 designs. KT delivered to Pankaj, Sandeep, Shailesh. Working on progress + task screen logic.
- **LAST COMMITTED (May 21 team call):** Give logic for progress and task screen to Sandeep and Shailesh tomorrow. Have a call with Darwin about V3 plans (product recommendation engine).
- **DONE RECENTLY:** All V2 designs completed ✓ (May 21), Full V2 design KT to Pankaj ✓ (May 21), AI team architecture discussion with Sandeep + Shailesh ✓ (May 21)
- **BLOCKED:** Twilio A2P compliance (30+ days).
- **SPRINT TASKS:** None on board (product/design work)

### Sandeep (AI Engineer)
- **NOW:** V2 deployed on dev (live). Shipped 31 fixes across 9 PRs today. Reviewed new designs with Abhinav. Card matching algorithm improved (last-4-digit priority).
- **LAST COMMITTED (May 21 team call):** Launch V2 on TestFlight tomorrow. Start building new APIs for new design screens (morning tech calls this week). Fix V2 bugs from QA in parallel. Integrate Plaid event data for better AI responses on card linking. Collaborate on budgeting implementation (EveryDollar model + minimum obligations first).
- **DONE RECENTLY:** V2 deployed on dev ✓ (May 21), 31 fixes across 9 PRs shipped ✓ (May 21), Card matching algorithm reversed to last-4-digit priority ✓ (May 21), Location feature deployed on dev ✓ (May 21), Dave Ramsey 100 episodes downloaded ✓ (May 21)
- **BLOCKED:** Waiting on Pankaj for Proactive Briefing JSON schema + Budgeting Agent schema.
- **SPRINT TASKS:** None assigned yet

### Pankaj (Frontend Engineer)
- **NOW:** Shipped 4 UI components today. Shared proactive briefing payload to Sandeep.
- **LAST COMMITTED (May 21 team call):** Upload V2 build for internal testing/TestFlight tomorrow.
- **DONE RECENTLY:** Opportunities UI in chat ✓ (May 21), Task UI in chat ✓ (May 21), Chart bug fixes ✓ (May 21), Active alerts UI in chat ✓ (May 21), Proactive briefing payload shared to Sandeep ✓ (May 21)
- **BLOCKED:** Android build pending Play Store review (9+ days).
- **SPRINT TASKS:** None assigned yet

### Samder (Co-founder CEO)
- **NOW:** Marketing strategy crystallized — single mom focus for 100 days. Dave Ramsey transcripts downloaded (165 episodes). Kathleen MoneyLine links forwarded.
- **LAST COMMITTED (May 21 team call):** Work over the weekend on single mom-specific data points and budgeting insights. Share findings Monday/Tuesday. Continue Dave Ramsey data PII cleanup.
- **DONE RECENTLY:** 165 Dave Ramsey transcripts downloaded ✓ (May 21), Kathleen MoneyLine links forwarded ✓ (May 21), Single mom marketing strategy articulated ✓ (May 21), Single mom cohort research completed ✓, 16 YouTube shorts scripted ✓
- **BLOCKED:** Nothing currently (was traveling, back now).
- **SPRINT TASKS:** None assigned yet

### Shailesh (AI Engineer)
- **NOW:** Deep RCA on card matching engine bugs. Code review found 4 issues. Fix PR in progress. Will validate V2 from tech side.
- **LAST COMMITTED (May 21 standup — did not speak directly in team call):** Card matching engine fix PR — strict last-4 digit priority, closed tradelines excluded, name normalization fix. Investigating data sync pipeline for user 2891.
- **DONE RECENTLY:** RCA on users 2821, 2891, 2869 ✓ (May 21), Matching engine code review: 4 bugs found ✓ (May 21)
- **BLOCKED:** Laptop overheating (Docker + ventilation). Not work-blocking.
- **SPRINT TASKS:** None assigned yet
- **Note:** (did not speak directly in team call — Abhinav mentioned discussion with "Jalish"/Shailesh earlier + Shailesh to validate V2 from tech side)

### Darwin (Co-founder COO)
- **NOW:** User audits continuing. Shared detailed user scenarios (2854, 2891, 2894) showing budgeting and card linking pain points. Pushed for simplified budgeting and product recommendation engine.
- **LAST COMMITTED (May 21 team call):** Double-check users 2891 and 2894 for card linking issues. Organize Q1 operational metrics for Ventures Lab and share with team. Have a call with Abhinav about V3 plans.
- **DONE RECENTLY:** User audits on 2854, 2891, 2894 presented in team call ✓ (May 21), Simplified budgeting approach proposed and approved ✓ (May 21), Product recommendation engine need identified ✓ (May 21)
- **BLOCKED:** Nothing currently.
- **SPRINT TASKS:** None assigned yet

### Tarun (QA Intern)
- **NOW:** V2 charts testing completed. Bug doc shared with Sandeep/Pankaj. Next: V2 TestFlight QA on 10 users.
- **LAST COMMITTED (May 21 standup — did not speak in team call):** Retest V2 charts after bug fixes. Explore Appium automation.
- **DONE RECENTLY:** V2 charts testing completed ✓ (May 21), Bug document shared ✓ (May 21)
- **BLOCKED:** Profile "string string String" bug (needs Sai to check backend).
- **SPRINT TASKS:** None assigned yet
- **Note:** (did not speak in tonight's team call — assigned V2 TestFlight QA on 10 users by Sandeep)

### Nilesh Kumar (Backend Engineer — ~DAY 17)
- **NOW:** Shipped user location feature (PR #120 merged & deployed to dev). Investigating rewardscc for credit card images.
- **LAST COMMITTED (May 21 standup — did not speak in team call):** Logos API — rewardscc platform. Twilio SMS + WhatsApp setup (pending Abhinav sync).
- **DONE RECENTLY:** User location feature PR #120 merged & deployed to dev ✓ (May 21), CI/CD + Logs KT with Harish ✓, Spinwheel KT with Sai ✓
- **BLOCKED:** Twilio WhatsApp setup pending Abhinav sync.
- **SPRINT TASKS:** None (Logos API + Twilio WhatsApp + MoneyLine)
- **Note:** (did not speak in tonight's team call — MoneyLine blocker resolved by Kathleen)

### Sai (External — MobileFirst)
- **NOW:** Customer.io push fix deployed. KT with Nilesh completed.
- **LAST COMMITTED (May 20):** KT sessions completed.
- **DONE RECENTLY:** Customer.io push fix deployed ✓, Spinwheel KT with Nilesh ✓
- **BLOCKED:** Nothing currently.

---

## Active Decisions (last 2 weeks)
1. **Simplified budgeting: minimum obligations first** — Show total minimum monthly payments from tradelines BEFORE detailed budget. "How much do I need to pay?" answered immediately. Detailed budget offered as next step. Increases card linking probability. (May 21 team call — NEW)
2. **MoneyLine UI: 3 CTAs only** — Cash advance, loans, credit cards → redirect to MoneyLine webview. No full product listing (we can't match specific cards). Pankaj's suggestion, team agreed. (May 21 team call — NEW)
3. **Product recommendation engine = V3** — Darwin identified need: classify users by credit profile → recommend products via MoneyLine. Under 500 → cash advance. Above 700 → card upgrades. Abhinav confirmed: V3 scope, not current sprint. (May 21 team call — NEW)
4. **V2 TestFlight validation: 10 users** — 5 from Darwin's audits + 5 from Sandeep. Tarun leads QA. Darwin/Samder test business angle. (May 21 team call — NEW)
5. **Plaid event data for AI responses** — Replace hardcoded "card not showing up" with dynamic responses using real Plaid event data from Amplitude. (May 21 team call — NEW)
6. **Customer.io push is a PERMISSION problem, not backend** — Only ~10% users have notification permission. Needs UX strategy. (May 21 — REFRAMED)
7. **Single mom marketing: 100-day focus** — YouTube shorts, influencer collabs, referral incentives, PR strategy. Veterans segment comes after. (May 21 team call — NEW)
8. **Card matching engine: strict last-4 priority** — Shailesh rebuilding: 4-digit + credit-card subtype first, name normalization second, exclude closed tradelines. (May 21)
9. **24-table data migration DEFERRED** — Stabilize V2 bugs first, then migrate prod. (May 21)
10. **WhatsApp: Twilio primary, Plivo backup** — Nilesh setting up, pending Abhinav sync. (May 20)

## Active Blockers
| Blocker | Days Active | Owner | Status |
|---------|------------|-------|--------|
| Card matching engine bugs | RECURRING | Shailesh | ROOT CAUSE FOUND. Last-4-digit priority implemented by Sandeep. Shailesh fix PR in progress for full resolution. |
| Data sync pipeline (user 2891) | 1 | Shailesh | tradeline_matrix/financial_profiles empty despite Array data. Investigating. |
| Push notification low delivery (~7.6%) | 6+ (REFRAMED) | Abhinav/UX | Backend fix deployed. ~10% permission opt-in. UX problem. |
| ~~MoneyLine static URL not received~~ | ~~RESOLVED~~ | ~~Nilesh/Samder~~ | ✅ RESOLVED May 21 — Kathleen responded, links forwarded by Samder. |
| Sandeep waiting on Pankaj schemas | 1 | Pankaj → Sandeep | Proactive Briefing JSON + Budgeting Agent schema. |
| Plaid card linking 78-80% drop-off | 38+ | Shailesh | Matching engine fix + simplified budgeting approach will address. |
| Twilio A2P campaign registration | 30+ | Abhinav/Sai | Temporary direct method working. |
| Profile "string string String" bug | 6+ | Sai/Nilesh | Found in testing. Likely backend ID removal. |
| Android build pending Play Store | 9+ | Pankaj | iOS approved. Waiting on Play Store review. |
| Twilio WhatsApp setup | 1 | Nilesh | Pending sync with Abhinav. |
| Dave Ramsey transcripts PII cleanup | NEW | Samder/Sandeep | 165 episodes downloaded. Need PII removal before AI training use. |

## Metrics (Amplitude-verified May 21, 16:30 UTC)
- **DAU (real users):** May 14: 16, May 15: 15, May 16: 14, May 17: 9, May 18: 9, May 19: 16, May 20: 18, May 21: 7 (10 PM IST — day not complete)
- **Sprint 8 so far:** May 19: 16, May 20: 18 (strong), May 21: 7 (still growing).
- **Email delivery:** ~94% delivered, 48% open rate (healthy)
- **Push notification delivery:** ~7.6% — backend fix deployed, low rate is permission opt-in issue
- **Plaid card linking:** 78-80% drop-off. Card matching algorithm improved (last-4-digit priority).

## What Changed May 21 (from 9 PM IST team call)
- *MoneyLine UNBLOCKED:* Kathleen responded. Samder forwarded links. 8+ day blocker resolved.
- *V2 dev is LIVE:* Sandeep confirmed V2 deployed on dev environment. Testing can begin immediately.
- *TestFlight launch TOMORROW:* Pankaj uploading build. 10-user validation (5 Darwin audit users + 5 Sandeep users). Tarun leads QA. Darwin/Samder test business flows.
- *Simplified budgeting approach decided:* Show minimum monthly obligations from tradelines FIRST → then offer detailed budget. Reduces drop-off for complex/low-score users (Darwin's proposal, team agreed).
- *Card matching algorithm improved:* Sandeep reversed priority to last-4-digit matching. Array uses bank names, Plaid uses brand names — name mismatch was root cause. Fix in data sync service.
- *Plaid event data for AI responses:* Replace hardcoded messages with dynamic responses using real Plaid events. Sandeep to implement.
- *Product recommendation engine = V3:* Darwin identified need. Classify users by profile → recommend via MoneyLine. Abhinav confirmed V3 scope.
- *MoneyLine UI: 3 CTAs:* Cash advance, loans, credit cards → redirect to webview. Pankaj's suggestion, team agreed.
- *Location data for budgeting:* Deployed on dev. Current city/state/country from Amplitude events. Used for seasonal/regional budgeting context.
- *Dave Ramsey transcripts: 165 episodes downloaded.* Samder + Sandeep. Need PII cleanup. Training data for financial coaching.
- *Single mom marketing strategy crystallized:* 100-day focus. Shorts, influencers, referrals, PR angle. 5-10M addressable market. Veterans segment next.
- *Ventures Lab Q1 metrics:* Darwin organizing for sharing.

## Upcoming
- **May 22 (Friday IST):** TestFlight build uploaded (Pankaj). V2 10-user QA begins (Tarun + Darwin + Samder). Sandeep starts new API development. Abhinav delivers progress/task screen logic to Sandeep & Shailesh. Abhinav-Darwin V3 discussion.
- **This weekend:** Team tests V2 on TestFlight. Samder works on single mom data/budgeting insights.
- **Monday/Tuesday:** Samder shares single mom marketing findings.
- **This week:** V2 testing + API development + card matching fix pipeline active.
- **First week of June:** V2 app release target (revised).
- **June 22:** V2 chat/AI features live date.
- **PMF target:** June 30. Series A this year. $1M ARR goal.
