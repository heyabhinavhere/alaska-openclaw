# Alaska V5 — PMF Cohort Operating System Plan

**Date:** 2026-06-02  
**Status:** In progress. Foundation merged in PR #59.  
**Canonical runtime contract:** `workspace/knowledge/definitions/pmf-cohort-os.md`  
**Runtime skill:** `skills/pmf-cohort-os/SKILL.md`  

---

## Executive Summary

Alaska V5 is being built as the **PMF Cohort Operating System** for BON's first focused V2 launch cohort. The goal is not another dashboard. The goal is an operating layer that lets Alaska track, understand, and act on one selected 3-day signup cohort at user-level depth.

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

PR #59 does **not** mean V5 is production-complete. Live Amplitude extraction, User 360 enrichment, Slack delivery, DocFlow artifact integration, live CredGPT ingestion, LLM judging, Customer.io execution, and end-cohort intelligence still need follow-up PRs.

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

PR #59 includes a lightweight stdlib artifact renderer. The user added a stronger `Artifacts and docx/docflow-agent` package after PR #59. That package should be integrated in a follow-up PR rather than copied wholesale because it includes generated examples, temp files, a zip, and `node_modules`.

---

## Phase Status

| Phase | Name | Status | What PR #59 did | Remaining work |
|---|---|---|---|---|
| 0 | Contracts and guardrails | Mostly done | schema, PMF rules, privacy tiers, Customer.io boundary, CredGPT rubric, skill/KB contract | add DocFlow docs renderer contract; update roadmap/memory docs |
| 1 | Cohort Registry | Partially done | tables, CLI, batch signup ingestion, date-window exclusion | live Amplitude extraction, activation workflow, cron/manual operator path |
| 2 | Signal Spine and Case Files | Partially done | normalized fact/evidence tables, case-file builder | full Amplitude/User 360/Customer.io normalizers |
| 3 | PMF Funnel Engine | Mostly done | deterministic engine and tests | calibrate against real data and finalize metric mapping |
| 4 | Artifact Generation | Partially done | structured snapshot, HTML, lightweight DOCX/PDF, QA gates | integrate DocFlow, Slack file/link delivery, polished templates |
| 5 | Customer.io Execution | Guardrails done | validation/approval gate | live segment/attribute sync, email/push execution, outcome tracking |
| 6 | CredGPT Quality Observatory | Partially done | deterministic review, queue creation, clustering | live chat ingestion, selected LLM judging, optional Langfuse phase |
| 7 | End-Cohort Intelligence | Not started | storage/report foundation only | final memo, lover list, dropoff analysis, roadmap implications |

---

## Follow-Up PR Sequence

### PR #60 — V5 Documentation and Roadmap

Goal: make V5 understandable to a new session/agent.

Scope:

- add this plan;
- update `docs/ROADMAP.md`;
- update `workspace/MEMORY.md` with the V5 PMF OS entry point.

### PR #61 — DocFlow Artifact Integration

Goal: replace/augment the lightweight DOCX/PDF renderer with the stronger DocFlow spec-based renderer.

Scope:

- cleanly import only required DocFlow files;
- exclude `.DS_Store`, generated examples, temp files, zips, and `node_modules`;
- decide dependency installation strategy for `docx` and `reportlab`;
- render DOCX/PDF from a shared report spec;
- preserve visual QA gating.

### PR #62 — Live Cohort Intake

Goal: populate the cohort registry from real Amplitude data.

Scope:

- query `onboarding_step_completed` / `phone_number_submitted` for selected 3-day window;
- no Real Users filter on intake;
- batch ingest JSONL;
- activation command/runbook;
- idempotency and exclusion reporting.

### PR #63 — User 360 Enrichment and Case Files

Goal: turn the registry into living user case files.

Scope:

- resolve BON `user_id`;
- pull profile, credit, Plaid, income, subscriptions, chat;
- normalize profile facts;
- generate daily snapshots;
- preserve evidence for every derived claim.

### PR #64 — Daily Cockpit Delivery

Goal: make daily reporting usable by the team.

Scope:

- team HTML cockpit;
- founder detailed report;
- short Slack summary plus artifact file/link;
- no PII in team artifacts;
- report metadata in `pmf_report_runs`.

### PR #65 — CredGPT Live Observability

Goal: evaluate actual cohort chat quality.

Scope:

- ingest turns from User 360 and Amplitude fallback;
- run deterministic review on all turns;
- add selected LLM review;
- create clusters and internal recommendations;
- annotate case files.

### PR #66 — Customer.io Execution Layer

Goal: execute approved email/push interventions safely.

Scope:

- approved cohort/wave/queue segments or attributes;
- dry-run previews;
- suppression checks;
- email/push execution only;
- delivery/open/click/conversion outcome tracking.

### PR #67 — End-Cohort Intelligence

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

Current recommended next PR: **DocFlow Artifact Integration**.

---

## Open Questions

- Exact cohort window: not final. Could be June 11-13, 12-14, 13-15, or 14-16.
- Exact six PMF success metrics: existing metrics doc has the current basis, but some need instrumentation review.
- User 360 production base URL/cutover must be confirmed before live cohort enrichment.
- Slack file upload availability should be verified in production; fallback is a short Slack summary plus persistent artifact link.
- In-app messaging and Langfuse remain Phase 2 unless they become ready earlier.
