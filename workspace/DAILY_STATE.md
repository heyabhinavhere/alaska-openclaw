# DAILY_STATE.md — Single Source of Truth
# Written by Meeting Intelligence. Read by ALL agents before acting.
# Last compiled: 2026-04-28 (from Apr 28 team call)

---

## Current Sprint
- **Sprint:** 5 (Apr 28 – May 4)
- **Status:** DRAFT — awaiting Abhinav approval
- **Cadence:** Weekly (Monday–Sunday)
- **Capacity:** 10pts per person per week MAX

## This Week's Goals (from Apr 28 call)
1. **Card linking is THE critical product step** — team consensus: PMF = trust → link card → track payment. Focus on increasing initiation from 60% → 80%, then fix credential dropoffs
2. **V2 agent rewiring** — Sandeep rewiring existing 4 agents with new V2 tables (DB query rewriting)
3. **Engagement Dashboard live** — Sandeep deploying to production (1-2 hours from call)
4. **Voice AI TTS integration** — Shailesh shares TTS websocket, Pankaj integrates
5. **Cross-system intelligence** — Abhinav building unified Amplitude + Customer.io + user data dashboard in Slack (ETA 1-2 days)
6. **User audits** — Darwin continuing, found tradeline mismatch on user 2750
7. **Explore Plivo** as Twilio SMS alternative (Abhinav — have 1 verified number)
8. **YouTube content** — Samder continues tomorrow (sick today, half shoot only)

---

## Per Person

### Sandeep (AI Engineer)
- **NOW:** Deploying Engagement Dashboard to production (1-2 hours). Rewiring existing 4 V2 agents with new table DB queries. Integration testing. Building filter web app for dev testing.
- **LAST COMMITTED (Apr 28):** Deploy Engagement Dashboard to prod, continue V2 agent rewiring with new tables, complete activities section, integration testing with Pankaj, filter web app.
- **DONE RECENTLY:** Engagement Dashboard built (3rd tab in Audit Dashboard — active users monthly, conversations, new/returning/old user classification) ✓, voice agent architecture reviewed ✓, charts added for Darwin (audit dashboard) ✓, V2 coding round V1 DONE ✓
- **BLOCKED:** Nothing currently
- **SPRINT TASKS:** TSK-246 (Wire 24 tables with V2 agents, 4pts, due May 3)

### Shailesh (AI Engineer)
- **NOW:** TTS implementation — handling encoding complexity and websocket connection. Expected to share TTS websocket with Pankaj today.
- **LAST COMMITTED (Apr 28):** Complete TTS websocket and share with Pankaj today, then continue with V2 architecture.
- **DONE RECENTLY:** Speech-to-text DONE ✓, WhatsApp redirect live ✓, all audit bugs fixed on dev ✓
- **BLOCKED:** Nothing currently
- **SPRINT TASKS:** TSK-244 (Complete TTS implementation, 2pts, due May 1)

### Pankaj (Frontend Engineer)
- **NOW:** Waiting for TTS websocket from Shailesh to start TTS integration. Card linking Plaid deep dive — analyzing exit-step data. Adding "forgot credentials" option (waiting for exact string from Abhinav).
- **LAST COMMITTED (Apr 28):** Integrate TTS websocket when Shailesh shares, add "forgot credentials" to card linking, deep dive into Plaid linking failure causes (auth/credential dropoffs).
- **DONE RECENTLY:** STT websocket implemented ✓, sidebar icon changes implemented ✓, Plaid exit-step analysis (April: 36 initiated → 7 success, 24 unsuccessful) ✓
- **BLOCKED:** Waiting on Shailesh for TTS websocket; waiting on Abhinav for "forgot credentials" string
- **SPRINT TASKS:** TSK-245 (Voice AI websocket endpoint, 4pts, due May 3), TSK-247 (Session tracking, 2pts, due May 1)

### Darwin (Co-founder COO)
- **NOW:** Detailed user audits. Found tradeline mismatch on user 2750 (Array: 23 credit cards, AI: 18). User 1778 is a power user (4 days, 5 linked accounts, actively using AI for spending analysis).
- **LAST COMMITTED (Apr 28):** Finish 1-2 audits tonight, 1-2 more tomorrow. Validate Engagement Dashboard data once deployed to prod.
- **DONE RECENTLY:** User 2750 audit (tradeline mismatch found) ✓, user 1778 audit (power user identified) ✓
- **BLOCKED:** Nothing currently
- **SPRINT TASKS:** TSK-250 (Complete 15 user audits by Apr 30, 1pt, In Progress)

### Samder (Co-founder CEO)
- **NOW:** YouTube content — did half shoot today but felt sick, will continue tomorrow. TSK-249 (website redesign) deferred to next week. Needs Figma link from Abhinav for website redesign demo.
- **LAST COMMITTED (Apr 28):** Continue YouTube shoot tomorrow. Website redesign content pushed to next week. Share flight itinerary for Goa trip coordination.
- **DONE RECENTLY:** Hotel booked for Goa (under his name) ✓, connecting Darwin/Abhinav with hotel for airport pickup ✓, half YouTube shoot ✓
- **BLOCKED:** Felt sick today — partial day only
- **SPRINT TASKS:** TSK-249 (Website redesign content preparation, 2pts, due May 4 — likely to slip to next week)

### Abhinav (Head of Product & Design)
- **NOW:** Building cross-system intelligence dashboard (Amplitude + Customer.io + user data unified in Slack — ETA 1-2 days). Researching Twilio docs for transaction notification compliance. Exploring Plivo as alternative. Card linking analysis.
- **LAST COMMITTED (Apr 28):** Complete cross-system intelligence dashboard (deploy on Railway, connected to Slack). Read Twilio docs on transaction notifications, may create new campaign. Send "forgot credentials" string to Pankaj. Share Figma link with Samder for website redesign.
- **DONE RECENTLY:** Session tracking implemented (30-min inactivity = new session in Amplitude) ✓, UI icon changes for better UX ✓, card linking funnel analysis complete (Mar 16-31 + April data) ✓
- **BLOCKED:** Twilio A2P compliance (19+ days — campaigns rejected). Audio issues during call (voice breaking multiple times).
- **SPRINT TASKS:** None on board (product/design work)

### Tarun (QA Intern)
- **NOW:** Performance testing on AWS. Yesterday tried on own account ($2.50 spent), 60-70% failure at 10k concurrent on single instance. Sandeep connecting him to dev team for proper AWS access.
- **LAST COMMITTED (Apr 28):** Create instances again for performance testing with dev team AWS access. Connect with dev team through Sandeep.
- **DONE RECENTLY:** Attempted AWS performance testing (single instance, 10k concurrent) ✓, connected with Sai for API testing ✓
- **BLOCKED:** Was using personal AWS account — Sandeep fixing by connecting to dev team's configured instances
- **SPRINT TASKS:** TSK-248 (QA testing for Voice AI and session tracking, 1pt, due May 4)

---

## Active Decisions (last 2 weeks)
1. **User classification for dashboard:** New (started this month), Returning (chatted this AND previous month), Old (only previous months) — Darwin/Sandeep (Apr 28)
2. **Card linking priority:** Focus on initiation rate first (60% → 80%), then fix credential/auth dropoffs. Don't tackle institution-not-found yet — Samder/Abhinav (Apr 28)
3. **Explore Plivo as Twilio alternative** — have 1 fully verified number that can send campaigns — Abhinav (Apr 28)
4. **Consider incentives for card linking** — "BON free for 100 days" if all cards linked, or free subscription months — Samder/Sandeep (Apr 28)
5. **TSK-249 website redesign deferred** to next week by Samder (Apr 28)
6. **Focus on first card link** — once user links one card, show benefits to drive more linking — Sandeep (Apr 28)
7. Card linking: add "forgot credentials" 3rd option — Sandeep/Pankaj (Apr 27)
8. Keep anonymized chat history after user deletion — Darwin/Sandeep (Apr 27)
9. LLM temp tuning needed (0.1-0.3) to reduce hallucination — Sandeep (Apr 27)
10. Shailesh transitions to V2 architecture with Sandeep from Monday Apr 28 (Apr 24)

## Active Blockers
| Blocker | Days Active | Owner | Status |
|---------|------------|-------|--------|
| Card linking ~21-28% success rate | 30+ | Pankaj/Abhinav | Deep analysis done — credential/auth is main cause. Prioritizing initiation rate first. |
| Twilio A2P compliance | 19+ | Abhinav | Exploring Plivo alternative (1 verified number available) |
| LLM hallucination (temp tuning 0.1-0.3) | 2 | Sandeep | From Apr 27 call |
| User 2750 tradeline mismatch | NEW | Sandeep/Darwin | Array: 23 CC, AI: 18 CC — investigating |
| MoneyLion sandbox credentials | 4+ | Pankaj/Abhinav | Waiting on Figma approval |
| Sai KT for Tarun | 6+ | Sai (external) | On hold — Sai busy |
| Push notifications 4% delivery | 18+ | Pankaj/Sandeep | No visible progress |
| Tarun AWS access | NEW | Sandeep | Connecting Tarun to dev team for proper access |

## Metrics (Amplitude-verified Apr 28 + call data)
- **DAU (Amplitude verified, real users):** Apr 21: 12, Apr 22: 15, Apr 23: 18, Apr 24: 12, Apr 25: 17, Apr 26: 16, Apr 27: 23
- **Card linking (Mar 16-31):** 55 users, 44 (80%) initiated within Day 1, only 12 successfully linked. Median initiation time: 1 min 22 sec.
- **Card linking (April):** 45 tried, 10 succeeded (~22%), 30 unsuccessful. Breakdown: 11 institution-not-found, 14 auth/credentials, 5 dropped off.
- **Engagement (Sandeep dashboard, dev data):** March: 34 active users / 283 conversations. April: 25 users / 746 conversations (3x engagement per user).
- **Retention:** ~8% return 3+ days. Pre/post March nearly identical (~22% return 2+ days)
- **Chat users:** 362 all-time, 162 in last 30 days
- **User 1778:** Power user — 4 days in last month, linked 5 accounts (2 checking, 2 saving, 1 CC), actively using AI for spending
- **User 2750:** Tradeline mismatch — Array shows 23 CC + 1 loan + 2 auto, AI says 18 CC + 4 loans
- **Performance testing:** Single AWS instance: 60-70% failure at 10k concurrent (multi-instance needed)
- **OTP dropout:** 30%
- **FB ads:** $1500 → 90 downloads → 34 valid = $45 CAC

## What Changed Apr 28 (today's call)
- **Product clarity:** Team consensus that card linking is THE critical product step. PMF = 3 steps: trust/conversation → link card → track payment. Everything else is secondary.
- **Card linking deep dive:** Pankaj showed Plaid exit-step data. April: 36 initiated → 7 success, 24 fail. Main causes: auth/credentials (not Plaid's fault). Users have high intent (80% try Day 1) but fail on credentials.
- **Engagement Dashboard created** by Sandeep (Audit Dashboard 3rd tab). Deploying to prod today. New/Returning/Old user classification defined with Darwin.
- **Cross-system intelligence** being built by Abhinav — unified Amplitude + Customer.io + user data queryable from Slack. ETA 1-2 days.
- **Plivo exploration** as Twilio alternative — have 1 fully verified number.
- **TSK-249 website redesign** deferred to next week by Samder (sick today).
- **Tarun's AWS misstep** — used personal account, spent $2.50. Sandeep connecting to dev team for proper access.
- **DAU trending up** — Amplitude verified: 12-23 range last 7 days (vs 7-9 previously reported). Filter appears more accurate now.

## Upcoming
- **May 8-13:** Goa retreat. V2 demo target: Goa Day 1. Hotel booked under Samder's name, airport pickup arranged.
- **PMF target:** June 30. Series A this year. Aggressive marketing Jun-Aug. $1M ARR goal.
- **Darwin travel:** Apr 30 to SE Asia
- **Engagement Dashboard:** Live today (Sandeep, 1-2 hours)
- **Cross-system intelligence:** Abhinav, ETA 1-2 days
