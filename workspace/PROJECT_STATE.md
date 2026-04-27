# PROJECT_STATE.md — Alaska's Living Understanding
# Updated by Meeting Intelligence after every meeting analysis
# Read by ALL agents before acting
# Last updated: 2026-04-27 (Team call transcript processed)

---

## Current Sprint
- **Sprint:** 4 (Week of Apr 21-27) — FINAL DAY
- **Cadence:** Weekly (Monday-Sunday)
- **Status:** DRAFT — not yet approved
- **Capacity:** 10pts per person per week MAX

## Strategic Priority (from most recent meetings)
1. **V2 Agent architecture** — Sandeep: V1 coding round for V2 architecture DONE ✓ (all 24 tables + 7 agent coding complete via Claude Code in 4 phases). Now validating each agent (opportunity engine, bursting agent, Plaid parser, progress tracker, response renderer, task system, trigger monitor) with real user data. Target: demo on Goa Day 1 (May 8). Shailesh joining V2 from tomorrow (Apr 28).
2. **Voice AI** — Speech-to-text DONE ✓. Text-to-speech nearly done (few fixes remaining). Pankaj implemented voice preference storage APIs + settings UI (language list with search, per-language voices with sample playback, feminine/masculine tags). Sara built DB migrations + API endpoints for voice preferences. Default: English + default voice, saved per user in demographics.
3. **MoneyLion integration** — Sara: infrastructure READY, code integrated. Awaiting sandbox/prod credentials from MoneyLion (Figma approval needed first). 3 tables: status, webhook comm, user activity. Webhook for finalized events, engine sync every 1hr for status updates. Can pre-fill user data (mobile, DOB). Pankaj raised sandbox query. MoneyLion call Wednesday. Abhinav completing Figma docs today.
4. **Card linking Plaid fix** — Major UX issue: Plaid shows some cards as non-clickable (unsupported) but BON keeps recommending them. Plan: add "I forgot my credentials" as 3rd popup option, update data sync agent to mark unsupported cards as "not available" and stop recommending CTA. Pankaj sends string → Sandeep updates agent.
5. **Swagger API cleanup** — Sara: 80/100 routes manually verified + validated, 100-150 APIs deprecated. 20 routes remaining. Needs Pankaj's list of active mobile APIs to segregate used vs unused. Testing with Ashwini planned.
6. **Load testing** — Website: 10K concurrent users ZERO ERRORS ✓ (5 AWS instances × 2K users = 107K samples). Backend API load testing for 10K users next (Ashwini).
7. **User retention analysis** — Abhinav shared session + day distribution. Pre-March vs post-March retention nearly identical (~22% return 2+ days, 3-day: 4.8% → 2.6%). Agent didn't significantly improve multi-day return rates. Darwin surprised — expected improvement from chat. Darwin requested chat-user-specific distribution (362 users) from Sandeep.
8. **User deletion flow** — User 2564 deleted after active engagement (Capital One trade line question). Need multi-step deletion (Facebook-style 30-90 day grace with win-back emails). NOT current priority per Samder, but noted.
9. **LLM hallucination fix** — Data from DB is correct, but LLM rephrasing hallucinates (temperature too high). Need to tune to 0.1-0.3 for deterministic responses. Testing on multiple users confirms data accuracy.
10. **Twilio A2P** — Still pending. Weekend support didn't respond. Abhinav raising ticket through AI + human today/tomorrow morning PST.
11. **Goa retreat (May 8-13)** — Still on. V2 demo target for Day 1.

## Per-Person Current Focus
- **Sandeep:** V2 architecture V1 coding DONE ✓ (24 tables + 7 agents coded). Now validating each agent with real user data (2 test users). Removed response capping from Financial Insight + Paydown Plan agents (now shows summary → details). After validation, rewire V1 agents with new tables. Target: V2 demo Goa Day 1. Also: update data sync agent for Plaid unsupported card marking, generate chat user session/day distribution for Darwin.
- **Pankaj:** Voice preference APIs implemented ✓ (3 APIs from Sai). Voice settings UI built (language search, voice list with playback, gender tags). Today: websocket integration (webhook API). Meeting Sai at 4-5pm for deprecated API list. Card linking: add "I forgot my credentials" option.
- **Shailesh:** Voice AI mostly complete — few TTS fixes today, then coordinate with Pankaj on frontend integration. Confirmed LLM hallucination is temperature issue (tested multiple users). Joining Sandeep on V2 from tomorrow (Apr 28).
- **Darwin:** Looked at 3 users today — agents getting smarter, handling complicated questions. User 2564 deep dive (deleted after active engagement — dashboard shows "unknown user" but chat has name = bug). Needs follow-up mechanism. This week: couple more audits Mon-Tue, Stripe conference Wed-Thu, Stanford conference Fri-Sat.
- **Samder:** Both standup items done ✓. This week: Mon-Tue May YouTube content shoot, Wed-Thu Stripe conference with Darwin, Fri-Sat Stanford reunion. Website header/App Store/Play Store edits done. Searching for review agency (SEO/GEO boost).
- **Abhinav:** Session + day distribution analytics added (30-min inactivity = new session, PST-based days). Distribution analysis of 82 neither-linked users NOT yet done. Today: complete MoneyLion Figma docs (call Wednesday), product-side work, V2 design, Twilio support ticket.
- **Tarun:** Friday Swagger API follow-up done. Today: website performance testing 10K concurrent users, connect with Sai for Swagger KT. Learning AWS (EC2 instances for load testing — DevOps to help with access).

## Active Blockers
| Blocker | Days Active | Owner | Status |
|---------|------------|-------|--------|
| MoneyLion sandbox/prod credentials | 3+ | Sara/Pankaj | Infrastructure ready, waiting on Figma approval → credentials |
| Twilio A2P compliance | 19+ | Abhinav | Weekend support didn't respond. Raising ticket today/tomorrow PST |
| Plaid unsupported cards keep being recommended | NEW | Sandeep/Pankaj | Adding 3rd option + data sync agent update |
| Dashboard "unknown user" bug (user 2564) | NEW | Sandeep | Dashboard shows unknown but chat has name |
| LLM hallucination (temperature) | 3+ | Sandeep/Shailesh | Data correct, LLM rephrasing issue. Need temp tuning. |
| Claude rate limits | 7+ | Pankaj | Needs premium seat, currently standard |
| Array vs Spin Wheel data discrepancy | 7+ | Sandeep/Darwin | Different balances + utilization |
| FB ads poor ROI | 9+ | Samder | $23/download. Relaunching different creative |
| Unknown user bug | 14+ | Shailesh/Sai | Blocked on Sai — deleted user still in chat DB |
| Push notifications 4% delivery | 18+ | Pankaj/Sandeep | No visible progress |
| Card linking 70%+ failure | 32+ | Unassigned | Plaid unsupported card fix in progress |
| Play Store outdated | 8+ | Samder | Working on it + searching review agency |

## Recent Decisions (keep last 2 weeks)
- **Card linking popup: add "I forgot my credentials" as 3rd option; "My card isn't showing up" covers both wrong name + Plaid unsupported (Apr 27)**
- **Data sync agent: mark Plaid-unsupported cards as "not available" → stop recommending CTA (Apr 27)**
- **Keep anonymized chat history after user deletion (Langfuse backup DB, PII removed) (Apr 27)**
- **Multi-step user deletion flow (Facebook-style grace period) — noted for FUTURE, not current priority (Apr 27)**
- **Backend API load testing for 10K users — Ashwini (Apr 27)**
- **MoneyLion tables to be added to DB2 + DB3 for agent integration (Apr 27)**
- **Voice settings: keep ALL voices per language (don't restrict to 5-6) — Samder overruled (Apr 27)**
- **Default voice: English + default voice, saved per user in demographics (Apr 27)**
- **LLM temperature tuning needed to reduce hallucination (0.1-0.3 range) (Apr 27)**
- **Session definition: 30 min inactivity = new session (Apr 27)**
- Twilio campaigns: delete current, create compliant ones for transaction alerts + app updates ONLY (Apr 24)
- Voice UI: hide Deepgram/OpenAI from users — show language + voice tone + read-aloud toggle only (Apr 24)
- Home screen: simple navbar + chat + task progress + dynamic scenario cards — finalized (Apr 24)
- MoneyLion: credit cards + loans (cash advance under personal loan) — web redirect only (Apr 24)
- Shailesh transitions to V2 architecture with Sandeep from Monday Apr 28 (Apr 24)
- Darwin: 15 user audits by April 30 — team each does 1-2 additional (Apr 24)
- Weekly product call on Fridays (Apr 24)
- Voice settings: 3 parameters — language, voice tone/accent, read-aloud toggle (Apr 24)

## Board vs Reality Gaps
- Sandeep: V2 coding round V1 DONE — board may still show "In Progress" for TSK-231/237/242. TSK-243 (migrate DAL) is the next step after validation.
- Shailesh: Voice AI nearly done (TTS fixes remaining). Board may not reflect near-completion.
- Pankaj: Voice settings UI built + APIs integrated — not on board. Websocket still WIP.
- MoneyLion: Sara's infrastructure ready — not on board. Waiting on credentials only.
- Load testing: Website 10K ✓ with zero errors — board may still show in progress.
- Swagger: 80% routes validated — not reflected on board.

## Metrics
- **Total chat users (all time):** 362 (Sandeep dashboard)
- **Chat users (recent period):** 244 (dashboard filtered)
- **Session retention (post-March):** ~22% return 2+ days; 3-day: 2.6%; 4+ day: slightly higher
- **Session retention (pre-March):** ~22% return 2+ days; 3-day: 4.8%
- **Website load test:** 10K concurrent users, zero errors, 107K samples across 5 AWS instances
- **Swagger APIs:** 80/100 routes validated, 100-150 deprecated
- **Users with credit reports:** 1,411 unique
- DAU: ~7-9 (real, after removing QA/bot traffic)
- Card linking success: 28%
- Push notification delivery: 4%
- Email: 80%+ delivery, 34% open rate
- FB ads: $23/download, poor ROI

## What Changed Recently (for context between meetings)
- **Apr 27 (Team Call — 96 min, Fireflies 01KQ6FWBZ6T1ZNF6TV1XDZBWZQ):** Two parts. (1) External: Sara — Swagger 80% validated, 100-150 APIs deprecated, MoneyLion infra ready (3 tables, webhook + engine sync), needs credentials after Figma approval. Ashwini — website load test 10K users ZERO errors (5 instances × 2K = 107K samples). Backend API load testing next. Twilio still pending (weekend). (2) Internal: Sandeep — V2 coding V1 DONE (24 tables + 7 agents coded in 4 Claude Code phases), now validating each agent. Removed response capping (summary → details for Financial Insight, Paydown Plan, Bursting agents). LLM hallucination = temperature issue, data is correct. Card linking: adding "forgot credentials" option + data sync agent update for Plaid unsupported cards. Pankaj — voice preference APIs + settings UI built (language list, voices with playback). Shailesh — TTS fixes today, joining V2 tomorrow. Darwin — 3 user audits, agents getting smarter, user 2564 deleted after active engagement (dashboard "unknown user" bug), needs follow-up mechanism + multi-step deletion. Samder — Mon-Tue YouTube shoot, Wed-Thu Stripe, Fri-Sat Stanford. Abhinav — session + day distribution analytics added (retention similar pre/post March), MoneyLion Figma today, Twilio ticket. Abhinav shared retention data: 3-day 4.8% → 2.6% post-March (unexpected — agent didn't improve multi-day return). Darwin requested chat-user distribution from Sandeep (362 users).
