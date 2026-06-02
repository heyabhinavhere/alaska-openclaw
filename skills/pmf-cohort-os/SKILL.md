---
name: pmf-cohort-os
description: Alaska V5 PMF Cohort Operating System — configurable 3-day signup cohort registry, PMF Funnel, user case files, CredGPT quality observatory, rich artifacts, and Customer.io approval packs
version: 0.1.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3, python3]
      env: [AMPLITUDE_API_KEY, AMPLITUDE_SECRET_KEY, BON_ADMIN_API_KEY, BON_API_BASE_URL, CUSTOMERIO_APP_API_KEY]
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

## CLI Pattern

All commands return JSON. Use `/data/queue/alaska.db` in production.

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska.db <command> ...
```

In local repo tests or manual development, use:

```bash
python3 lib/pmf_cohort_os.py --db /tmp/alaska-pmf.db <command> ...
```

## Activate a Cohort

No hardcoded dates. Abhinav chooses the window.

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska.db create-cohort \
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
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska.db ingest-signups-file \
  --cohort-id pmf-2026-06-wave-1 \
  --events-file /tmp/pmf-signup-events.jsonl
```

Single-event debugging path:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska.db ingest-signup \
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
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska.db review-credgpt-turn \
  --cohort-id pmf-2026-06-wave-1 \
  --user-key user:2714 \
  --turn-json '{"thread_id":"t1","turn_id":"t1-1","event_time":"2026-06-12T18:00:00Z","question":"How should I pay down my cards?","answer":"...","feedback":null,"chat_stopped_by_user":false,"dropoff_adjacent":false,"user_context_present":true}'
```

The deterministic layer flags weak, unsafe, ungrounded, interrupted, bad-feedback, and dropoff-adjacent turns. LLM review is selected but not run automatically here; a future workflow can fill `llm_review_json`.

## Reports

Daily team cockpit:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska.db render-report \
  --cohort-id pmf-2026-06-wave-1 \
  --report-id daily-2026-06-12-team \
  --report-type daily_cockpit \
  --privacy-tier team \
  --snapshot-date 2026-06-12
```

Founder detailed report with DOCX/PDF:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska.db render-report \
  --cohort-id pmf-2026-06-wave-1 \
  --report-id daily-2026-06-12-founder \
  --report-type founder_daily \
  --privacy-tier founder \
  --snapshot-date 2026-06-12 \
  --include-docx \
  --include-pdf
```

The report run stores file paths and QA status in `pmf_report_runs`.

## Customer.io Approval Pack

Before any Customer.io write:

```bash
python3 /opt/lib/pmf_cohort_os.py --db /data/queue/alaska.db validate-customerio-action \
  --action-json '{"cohort_id":"pmf-2026-06-wave-1","channel":"push","name":"D2 stuck onboarding nudge","approved_by":"U07GKLVA9FE","dry_run":{"ok":true},"audience_preview":{"count":82},"suppression_check":{"suppressed":3},"frequency_cap_checked":true}'
```

Only execute with `customerio-ops` if `decision.allowed=true`.

## Slack Response Shape

Slack should receive a concise summary plus artifact file/link, not giant tables:

```text
PMF Cohort daily cockpit is ready.
Signups: 1,004 · Real users: 742 · Activated: 218 · Likely lovers: 39
Open queues: 126 · Weak CredGPT turns: 18
Attached: HTML cockpit. Founder DOCX/PDF are awaiting visual QA.
```

Never paste user-level PII into team channels.
