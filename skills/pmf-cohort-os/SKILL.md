---
name: pmf-cohort-os
description: Alaska V5 PMF Cohort Operating System — configurable 3-day signup cohort registry, PMF Funnel, user case files, CredGPT quality observatory, rich artifacts, and Customer.io approval packs
version: 0.1.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3, python3]
      env: [AMPLITUDE_API_KEY, AMPLITUDE_SECRET_KEY, BON_ADMIN_API_KEY, BON_API_BASE_URL, CUSTOMERIO_APP_API_KEY, ANTHROPIC_API_KEY]
    emoji: "🧭"
---

# PMF Cohort OS

Alaska V5 operates one configurable 3-day PMF signup cohort. This skill is the operating wrapper around `/opt/lib/pmf_cohort_os.py` and the SQLite tables from migration `0005_pmf_cohort_os.sql`.

Use this skill when:
- Abhinav asks to activate or inspect the PMF cohort.
- The team asks for the daily PMF cockpit, founder report, operating queues, likely lovers, or stuck users.
- Alaska needs to explain a user's PMF Funnel stage with evidence.
- Alaska needs a Customer.io email/push approval pack for cohort users.
- Alaska needs to review CredGPT response quality for cohort users.

Do **not** use this skill for ordinary Alaska task tracking. `task-handler` remains the sole writer of team task tables.

## `!pmf` — the PMF query mode

This skill owns the **`!pmf`** command (legacy `/pmf` alias also works) — the user-facing signal for a PMF-cohort question (e.g. `!pmf what's up with user 2903`, `!pmf who are the likely lovers`, `!pmf show the cockpit`). `SOUL.md` → "STEP 0 — Command Router" routes the `!pmf` verb here. **A *bare* `pmf …` WITHOUT the `!` is NOT a trigger** — "pmf is strong this week" is normal chat, not a command; don't run this skill for it. Answer **only** from the PMF source set, grounded, and never blend in the default 360/Amplitude user-intel read (that is a different lens):

- **Source set:** the PMF store (`alaska_pmf.db` — registry, daily snapshots, **case files**, funnel, operating queues, interventions), end-of-cohort survey responses, PMF Watchers, and `workspace/knowledge/definitions/pmf-cohort-os.md`.
- **If no cohort is active** (or the user isn't a cohort member), say so plainly — do NOT invent a funnel stage or case file. You may still give their raw 360 read separately if asked, but label it as such.
- Per-user PMF detail (the case file) is founder-grade operational info the whole team may see; the aggregate daily Slack line stays aggregate.

**`!pmf tell me about user <id>`** → fetch their case file and render it with your read:
```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db case-file --bon-user-id <id>
```
`--cohort-id` defaults to the active cohort; pass `--user-key user:<id>` if you have it. The result is the structured case file (identity, onboarding, linked accounts, financial context, activity, CredGPT, **funnel stage + evidence**, interventions). Compose a tight Slack message from it — lead with the stage + what's notable + what to do; first names, exact numbers, no JSON dump. If `case_file` is null, say so plainly (not in this cohort, or no daily run has populated it yet) — never invent a stage. Grounded in the PMF store; don't blend the default 360/Amplitude read into a `!pmf` answer.

## Operating Truth

- Alaska owns PMF operating truth in SQLite.
- Amplitude supplies event truth.
- User 360 enriches user case files.
- Customer.io executes approved email/push campaigns only.
- Slack is a notification layer.
- HTML/DOCX/PDF artifacts are the human-facing reporting layer.

## Hard Rules

1. Cohort entry is `phone_number_submitted` during the selected 3-day signup window.
2. Users before/after the selected window do not enter the cohort registry.
3. Real user = onboarding complete plus credit score greater than zero.
4. Failed linking alone creates high intent, not activation.
5. Activated Saver `computed` and `candidate` are separate. Do not merge them in summaries.
6. Confirmed Lover requires explicit proof only: survey, interview/manual audit, or a clear user quote.
7. SMS is blocked in Phase 1 because A2P is not approved.
8. Customer.io mutations require approval, dry-run, audience preview, and suppression check.
9. CredGPT quality findings create internal product/model work only in Phase 1. Do not send user-facing interventions from CredGPT quality flags.
10. Team reports must be aggregate/redacted. Founder reports may include user-level case files.
11. DOCX/PDF artifacts must pass visual render QA before delivery. If render tooling is unavailable, do not mark those files delivered; send the HTML cockpit and note that DOCX/PDF are rendered but awaiting visual QA.

## Database Boundary

PMF OS defaults to `/data/queue/alaska_pmf.db`, not the V4 task/watchers database. This isolates high-volume cohort snapshots, signal facts, and chat reviews from the live V4 graph in `/data/queue/alaska.db`.

The boot entrypoint migrates the PMF DB on deploy. Operators can override the path with `$PMF_DB_PATH`, but do not point PMF live intake at `alaska.db` unless Abhinav explicitly approves the contention risk.

## CLI Pattern

All commands return JSON. Use `/data/queue/alaska_pmf.db` in production, or omit `--db` and let the CLI use `$PMF_DB_PATH` / the PMF default.

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db <command> ...
```

In local repo tests or manual development, use:

```bash
python3 lib/pmf_cohort_os.py --db /tmp/alaska-pmf.db <command> ...
```

## Activate a Cohort

No hardcoded dates. Abhinav chooses the window.

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db create-cohort \
  --cohort-id pmf-2026-06-wave-1 \
  --name "PMF Cohort Wave 1" \
  --signup-window-start "2026-06-11T00:00:00-07:00" \
  --signup-window-end "2026-06-13T23:59:59-07:00" \
  --expected-signups 1000 \
  --expected-real-users 750 \
  --created-by "$SLACK_USER_ID" \
  --activate
```

The CLI rejects windows longer than 3 days.

## Daily Ingest Flow

1. Query Amplitude for `onboarding_step_completed` with `step_name=phone_number_submitted` for the cohort window. Do not apply the Real Users filter to this intake query.
2. Write matching events as a JSON array or JSONL file under `/tmp` and call `ingest-signups-file`.
3. Resolve `bon_user_id` when available via Amplitude `gp:user_id` or User 360 search.
4. Pull User 360 sections needed for case files: `profile`, `credit_report_history`, `tradeline_history`, `plaid_profiles`, `plaid_income`, `subscriptions`, `chat.recent_turns`, `chat.feedback_summary`.
5. Call `update-profile` for resolved users.
6. Build normalized daily facts and call `snapshot-user`.
7. Ingest all cohort CredGPT turns and call `review-credgpt-turn`.
8. Call `refresh-credgpt-clusters`.
9. Render reports.

## Ingest a Signup Event

Batch path for cohort intake:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db ingest-signups-file \
  --cohort-id pmf-2026-06-wave-1 \
  --events-file /tmp/pmf-signup-events.jsonl
```

Single-event debugging path:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db ingest-signup \
  --cohort-id pmf-2026-06-wave-1 \
  --event-json '{"event_type":"onboarding_step_completed","step_name":"phone_number_submitted","event_time":"2026-06-11T10:15:00-07:00","user_id":"2714","user_properties":{"gp:first_name":"Asha","gp:email":"asha@example.com","gp:phone_number":"+15551234567"}}'
```

Out-of-window users return `status=excluded` and are not written.

## Snapshot Facts Contract

`snapshot-user` accepts a JSON object with these stable keys:

```json
{
  "onboarding_complete": true,
  "credit_score": 712,
  "meaningful_credgpt_messages": 3,
  "high_intent_usable_qas": 1,
  "value_actions": ["card_link_success"],
  "failed_link_attempts": [],
  "pmf_success_metrics": {
    "activation_depth": "confirmed",
    "repeat_engagement": "candidate",
    "financial_action": false,
    "linked_financial_context": "confirmed",
    "qualitative_positive_signal": false,
    "retained_value": false
  },
  "active_days": ["2026-06-11", "2026-06-12"],
  "inactive_days": 0,
  "explicit_love_proof": false,
  "negative_signals": [],
  "profile_summary": {},
  "financial_context": {},
  "credgpt": {},
  "product_learning_tags": []
}
```

PMF Funnel rules:
- `activated_user`: 3+ meaningful CredGPT messages, or 2 high-intent usable Q&As, or a qualifying value action.
- `activated_saver/computed`: 2+ confirmed PMF success metrics.
- `activated_saver/candidate`: 2+ combined confirmed/candidate PMF success metrics but insufficient clean evidence.
- `likely_lover`: Activated Saver plus repeated engagement across days and no strong negative signal.
- `confirmed_lover`: explicit proof only.

## CredGPT Quality Review

For every cohort chat turn from User 360 `chat.recent_turns` or Amplitude `chat_thread_processed`:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db review-credgpt-turn \
  --cohort-id pmf-2026-06-wave-1 \
  --user-key user:2714 \
  --turn-json '{"thread_id":"t1","turn_id":"t1-1","event_time":"2026-06-12T18:00:00Z","question":"How should I pay down my cards?","answer":"...","feedback":null,"chat_stopped_by_user":false,"dropoff_adjacent":false,"user_context_present":true}'
```

The deterministic layer flags weak, unsafe, ungrounded, interrupted, bad-feedback, and dropoff-adjacent turns and SELECTS them for review (`needs_llm_review=1`, `llm_review_status='pending'`). Run the LLM quality/safety judge on those turns explicitly — it costs tokens, so it is a gated step, not part of the daily run:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db judge-credgpt-reviews --cohort-id <id> [--limit N]
```

The judge scores the rubric + decides `unsafe_advice` per turn and writes the verdict to `llm_review_json` (`llm_review_status='completed'`). It is safety-forward: it only ESCALATES `quality_state`, never clears a deterministic flag. Needs `ANTHROPIC_API_KEY`; without it, pending reviews are marked `'skipped'` (never a false `'completed'`).

## Reports

Daily team cockpit:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db render-report \
  --cohort-id pmf-2026-06-wave-1 \
  --report-id daily-2026-06-12-team \
  --report-type daily_cockpit \
  --privacy-tier team \
  --snapshot-date 2026-06-12
```

Founder detailed report with DOCX/PDF:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db render-report \
  --cohort-id pmf-2026-06-wave-1 \
  --report-id daily-2026-06-12-founder \
  --report-type founder_daily \
  --privacy-tier founder \
  --snapshot-date 2026-06-12 \
  --include-docx \
  --include-pdf
```

The report run writes:

- `*.json`: structured PMF report snapshot.
- `*.docflow.json`: renderer-neutral DocFlow document spec.
- `*.html`: self-contained cockpit/report.
- `*.docx` / `*.pdf`: optional document artifacts rendered from the DocFlow spec.

`pmf_report_runs.file_refs_json` stores all artifact paths. `pmf_report_runs.qa_json` stores structural and visual QA results. DOCX/PDF are deliverable only after visual render QA passes; HTML may be delivered after structural QA because it has no external CDN dependency.

After any Docker/runtime change touching artifact tooling, verify the deployed container:

```bash
python3 /opt/lib/pmf_artifact_runtime_check.py
```

This command must return `"ok": true` before DOCX/PDF artifacts are treated as deliverable. Local development may use `--structural-only`, but production delivery may not.

## Customer.io Approval Pack

Before any Customer.io write:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db validate-customerio-action \
  --action-json '{"cohort_id":"pmf-2026-06-wave-1","channel":"push","name":"D2 stuck onboarding nudge","approved_by":"U07GKLVA9FE","dry_run":{"ok":true},"audience_preview":{"count":82},"suppression_check":{"suppressed":3},"frequency_cap_checked":true}'
```

Only execute with `customerio-ops` if `decision.allowed=true`.

### Intervention state machine (P6 — persisted, gated, outcome-tracked)

Interventions live in `pmf_interventions`; nothing is sent autonomously:

```bash
# 1. Draft (never sends). Mutation channels (email/push) start 'needs_approval'.
python3 /opt/lib/pmf_cohort_os.py ... draft-intervention --cohort-id <id> \
  --intervention-json '{"user_key":"user:1001","channel":"email","action_type":"nudge_link_card","draft":{...},"dry_run":{...},"audience_preview":{"count":1},"suppression_check":{...}}'
# 2. Human approval gate (sets approved_by/at).
python3 /opt/lib/pmf_cohort_os.py ... approve-intervention --cohort-id <id> --intervention-id <iid> --approved-by <slack_user>
# 3. Execute — re-validates via the guard; sends only an APPROVED + valid action.
#    Default sends NOTHING (records 'no_executor'); --execute-live sends via Customer.io
#    (needs CUSTOMERIO_APP_API_KEY); or pass --customerio-ref to record a human/skill send.
python3 /opt/lib/pmf_cohort_os.py ... execute-intervention --cohort-id <id> --intervention-id <iid> [--execute-live | --customerio-ref <ref>]
# 4. Record delivery/open/click/conversion as outcomes arrive.
python3 /opt/lib/pmf_cohort_os.py ... record-intervention-outcome --cohort-id <id> --intervention-id <iid> --outcome-json '{"delivered":true,"opened":true}'
```

`execute-intervention` refuses anything not `approved` or not passing the guard, and a live-send failure records `failed` (never raises). SMS is blocked at every layer.

### Queue → intervention (P9 — propose from open queues, human-gated)

Turn actionable open queues into *proposed* interventions in one step (never sends; idempotent — won't re-draft a queue that already has a non-`failed` intervention):

```bash
python3 /opt/lib/pmf_cohort_os.py ... draft-queue-interventions --cohort-id <id> [--draft-copy-live]
```

The deterministic map (`queue_actions.QUEUE_INTERVENTION_MAP`) decides which queues warrant which nudge: `high_intent` / `stuck_onboarding` → email, `at_risk` → push, `potential_lover` → an **internal founder-outreach task (not an automated send)**. Review/quality queues get no draft. Drafts land in `needs_approval` linked via `queue_id`; on a successful `execute-intervention` the originating queue is **resolved automatically** (the closed loop). The draft's `suppression_check` is honestly **unverified** — the real suppression + frequency check is the **live executor's** job before it actually sends (`customerio_exec`); never send a draft without it.

## Slack Response Shape

Slack should receive a concise summary plus artifact file/link, not giant tables:

```text
PMF Cohort daily cockpit is ready.
Signups: 1,004 · Real users: 742 · Activated: 218 · Likely lovers: 39
Open queues: 126 · Weak CredGPT turns: 18
Attached: HTML cockpit. Founder DOCX/PDF are awaiting visual QA.
```

Never paste user-level PII into the Slack message *text* — keep it aggregate (the
generated summary already is). Per-user detail lives in the cockpit file, not the line.

## Daily delivery (`run-cohort-day --deliver`)

`run-cohort-day --deliver --slack-channel <id>` posts the aggregate summary line above
and uploads the HTML cockpit as a file (needs `SLACK_BOT_TOKEN`). Delivery is
best-effort and recorded in the run's `delivery` field — a Slack failure is captured,
it never sinks the run. The cockpit file carries the full per-user operating view
(name / stage / health), which the whole team is meant to see per the data-minimization
policy: SSN / routing / address are never present and account numbers are last-4.

## Weekly digest (`weekly-digest`)

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db weekly-digest --cohort-id <id> [--week-start YYYY-MM-DD] [--narrate-live]
```

Deterministic facts (this-week stage movements, the current funnel + 6-metric rollup, product-friction themes from friction queues + CredGPT clusters, intervention outcomes) plus — with `--narrate-live` — Alaska's trajectory read (`toward_pmf` / `flat` / `away_from_pmf` / `too_early` + what's working / what's blocking / do-this-week). This is the *PMF-signal* + *product-friction* report. Aggregate-only.

## Cron activation (GATED — do not enable until the dry run passes + Abhinav's go)

Once activated, the PMF OS runs on a schedule. These are the specs to add **in the OpenClaw dashboard** (the live dashboard is canonical — do NOT hand-edit the cron snapshot, and nothing here is live yet). All times IST; `delivery.mode='none'`; payload = an agent turn that shells the command.

**Create the launch cohort with incremental enrichment** (the daily run then enriches new + recently-moved + a capped slow-refresh slice, not the whole cohort): `create-cohort --cohort-id <id> ... --activate --config-json '{"enrichment": {"mode": "incremental", "active_window_days": 3, "slow_refresh_cap": 150}}'`. Thresholds: defaults (backfill-validated). `slow_refresh_cap` is a conservative floor — raise it from the first live day's `run["latency"]`. Full readiness + go/no-go: `docs/v5-pmf-launch-readiness.md`.

| When | Command | Purpose |
|---|---|---|
| Daily ~9:00 AM | `run-cohort-day --cohort-id <id> --date <today> --deliver --slack-channel <c> --briefing-live` | daily pass + cockpit + founder briefing |
| 2nd pass during the 3-day signup window (~3 PM) | `run-cohort-day ...` | catch intake-only queues (stuck onboarding) fast |
| Daily, after the main run | `judge-credgpt-reviews --cohort-id <id>` | LLM quality/safety pass on flagged turns |
| Weekly (Mon ~9 AM) | `weekly-digest --cohort-id <id> --week-start <mon> --narrate-live` | the trajectory step-back |
| Once, after the window closes | `end-cohort-memo --cohort-id <id> --narrate-live` | the PMF verdict |

**Gate:** enable these only after a real-data dry run looks right (calibration) and Abhinav explicitly says go — see the go/no-go scorecard in `docs/v5-pmf-launch-readiness.md`. The daily run is hardened: a per-user wall-clock timeout (a hung User-360 call can't stall it), incremental enrichment (bounded daily load), and the friction queues (stuck_onboarding / at_risk / high_intent) now fire from derived + Amplitude signals. Customer.io sends stay human-approved regardless of any cron, and live `--execute-live` is blocked until the suppression-check lands.
