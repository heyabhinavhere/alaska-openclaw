# PROJECT_STATE.md — Alaska's Living Understanding
# Updated by Meeting Intelligence after every meeting analysis
# Read by ALL agents before acting
# Last updated: 2026-04-24 (Team call transcript processed)

---

## Current Sprint
- **Sprint:** 4 (Week of Apr 21-27)
- **Cadence:** Weekly (Monday-Sunday)
- **Status:** DRAFT — not yet approved
- **Capacity:** 10pts per person per week MAX

## Strategic Priority (from most recent meetings)
1. **V2 Agent architecture** — Sandeep wiring 24 new tables with V2 agents (opportunity engine, bursting agent, Plaid parser, progress tracker, response renderer, task system, trigger monitor). Architecture V2 target: done by May 8th. Shailesh joining Sandeep on V2 from Monday Apr 28.
2. **Voice AI** — Speech-to-text DONE and demoed live (3 modes: continuous, tap-to-talk, auto-shutoff). Text-to-speech targeting completion today. V1 deployment imminent. Pankaj implementing websocket endpoint. Settings: language, voice tone (accent/gender), read-aloud toggle. Hide provider names from users.
3. **Home screen redesign** — Finalized: simple navbar + chat + task progress + dynamic scenario cards. 6 visual scenarios (credit score update, salary, transactions, payment due, card link, progress). Chat opens expanded with keyboard on tap. One-page dashboard approach.
4. **Twilio A2P compliance crisis** — Campaigns rejected: credit repair/debt reduction content violates US/Canada messaging policy. Plan: delete current campaigns, create new ones for transaction alerts + app updates ONLY. Sara filtering messages. Abhinav contacting Twilio support.
5. **Competitive audit** — BON ranks lowest among 5 apps (with Cleo). App Store/Play Store info outdated (still showing rewards). Samder doing deeper SEO/GEO audit. Product brief WIP covering MoneyLion + budgeting flow.
6. **User audits for PMF** — Darwin targeting 15 audits by Apr 30 (2hrs each, 3-4 done so far). User 2714: AI handled survival mode budget well. Team each to do 1-2 additional. Will analyze with LLM. PMF requires: good agents, user journey, retention scenarios.
7. **MoneyLion integration** — Credit cards + loans (cash advance = personal loan). Web redirect only (no API). Needs Figma docs from Abhinav for compliance. Placement: in chat + dashboard.
8. **Load testing** — 50% failure rate due to continuous requests without delay. Ashwini retesting with delays. 10K users should be able to use site.
9. **Conference insights (Darwin)** — Industry validates AI direction. GEO increasingly important (25-50% users search AI for financial advice). NerdWallet feeling pressure from AI chatbot traffic. Lenders sophisticated, love subprime. Nobody doing serious AI yet. Affiliate marketing still strong. User-designed cards concept (long-term vision).
10. **Goa retreat planning (May 8-13)** — Still on. Darwin traveling Apr 30 to Southeast Asia then meeting team.

## Per-Person Current Focus
- **Sandeep:** Wiring 24 new tables with V2 agents WIP. Voice V1 deployment target today. Showing Sara AI swagger docs. V2 architecture continues (May 8 target).
- **Pankaj:** Socket integration architecture completed. Implementing websocket endpoint for voice (waiting for dev WS from backend). MoneyLion — needs Figma docs for compliance.
- **Shailesh:** Speech-to-text DONE ✓ (demoed live). Text-to-speech today (V1 target: complete today). Starting V2 architecture with Sandeep from Monday Apr 28.
- **Darwin:** Conference DONE ✓. User 2714 audit done — AI quality good. Back Saturday. Target: 15 user audits by Apr 30. Traveling Apr 30 to SE Asia.
- **Samder:** Deep competitive audit DONE ✓ (5 apps — BON at bottom). Marketing audit done. SEO/GEO competitor audit today. Product brief WIP. Weekly product call Friday.
- **Abhinav:** Distribution analysis DONE ✓ (in Amplitude). Voice AI Figma DONE ✓ (shared with team). Home + task screen designs done. TODAY: home screen progress scenarios, MoneyLion flow docs, Twilio campaign restructure, user audit planning.
- **Tarun:** Sai KT ON HOLD (Sai busy). Found + fixed profile upload bug with Pankaj. Testing WIP. Created docs.

## Active Blockers
| Blocker | Days Active | Owner | Status |
|---------|------------|-------|--------|
| ~~Figma designs for Voice AI~~ | RESOLVED | Abhinav/Pankaj | Abhinav completed Voice AI design Apr 24 — Pankaj unblocked |
| *NEW* Twilio A2P compliance — credit repair/debt content violates policy | 0 | Abhinav/Sara | Campaigns rejected. Must delete + recreate for transaction alerts + app updates only |
| *NEW* Swagger API validations empty/generic | 0 | Sara | 9/10 routes accept empty bodies. Sara manually fixing. |
| *NEW* Load testing 50% failure rate | 0 | Ashwini | Continuous requests without delay. Retesting with delays. |
| AppsFlyer API integration | 6+ | Abhinav | API not working — will retry |
| Claude rate limits | 4+ | Pankaj | Needs premium seat, currently standard. 3 premium seats needed. |
| Array vs Spin Wheel data discrepancy | 4+ | Sandeep/Darwin | Different balances + utilization between sources. |
| FB ads poor ROI | 6+ | Samder | $23/download. Relaunching different creative. |
| Unknown user bug | 11+ | Shailesh/Sai | Blocked on Sai — deleted user still in chat DB |
| Twilio A2P SMS | 16+ | Abhinav/Sara | NOW ESCALATED — campaigns rejected for compliance |
| Push notifications 4% delivery | 15+ | Pankaj/Sandeep | No visible progress |
| Card linking 70%+ failure | 29+ | Unassigned | Investigation only |
| Play Store outdated | 5+ | Samder | Old screenshots — audit confirmed it's still bad |

## Recent Decisions (keep last 2 weeks)
- Weekly sprints, weekly releases (Apr 5-6)
- Sandeep 80% architecture / 20% bugs (Apr 7)
- WhatsApp redirect for V1 support (Apr 7)
- V1 APR: hardcode 24% with disclaimer (Apr 7)
- Monthly goals per person, singular PMF focus (Apr 8)
- Card linking is #1 priority (Apr 11)
- Override stuck build with WhatsApp feature (Apr 11)
- Use current T&C/privacy now, update after lawyer (Apr 11)
- Default credit report to open accounts only (Apr 11)
- Remove "other loans" from external report — privacy (Apr 14)
- Remove "confidential" tag from external report (Apr 14)
- Send external reports via DocSend (Apr 14)
- Manual credit reports for 10-12 days before automation (Apr 14)
- External reports sent as human (Darwin), not AI (Apr 14)
- Daily/frequent releases enabled via JSON schema (Apr 14)
- Reorder strategy gates: quick win first, score first second, min interest third, optimal last (Apr 15)
- Target distribution: 60% quick win, 20% score first, 15% min interest, 5% optimal (Apr 15)
- WhatsApp talk-to-us button redirects to Darwin's secondary number (Apr 15)
- Feedback button hidden under menu after this release (Apr 15)
- Bug backlog: all fixed by Friday, clean slate for algorithms (Apr 15)
- Competitive benchmarking spreadsheet — to be built during Goa trip (Apr 15)
- Sandeep to pursue L1 visa via Nicole for June US relocation (Apr 15)
- Review bounty rethinking — original approach scrapped (Apr 16)
- MoneyLion integration is discussion only — after budgeting feature (Apr 16)
- Webinars dropped for B2C — short videos only for April-June (Apr 16)
- WhatsApp welcome message: user name + ID + FICO score (Apr 16)
- Intra-bank transfers excluded from spending calculations (Apr 16)
- App Store reviews via cheap agencies ($1-2), Trustpilot bounty at $5 (Apr 16)
- Transaction summary email: 9AM local time, not 9PM PST (Apr 17)
- Global message caps: max 3 push + 3 email per user per day (Apr 17)
- Merge transaction push notifications into single summary (Apr 17)
- Transaction email redesign: line items by account, money in/out, CTA to app, no tables (Apr 17)
- BON = intelligence company, not infrastructure — from ByteDance/Experian meetings (Apr 17)
- FB ads: $1K test budget, measure cost per initiation not just download (Apr 17)
- Shailesh to work on architecture with Sandeep after bugs done (Apr 17)
- Rejection letter partnership: add BON Credit line in card issuer rejection letters for near-zero CAC lead gen (Apr 18)
- Integrate AppsFlyer for FB ad attribution tracking (Apr 18)
- Target single moms as key audience via non-profit partnerships (Apr 18)
- Update Play Store images/descriptions to match App Store (Apr 18)
- Investigate dashboard data discrepancy: Sandeep 298 vs Amplitude 142 chat users (Apr 18)
- **Interest estimation: 24% APR, 2% monthly on remaining balance — payment goes to interest first then principal (Apr 20)**
- **APR from Spin Wheel, all other credit data from Array as primary source (Apr 20)**
- **Push notifications deep link to chat interface, not transactions page (Apr 20)**
- **Skip zero-transaction accounts in email summary — heading: "accounts with activity" (Apr 20)**
- **Use Slack instead of WhatsApp for all project communication (Apr 20)**
- **Pause new home UI for 1 week — Abhinav completing task screen first (Apr 20)**
- **Email subject/heading must clarify: "how your money moved" — user confused BON Credit debited money (Apr 20)**
- **Card ending digits + institution name in email account sections (Apr 20)**
- **CTA in email opens app transaction page (Apr 20)**
- **Pitch card linking at: high balance (interest loss), high utilization (payment plan), late fee detection (Apr 20)**
- **Create internal + external financial reports for NEW users going forward (Apr 20)**
- **Claude team plan: 3 premium seats for Sandeep, Pankaj, Shailesh — Samder as admin (Apr 20)**
- **PMF target: June 30. Series A this year. Aggressive marketing Jun-Aug. $1M ARR goal (Apr 20)**
- **Twilio campaigns: delete current, create compliant ones for transaction alerts + app updates ONLY (Apr 24)**
- **Voice UI: hide Deepgram/OpenAI from users — show language + voice tone + read-aloud toggle only (Apr 24)**
- **Home screen: simple navbar + chat + task progress + dynamic scenario cards — finalized (Apr 24)**
- **MoneyLion: credit cards + loans (cash advance under personal loan) — web redirect only (Apr 24)**
- **Shailesh transitions to V2 architecture with Sandeep from Monday Apr 28 (Apr 24)**
- **Darwin: 15 user audits by April 30 — team each does 1-2 additional (Apr 24)**
- **Weekly product call on Fridays (Apr 24)**
- **Voice settings: 3 parameters — language, voice tone/accent, read-aloud toggle (Apr 24)**

## Board vs Reality Gaps
- Sandeep: TSK-231 (New Arch Sprint 4) In Progress — correct. TSK-237 (V2 arch Plaid→opportunity→bursting) In Progress — correct. TSK-242 (wire tables) In Progress — correct. TSK-243 (migrate DAL) Not started — next after wiring.
- Shailesh: TSK-232 (Voice Integration Architecture Doc) In Progress — speech-to-text DONE, TTS today. TSK-236 (Transition to arch with Sandeep) In Progress — starts Monday.
- Pankaj: TSK-233 (Frontend Architecture Alignment) In Progress — websocket endpoint work. No separate board task for voice AI websockets.
- Abhinav: TSK-234 (Voice UI/UX Design) → DONE ✓. TSK-238 (Share voice arch + email layout) → In Progress (updated Apr 24).
- MoneyLion: Pankaj + Samder WIP — needs Figma from Abhinav. Not on board.
- Transaction email: TSK-241 In Progress (external Sai) — correct.
- Customer.IO: TSK-240 Not started — no update.
- Home screen redesign: design finalized (simple navbar) — not on board yet.

## Metrics
- **Users with credit reports:** 1,411 unique (confirmed from Amplitude)
- **Total DAUs (Nov 1 - Apr 14):** 3,480 (avg 14.5/day)
- **Credit score distribution:** 71% below 670 (target segment), only 2% above 800
- **User engagement post-agent:** 17/40 audited users returned on multiple days. DAU > new signups (retention signal).
- **Avg time per user:** ~5.5 min (stable)
- **Chat users (last 30 days):** 142 unique (Amplitude) vs 298 (Sandeep dashboard — discrepancy under investigation)
- **AI response latency:** Avg 2.22s, spikes to 5-6s
- **Agent distribution:** Credit report agent handles most queries (239). Journal agent is #2 at 25.
- **Top user intent:** "How can I improve my credit score?" (39 times)
- DAU: ~7-9 (real, after removing QA/bot traffic)
- Card linking success: 28%
- Push notification delivery: 4%
- Email: 80%+ delivery, 34% open rate
- **FB ads:** LIVE but poor ROI — $23/download, 5 downloads. Relaunching with different creative.

## Competitive Intelligence
- **Origin:** Best answer quality (thorough analysis, understands financial context), but slow response time
- **Cleo:** Fastest responses, but generic/dumb answers
- **BON:** Better than Cleo (uses real data), behind Origin on quality. Darwin audit shows AI answers "solid" for credit advice, payment plans, utilization reduction.
- **Industry view:** BON = intelligence company. Experian testing AI credit report reconstruction (70% accuracy). Bureau stocks down 30% on AI fears.

## What Changed Recently (for context between meetings)
- **Apr 24 (Fireflies transcript 01KPYSH43DY0WWE3BHKCQY07D2 processed):** Full team call (2h14m). Two parts: (1) External team — Twilio A2P compliance crisis (campaigns rejected for credit repair/debt content, must delete + recreate for transactions + app updates ONLY), load testing 50% failure (Ashwini retesting with delays), Swagger APIs 9/10 routes accept empty bodies (Sara fixing manually). (2) Internal team — Voice AI STT DONE + live demo (3 modes: continuous, tap-to-talk, auto-shutoff), TTS targeting today, home screen finalized (simple navbar + chat + task progress + dynamic scenario cards with 6 visual triggers), competitive audit BON at bottom with Cleo, MoneyLion credit cards + loans (cash advance = personal loan, web redirect only), Darwin conference done (industry validates AI, GEO 25-50% users search AI for financial advice, NerdWallet feeling pressure, lenders love subprime, nobody doing serious AI yet), user-designed cards concept (long-term), 15 user audits by Apr 30, Shailesh to V2 arch from Monday, weekly product call Fridays. Board confirmed: all statuses match transcript.
- **Apr 23 (standup replies processed, Daily Scrum written):** Sandeep: data migration DONE, continuing discrepancy investigation + V2 arch. Pankaj: MoneyLion + Voice AI both WIP, now focused on Voice AI web sockets — *BLOCKER: needs Figma designs from Abhinav*. Shailesh: Voice AI 40% done targeting V1 today, V2 arch support deferred to later this week. Tarun: Ashwini KT done, Sai KT WIP. Samder: marketing audit + YouTube done, today user audit + product brief. Darwin: no reply (conference). Abhinav: no reply. No new Fireflies transcript today.
- **Apr 22 (all standup replies processed):** Sandeep: 24 Plaid tables DONE, data migration next, V2 target May 8. Pankaj: deep link done, build live, now on MoneyLion + voice AI. Shailesh: interest calc done, WhatsApp redirect live, now on voice feature dev (Deepgram+OpenAI) + V2 architecture. Darwin: user audit done, attending conference. Samder: competitor auditing done, YouTube strategy done, FB new ads live, one-page B plan done — today marketing + product brief + user audits + YouTube. Tarun: QA + feature testing done, today KT with Ashwini + Sai. Abhinav: no reply (back from travel).
- Apr 5: Shifted from 2-week to weekly sprints. Architecture v2 deep-dive.
- Apr 7: Human support descoped to WhatsApp redirect. Interest calculator tested.
- Apr 8: PMF focus mandated. Daily scrum adopted.
- Apr 10: Twilio rejected. Competitor audit started.
- Apr 11: Amplitude audit revealed real DAU=7. Card linking confirmed as #1 problem.
- Apr 12: Darwin confirmed APR + paydown ready for testing.
- Apr 13: Alaska reset. Sprint 2 closing at 3%.
- Apr 14: Play Store APPROVED. App released both stores. Darwin's first complete credit report. DocSend for reports. Daily releases enabled.
- Apr 15: Strategy gate reordering decided. Bug backlog blitz targeting Friday. Sandeep US relocation (L1, June).
- Apr 16 (standup): Pankaj WhatsApp UI done. Sandeep strategy gates done. Shailesh outstanding balance done. Samder YouTube setup + FB ads WIP.
- Apr 16 (transcript): Live competitive demo. Webinars dropped. WhatsApp welcome msg spec. Chat analytics dashboard.
- Apr 17 (standup): Pankaj cleared all 4 items ✓. Sandeep dashboard deployed + bugs done, Plaid WIP Day 5. Shailesh intra-bank done.
- Apr 17 (transcript): Transaction email system live but needs redesign. Push notification bug fixed. Global message caps. Customer.IO exit conditions. App build approved. User deletion webhook needed. Darwin met ByteDance AI + Experian AI. FB ads launching. Shailesh to join architecture.
- Apr 18 (transcript): Founders-only Saturday. FB ads LIVE ✓. Darwin rejection letter lead gen. Deep Amplitude engagement analysis. Dashboard discrepancy. AppsFlyer needed. Single moms targeting.
- **Apr 20 (transcript): Transaction email redesign deep dive (clarity: "how money moved" heading, account grouping by institution, card last-4, skip zero-tx accounts, mobile-friendly). Customer.IO global cap 6/day deployed to dev. Darwin user audit #999: chatbot quality solid, interest calc 24% APR framework, Array vs Spin Wheel discrepancies. Shailesh: ALL audit bugs fixed on dev. Sandeep: architecture 30-40%, Plaid almost done. FB ads $23/download poor ROI — relaunching. Slack > WhatsApp mandate. Goa retreat May 8-13 (Marriott/Grand Hyatt). Samder: PMF June 30 target, $1M ARR goal, aggressive marketing Jun-Aug. Abhinav unavailable Apr 21-22 (flying to India).**
