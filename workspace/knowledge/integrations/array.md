# Array — Credit Report Aggregator

**Last updated:** 2026-05-29 by Abhinav
**Status:** Draft

---

## Purpose at BON

Array is BON's **credit report source of truth**. It pulls credit reports from Equifax and exposes them to BON via an API. Array sits between BON and the credit bureau, handling the regulatory compliance layer (FCRA permissible purpose, consent, dispute flows) so BON doesn't integrate with Equifax directly.

The credit model BON uses is **VantageScore 3.0 (via Array, from Equifax) — not FICO.** Anywhere a "score" appears, it's VantageScore 3.0.

The flow:

1. During onboarding, after Spinwheel returns the SSN, the backend creates an Array user with that SSN.
2. Array orders the first credit report from Equifax.
3. Backend stores it and shows the user their score in-app.
4. Ongoing, an Array cron re-pulls the report every ~20 days.

Both Spinwheel and Array use Equifax under the hood. BON treats **Array** as the canonical credit report, not Spinwheel's. See `integrations/spinwheel.md` for the mandatory-pull-but-discard nuance on Spinwheel's credit data.

Why every ~20 days: credit reports in the US are only updated by the bureaus every 30 days. BON pulls every 20 days so we don't miss an update or delay it for the user.

---

## How Alaska gets Array data

Alaska does NOT call Array directly. No Array MCP, no API connector.

| Question type | Where to go |
|---|---|
| Aggregate credit-score refresh events (when scores update, score distribution over time) | **Amplitude** (`credit_score` event) |
| Per-user score history (score on date X, score change over N days) | **Amplitude** `credit_score` events filtered by `user_id` |
| Current credit score for a user | **Amplitude** user property `gp:credit_score` |
| Full credit report content: tradelines, balances, liabilities, inquiries, payment history, borrower details (name, address, DOB) | **User 360 profile API** (Sandeep) |
| Whether a linked Plaid card matched to a tradeline in the credit report | **User 360 profile API** |

Rule of thumb: Amplitude has the score and the refresh events. User 360 has the full credit report content. → the per-user credit data Alaska actually reads comes via `integrations/user-profile-api.md`. Treat borrower PII (name, address, DOB, SSN-last-4 if exposed) as sensitive. Never log or surface.

---

## Events fired to Amplitude

Verified against Amplitude taxonomy on 2026-05-29.

### `credit_score`

Fires per credit report refresh. Roughly every ~20 days per user.

| Property | Description |
|---|---|
| `score` | Numeric credit score from the refresh |
| `platform` | `ios` or `android` |
| `user_id` | BON user_id |

That's the entire payload. No score trajectory, no bucket label, no inquiry count. The actual report content is in the User 360 API.

### Onboarding-touching credit events

These fire in the onboarding flow when the user encounters the credit-report disclaimer screen. Not credit-data events per se, but they live in the same domain.

- `credit_report_disclaimer_screen` — user viewed the disclaimer screen
- `credit_report_disclaimer` — user interacted with the disclaimer
- `credit_report_disclaimer_screen_dropoff_event` — user dropped off from the disclaimer screen

See `definitions/lifecycle-events.md` for onboarding step context.

---

## What is NOT in Amplitude (use User 360 API instead)

- **Full credit report content.** Tradelines, balances, payment history, account status, inquiries.
- **Borrower details.** Full name, residential address, DOB, sometimes SSN-last-4. All PII.
- **Score history with timestamps.** Score on a given date.
- **Per-card liability detail.** Minimum payment (when present in the report), due date (when present), APR (when present), open/closed status.
- **Matching engine state.** Whether a linked Plaid card was tied to a tradeline.

The Amplitude footprint for Array is small on purpose: just the refresh signal and the current score. Everything else is backend data, surfaced through the User 360 API.

---

## Definitions used across the team

- **"Credit score"** = the score from Equifax via Array. Stored as `gp:credit_score` user property in Amplitude (current value). Score history is fetched from the User 360 API.
- **"Score bucket"** = Deep Subprime / Subprime / Near Prime / Prime / Super Prime. Working score-range buckets (score is VantageScore 3.0 via Array/Equifax — not FICO; ranges are standard conventions). See `definitions/personas.md` § Credit-score buckets.
- **"20-day refresh"** = the Array cron cadence for ongoing credit-report pulls.
- **"AfterSpinwheel chain"** = code paths that run as part of onboarding (create Array user from SSN, order + retrieve first report). See `integrations/spinwheel.md` § Spinwheel chain.
- **"Tradeline"** = an individual credit account in the report (a specific credit card, loan, etc.). Industry term from the credit bureau world.

## Known failure modes / edge cases

- **Score = 0 means "no profile yet."** This happens when Spinwheel succeeded but Array silently failed. Don't interpret 0 as a real low score.
- **Refresh lag.** Array cron runs daily but only refreshes profiles > 20 days stale. A user could have a 21-day-old score for a few hours.
- **`credit_score` event has minimal properties.** Just `score`, `platform`, `user_id`. Don't expect bucket labels, trajectory, or report fields here.
- **Borrower data in the User 360 API is PII.** Never log, never include in Slack output, never echo in chat.
- **Real user gate depends on Array.** `gp:credit_score > 0` is the Real Users filter condition. If Array fails silently for a user, they never become a real user.
- **Onboarding-disclaimer events.** `credit_report_disclaimer_screen_dropoff_event` users abandoned before consenting. They never make it to Spinwheel or Array.

## Common queries / patterns

| Query | How |
|---|---|
| Users with a credit score in range X-Y | Filter `gp:credit_score` user property by range. See `definitions/metrics.md` § By credit score bucket. |
| Score change for a user over N days | Pull `credit_score` events filtered by `user_id`, compare `score` values across the window |
| Score distribution | Group `gp:credit_score` user property by buckets |
| Stale credit profiles (> 20 days) | Approximate Amplitude proxy: users with no `credit_score` event in the last 25 days. Authoritative: User 360 API |
| Full per-user credit report | User 360 API (Sandeep). PII inside. Don't surface borrower details. |
| Tradeline match state | User 360 API |
| Onboarding drop-off at the credit-report disclaimer | `credit_report_disclaimer_screen_dropoff_event` count |

## People

- **Owns Array integration (backend):** Sandeep.
- **Owns credit-data consumption (CredGPT):** Sandeep.
- **Owns the score-bucket strategy:** Abhinav.
