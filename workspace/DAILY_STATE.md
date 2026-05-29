# DAILY_STATE.md — Single Source of Truth
# Written by Meeting Intelligence. Read by ALL agents before acting.
# Last compiled: 2026-05-29 13:00 UTC (RECONSTRUCTED from the May 28 team call + May 27–29 Slack standup sheets, daily pulses, and team-call summaries)
#
# NOTE: This file was reconstructed on 2026-05-29 during the workspace-persistence fix
# (Issue H) — it is grounded in Slack data, NOT a normal Meeting Intelligence compile.
# Meeting Intelligence will overwrite it with a fresh synthesis after the next team call,
# and from now on those updates PERSIST (the workspace moved to the persistent volume).
# Sprint Board was retired 2026-05-23 — this file is sprint-agnostic ("Current Focus",
# not "Current Sprint"). Agents MUST check the "Last compiled" timestamp and refuse to
# quote dated commitments if the file is more than 48 hours stale.

---

## Current Focus
- **Status:** DATA ACCURACY is the team's #1 priority, hardening V2 for the **June 10 launch**. The AI agent has been presenting wrong financial numbers (total debt, credit-card balance, utilization, income) because it *skips backend tool calls* and answers from stale chat-history / proactive-briefing data instead of the real database — and one wrong number then corrupts every downstream answer. Shailesh documented the root cause + fixes (May 28–29).
- **Three bug categories formalized (May 28 call):** (1) **Design** — charts/graphs (20 fixed May 28–29), (2) **Data** — tool-call skipping / number accuracy, (3) **Flow** — response quality per question type.
- **Cadence:** Nightly team calls ~9 PM IST. Capacity ~10 pts/person/week.
- **Headline shifts (May 26–28):** Darwin's deep audit of user 2756 exposed the accuracy gap (total debt $46K shown vs ~$64K actual, CC balance $24K vs $41K, utilization 48% vs 82.5%, income unverifiable) → "number accuracy is #1." **"Doctor/pharmacist" directive** (Darwin): double-check every number before presenting it. **Debt-misclassification root cause found** — the keyword "car" inside "credit card" mis-bucketed credit cards as car loans (category breakdown wrong; totals correct). **Data consistency mandated** — app chat, dashboard, and backend API must show identical numbers per user. **Budget simplified to 4 lines** (income, debt obligations, living expenses, surplus); financial jargon (DSS, 50/30/20, snowball, autopilot) removed from user-facing replies.

## This Week's Goals (toward June 10 launch)
1. **Number/data accuracy** (CRITICAL) — Sandeep: fix tool-call skipping so the agent reads real DB data; enforce 3-way consistency (app / chat / dashboard / API).
2. **Debt misclassification fix** — Sandeep (classification logic) + Nilesh (partial fix landed): the "car"-in-"credit card" bug.
3. **Returning user feature** — Nilesh (API completed + shared) → Pankaj (UI + API integrated; task/progress schema done); tasks/progress API from Sandeep → Nilesh.
4. **V2 QA** — Tarun: retest remaining 3/10 users after fixes land; full end-to-end app + chart retest; 70-question × 15-section framework.
5. **Charts** — Sandeep: 20 chart bugs fixed, 15-chart JSON schema created.
6. **Agent proactivity overhaul** — shift from passive Q&A to proactive holistic advisor (3 pillars: full data comprehension → evolving recommendations → ongoing progress tracking). Critical for launch.
7. **TechCrunch application** — Samder + Abhinav (demo video shared).
8. **VenturesLab report** — Darwin (was 90% done May 28, submitting).
9. **Single mom marketing + user research** — Samder: Listen Labs + Outset AI user interviews (first week of June).

---

## Per Person

### Abhinav (Head of Product & Design)
- **NOW:** PMF card development; cylinder-chart close-icon design in Figma (with Pankaj); TechCrunch demo video shared.
- **LAST COMMITTED (May 28 standup):** Finalize Figma cylinder-chart close icon; progress PMF card development; review TechCrunch demo feedback.
- **DONE RECENTLY:** TechCrunch demo video shared ✓ (May 28).
- **BLOCKED:** Twilio A2P compliance (30+ days).

### Sandeep (AI Engineer)
- **NOW:** The #1 critical work — fix agent tool-call skipping (hallucination root cause: agent must read real DB, not chat history); 3-way data consistency (app/chat/dashboard/API); debt-misclassification classification-logic fix; deliver tasks/progress API to Nilesh.
- **LAST COMMITTED (May 28 standup):** Complete misclassification fix (debt categories root cause); deliver tasks/progress API to Nilesh; continue data-consistency fixes for chart-suggestion bugs.
- **DONE RECENTLY:** Debt misclassification root cause found ("car" keyword) ✓ (May 28); 20 chart bugs fixed + 15-chart JSON schema ✓ (May 29); proactive-summarizer double-word bug fixed ✓ (May 27); 2 CredGPT PRs merged (#119, #120) ✓ (May 28).
- **BLOCKED:** None currently.

### Pankaj (Frontend Engineer)
- **NOW:** Returning-user UI + API integration; cylinder-chart close icon.
- **LAST COMMITTED (May 28 standup):** Cylinder-chart close-icon implementation; continue returning-user API integration coordination with Nilesh.
- **DONE RECENTLY:** Returning-user UI (7 screens) + schema handed to Nilesh ✓; returning-user UI + API integrated ✓ (May 29); task/progress schema completed ✓ (May 29); navbar flow implemented ✓ (May 28); AI section APIs integrated ✓ (May 27).
- **BLOCKED:** Android build pending Play Store review (13+ days).

### Shailesh (AI Engineer)
- **NOW:** Deep data validation on user 2756; documenting agent tool-call-skipping root causes; validating Sandeep's backend fixes across user profiles.
- **LAST COMMITTED (May 28 standup):** Complete deep data validation on user 2756; collaborate with Nilesh on data accuracy; validate backend fixes as Sandeep implements them.
- **DONE RECENTLY:** Agent tool-call-skipping root cause documented ✓ (May 29); ongoing user-2756 data validation.
- **BLOCKED:** None currently.

### Nilesh (Backend Engineer)
- **NOW:** Returning-user API (completed + shared); debt-breakdown logic; collaborating with Shailesh on data accuracy; integrate tasks/progress API once Sandeep delivers.
- **LAST COMMITTED (May 28 standup):** Implement returning-user API with approach changes; continue data-accuracy collaboration with Shailesh; integrate tasks/progress API.
- **DONE RECENTLY:** Returning-user API completed + shared ✓ (May 29); debt-breakdown logic bug partially fixed ✓ (May 28); 4 webservices PRs merged (#125–128) ✓ (May 28); led the "car"-keyword debt-classification RCA (the user-2756 investigation).
- **BLOCKED:** Was waiting on tasks/progress API from Sandeep (returning-user feature) — confirm if still open.

### Darwin (Co-founder COO)
- **NOW:** User audits focused on data-accuracy validation; VenturesLab report; debt strategy.
- **LAST COMMITTED (May 28 standup):** Submit VenturesLab report (for Ben); continue user audits on data accuracy; follow up on TechCrunch.
- **DONE RECENTLY:** User 2756 deep audit + debt strategy formalized ✓; surfaced the number-accuracy gap (now the #1 priority); "doctor/pharmacist" double-check-every-number directive; VenturesLab report 90% done (May 28, submitting).
- **BLOCKED:** None currently.

### Samder (Co-founder CEO)
- **NOW:** TechCrunch application; single-mom marketing strategy; preparing Listen Labs + Outset AI user interviews (first week of June).
- **LAST COMMITTED (May 28 standup):** Complete TechCrunch application; advance single-mom marketing; prep user interviews.
- **DONE RECENTLY:** MobileFirst KT closure confirmed ✓ (May 26). (Was absent from the May 27 call.)
- **BLOCKED:** None currently.

### Tarun (QA Intern)
- **NOW:** Full end-to-end app testing + chart retest; retest remaining 3/10 user IDs after Sandeep's fixes; 70-question × 15-section QA framework.
- **LAST COMMITTED (May 28 standup):** Retest remaining 3 user IDs once fixes land; continue QA via the 70-question spreadsheet; document new bugs.
- **DONE RECENTLY:** 7/10 user QA completed + chart bugs documented ✓ (May 27); user 2756 QA ✓ (May 26).
- **BLOCKED:** Chart-suggestion bugs (AI showing wrong chart types) — was waiting on Sandeep's fixes before retesting the final 3 (Sandeep fixed 20 chart bugs May 29 — confirm unblocked).

### Sai (External — MobileFirst, offboarding)
- **NOW:** KT to Nilesh complete; MobileFirst KT closure confirmed (May 26). Transitioning off — do not assign sprint work.

---

## Active Decisions (last ~2 weeks)
1. **June 10 launch CONFIRMED** (hardened from "first week of June"). V2 chat/AI features target June 22. (May 22–23 calls)
2. **Number/data accuracy = #1 priority** — driven by Darwin's user-2756 audit. (May 26–28)
3. **Data consistency mandated** — app chat, dashboard, and backend API must show identical numbers per user. (May 27–28)
4. **"Doctor/pharmacist" directive** — double-check every number before presenting. (May 28)
5. **Agent philosophy: passive Q&A → proactive holistic advisor** — 3 pillars (full data comprehension → evolving recommendations → progress tracking). (May 22–23)
6. **Budget simplified to 4 lines** (income, debt obligations, living expenses, surplus); jargon removed from user-facing replies. (May 26)
7. **Bug ownership formalized** — Sandeep fixes + features, Shailesh validates backend (DB verification), Tarun frontend QA; 24h turnaround. (May 25)
8. **Card matching ~95%** (two-tier algorithm); ~5% unmatchable (AMEX dual numbering, new/reissued cards) → post-launch user flagging. (May 22–23)
9. **WhatsApp → Twilio primary** (Plivo backup). (May 20)
10. **MoneyLion = webview only** (Kathleen hosts the UI via static URL; no backend API from us). (May 15)

## Active Blockers
| Blocker | Days Active | Owner | Status |
|---------|------------|-------|--------|
| Agent tool-call skipping / number accuracy (hallucinated financials) | RECURRING — CRITICAL for June 10 | Sandeep / Shailesh | Root cause documented (agent reads chat history instead of DB). Fixes in progress. |
| Android build pending Play Store review | 13+ | Pankaj | iOS fine; awaiting Play Store review. |
| Twilio A2P compliance | 30+ | Abhinav | Long-standing. |
| Push notification opt-in (~7.6% delivery) | 40+ | Abhinav / UX | Backend fixed; low rate is a permission/UX problem (~10% opt-in). |
| Plaid card-linking success rate declining | RECURRING | Shailesh / Sandeep | May 18–24: 6/21 successful (~29%); mostly user self-drop-off. |
| Debt misclassification ("car" keyword) | Found May 26–27 | Sandeep / Nilesh | Nilesh partially fixed; Sandeep fixing classification logic. Category breakdown only (totals were correct). |

## Metrics
- **Real DAU:** [NEEDS AMPLITUDE REFRESH — last grounded value mid-May was ~12–18/day; do not quote without a fresh Real-Users-filtered query.]
- **Push notification delivery:** ~7.6% (permission/opt-in problem, not backend).
- **Plaid card-linking success:** May 18–24: 6/21 (~29%) — declining; user self-drop-off is the main factor.
- **Card matching accuracy:** ~95% (two-tier algorithm); ~5% unmatchable.
- (Email delivery, MAU, card-linked counts: pull fresh from Amplitude/Customer.io before quoting — Abhinav requested a precise investor-metrics set on May 23; that was a separate deliverable.)

## Upcoming
- **June 10:** V2 launch target (confirmed).
- **June 22:** V2 chat/AI features live.
- **First week of June:** Listen Labs + Outset AI user interviews (Samder).
- **June 30:** PMF target. Series A this year. $1M ARR goal.
- **Near-term:** Land the number-accuracy + tool-call-skipping fixes; finish the returning-user feature; complete V2 QA (Tarun's remaining 3 users + end-to-end + chart retest).
