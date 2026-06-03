# Alaska V5 — PMF Cohort Operating System Plan

> **⚠️ SUPERSEDED (2026-06-03)** by [`2026-06-03-alaska-v5-master-plan.md`](2026-06-03-alaska-v5-master-plan.md). This doc captured the #59-#64 foundation. The master plan reprioritizes the remaining work around the data pipeline (collectors + orchestrator) and the full build-before-launch sequence. Kept for history.

**Date:** 2026-06-02  
**Status:** In progress. Foundation merged in PR #59; DocFlow artifact contract added in the follow-up artifact slice.
**Canonical runtime contract:** `workspace/knowledge/definitions/pmf-cohort-os.md`  
**Runtime skill:** `skills/pmf-cohort-os/SKILL.md`  

---

## Executive Summary

Alaska V5 is the **PMF Cohort Operating System** for BON's first focused V2 launch cohort. This is the headline of the V5 era and the most important Alaska work right now.

The goal is not another dashboard. The goal is an operating layer that lets Alaska track, understand, and act on one selected 3-day signup cohort at user-level depth. PMF OS sits inside the larger horizontal AI-coworker arc: Alaska should eventually feel like "the rest of your startup team." V5 is not saying Alaska is only ever a cohort tool; it is saying the current V5 focus is the PMF cohort job.

PR #59 completed the **foundation layer**:

- PMF SQLite tables.
- PMF OS Python core and CLI.
- cohort registry primitives.
- PMF Funnel engine.
- user case-file builder.
- operating queue primitives.
- CredGPT Quality Observatory deterministic layer.
- Customer.io approval/safety gate.
- HTML/DOCX/PDF artifact scaffolding.
- `pmf-cohort-os` skill and KB contract.
- focused tests.

PR #59 does **not** mean the PMF OS track is production-complete. Live Amplitude extraction, User 360 enrichment, Slack delivery, polished report templates, live CredGPT ingestion, LLM judging, Customer.io execution, and end-cohort intelligence still need follow-up PRs. Artifact runtime changes also require a deploy-time smoke check before DOCX/PDF delivery.

---

## Product Scope Boundary

Use this scope unless Abhinav changes it explicitly:

- **V5 = PMF Cohort Operating System.** It is the current top-priority focus and headline of the V5 era.
- **Bigger product arc = horizontal AI coworker / the rest of your startup team.** PMF OS lives inside this arc; it does not delete or exhaust it.
- **KB self-maintenance agent = deferred V4 capstone.** It belongs to the V4 Watchers/KB track, not the V5/PMF track. It should be built only after V4 live validation plus Ops-4 tasks-landing proof, and after Phase E cutover is activated.

Do not route KB self-maintenance work through this PMF OS plan. Keep this plan focused on cohort operation.

---

## Business Context

BON is preparing a V2 app launch and a PMF cohort push. The cohort will be a configurable 3-day signup window, likely around June 2026. Exact dates are chosen at activation time.

Planning assumptions:

- target: roughly 1,000 signups;
- expected real users: roughly 750;
- real user = onboarding complete plus credit score greater than zero;
- only users entering during the selected 3-day window enter this V5 cohort registry;
- users before/after the selected window are excluded from this cohort.

The core operating problem: humans cannot track 1,000 users at sufficient depth across onboarding, financial state, CredGPT interactions, campaign touches, product friction, intent, retention, and qualitative love signals. Alaska should become the active PMF operator.

---

## System Boundary

Alaska owns PMF operating truth.

| System | Role |
|---|---|
| Amplitude | event truth: signup, onboarding, activity, linking, chat events, feedback |
| User 360 API | per-user context: profile, credit, Plaid, income, subscriptions, chat history |
| Customer.io | approved email/push execution and delivery metrics |
| Slack | notification layer only |
| Alaska SQLite | registry, stages, evidence, queues, reports, recommendations |
| Artifacts | HTML/DOCX/PDF reporting surface |

Customer.io is not the PMF brain. Slack is not the reporting surface for large tables. Alaska should send concise Slack summaries plus artifact links/files.

PMF OS uses a separate SQLite database by default: `/data/queue/alaska_pmf.db`. V4 remains on `/data/queue/alaska.db`. Do not run live PMF intake against the V4 database unless Abhinav explicitly accepts the contention/blast-radius risk.

---

## PMF Funnel

1. **Signed Up**
   - User entered the selected 3-day signup window.

2. **Onboarded Real User**
   - User completed onboarding and has `credit_score > 0`.

3. **Activated User**
   - Real user performed a meaningful value action:
     - 3+ meaningful CredGPT messages, excluding greetings/logistics;
     - or 2 high-intent financial questions with usable responses;
     - or successful card/bank link;
     - or strategy, budget, paydown, autopay, or another personalized financial action.
   - Failed linking alone creates high intent, not activation.

4. **Activated Saver**
   - `computed`: clean evidence for at least 2 of the 6 PMF success metrics.
   - `candidate`: promising evidence exists, but one or more metrics need review or better instrumentation.
   - Computed and candidate must remain separate in data, reports, and language.

5. **Likely Lover**
   - Activated Saver computed/candidate plus repeated return or engagement across days, with no strong negative signal.

6. **Confirmed Lover**
   - Explicit proof only: Sean Ellis/NPS/survey, interview/manual audit tag, or a clear user quote that BON helped them.

---

## Operating Queues

V5 queues:

- `stuck_onboarding`
- `spinwheel_stuck`
- `plaid_failed`
- `high_intent`
- `at_risk`
- `potential_lover`
- `needs_human_review`
- `weak_credgpt_response`
- `repeated_product_model_issue_cluster`

`stuck_onboarding` and `spinwheel_stuck` are intake-only queues. They matter during the signup window and immediate post-signup period, not throughout the whole cohort lifecycle.

---

## CredGPT Quality Observatory

CredGPT quality is a dedicated subsystem inside PMF OS, not a generic note in user analytics.

Inputs:

- User 360 `chat.recent_turns`;
- Amplitude `chat_thread_processed`;
- `credgpt_message_sent`;
- `ai_chat_feedback_good`;
- `ai_chat_feedback_bad`;
- `chat_stopped_by_user`;
- post-response behavior.

Coverage:

- ingest all cohort chat turns;
- run deterministic checks on all turns;
- run LLM review only on selected turns: flagged, high-intent, bad-feedback, interrupted, or dropoff-adjacent.

Rubric:

- correctness;
- data grounding;
- personalization;
- usefulness/actionability;
- clarity;
- empathy/trust;
- next-step quality;
- hallucination/unsafe advice risk;
- PMF usefulness.

Phase 1 output is internal only: case-file annotations, product/model issue clusters, and internal recommendations/tasks. Do not send user-facing interventions from CredGPT quality findings.

---

## Artifact Strategy

Human-facing reporting should not live in huge Slack messages.

Artifact targets:

- daily cockpit: HTML;
- weekly PMF review: HTML + PDF;
- end-cohort memo: DOCX + PDF;
- user research / lover case studies: DOCX + PDF;
- product/model issue reports: DOCX for editing, PDF for archive.

Privacy tiers:

- team report: aggregate/redacted;
- founder/Abhinav report: user-level detail and case files.

The artifact contract is now:

1. build a structured `report_snapshot.json`;
2. derive a renderer-neutral `*.docflow.json` spec;
3. render HTML/DOCX/PDF from those structured inputs;
4. store all paths in `pmf_report_runs.file_refs_json`;
5. gate delivery with structural QA plus visual render QA for DOCX/PDF.

The production artifact runtime must include LibreOffice/`soffice` and Poppler/`pdftoppm`. After deploy, run `python3 /opt/lib/pmf_artifact_runtime_check.py` through Railway SSH or an equivalent container shell. DOCX/PDF are not deliverable until that smoke check returns `"ok": true`.

The user added a stronger `Artifacts and docx/docflow-agent` package after PR #59. The implementation adopted the DocFlow spec pattern without copying the package wholesale because it includes generated examples, temp files, a zip, and `node_modules`, and because the production image does not yet install the package's optional `docx`/`reportlab` runtime dependencies.

---

## Phase Status

| Phase | Name | Status | What PR #59 did | Remaining work |
|---|---|---|---|---|
| 0 | Contracts and guardrails | Mostly done | schema, PMF rules, privacy tiers, Customer.io boundary, CredGPT rubric, skill/KB contract | production calibration against live data |
| 1 | Cohort Registry | Partially done | tables, CLI, batch signup ingestion, date-window exclusion | live Amplitude extraction, activation workflow, cron/manual operator path |
| 2 | Signal Spine and Case Files | Partially done | normalized fact/evidence tables, case-file builder | full Amplitude/User 360/Customer.io normalizers |
| 3 | PMF Funnel Engine | Mostly done | deterministic engine and tests | calibrate against real data and finalize metric mapping |
| 4 | Artifact Generation | Partially done | structured snapshot, DocFlow spec, runtime visual-QA packages, smoke check, HTML, DOCX/PDF, QA gates | deploy-time smoke check, Slack file/link delivery, polished templates, richer document renderers if runtime deps are approved |
| 5 | Customer.io Execution | Guardrails done | validation/approval gate | live segment/attribute sync, email/push execution, outcome tracking |
| 6 | CredGPT Quality Observatory | Partially done | deterministic review, queue creation, clustering | live chat ingestion, selected LLM judging, optional Langfuse phase |
| 7 | End-Cohort Intelligence | Not started | storage/report foundation only | final memo, lover list, dropoff analysis, roadmap implications |

---

## Follow-Up Sequence

### Completed: PR #60 — V5 Documentation and Roadmap

Goal: make V5 understandable to a new session/agent.

Scope:

- add this plan;
- update `docs/ROADMAP.md`;
- update `workspace/MEMORY.md` with the V5 PMF OS entry point.

### Completed: PR #61 — Review Follow-Ups

Goal: harden the inert foundation before live intake.

Scope:

- separate PMF DB default from V4's SQLite database;
- preserve resolved CredGPT clusters;
- prevent partial daily snapshots from demoting users;
- make deterministic CredGPT checks explicit triage, not a safety net;
- tighten artifact privacy and QA temp handling;
- add regression tests for review findings.

### In review: PR #62 — V5 Framing Reconciliation

Goal: make the product story unambiguous.

Scope:

- V5 = PMF Cohort Operating System;
- PMF OS sits inside the larger AI-coworker arc;
- KB self-maintenance moves to deferred V4 capstone after V4 validation plus Phase E cutover.

### Current Artifact Slice — DocFlow Spec Integration

Goal: make DocFlow the stable intermediate contract for V5 PMF artifacts without importing generated sample files or runtime-heavy dependencies.

Scope:

- generate a private `*.docflow.json` file for each report run;
- render DOCX/PDF from that shared report spec;
- preserve HTML as self-contained and CDN-free;
- record snapshot/spec/HTML/DOCX/PDF paths in `pmf_report_runs.file_refs_json`;
- exclude `.DS_Store`, generated examples, temp files, zips, and `node_modules`;
- keep visual QA gating for DOCX/PDF.

### Current Runtime Slice — Artifact Runtime Verification

Goal: make the DOCX/PDF delivery gate pass in the deployed Railway container, not only in theory.

Scope:

- install LibreOffice/`soffice` and Poppler/`pdftoppm` in the Docker image;
- add a runtime smoke check that renders PMF DOCX/PDF artifacts and runs visual QA;
- verify the smoke check through Railway SSH after deploy;
- keep HTML deliverable even if DOCX/PDF are awaiting visual QA;
- record any image-size/cold-start impact before moving to live cohort intake.

### Planned — Live Cohort Intake

Goal: populate the cohort registry from real Amplitude data.

Scope:

- query `onboarding_step_completed` / `phone_number_submitted` for selected 3-day window;
- no Real Users filter on intake;
- batch ingest JSONL;
- activation command/runbook;
- idempotency and exclusion reporting.

### Planned — User 360 Enrichment and Case Files

Goal: turn the registry into living user case files.

Scope:

- resolve BON `user_id`;
- pull profile, credit, Plaid, income, subscriptions, chat;
- normalize profile facts;
- generate daily snapshots;
- preserve evidence for every derived claim.

### Planned — Daily Cockpit Delivery

Goal: make daily reporting usable by the team.

Scope:

- team HTML cockpit;
- founder detailed report;
- short Slack summary plus artifact file/link;
- no PII in team artifacts;
- report metadata in `pmf_report_runs`.

### Planned — CredGPT Live Observability

Goal: evaluate actual cohort chat quality.

Scope:

- ingest turns from User 360 and Amplitude fallback;
- run deterministic review on all turns;
- add selected LLM review;
- create clusters and internal recommendations;
- annotate case files.

### Planned — Customer.io Execution Layer

Goal: execute approved email/push interventions safely.

Scope:

- approved cohort/wave/queue segments or attributes;
- dry-run previews;
- suppression checks;
- email/push execution only;
- delivery/open/click/conversion outcome tracking.

### Planned — End-Cohort Intelligence

Goal: generate the final PMF cohort memo and next-cohort recommendations.

Scope:

- final PMF Funnel report;
- likely/confirmed lover evidence;
- stuck/dropoff analysis;
- CredGPT quality analysis;
- intervention outcomes;
- product/model/campaign roadmap implications.

---

## Files Added in PR #59

Core:

- `migrations/0005_pmf_cohort_os.sql`
- `lib/pmf_cohort_os.py`
- `lib/pmf_os/__init__.py`
- `lib/pmf_os/model.py`
- `lib/pmf_os/store.py`
- `lib/pmf_os/funnel.py`
- `lib/pmf_os/credgpt_quality.py`
- `lib/pmf_os/customerio_guard.py`
- `lib/pmf_os/artifacts.py`

Alaska-facing:

- `skills/pmf-cohort-os/SKILL.md`
- `workspace/knowledge/definitions/pmf-cohort-os.md`

Tests:

- `tests/test_pmf_cohort_os.py`

---

## How a New Agent Should Resume

1. Read this file first.
2. Read `workspace/knowledge/definitions/pmf-cohort-os.md`.
3. Read `skills/pmf-cohort-os/SKILL.md`.
4. Inspect PR #59 / commit `9a67db4` for the foundation implementation.
5. Do not assume V5 is production-complete. Treat PR #59 as the foundation.
6. Choose the next PR from the sequence above.
7. Avoid touching V4 Phase E / live-testing changes unless the current task explicitly requires it.

Current recommended next PR after the artifact runtime slice is deployed and the smoke check passes: **Live Cohort Intake**.

---

## Open Questions

- Exact cohort window: not final. Could be June 11-13, 12-14, 13-15, or 14-16.
- Exact six PMF success metrics: existing metrics doc has the current basis, but some need instrumentation review.
- User 360 production base URL/cutover must be confirmed before live cohort enrichment.
- Slack file upload availability should be verified in production; fallback is a short Slack summary plus persistent artifact link.
- In-app messaging and Langfuse remain Phase 2 unless they become ready earlier.
