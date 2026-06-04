# Alaska V5 — PMF Cohort Operating System: Master Build Plan

**Date:** 2026-06-03
**Status:** Active. This is the canonical V5 plan.
**Supersedes:** `docs/superpowers/plans/2026-06-02-alaska-v5-pmf-cohort-os.md` (Codex foundation plan — kept for history).
**Owner:** Abhinav (product) · Claude (lead engineer / architect, driving execution)
**Runtime contract:** `workspace/knowledge/definitions/pmf-cohort-os.md` · **Skill:** `skills/pmf-cohort-os/SKILL.md`
**Target:** Full V5 built and end-to-end validated **before** the PMF cohort window opens (window is one of Jun 11-13 / 12-14 / 13-15). Calibrate live on the real cohort.

---

## Progress log (updated 2026-06-04)

**Done + merged:** P0 data-minimization + dogfood (#66) · P1 Amplitude intake (#70) · P2 User 360 enrichment + identity (#71) · P3 daily orchestrator (#72) · **P4** CredGPT turn ingestion + Amplitude fallback + greeting-filtered meaningful count (#75) · **6-metric computation** (4 deterministic PMF metrics + chat over-count fix) (#81) · **P5** Slack delivery + cockpit + slim image (#83) · **P4.1** CredGPT LLM quality/safety judge (#84). **P6** Customer.io intervention execution (gated state machine) in PR.

**Privacy policy changed (supersedes the tier framing in §7 below):** not aggregate-vs-detail tiers — the whole team sees full per-user detail (name/email/phone/credit/financials). We *minimize at the source*: drop SSN / routing numbers / home address, reduce account numbers to last-4 (`lib/pmf_os/model.py: minimize_secrets`).

**Real-data validation (dev User 360 + prod Amplitude) — passed:** intake, identity (backfilled signup events carry `user_id` → trivial resolution; backfill-after-window is the clean path), credit, chat, funnel, and privacy all confirmed on live data. Timezone confirmed **Pacific** (`EVENT_TIME_TZ`, verified via wave mapping). User 360 chat can be **thin/incomplete** → the Amplitude `credgpt_message_sent` fallback (P4) exists for exactly this.

**Six-metric computation — scoped + built (lean):** Full 360 API re-analyzed end-to-end via parallel subagents against dev (the 05-27 "product layer empty" catalog note is stale — `tasks` / `budgeting` / `progress` / `opportunities` / `financial_profile_v2` now populate). Definitions locked with Abhinav; activated_saver bar = **2 of 6 confirmed**.
- **Built now (raw signals only):** `activation_depth` (≥2 meaningful threads OR ≥5 greeting-filtered **non-null-answer** exchanges; confirmed-only — no candidate tier, so it can't collapse the activated_user / activated_saver tiers) · `repeat_engagement` (≥3 active days = confirmed, 2 = candidate; chat distinct-days, store unions across snapshots) · `financial_action` (completed money-task / `budget_plan.source ∈ {manual, credgpt}` / budget check-in = confirmed; auto-seed plan / active-budget / general task = candidate — from raw `tasks` + `budgeting`) · `linked_financial_context` (card OR bank).
- **Principle (load-bearing):** Alaska derives from **raw facts/actions, never CredGPT's interpreted layer**, so it can independently judge CredGPT (the quality observatory). Explicitly **skipped** `financial_profile_v2` + `progress.ledger` deltas; `opportunities` skipped as system noise (0 user-acted transitions across all sampled users — 100% auto-detected, daily-regenerated).
- **Deferred (with clear unlocks):** `qualitative_positive_signal` — no API source (chat thumbs effectively dead, ~1 across hundreds of turns; no sentiment field anywhere) → P4.1 LLM judge on turn text. `retained_value` — time-gated (weekly cadence, needs ≥2 snapshots) → computed later from Alaska's *own* raw credit/savings snapshots over the cohort, not BON's precomputed deltas.
- **Fix shipped:** the chat real-turn heuristic over-counted on null-answer mega-threads (user 2762: 92 "real" turns from 2 null-answer threads) — the meaningful count is now gated on a non-null answer; `_real_chat_turns` stays broad for observatory ingestion.

**P5 / P4.1 / P6 — operate + judge + deliver (merged #83 / #84; P6 in PR):** Slack delivery wired into `run-cohort-day` (`--deliver`; injectable, best-effort) + image slimmed (LibreOffice/poppler dropped, DOCX/PDF deferred). The CredGPT **LLM judge** runs on deterministically-flagged turns as a gated CLI step (`judge-credgpt-reviews`) — injectable + key-gated (no in-repo LLM SDK; thin urllib adapter; `ANTHROPIC_API_KEY` is deploy-time). **P6** adds the gated Customer.io intervention state machine (draft → human approve → guard-validated execute → outcome) in `pmf_interventions`; nothing sends autonomously, SMS blocked, live send only on explicit `--execute-live`.

**Open items (tracked):**
- **6 PMF success-metrics: 4 of 6 computed** → funnel reaches Activated Saver / Lover. Remaining 2 (`qualitative_positive_signal`, `retained_value`) deferred with clear unlocks (LLM judge already built — wire it in; raw time-series).
- **P7 end-cohort intelligence** is the last build phase. The **E2E dogfood run** (synthetic CI-covered; real historical-backfill calibration via Alaska still to do) and **cron activation** (gated, explicit go) remain.
- **Deploy-time keys**: `SLACK_BOT_TOKEN` (P5), `ANTHROPIC_API_KEY` (P4.1), `CUSTOMERIO_APP_API_KEY` (P6) must be set + validated on Railway; **User 360 prod** cutover ~week of Jun 9.
- **Cohort window** date not finalized. DOCX/PDF + LibreOffice still deferred.

---

## 1. Purpose and the bar

V5 turns Alaska into the **active operator of BON's first PMF launch cohort**: one configurable 3-day signup window (~1,000 signups, ~750 real users), tracked at user-level depth across onboarding, financial state, CredGPT chat quality, engagement, friction, intent, retention, and qualitative "love" signals. The job no human can do at 1,000-user scale: know every cohort user, surface who is stuck / at risk / a likely lover, and operate interventions.

V5 is the headline of the V5 era. It sits **inside** the larger horizontal AI-coworker arc ("the rest of your startup team"); it does not exhaust it. The KB self-maintenance agent is a deferred V4 capstone, not V5.

**The engineering bar (hold this and beyond):**
- Deterministic core, evidence for every claim, separation of computed vs candidate, no silent failure.
- Machines do the ETL; the LLM does judgment. Never make the LLM hand-paginate 1,000 users.
- Tests ship with every phase. Collectors tested against recorded fixtures, never live APIs in CI.
- One PR per phase, stop for review, never auto-merge. V5 stays isolated from V4 (`alaska_pmf.db`).
- No autonomous user-facing sends. Customer.io execution is human-approved, dry-run-first.
- 360-degree before "done": data in, processing, judgment, delivery, failure modes, calibration.

---

## 2. Where V5 stands today (honest baseline, after PRs #59-#64)

**Built and solid (the deterministic core):**
- Schema `0005` (12 evidence-carrying tables) on a **separate** DB `/data/queue/alaska_pmf.db` (isolated from V4; migration auto-applies on boot to the PMF DB only).
- PMF Funnel engine (`funnel.py`) — deterministic, computed-vs-candidate separated, failed-link ≠ activation.
- Store/data layer (`store.py`, 1,084 lines) — registry, signal facts, claim evidence, daily snapshots, funnel transitions, case files, queues, CredGPT review/clusters, report runs. Idempotent upserts throughout.
- Customer.io safety gate (`customerio_guard.py`) — deny-by-default, SMS blocked in code AND in schema (`CHECK channel != 'sms'`).
- Artifact rendering (`artifacts.py` + `docflow.py`) — HTML/DOCX/PDF, privacy tiers, visual-QA gate. **Over-built relative to need** (see below).
- CLI (`pmf_cohort_os.py`) — 11 commands. Strong tests (idempotency, SMS guard, privacy redaction, CredGPT escalation all ★★★).

**Review findings from the #59 audit — current status:** separate DB ✅ fixed, funnel demotion-on-partial-facts ✅ fixed, cluster resurrection ✅ fixed, grounding/hallucination mislabel ✅ fixed, artifact perms/temp/tz ✅ fixed, unsafe-advice detection reframed as honest triage ✅. **Open:** team-tier reports still render a per-user row (`user_key`, stage, health, saver-state) — direct PII is redacted but it is not "aggregate." Fix in P0.

**The gap that defines the remaining work — the system is fed, not self-feeding:**
There is **no Amplitude client, no User 360 client, no networking code anywhere** in `lib/pmf_os`. By design it owns durable state + rules + artifacts + gates and delegates collection. So today "intake" = read a JSON file someone exported by hand; "enrichment" = process a JSON blob someone assembled by hand. There is **no collector, no orchestrator, no cron**. The engine can process a cohort; nothing collects or operates one.

**Misallocation to correct:** #61-#64 invested ~750 lines in DocFlow + a LibreOffice-in-image visual-QA runtime, rendering reports of zero-data snapshots, while the data pipeline stayed unbuilt. We **defer DOCX/PDF + LibreOffice** (slim the image; HTML cockpit is enough to launch) and redirect all effort to the pipeline.

---

## 3. The architecture (the correction)

Right principle (Alaska is a thinking system), applied correctly: **deterministic collectors do the bulk ETL into the store; the LLM sits on top for judgment.**

```
   EXTERNAL TRUTH                 DETERMINISTIC ETL (new)            DURABLE STATE             JUDGMENT (LLM)            DELIVERY
 ┌────────────────┐         ┌──────────────────────────┐      ┌────────────────────┐   ┌──────────────────────┐  ┌─────────────────┐
 │ Amplitude API  │──events─▶│ collectors/amplitude.py  │      │                    │   │ CredGPT LLM review   │  │ Slack summary   │
 │ (events, chat) │         │  (BUILD new)             │─────▶│                    │──▶│  (selected turns)    │  │  + HTML cockpit │
 ├────────────────┤         ├──────────────────────────┤      │   PmfStore         │   │ Lover confirmation   │  │   file / link   │
 │ User 360 API   │─profile─▶│ collectors/user360.py    │─────▶│  alaska_pmf.db     │──▶│ Intervention drafts  │──▶  (P5)          │
 │ (profile/credit│         │  (REUSE up-360 client)   │      │  funnel · queues   │   │ Daily narrative      │  ├─────────────────┤
 │  plaid/chat)   │         ├──────────────────────────┤      │  case files · evid │   └──────────┬───────────┘  │ Customer.io     │
 ├────────────────┤         │ collectors/credgpt.py    │─────▶│                    │              │ approval pack │  email/push     │
 │ CredGPT chat   │─turns───▶│  (REUSE up-360 chat)     │      │                    │              ▼ + human OK   │  (gated, P6)    │
 └────────────────┘         └──────────────────────────┘      └─────────┬──────────┘   ┌──────────────────────┐  └─────────────────┘
                                        ▲                                 │              │ customerio-ops skill │
                                        │                                 │              └──────────────────────┘
                              ┌─────────┴───────────┐                     │
                              │ orchestrator.py     │◀────────────────────┘
                              │ run-cohort-day  D   │  collect → enrich → snapshot → review → cluster → render → notify
                              │ (daily cron, idempotent, resumable, partial-failure-tolerant)
                              └─────────────────────┘
```

**Reuse map (what exists, so we don't rebuild):**
| Need | Reuse / Build |
|---|---|
| User 360 profile/credit/plaid/income/subscriptions/chat | **REUSE** `skills/user-profile-360/{client,lookup,sections,cache,redactor,summarizer}.py` (already tested) |
| Amplitude event export (cohort intake + activity) | **BUILD** `collectors/amplitude.py` using `AMPLITUDE_API_KEY/SECRET` + `workspace/references/amplitude-api-reference.md` (charts.py is charts-only, not reusable) |
| CredGPT chat turns | **REUSE** User 360 `chat.recent_turns` section + Amplitude `chat_thread_processed` fallback |
| Customer.io execution | **REUSE** `skills/customerio-ops` + the built `customerio_guard.py` gate |
| Domain facts (6 PMF metrics, personas, lifecycle events) | **REUSE** `workspace/knowledge/definitions/*` + `integrations/*` |

---

## 4. Component contracts (what each new piece must do)

**`collectors/amplitude.py` (BUILD).**
- `fetch_signup_events(window_start, window_end) -> list[event]`: query `onboarding_step_completed` where `step_name=phone_number_submitted` for the window (no Real-User filter), paginate fully, normalize to the shape `upsert_signup_user` expects. Idempotent, re-runnable (events carry stable ids).
- `fetch_user_activity(user_keys, since) -> dict[user_key, facts_delta]`: engagement, linking, value actions, chat events for daily snapshots.
- Deterministic, rate-limited, retried with backoff, structured errors. Records raw responses as evidence.

**`collectors/user360.py` (REUSE).**
- Wrap the existing client: `enrich_user(bon_user_id) -> profile_facts` and `daily_facts(bon_user_id) -> facts` (credit, plaid, income, subscriptions, chat). Use the existing cache + redactor.
- Drive `update_user_profile` + feed `apply_daily_snapshot`.

**`identity.py` (BUILD, small but critical).**
- Canonical key precedence: `bon_user_id` > `amplitude_user_id` > hashed phone > hashed email. Reconcile/merge rows that resolve to the same person across sources. Tested for collisions (the current untested risk).

**`orchestrator.py` + `run-cohort-day --date D` (BUILD).**
- Steps: intake delta → enrich changed users → snapshot all → CredGPT review → refresh clusters → render founder+team HTML → Slack summary + link.
- Idempotent, resumable per-user checkpoint, partial-failure tolerant (one user's API error never sinks the run), structured per-step logging, writes a run record. Wired as the **first V5 cron**: daily, plus a second pass/day during the signup window for the intake-only queues (`stuck_onboarding`, `spinwheel_stuck`).

**LLM judgment layer (via the `pmf-cohort-os` skill, not bulk ETL).**
- CredGPT LLM review: score the rubric + flag genuine unsafe credit advice on the deterministically-selected turns (`needs_llm_review=1`). This is the real quality/safety judge.
- Lover confirmation: review candidate-lover evidence, draft the qualitative case.
- Intervention drafting: draft email/push copy for a queue → `customerio_guard` approval pack → **human approve** → `customerio-ops` execute → outcome tracking.
- Daily narrative: write the concise Slack summary + the founder "what changed / what needs you" note over the deterministic snapshot.

**Delivery (P5).** Slack summary + HTML cockpit file/link (reuse `render_html`, verify the P0 tier gate). DOCX/PDF deferred; pull LibreOffice from the image (and the CI test that asserts it) to keep the launch image lean.

**Customer.io execution (P6).** Reuse `customerio-ops`. Email/push only, SMS blocked. Approval pack → human approve → execute → record delivery/open/click/conversion into `pmf_interventions`.

**End-cohort intelligence (P7).** LLM-narrated final memo over the deterministic funnel / lover / dropoff / quality / intervention data. Runs after the window, toward Jun 30 PMF.

---

## 5. Phase plan, sequencing, and the aggressive timeline

Today is Jun 3; earliest window open is Jun 11. Target: **everything built + dry-run-validated by ~Jun 10**, flip on at window open, calibrate live. Each phase = one reviewable PR off current `main`, isolated worktree, stop-for-review.

| Phase | PR | Deliverable | Depends on | Lane |
|---|---|---|---|---|
| **P0** | 1 | H1 team-tier privacy gate; **confirm Amplitude + User 360 prod API access**; dogfood harness (synthetic + historical cohort) | — | A |
| **P1** | 2 | `collectors/amplitude.py` + `ingest-cohort`; window-agnostic intake | P0 | A |
| **P2** | 3 | `collectors/user360.py` (reuse client) + `identity.py` + collision tests | P0 (parallel-buildable vs P1 via fixtures) | B |
| **P3** | 4 | `orchestrator.py` + `run-cohort-day` + first V5 cron | P1, P2 | A |
| **P4** | 5 | CredGPT live ingest + **LLM review pass** (real safety/quality judge) | P2 (chat turns) | B |
| **P5** | 6 | Slack delivery + cockpit wiring + verify H1; defer DOCX/PDF, slim image | P3 | A |
| **P6** | 7 | Customer.io execution (gated, dry-run → approve → send → outcomes) | P3 | B |
| **P7** | 8 | End-cohort intelligence (final memo, lovers, dropoff, outcomes) | P3+ | A |

**Parallel lanes (with multiple worktrees/agents):**
- **Lane A (spine):** P0 → P1 → P3 → P5 → P7. The capture-and-operate backbone.
- **Lane B (independent subsystems):** P2 (enrichment) builds against fixtures alongside P1; P4 (CredGPT LLM) and P6 (CIO execution) attach after P3.
- Integration point: P3 needs P1+P2 merged. Conflict surface is low (collectors are new files; P5/P6 touch the skill + a cron).

**Rough day map (aggressive, honest):** P0 Day 1 · P1 Day 1-2 · P2 Day 2-3 (parallel) · P3 Day 3-4 · P4 Day 4-5 (parallel) · P5 Day 5 · P6 Day 5-6 (parallel) · P7 Day 6-7 · full E2E dry-run + calibration pass Day 7. Built and validated before Jun 11.

---

## 6. Test and validation strategy

- **Unit:** each collector tested against **recorded fixtures** (capture a handful of real API responses once, replay in CI). No live calls in CI. Identity resolution collision tests. Orchestrator partial-failure tests.
- **Dogfood (the key to "validated before launch"):** build a **synthetic cohort** AND **backfill a past 3-day signup window** from real Amplitude data, then run the full orchestrator end-to-end against it before the real window exists. Proves the pipeline on real-shaped data and surfaces calibration issues early.
- **Calibration:** funnel thresholds + the 6 PMF success-metric mappings + "meaningful CredGPT message" classification get tuned on the dogfood/historical run, finalized live on the real cohort (the one thing that genuinely needs the real cohort).
- **Pre-deploy:** the artifact visual-QA smoke check stays manual (not boot) until needed; HTML path requires none of it.

---

## 7. Risks and external dependencies (the real constraints, not our build speed)

1. **API access actually working — the #1 external blocker.** Amplitude Export/Query API with the provisioned keys, and the **User 360 production base URL/cutover** (an open question in the prior plan). Confirm both Day 1; User 360 prod must be unblocked by the team or P2 stalls. This, not coding speed, is the schedule risk.
2. **Calibration needs real data.** Final funnel/metric tuning can only complete once signups exist (Jun 11+). Mitigated by dogfooding on historical data so only fine-tuning remains.
3. **Compliance on sends.** Email/push only; SMS blocked (A2P). During launch, sends stay **human-approved** — Alaska never autonomously emails real users mid-launch.
4. **Scale + rate limits.** ~1,000 users/day of enrichment. Reuse `user-profile-360/cache.py`, batch, backoff. Intake/enrichment must be re-runnable and reconcile late-arriving events.
5. **Image/runtime hygiene.** Deferring LibreOffice slims the launch image; no new boot-time execution without sign-off.

---

## 8. Working agreement (guardrails)

- Branch off current `origin/main` in an isolated worktree; one PR per phase; **stop for Abhinav's review; never auto-merge.**
- V5 stays on `alaska_pmf.db`. No edits to V4 skills/config/migrations. No conflict with the in-flight V4 work (Phase E, the docs branch).
- Tests with every phase. No live API calls in CI.
- No autonomous user-facing actions. CIO execution is gated + human-approved.
- Plan is living: update phase status here as PRs land.

---

## 9. Open decisions / what's needed from Abhinav

1. **Cohort window date** — one of Jun 11-13 / 12-14 / 13-15. Not a build blocker (we build window-agnostic; you set it at `create-cohort --activate`). Needed before the live run.
2. **Confirm API access Day 1** — Amplitude keys live? User 360 **production** base URL available? This is the real gate; please point me at whoever can confirm/unblock.
3. **Pace = full V5 before launch** — confirmed. Build everything, validate via dogfood, calibrate live.
4. **DOCX/PDF deferred** — confirmed. HTML cockpit only for launch; revisit printable memos post-cohort.

---

## 10. Definition of done (V5 complete)

A daily cron ingests the real cohort from Amplitude, enriches every user via User 360, computes funnel stages + case files + queues with evidence, runs deterministic + LLM CredGPT quality review, renders the team + founder HTML cockpit, posts a Slack summary with an artifact link, and supports human-approved Customer.io interventions with outcome tracking — running unattended, idempotently, with no PII in team artifacts, isolated from V4, and an end-cohort memo at the close. Validated end-to-end on a dogfood cohort before the window opens; calibrated on the real cohort during it.
