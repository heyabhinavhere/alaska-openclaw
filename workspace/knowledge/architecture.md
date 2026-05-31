# BON Credit — System Architecture

**Last updated:** 2026-05-29 by Abhinav
**Status:** Draft

---

## Purpose at BON

BON Credit is an AI financial advisor app for deep sub prime Americans. Users connect bank accounts and credit cards through Plaid. Identity is verified via Spinwheel (uses Equifax SMFA). Credit reports are pulled via Array (also Equifax). The AI chat (CredGPT) is the primary surface. Two pillars: Save Money and Manage Money.

This file describes the systems behind the app. For per-integration detail, see `integrations/`.

## High-level stack

```
┌─────────────────────────────────────────────────────────────────┐
│                          USER (mobile)                          │
│                       Flutter app (Pankaj)                      │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ REST / JWT
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                       BACKEND (Node.js)                         │
│                  Bonhq/bon_webservices (Nilesh)                 │
│   Express + Sequelize + PostgreSQL + Redis + Bull queues        │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                       CORE INTEGRATIONS                         │
│                                                                 │
│   Plaid      bank + card linking                                │
│   Array      credit reports (Equifax)                           │
│   Spinwheel  identity verification + credit card bill payments  │
│              (AutoPay and manual)                               │
│   MoneyLion  offers rail (cash advance, loans, cards)           │
│                                                                 │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                       AI LAYER (Python)                         │
│                Bonlife/BON-CredGPT (Sandeep)                    │
│           LangChain + LangGraph + Langfuse (observability)      │
│                                                                 │
│   Hub: Opportunity Engine, Trigger Monitor, Progress Tracker,   │
│        Conversational Agent (CredGPT)                           │
│   Spokes (current): Credit Report Analyzer, Budget Analyzer,    │
│                     Debt Payoff Analyzer, Savings Analyzer.     │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MESSAGING & ANALYTICS                        │
│   Customer.io  campaigns / push / email / SMS orchestration     │
│   Firebase Admin  direct push                                   │
│   SendGrid  transactional email (primary)                       │
│   Postmark  email backup                                        │
│   Twilio  SMS (A2P pending), primary                            │
│   Plivo  SMS backup                                             │
│   Amplitude  product analytics (primary)                        │
│   Mixpanel  source-of-user attribution (organic / web / ads)    │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              INFRASTRUCTURE (AWS, Sandeep owns)                 │
│   EKS (Kubernetes) ← ArgoCD (CD) ← ECR ← Jenkins (CI)           │
│   Terraform (Bonlife/BON-Terraform), EKS manifests (BON-EKS)    │
└─────────────────────────────────────────────────────────────────┘
```

**MoneyLion** (offers rail, shown under Core Integrations above) is **integration in progress — not yet live; no offers-rail data yet.** Don't compute against it or surface offers as available.

## Repository map

Nine repos across two GitHub orgs. **Read-only for Alaska.** Never push, merge, or branch. `integrations/github.md` is the canonical repo list + branch conventions; this table is a summary.

| Repo | Org | Owner | Purpose |
|---|---|---|---|
| `bon_app` | Bonhq | Pankaj | Flutter mobile app |
| `bon_webservices` | Bonhq | Nilesh | Node.js backend API |
| `Landingpage` | Bonhq | _TBD_ | Marketing website |
| `BON-CredGPT` | Bonlife | Sandeep | AI credit analysis engine |
| `Agentic-Dashboard` | Bonlife | Sandeep | Internal AI dashboard |
| `Agentic-Chat-UI` | Bonlife | Sandeep | Internal chat UI for testing |
| `BON-Terraform` | Bonlife | Sandeep | AWS infrastructure (Terraform) |
| `BON-EKS` | Bonlife | Sandeep | Kubernetes manifests + Helm |
| `BON-langfuse` | Bonlife | Sandeep | LLM observability (Langfuse) |

## Core data pipelines

### Pipeline A. Credit data (Spinwheel → Array → Equifax)

```
First time (onboarding):
  Spinwheel verifies identity, returns SSN + profile
    → Backend creates Array user with that SSN
    → Backend orders + retrieves first credit report from Array
    → User sees their credit score in-app

Ongoing (every ~20 days, cron):
  Array cron re-pulls credit report directly (no Spinwheel needed)

On-demand (rare):
  Spinwheel can do a real-time credit report pull. Currently used rarely.
```

Code: `src/controllers/spinwheel.controller.js`, `src/controllers/array.controller.js`.

### Pipeline B. Financial data (Plaid)

```
User completes Plaid Link UI
  → Backend exchanges public_token for access_token
  → Saves accounts + institution
  → Queues async sync jobs in Bull:
      • Transactions sync
      • Liabilities sync
      • Account sync
  → is_bank_added = true (or is_card_added)
```

Code: `src/controllers/plaid.controller.js`, `src/schedulers/{transactions,liabilities,accounts}/`.

### Pipeline C. Credit card bill payments (Spinwheel)

Two flows. Both go through Spinwheel.

**AutoPay (scheduled):**

```
User sets up AutoPay → backend creates spinwheel_payer + auto_pays row
  → Daily cron finds due payments
    → Bull queues each
      → Spinwheel /v1/payment API call
        → Webhook returns payment result → DB updated
```

**Manual payment (one-time):**

```
User initiates payment in-app → backend creates spinwheel_payment_request
  → Spinwheel /v1/payment API call
    → Webhook returns payment result → DB updated
```

Code: `src/db/models/AutoPays.model.js`, `src/schedulers/autopays/autopay.process.js`.

### Pipeline D. Analytics + attribution

```
App → Amplitude SDK → Amplitude (primary product analytics)
App → Mixpanel SDK → Mixpanel (source-of-user attribution: organic, website, ads, etc.)
App → Firebase Analytics → Firebase
```

Amplitude is the primary product analytics platform. Mixpanel is used specifically for attribution (where the user came from). Both are live and active. Note: Mixpanel is live for attribution **but NOT connected to Alaska — she has no Mixpanel access and does not read it; it is not dead code, just outside her data surface.**

## Backend internals (Node.js)

| Layer | Technology |
|---|---|
| Runtime | Node.js |
| Framework | Express.js |
| ORM | Sequelize (~75 models) |
| Database | PostgreSQL (SSL + connection pooling) |
| Cache | Redis |
| Job Queue | Bull (Redis-backed) |
| Auth | JWT (access + refresh), Phone OTP |
| Validation | Hapi/Joi |
| API docs | Swagger at `/v1/docs` |
| Logging | Winston + Morgan |
| Migration | Sequelize + Flyway (dual systems, known tech debt) |

Project structure rooted at `bon_webservices/src/`: controllers, services, db (models / migrations / seeders / config), routes (`v1/`), middlewares, jobs (cron), schedulers (Bull processors), validations, utils.

## AI layer (Python, separate repos)

- **Framework:** LangChain + LangGraph
- **Observability:** Langfuse
- **Architecture model:** hub-and-spoke. Created by Abhinav, delivered on April 3 2026.
- **Hub (feature-agnostic):** Opportunity Engine, Trigger Monitor, Progress Tracker, Conversational Agent. These rank, monitor, track, talk.
- **Spokes (feature-specific analyzers):** Credit Report Analyzer, Budget Analyzer, Debt Payoff Analyzer, Savings Analyzer. All current. Each spoke reads data, produces a profile/plan, feeds opportunity/trigger/progress types into the hub.
- **User data access:** Alaska has access to the complete user 360-degree profile API provided by Sandeep. Use that API when looking up any user's state across systems.

## Infrastructure & deployment

```
Push to bon_webservices
  → Jenkins (CI) builds Docker image
    → AWS ECR (container registry)
      → ArgoCD (CD) detects new image, deploys
        → AWS EKS (Kubernetes), runs containers
```

K8s manifests in `Bonlife/BON-EKS`. Infrastructure in `Bonlife/BON-Terraform`. **All infra owned by Sandeep.** Single-owner risk. No Dockerfiles in `bon_webservices` itself (separation of concerns).

## Auth methods

App users log in with phone number + 6-digit OTP. That's the only path for end users. Google OAuth and Apple OAuth are not present.

| Surface | Method | Use |
|---|---|---|
| App | Phone number + 6-digit OTP (`GET /auth/send-otp-phone` → `POST /auth/verify-otp-user`) | End users |
| Admin dashboard | `POST /auth/admin-login` (email + password) | Internal admin |
| Employee dashboard | `POST /auth/employee-login` (email + password) | Internal team |

RBAC model for internal dashboards: `role` → `role_permissions` → `(page_id, can_view, can_edit, can_delete)`. Enforced by `permission(page_ids, action)` middleware (`src/middlewares/adminDashboard.js`).

Known auth tech debt lives in `playbooks/failure-modes.md` (unprotected routes, dead admin auth middleware, token logging in production).

## How Customer.io is triggered

CIO has 27 notification types across 6 categories: Transactional (payment due, score change), Re-Engagement (dormant users), Credit Score Alerts, Proactive Insights (savings opportunities), Referral, Feature Discovery.

Triggering is **mixed, not external-only**. Three sources fire events into CIO:

1. **App-side** via the Customer.io SDK and Track API. User-action events (chat open, screen view, button tap) and basic identify calls.
2. **Backend-side** via Track API. Transactional and time-driven events that the app cannot detect: payment-due reminders (Bull cron), score-change alerts (Array cron), AutoPay execution results (webhook), dormant-user re-engagement (cron evaluating last-active), proactive insights from CredGPT.
3. **CIO dashboard.** Campaigns themselves (segments, message templates, send schedules, frequency caps) are configured in the CIO admin UI. The code does not define what gets sent. It only fires the events that trigger sends.

Frequency caps live in CIO: max 1 push/day, max 3 emails/week, SMS limited to 2-3/day with no links.

Push notifications are delivered through the Customer.io SDK embedded in the app. Email goes through SendGrid (primary) or Postmark (backup). SMS goes through Twilio (primary) or Plivo (backup), pending A2P clearance.

For full CIO behavior see `integrations/customerio.md`.

## What's NOT in the backend

- **Amplitude** events fire from the Flutter app directly. No Amplitude-write code in backend.
- **AI layer** is a separate service in `BON-CredGPT`. Backend exposes data the AI reads (DB access or API). Agent logic is Python, not Node.
- **CIO campaign definitions** live in the CIO dashboard. Backend only fires events.

## Definitions used across the team

- **"Hub"** = the 4 feature-agnostic AI modules (Opportunity, Trigger, Progress, Conversational). Never changes when a new feature lands.
- **"Spoke"** = a feature-specific analyzer that plugs into the hub. Reads data, produces a profile/plan, emits opportunities/triggers/progress.
- **"AfterSpinwheel"** = code paths that run as part of the Spinwheel chain (auto-create Array user, order + retrieve first report).
- **"20-day refresh"** = the Array cron cadence for ongoing credit-report pulls.
- **"User 360 profile"** = the consolidated user-state API Sandeep provides. Alaska's primary read surface for any user lookup.

## Known failure modes / edge cases

- **Sequelize + Flyway dual migration system.** Two source-of-truth schemas can drift. Tech debt.
- **Two SMS providers (Twilio primary, Plivo backup).** Failover is intentional. Don't double-send.
- **Two email providers (SendGrid primary, Postmark backup).** Failover is intentional.
- **Push notification delivery is low.** Backend fix deployed; root cause is iOS permission opt-in. See `integrations/customerio.md` and `playbooks/failure-modes.md`.
- **Plaid card linking has historically high drop-off.** Matching engine improvements landed in May 2026. See `integrations/plaid.md`.

## Common queries / patterns

| Need | Where |
|---|---|
| User schema and state flags | `integrations/user-profile-api.md` |
| What counts as a "real user" | `integrations/amplitude.md` § Real Users filter |
| What counts as a "failed Plaid user" | `integrations/plaid.md` § Definitions |
| Onboarding funnel definition | `definitions/lifecycle-events.md` |
| Canonical metric formulas | `definitions/metrics.md` |
| Common Amplitude/CIO query patterns | `playbooks/common-queries.md` |
| User lookup across systems | Use the User 360 profile API (Sandeep) |

## People

- **Product & design:** Abhinav
- **Backend (Node.js):** Nilesh
- **Frontend (Flutter):** Pankaj
- **AI layer + infra (Python, K8s, Terraform):** Sandeep
- **AI development support:** Shailesh
- **QA:** Tarun
- **Co-founder, Marketing/GTM/partnerships:** Samder
- **Co-founder, Ops/strategy:** Darwin
