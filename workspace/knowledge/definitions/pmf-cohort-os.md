# PMF Cohort Operating System

**Status:** V5 implementation contract  
**Owner:** Alaska / Abhinav  

This file is the canonical operating definition for Alaska V5's first PMF cohort system. It complements the runtime skill `pmf-cohort-os`.

Implementation phase tracker: `docs/superpowers/plans/2026-06-02-alaska-v5-pmf-cohort-os.md`.

## Cohort Scope

- One active PMF cohort at a time in V5 Phase 1.
- The cohort is defined by one configurable 3-day signup window.
- Cohort entry is Amplitude `onboarding_step_completed` with `step_name=phone_number_submitted`.
- Users before or after the selected window are excluded from the cohort registry.
- Real user means onboarding complete plus credit score greater than zero.

## Funnel Stages

1. `signed_up`: entered the selected signup window.
2. `onboarded_real_user`: completed onboarding and has credit score greater than zero.
3. `activated_user`: real user with 3+ meaningful CredGPT messages, or 2 high-intent usable Q&As, or a qualifying value action such as card/bank link, strategy, budget, paydown, autopay, or another personalized financial action.
4. `activated_saver`: activated user with PMF success metric evidence.
   - `computed`: at least 2 confirmed PMF success metrics.
   - `candidate`: at least 2 combined confirmed/candidate PMF success metrics but instrumentation or review is incomplete.
5. `likely_lover`: Activated Saver plus repeated engagement across days and no strong negative signal.
6. `confirmed_lover`: explicit proof only: survey, interview/manual audit, or clear quote that BON helped.

Failed linking creates high intent and may open an operating queue, but does not count as activation by itself.

## Operating Queues

- `stuck_onboarding`
- `spinwheel_stuck`
- `plaid_failed`
- `high_intent`
- `at_risk`
- `potential_lover`
- `needs_human_review`
- `weak_credgpt_response`
- `repeated_product_model_issue_cluster`

`stuck_onboarding` and `spinwheel_stuck` are intake-only queues and should be emphasized during the signup window and immediate post-signup period.

## CredGPT Quality Observatory

Coverage:

- Ingest all cohort chat turns.
- Run deterministic checks on all turns.
- Select LLM review for flagged, high-intent, bad-feedback, interrupted, or dropoff-adjacent turns.

Rubric:

- correctness
- data grounding
- personalization
- usefulness/actionability
- clarity
- empathy/trust
- next-step quality
- hallucination/unsafe advice risk
- PMF usefulness

Phase 1 output is internal only: product/model recommendations, case-file annotations, and issue clusters. Do not send user-facing interventions from CredGPT quality findings.

## Customer.io Boundary

Customer.io is the execution layer, not the PMF brain.

Allowed in Phase 1:

- email
- push
- approved cohort/wave/queue attributes or static segment support

Blocked in Phase 1:

- SMS, because A2P is not approved
- in-app messaging, unless the app/CIO provisioning is confirmed later

Every Customer.io write requires explicit approval, dry-run, audience preview, suppression check, and outcome tracking.

## Artifact Standards

- Daily cockpit: HTML.
- Weekly PMF review: HTML + PDF.
- End-cohort memo: DOCX + PDF.
- User research/lovers: DOCX + PDF.
- Product/model issue reports: DOCX for editing, PDF for archive.

Team artifacts are aggregate/redacted. Founder artifacts may contain user-level detail and case files. No public hosting of PII artifacts.

DOCX/PDF files must pass visual render QA before delivery. If render tooling is unavailable, HTML may still be delivered and DOCX/PDF should remain in rendered/awaiting-QA state.
