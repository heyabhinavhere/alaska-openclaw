# PROJECT_STATE.md — Alaska's Living Understanding
# Updated by Meeting Intelligence after every meeting analysis
# Read by ALL agents before acting
# Last updated: 2026-04-14 (BON Product Discussion)

---

## Current Sprint
- **Sprint:** 3 (Week of Apr 14-20)
- **Cadence:** Weekly (Monday-Sunday)
- **Status:** DRAFT — not approved
- **Capacity:** 10pts per person per week MAX

## Strategic Priority (from most recent meetings)
1. **App release today** — Play Store APPROVED. Releasing on both App Store + Play Store with Plaid data logging + WhatsApp human support feature.
2. **Credit report analysis → user engagement** — Darwin building internal/external credit reports manually (10-12 days before automation). First user (Kelly Cooper) complete. This is the PMF play.
3. **V2 Architecture tables** — Sandeep: Opportunity + Trigger tables done. 5-6 more Plaid tables in ~2 days. Report data tables complete.
4. **Card linking fix** — Still #1 technical priority per Apr 11. 70%+ failure rate.
5. **Daily releases enabled** — JSON schema architecture means bug fixes + features can ship server-side without app republishing.
6. **Bug fixes / audit items** — Shailesh handling daily. Unknown user bug fixed. Outstanding panels next.

## Per-Person Current Focus
- **Sandeep:** V2 architecture tables — Opportunity + Trigger tables DONE, analyzing Plaid data for 5-6 more tables (~2 days). App release + final AI feature testing today. Interest calculator integration with Plaid for principal/interest breakdown.
- **Pankaj:** Plaid API integration finishing today. WhatsApp UI feature next. App release today (both stores). Check with Sai on privacy policy/T&C for Twilio re-approval.
- **Shailesh:** Unknown user bug DONE (needs Sandeep review). Outstanding panels task picked up from audit sheet. Only 2 bugs remaining — rest are features for V1/V2.
- **Darwin:** First internal/external credit report complete (Kelly Cooper). Daily manual reports for 10-12 days. Designed 10-step agent conversation flow. Need new user email IDs from Sandeep.
- **Abhinav:** Metrics FIXED (DAU/MAU/WAU correct). Home screen design started. Website blocked on animations (weekend). Feedback forms + bounty published (test users starting tomorrow). Privacy policy/T&C update for Twilio.
- **Samder:** User profiling DONE (27 recurring users analyzed — young paycheck-to-paycheck with CC debt + car loans). YouTube agency call tonight. Competitor audit tomorrow. DocSend setup for report delivery. Hub architecture notes for AI advisor meeting.
- **Tarun:** Connected with Sairam + Aswani. Waiting for new features before comprehensive testing. Performance testing will be automated tool (per Sandeep).

## Active Blockers
| Blocker | Days Active | Owner | Status |
|---------|------------|-------|--------|
| Play Store review stuck | RESOLVED | Pankaj | ✅ APPROVED — releasing today |
| Push notifications 4% delivery | 7+ | Pankaj/Sandeep | No visible fix progress |
| Twilio A2P SMS rejected | 7+ | Abhinav/Pankaj | Pankaj checking with Sai on privacy policy update TODAY |
| Card linking 70%+ failure | 21+ | Unassigned | Investigation only, no fix task |
| Website animations | NEW | Abhinav | Blocked, will use Yogesh or complete weekend |

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
- Remove "other loans" section from external report — privacy concern (Apr 14)
- Remove "confidential" tag from external report — could scare users (Apr 14)
- Send external reports via DocSend — tracking + legal safety (Apr 14)
- Manual credit reports for 10-12 days before automation (Apr 14)
- External reports sent as human (Darwin), not AI agent (Apr 14)
- Daily/frequent releases enabled via JSON schema (Apr 14)
- Pankaj to coordinate Twilio re-approval with Sai today (Apr 14)

## Board vs Reality Gaps
- Play Store blocker RESOLVED — approved, releasing today
- Opportunity + Trigger tables: DONE by Sandeep (not on Sprint Board)
- Report data tables: DONE (not reflected on board)
- Shailesh: Unknown user bug DONE
- Metrics: FIXED by Abhinav (daily credit brief now accurate)
- Samder: User profiling DONE (not a board task)
- Daily releases now possible — this changes velocity assumptions

## Metrics
- DAU: ~7-9 (real, after removing QA/bot traffic) — NOW CORRECTLY TRACKED
- WAU trend: 44→56→42→16
- Card linking success: 27/97 (28%)
- Push notification delivery: 4%
- Email: 80%+ delivery, 34% open rate (WORKING — underutilized)
- Recurring users: 27 out of ~35 active users profiled

## What Changed Recently (for context between meetings)
- Apr 5: Shifted from 2-week to weekly sprints. Architecture v2 deep-dive.
- Apr 7: Human support descoped to WhatsApp redirect. Interest calculator tested.
- Apr 8: PMF focus mandated. Daily scrum adopted (nobody used it).
- Apr 10: Twilio rejected. Competitor audit started. WhatsApp Business agreed.
- Apr 11: Amplitude audit revealed real DAU=7. Card linking confirmed as #1 problem. Email is only working channel.
- Apr 12: Darwin confirmed APR + paydown ready for testing. Zero standup responses.
- Apr 13: Abhinav initiated Alaska reset. Sprint 2 closing at 3%.
- Apr 14: Play Store APPROVED. App releasing today (both stores). Darwin's first complete credit report analysis. User profiling done. DocSend for reports. Daily releases enabled via JSON schema. Metrics fixed.
