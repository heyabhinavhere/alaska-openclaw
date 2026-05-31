# Metrics — Canonical Definitions

**Last updated:** 2026-05-29 by Abhinav
**Status:** Draft

---

## Purpose at BON

Some common metrics that are asked of Alaska, filtered by, or watched.

Two kinds of metrics live here. Both are real and useful.

**Day-to-day metrics.** The standard consumer-app vocabulary: DAU, MAU, WAU, signups, onboarding completion, chat engagement, linkage rates, drop-off, retention, delivery health, profile breakdowns. This is what Alaska gets asked about constantly. The team, investors, and you all need these numbers to read product health.

**Success metrics.** The 6 per-user metrics + Activated Saver composite. Used for PMF measurement on cohorts, not for daily reporting. Different question, different cadence.

If a metric isn't defined here, it isn't canonical. Pick a working definition, ship it, then add it here so the next person uses the same one.

---

## The Real Users filter (foundational, mandatory)

**Every user-count or engagement query MUST apply this filter.** Without it, numbers are inflated 3-5× by anonymous installs, internal team testing, and dev builds.

A "Real User" is someone who:

- Has `gp:credit_score > 0` (completed Spinwheel identity verification during onboarding)
- Is NOT in the internal team `user_id` exclusion list
- Is NOT on a dev build (`version` does not contain "dev")

### Internal team user_ids to exclude

```
2300 — Darwin
287  — Darwin
2601 — Darwin
2604 — Darwin
2503 — Samder (support/ops)
2062 — Samder (primary test account, highest activity)
2605 — Samder (secondary test account)
```

### Internal email domains to exclude

```
@boncredit.ai
@bonhq.com
@mobilefirstapplications.com
```

### Filter implementation

See `integrations/amplitude.md` § Real Users filter for the exact JSON payload. The filter goes inside the event definition's `filters` array. It does NOT go in the `s` (segments) parameter, which is silently ignored.

### Exception, Spinwheel events

`spinwheel_started`, `spinwheel_completed`, `spinwheel_failed` fire BEFORE `user_id` is assigned (during onboarding). Do NOT apply the Real Users filter to these. They would return 0.

---

## Activity metrics

### Real DAU

- **What:** unique real users active in a day.
- **Formula:** `uniques(_active)` with Real Users filter, daily interval (`i=1`).
- **Expected range (May 2026):** 12-22/day.
- **Common pitfall:** without the Real Users filter, returns 30-60/day. That's anonymous installs + internal team.

### Real WAU

- **What:** unique real users active in a rolling 7-day window.
- **Formula:** `uniques(_active)` with Real Users filter, weekly interval (`i=7`).
- **Expected range (May 2026):** 15-100.

### Real MAU

- **What:** unique real users active in a rolling 30-day window.
- **Formula:** `uniques(_active)` with Real Users filter, monthly interval (`i=30`).
- **Expected range (May 2026):** ~100-150.

### Returning users (week-over-week)

- **What:** real users active this week who were also active in the prior 7-day window.
- **Formula:** intersect `uniques(_active, this week)` with `uniques(_active, last week)`.
- **Use:** stickiness signal independent of new acquisition.

### Retention curve (D1, D7, D14, D30)

- **What:** of users who signed up on day X, what % returned on day X+N.
- **Source:** Amplitude retention chart, anchored on `onboarding_complete`.
- **Common windows:** D1, D7, D14, D30. Add D60/D90 for long-tail.

---

## Acquisition metrics

### Signups (new)

- **What:** users who entered the onboarding funnel.
- **Formula:** `uniques(onboarding_step_completed{step_name="phone_number_submitted"})`.
- **Expected range (May 2026):** ~100/30d.
- **No Real Users filter** at this step. Signups are pre-onboarded by definition.

### Onboarded users

- **What:** users who reached `onboarding_complete`.
- **Formula:** `uniques(onboarding_step_completed{step_name="onboarding_complete"})`.
- **Expected range (May 2026):** ~73/30d.

### Onboarding completion rate

- **Formula:** `uniques(step="onboarding_complete") / uniques(step="phone_number_submitted")`.
- **Expected range (May 2026):** ~73%.

### Onboarding step-by-step drop-off

Each step emits `onboarding_step_completed` with a `step_name` property. Query each step separately for unique users. Compare adjacent step counts to find the drop. See `definitions/lifecycle-events.md` § 9-step onboarding funnel for the full step list and typical numbers.

**Biggest historical drop:** `dob_submitted` (~85) → `spin_wheel_connection_successful` (~71) = ~15% Spinwheel identity failure.

### Spinwheel success rate

- **What:** of identity-verification attempts, what % succeeded.
- **Formula:** `totals(spinwheel_completed) / (totals(spinwheel_completed) + totals(spinwheel_failed))`.
- **Target:** > 85%. **Actual (May 2026):** ~70-85%.
- **CRITICAL:** do NOT apply Real Users filter. These events fire pre-user_id.

---

## Engagement metrics

### Chat-engaged users

- **What:** real users who sent at least one message to the agent in the window.
- **Formula:** `uniques(credgpt_message_sent)` with Real Users filter.
- **Expected range (May 2026):** 100-170/30d.
- **Why this not `credgpt_chat_started`:** `credgpt_chat_started` misses ~5% of chatters. `credgpt_message_sent` is the hard signal.

### Total messages sent

- **What:** total user-side messages in the window.
- **Formula:** `totals(credgpt_message_sent)` with Real Users filter.
- **Expected range (May 2026):** ~400+/30d.

### Messages per chatter (chat depth)

- **Formula:** `totals(credgpt_message_sent) / uniques(credgpt_message_sent)` over the window.

### Sessions per user

- **Formula:** `totals(session_start) / uniques(_active)` per segment.
- **Caveat:** `session_start` doesn't fire for ~5-10% of users.

### Screen views (top screens)

- **Source:** `common_screen_view_tracker` event with `screen_name` property.
- **Top screens (30d, May 2026):** `credGPTScreenView` (~131), `screen_view_cards` (~56), `screen_view_bank` (~50), `screen_view_transactions` (~45).
- **Note:** chat is BON's home screen. Three screen-name values map to chat: `credGPTScreenView`, `screen_view_credgpt_home`, `screen_view_credgpt_chat_page`. Naming inconsistency, dedupe if rolling up.

### Feature use

- **Source:** `feature_used` event with `feature_name` property.
- **Top features (30d, May 2026):** `notification_permission_granted` (187), `push_notification_on` (109), `link_card` (66), `actions_button` (55), `add_card_button` (51), `payoff_strategy_section_home` (27), `debt_strategy_choose_snowball` (21), `autopay_setup_button` (18), `invite_friend_button` (17).

---

## Linkage metrics

### Card linkage rate

- **What:** of users who initiated card linking via Plaid, what % succeeded.
- **Formula:** `totals(add_card_successful) / totals(add_card_initiate)`, both with Real Users filter, formula endpoint.
- **Expected range (May 2026):** 21-33%. Historic baseline ~30%.
- **Known issue:** on some days `add_card_successful > add_card_initiate`, event double-fire. Aggregate over multi-day windows.

### Bank linkage rate

- **Formula:** `totals(add_bank_successful) / totals(add_bank_initiate)`, both with Real Users filter.
- **Expected range (May 2026):** 50-63%.

### Card linkage drop-off (where)

- **Source:** group `add_card_unsuccessful` by `exit_step` to see which step in the Plaid Link modal users dropped from. Group by `institution_name` to see which banks fail most. Group by `failure_reason` / `error_type` for cause categories.
- **Use:** find the largest failure pocket and act on it.

### Linked-user counts (by segment)

Four segments defined by `gp:is_card_linked` and `gp:is_bank_linked`. Stored as strings `"true"` / `"false"`, not booleans.

| Segment | Filter | ~% of real users (May 2026) |
|---|---|---|
| Card Only | `is_card_linked = "true"` AND `is_bank_linked ≠ "true"` | ~9% |
| Bank Only | `is_card_linked ≠ "true"` AND `is_bank_linked = "true"` | ~14% |
| Both Linked | both `"true"` | ~10% |
| Neither Linked | both `≠ "true"` | ~68% |

### Linked-but-unmatched users

- **What:** linked a card via Plaid but the matching engine couldn't tie it to a tradeline in the credit report.
- **Definition:** `add_card_successful` fired but no `card_match_successful` within 7 days.
- **Source / detail:** `integrations/plaid.md`.

---

## Delivery metrics (Customer.io)

### Push notification delivery rate

- **Formula:** `delivered / sent` per campaign, from CIO metrics API.
- **Actual (May 2026):** ~7.6% (pull live to confirm). Root cause: ~10% iOS permission opt-in (UX problem, not backend).

### Email delivery / open rates

- **Actual:** pull live from Customer.io (`GET /v1/environments/211696/campaigns/{id}/metrics`); do not quote hardcoded figures.

### Campaign health rollup

- **Healthy:** delivery > 50%, open > 10%, bounce < 10%.
- **Source:** loop over campaigns, fetch metrics each, flag the unhealthy ones. See `playbooks/common-queries.md` § Push health.

---

## User profile breakdowns

Standard cuts Alaska gets asked for.

### By linking segment

See "Linked-user counts" above.

### By credit score bucket

Filter `gp:credit_score` ranges. The score itself is VantageScore 3.0 (via Array/Equifax), not FICO. Bucket boundaries are not yet locked; these use standard score-range conventions if no other instruction: Deep Subprime <580, Subprime 580-619, Near Prime 620-659, Prime 660-719, Super Prime 720+. See `definitions/personas.md` § Credit-score buckets for the BON-specific decision when locked.

### By platform

Group by `[Amplitude] Platform` (iOS / Android). iOS share of Real DAU was ~85-90% in May 2026.

### By country

Group by `[Amplitude] Country`. US share of Real Users was ~98% in May 2026.

### By signup date (cohort)

Group `_active` or any event by `gp:created_at_bon`. Use 3-day windows for cohorts (see Cohort framework below).

---

## The 6 success metrics (for PMF measurement)

**Use these when measuring PMF on a cohort, not for daily reports.** Each metric is per-user. Count how many of the 6 a user has hit by D7, D14, and D30 to determine Activated Saver.

### 1. Dollar value saved

- **What:** cumulative dollars BON has saved this user. Either confirmed by the user, or computed when the saving is irrefutable (a fee waived, a rate reduced, a subscription cancelled).
- **Why this matters:** the ultimate outcome metric.
- **Source:** CredGPT records each save event. Available via the **User 360 profile API** (Sandeep) which includes V2 hub tables.

### 2. Score delta from baseline

- **What:** current credit score (VantageScore 3.0 via Array) minus baseline score at signup.
- **Formula:** `gp:credit_score (current) - first credit_score event score`.
- **Source:** Amplitude `credit_score` event + `gp:credit_score` user property.
- **Caveat:** Array refreshes every ~20 days. Daily changes invisible.

### 3. Strategy adopted (and still on it)

- **What:** user picked a debt-reduction strategy (snowball, avalanche, balance transfer, consolidation) and is still using it.
- **Source:** `feature_used` events like `debt_strategy_choose_snowball`, `schedule_create_initiate_snowball`, `schedule_create_success_snowball`. Similar variants for avalanche, balance transfer. Also counts if user has talked about debt reduction more than 3 times with the AI chat (CredGPT).
- **"Still on it":** ongoing strategy-related actions in the last 14 days.

### 4. Budget set (and using it)

- **What:** user set up a budget and is actively using it.
- **Source:** Available via the **User 360 profile API** (Sandeep). Budget creation, updates, and usage events live there.
- **Caveat:** budget tracking needs Plaid transactions, so available to Plaid-linked users today. Layer 1 (minimum monthly obligations from credit report) works without Plaid.

### 5. Messages sent to the agent

- **What:** count of `credgpt_message_sent` events for this user in the window.
- **Formula (per user):** `totals(credgpt_message_sent) where gp:user_id = X`.

### 6. Linked credit card and/or bank account

- **What:** at least one credit card or bank account linked.
- **Source:** `gp:is_card_linked = "true"` (Spinwheel-side card data) OR `gp:is_bank_linked = "true"` (Plaid bank link).
- **Note:** Plaid card-link path also exists. Treat any of the three as "linked."

### Activated Saver composite

- **Definition:** user has hit **at least 2 of the 6** success metrics.
- **Tracked at D7, D14, and D30** from signup. D7 and D14 are leading indicators. D30 is the validator.
- **Cohort metric, not global.** Report as a rate per cohort.
- **PMF signal:** Sean Ellis ≥ 40% at D30 for a cohort.

### Cohort framework

- 3-day signup window = 1 cohort. Example: users who signed up June 11-13, 2026 = Cohort 1.
- Target 800-1000 users per cohort.
- Track at D7, D14, D30. Add D60, D90 for full retention curve.
- Unit of analysis = the cohort. Each cohort is a fresh experiment.

---

## Definitions used across the team

- **"Real user"** = passes the Real Users filter (credit_score > 0, not in test list, not on dev build).
- **"Active user"** = triggered any `_active` event in the window.
- **"Onboarded user"** = `onboarding_step_completed{step_name="onboarding_complete"}` fired.
- **"Chat-engaged"** = sent at least one `credgpt_message_sent` event in the window.
- **"Returning user"** = active in current window AND active in prior window of same size.
- **"Linked"** = `gp:is_card_linked = "true"` AND/OR `gp:is_bank_linked = "true"`. Filter with `"true"` (string), not `true` (boolean).
- **"Activated Saver"** = hit ≥ 2 of the 6 success metrics. Tracked at D7, D14, D30.
- **"Cohort"** = users who signed up in a fixed 3-day window.
- **"PMF signal"** = Sean Ellis ≥ 40% at D30 for a cohort.

## Known failure modes / edge cases

- **`s` parameter is silently ignored.** Putting Real Users filter in `s` instead of inside `e.filters` returns inflated numbers with no error.
- **Operator name mismatch.** Amplitude API requires "greater" not "greater than". Same for "less", "greater or equal", "less or equal". Using "greater than" returns HTTP 400.
- **`user_properties` aren't on every raw export event.** API segmentation resolves them server-side. Raw exports may have empty user_properties for returning users.
- **`gp:is_card_linked` is a string `"true"`, not boolean `true`.** Filter accordingly.
- **Credit scores sometimes passed as strings.** Use `"greater"` with `["0"]` (string array). Amplitude coerces.
- **Counter mismatches in Plaid events.** `add_card_successful + add_card_unsuccessful > add_card_initiate` on some days. Event double-fires.
- **`screen_time_spent` undercounts chat 3-10×.** Only fires on screen EXIT. Don't use as primary engagement.
- **`session_start` missing for ~5-10% of users.** Use `_active` uniques for user counts.
- **`credgpt_response_error` fires 0 times.** Error visibility broken. No alternative.

## Common queries / patterns

| Query | Where |
|---|---|
| Real DAU trend | `playbooks/common-queries.md` § DAU trend |
| Onboarding funnel (9 steps) | `playbooks/common-queries.md` § Onboarding funnel |
| Card linkage funnel | `playbooks/common-queries.md` § Card linkage funnel |
| Bank linkage funnel | `playbooks/common-queries.md` § Bank linkage funnel |
| Plaid drop-off by exit_step and institution | `playbooks/common-queries.md` § Plaid failure steps |
| Spinwheel success rate | `playbooks/common-queries.md` § Spinwheel success |
| Chat engagement (uniques + depth) | `playbooks/common-queries.md` § Chat engagement |
| Linking segment counts | `playbooks/common-queries.md` § Linking segments |
| Score range filter | `playbooks/common-queries.md` § Score range filter |
| Push / email delivery health | `playbooks/common-queries.md` § CIO health |
| User lookup (across systems) | Use the User 360 profile API (Sandeep) |
| Per-user value of the 6 success metrics | Use the User 360 profile API (Sandeep) |

## People

- **Owns metric definitions:** Abhinav.
- **Owns Amplitude integration:** Pankaj + Sandeep.
- **Owns Customer.io integration:** Samder (strategy), Sandeep + Nilesh (Track API), Abhinav (UX).
