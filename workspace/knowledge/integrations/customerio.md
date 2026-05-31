# Customer.io — Campaign & Messaging Orchestration

**Last updated:** 2026-05-29 by Abhinav
**Status:** Draft

---

## Purpose at BON

Customer.io (CIO) is BON's **campaign orchestration layer**. Push, email, SMS, in-app, webhooks. It owns campaign definitions, delivery metrics, per-user messaging history, segments, and frequency caps.

Channels used at BON: push (CIO SDK), email (SendGrid primary, Postmark backup), SMS (Twilio primary, Plivo backup; pending A2P clearance). Channels available but unused: in-app, webhook, Slack, WhatsApp, Line, Urban Airship.

Alaska should know CIO end-to-end, even capabilities we're not using yet. The team will ask for advice, and Alaska should be able to propose what CIO can do and execute when approved.

---

## How Alaska gets CIO data

Direct API access via env-var keys: `CUSTOMERIO_APP_API_KEY`, `CUSTOMERIO_TRACK_API_KEY`, `CUSTOMERIO_SITE_ID`.

| Question type | Endpoint |
|---|---|
| List campaigns and state | `GET /v1/environments/{env_id}/campaigns` |
| Per-campaign metrics | `GET /v1/environments/{env_id}/campaigns/{id}/metrics` |
| Per-user message history | Beta API `GET /v1/api/customers/{user_id}/messages` |
| Per-user activity log (events + deliveries) | `GET /v1/environments/{env_id}/logs?customer_id={id}` |
| Workspace health | `GET /v1/environments/{env_id}/health` |
| List segments + counts | `GET /v1/environments/{env_id}/segments` + `/segments/{id}/count` |
| Pause / resume / create / edit / delete | Write endpoints (approval rules below) |
| Push permission opt-in rate (upstream) | Amplitude `feature_used{feature_name="notification_permission_granted"}` |

---

## Critical operational note: "Allow agent to edit live data" toggle

CIO has a workspace setting that gates whether agents can edit live data (running campaigns, segments in use, etc). If it's off, write calls return 403 with a settings link in the body. Only a workspace admin can flip it. If Alaska hits this 403, surface the link from the error and explain it's a workspace setting, not a platform restriction.

---

## BON's CIO environment

| Field | Value |
|---|---|
| Account | `146028` (Bhim Digital, Inc.) |
| Prod environment ID | `211696` |
| Dev environment ID | `210456` |

Always query Prod (`211696`) for real metrics. Dev is for testing.

---

## APIs and auth

| API | Base URL | Auth |
|---|---|---|
| App API | `https://api.customer.io/v1/` | Bearer `$CUSTOMERIO_APP_API_KEY` |
| Beta API | `https://beta-api.customer.io/v1/api/` | Bearer `$CUSTOMERIO_APP_API_KEY` |
| Track API | `https://track.customer.io/api/v2/` | Basic `$CUSTOMERIO_SITE_ID:$CUSTOMERIO_TRACK_API_KEY` |

App API curl pattern:

```bash
curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" \
  "https://api.customer.io/v1/environments/211696/<endpoint>"
```

Track API is fired by the app and backend to push events. Alaska uses it directly when tagging users with attributes to build segment audiences.

---

## Current state (as of 2026-05-29)

**Campaign inventory + counts: pull live via `GET /v1/environments/211696/campaigns` — don't rely on a static list, it goes stale.** Most running campaigns are transactional (event-triggered), with a couple segment-triggered (e.g., Win-Back, AI Chat Introduction). Marketing/broadcast campaigns are not yet running.

### Segments

All stock CIO defaults — **no BON-custom segments exist today.** (Pull the live list/count via the segments API; don't hardcode a number — the stock set below is illustrative.)

```
1. All Users
2. Have not logged in recently
3. Paying Customers
4. Free Customers
5. Unsubscribed
6. Valid Email Address
7. Invalid Email Address
8. Have a Mobile Device
9. Doesn't have a Mobile Device
```

### Workspace health

Pull live via `GET /v1/environments/{env_id}/health` — returns the health score, alert count, and events-processed-today. Don't quote a static number.

### Frequency caps and subscription topics

Zero configured. Per-user limits and topic-level opt-out aren't in place.

---

## CIO capabilities (full surface)

What CIO can do and what BON is using vs not.

### Customers and identity

- Create, update, search, delete, merge customer profiles via App API.
- Activity logs: `GET /v1/environments/{env}/logs?customer_id={id}&type=event` returns a user's CIO-side event history. Use to inspect what events CIO has seen for a user. No separate `/customers/:id/events` endpoint, the logs endpoint is the path.
- Subscriptions: `POST /customers/subscribe` and `/unsubscribe`.
- SMS opt-outs: `GET/PUT /customers/:id/optouts`.

### Segments (where the leverage is)

**Dynamic segments** auto-update membership based on rules. Membership refreshes as user data flows in. Use for stable, attribute-based audiences ("all users with credit score under 580", "all users who linked a card but no bank").

**Static segments** are CSV-uploaded lists. Members added or removed via API. Use for one-off targeting from upstream analysis.

**Condition shape (dynamic segments):** Conjunctive Normal Form. An outer AND of OR groups. Each leaf is one of:

- `attribute_change` — match on a customer attribute (e.g. `credit_score < 580`).
- `event` — user fired a custom event N times within a window. Supports wildcards.
- `device_change` — device attribute match.
- `segment` — is or is not in another segment (max nesting depth 1).
- `relationship`, `related_object_attribute`, `relationship_attribute` — object-graph based (for companies, orders, etc. if we set them up).
- `optout` — opted out of a channel.

**Common condition patterns:**

```
"Signed up in last 30 days"
  → attribute_change on created_at, timestamp_gt -2592000

"Has NOT opened any email in 30 days"
  → event opened_email *, within 2592000, inverse: true

"Received any SMS"
  → event delivered_action twilio_*

"Clicked a specific campaign's push"
  → event clicked_action push-campaign_18
```

**Useful segment ops:**

- `GET /segments/{id}/count` — population size
- `GET /segments/{id}/metrics` — engagement breakdown
- `GET /metrics/segment_membership?segment_id={id}` — size over time, useful for cohort tracking

**Members of a segment** — no API to list. UI link: `https://fly.customer.io/workspaces/211696/journeys/segments/{id}/people`.

### Campaigns

Campaign types:

| Type | Trigger |
|---|---|
| `transactional` | Event-triggered. Fires when a named event happens. Most of BON's running campaigns. |
| `behavioral` | Segment-triggered. Fires when a user enters the segment. A couple of BON's running campaigns. |
| `date` | Date-attribute triggered (birthdays, anniversaries). Not used at BON. |
| `webhook` | External webhook triggers entry. |
| `api_triggered` | Fired explicitly via API. |
| `seg_attr` | Segment + attribute combo. |
| `relationship` | Object-relationship triggered. |
| `form` | Form submission triggered. |

Each campaign has actions (email, push, SMS, in-app, webhook, etc.) wired together with edges (branches, delays, wait-until conditions, multi-splits). Flow control supports time-window guards (e.g. only send during business hours).

A/B tests on campaigns: convert any message action to a split test with variant templates and traffic allocations summing to 100. Per-variant metrics via `/actions/{id}/split_metrics`. Pick a winner via `/actions/{id}/winner`.

### Newsletters (one-time broadcasts)

Newsletters are one-shot sends to a segment. Use for announcements, product launches, cohort blasts. Support all channels including in-app.

A/B tests on newsletters: spawn variations, set per-variation content and a `send_percentage`, end the test and ship the winner to the remainder.

### Transactional messages

Templated transactional sends fired from the backend via `/v1/send/*`. Different from transactional *campaigns*. Use for one-shot system messages (welcome email, password reset, payment receipt) where the trigger is purely backend code.

### In-app messages (unused, big opportunity)

CIO in-app messages render inside the Flutter app. Display modes: modal, overlay, inline, tooltip. Content can include lead-capture forms, surveys (NPS, rating, free-text feedback), CTAs with deep links, multi-step flows.

**BON has not provisioned in-app messaging.** First step would be `POST /in_app/provision` then wire the CIO SDK in the app. Once live, we could run in-app prompts (e.g., "Set up AutoPay now"), in-app surveys (NPS at D7, satisfaction after a savings event), and lead-style flows without writing custom UI for each.

**Worth proposing for PMF cohort work.** In-app NPS at D30 for each cohort would feed Sean Ellis tracking directly.

### Goals

Standalone goals measure whether users complete a target action, with per-campaign attribution. Funnel tracking from a start event to a goal event. Feature-gated. **Worth checking if enabled on BON's plan.** If yes, we can wire Activated Saver as a CIO goal and CIO will attribute completions across campaigns. Powerful for ROI per campaign.

### Subscriptions and topics

Subscription topics give granular per-topic opt-out (e.g., "marketing", "score updates", "payment reminders"). Lets users unsubscribe from one without losing everything. **Zero configured at BON today.** Single global unsubscribed flag (segment 5) is the only opt-out.

### Webhooks (reporting)

CIO can fire webhooks on delivery events (sent, delivered, opened, clicked, bounced, unsubscribed). Useful for syncing delivery metrics into our own analytics stack if we ever want a single dashboard. Configure under workspace settings.

### Frequency caps

Hard caps at the workspace level (e.g., max 1 push/day per user). **Zero configured at BON today.** When marketing scales, this is the lever that prevents over-messaging. Worth setting before ramping send volume.

### Templates and Design Studio

Email templates managed via App API templates endpoint. Design Studio is CIO's visual email builder (separate API surface). Liquid templating throughout: `{{customer.first_name}}`, `{{customer.credit_score}}`, etc.

### Translations

Multi-language sends via `/translations` and BCP-47 language codes. Match send-time language to the user's `language` attribute. Not in use, irrelevant until BON expands beyond US English.

### Object types and relationships

CIO can model non-person entities (companies, accounts, orders) and link them to customers. Not used at BON since we model person-only today, but if we ever need household-level messaging or shared-account flows this is the primitive.

---

## How CIO is triggered

Three sources fire events into CIO. When debugging "why didn't user X receive Y," check all three.

1. **App-side.** CIO SDK in Flutter + Track API calls. User-action events (chat open, screen view, button tap) and `identify()` on signup.
2. **Backend-side.** Track API calls from `bon_webservices`. Transactional events the app cannot detect: payment-due reminders (Bull cron), score-change alerts (Array cron), AutoPay results (Spinwheel webhook), dormant re-engagement (cron), proactive insights from CredGPT.
3. **CIO dashboard.** Campaign definitions. The code does NOT define what gets sent. It fires the events that trigger sends. The mapping lives in CIO.

---

## Trigger events for new transactional campaigns

For a new transactional (event-triggered) campaign, the trigger event has to exist in backend code. Alaska can build the campaign in CIO, but if backend doesn't fire that event via Track API, nobody enters.

Before agreeing to build a new transactional campaign:

1. Check if the trigger event already exists. `GET /v1/environments/211696/event_names` lists known events. Reuse if possible.
2. If it doesn't exist, tell the requester the campaign needs a new event from backend, and route to Nilesh with the proposed event name and payload.
3. Behavioral (segment-triggered) campaigns, newsletters, and date-triggered campaigns do NOT need a new backend event. Only transactional campaigns do.

---

## Natural-language workflows Alaska can run

Plain-English requests Alaska can execute end-to-end (subject to approval gates). Examples grounded in BON's actual needs.

### Build a cohort segment

User: "Build a CIO segment for Cohort 1 (signed up June 11-13)."

Alaska's steps:
1. Decide static vs dynamic. For a fixed cohort, static is simpler.
2. Query Amplitude for users with `onboarding_complete` between June 11-13.
3. Show the user count.
4. Ask Abhinav or a Founder for approval.
5. Create the static segment via `POST /segments` with `type: static`.
6. Add members via `PUT /segments/{id}/members` with `type: add` and the user_id list. CIO uses external `id` as long as we sent users in with that identifier via Track API.
7. Confirm in Slack with the segment URL and final member count.

### Build a dynamic segment from CIO attributes

User: "Segment of users with credit score under 580 who haven't linked a card."

Alaska's steps:
1. Confirm both attributes (`credit_score`, `is_card_linked`) exist in CIO via the data-index endpoints. If not, the Track API needs to push them first (talk to backend).
2. If they exist, build the segment with two conditions in CNF: `credit_score` attribute_change `to lt 580` AND `is_card_linked` attribute_change `to eq false`.
3. Show preview count.
4. Approval.
5. Create via `POST /segments` with `type: dynamic` and conditions.

### Build a Win-Back segment with BON's real dormancy threshold

User: "Replace the stock 'Have not logged in recently' with our 14-day dormancy threshold."

Alaska's steps:
1. Create a new dynamic segment "Dormant 14d" with condition: `event _active * within 1209600 inverse: true` (no `_active` event in last 14 days).
2. Update the Win-Back campaign trigger to point to the new segment (campaign 25 `recipients` update).
3. Approval.
4. Verify by pulling new segment count and confirming Win-Back's recipients.

### Launch an A/B test on a campaign

User: "A/B test the subject line on the Transaction summary email."

Alaska's steps:
1. Find campaign 39 and its email action ID.
2. Convert the action to a split test via `POST /actions/{id}/test`.
3. Show the user the two variant template IDs.
4. Wait for variant copy from the user.
5. Update each variant template subject.
6. Set traffic allocations (e.g., 50/50) via campaign action update.
7. Approval.
8. Activate. Monitor via `/actions/{id}/split_metrics`. Recommend a winner once significance is reached.

### Cohort-aware messaging suppression

User: "Pause all marketing for users in Cohort 1 until D30."

Alaska's steps:
1. Identify "marketing" campaigns (non-transactional, i.e., the segment-triggered ones).
2. Build an exclusion filter referencing the Cohort 1 segment.
3. Approval.
4. Apply exclusion to each marketing campaign.
5. Schedule the reversal at D30.

### Provision and launch in-app

User: "Add an in-app NPS survey at D30 for Cohort 1."

Alaska's steps:
1. Check `GET /in_app/status`. If not provisioned, run `POST /in_app/provision` and tell the user the SDK needs to be wired in the app (engineering ticket).
2. Once provisioned, create the NPS survey template with the standard NPS markup.
3. Create a behavioral campaign triggered by Cohort 1 segment at D30 with the in-app action.
4. Approval before going live.

---

## Campaign actions Alaska can take

### Read (no approval)

- List campaigns, get metrics, list segments, get segment count or metrics, workspace health, look up user attributes and activity logs, list templates.

### Safety actions (no approval, confirm after)

- Pause a campaign: `PUT /campaigns/{id}/actions/pause`
- Resume a campaign: `PUT /campaigns/{id}/actions/start`

### Approval required (Abhinav or Founders: Darwin, Samder)

- Create or edit a campaign, action, segment, frequency cap, subscription topic, template, or in-app message.
- Delete anything: campaigns, segments, templates. Confirmation phrase required for deletes ("Reply 'delete confirmed' to proceed").
- End an A/B test (pick winner, send remainder).
- Configure webhooks or workspace settings.

Always `dry_run` before mutating. Always read the campaign or segment first, store the pre-state, mutate, refetch, diff. A 200 response confirms the request was accepted, not that it did what you expected.

---

## Definitions used across the team

- **Delivery rate** = `delivered / sent` per campaign or channel.
- **Open rate** = `opened / delivered`. Email-meaningful.
- **Click rate** = `clicked / delivered`.
- **Bounce rate** = `bounced / sent`. High push bounces = expired tokens / revoked permissions.
- **Healthy campaign** = delivery > 50%, open > 10%, bounce < 10%. Quick rule.
- **Transactional** = event-triggered. Most of BON's running campaigns.
- **Behavioral** = segment-triggered. A couple of BON's running campaigns.
- **Stock segment** = CIO built-in defaults. All current segments are stock; zero BON-custom.
- **Activity log** = a user's CIO-side event and message history via `/logs?customer_id=...`.

## Known failure modes / edge cases

- **No BON-custom segments.** All 9 are CIO defaults. Targeting beyond defaults needs new segments (approval) or upstream-Amplitude-computed audiences pushed via Track API.
- **Push delivery historically low.** Permission opt-in is the binding constraint, not backend. Frame as UX problem. Spot-check fresh metrics before quoting.
- **SMS blocked.** Twilio A2P pending.
- **Triggering is mixed.** When a campaign doesn't fire, check app, backend, dashboard.
- **Campaign ambiguity in Slack commands.** When multiple campaigns match a name, list with IDs and ask. Never pause silently.
- **Metric response is a 45-day array.** `total_*` fields summarize, daily arrays show trends.
- **Segment members not listable via API.** Use the UI link to inspect.
- **`{"attribute": ...}` doesn't work in segment conditions.** Wrong shape, returns 500. Use `{"event": {"type": "attribute_change", "name": "...", "filters": ...}}` instead.
- **Timestamp offsets in segments are signed.** Negative = past. `"-2592000"` = 30 days ago. Positive is in the future.
- **In-app not provisioned.** `POST /in_app/provision` first, then app SDK work.
- **`/data_index/events` is a trap.** Returns 204 and queues an unwanted export. Use `GET /event_names` to list known events.

## Common queries / patterns

| Query | How |
|---|---|
| List active campaigns | `GET /campaigns`, filter `state=running` |
| Find a campaign by name | List campaigns, filter on name |
| Per-campaign delivery health | `GET /campaigns/{id}/metrics`, read `metric.total_sent`, `total_delivered`, `total_opened`, `total_clicked`, `total_bounced` |
| Channel-level rollup | Loop campaigns, sum per-channel totals from `campaign_metrics.{push\|email\|twilio\|...}.total_*` |
| Workspace health | `GET /health` |
| Per-user activity log | `GET /logs?customer_id={user_id}&type=event` |
| Per-user message history | Beta API `GET /v1/api/customers/{user_id}/messages` |
| Segment size | `GET /segments/{id}/count` |
| Segment size over time | `GET /metrics/segment_membership?segment_id={id}` |
| Push permission opt-in rate | Amplitude `feature_used` |
| Find broken push campaigns | Per-campaign push metrics, flag delivery < 50% or bounce > 10% |
| Pause a campaign | `PUT /campaigns/{id}/actions/pause` |
| A/B test split metrics | `GET /actions/{action_id}/split_metrics` |
| Active A/B tests dashboard | `GET /metrics/dashboard_tests?version=2&tz=America/New_York` |
| List known events in workspace | `GET /event_names` |

## People

- **Owns CIO campaign strategy:** Samder (proposes campaigns).
- **Owns Track API wiring (app + backend):** Sandeep + Nilesh.
- **Approves new campaigns, edits, deletes, segments, frequency caps, in-app provisioning, webhooks:** Abhinav or Founders (Darwin, Samder).
- **Owns push-permission opt-in UX:** Abhinav.
