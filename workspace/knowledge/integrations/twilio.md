# Twilio — SMS rail (OTP + transactional)

**Last updated:** 2026-05-30 by Abhinav
**Status:** Draft

---

## Purpose at BON

Twilio is BON's **SMS provider**. It serves two functions:

1. **OTP delivery for authentication.** BON's only login is phone + OTP. No email login, no Google, no Apple. Every signup and every returning-session login depends on Twilio (or its fallback) delivering an SMS to the user's phone within seconds.
2. **Transactional SMS via Customer.io** (planned, currently blocked). When A2P 10DLC clears, Customer.io campaigns will be able to send SMS through Twilio as a channel.

Plivo is the backup SMS provider, wired for failover.

Twilio also hosts BON's planned WhatsApp Business API integration. That work is in progress, not live.

**Most important fact for Alaska:** SMS as a Customer.io campaign channel is **blocked** on A2P 10DLC registration. Do not propose, draft, or assume SMS campaigns are deliverable until A2P clears. OTP SMS, which uses a separate Twilio sending path, is working in production.

---

## How Alaska gets Twilio data

Alaska does NOT call Twilio directly. No Twilio MCP, no Twilio Console access for Alaska.

| Question type | Where to go |
|---|---|
| OTP send / verify / fail events | **Amplitude** OTP event family |
| OTP delivery latency, signup-funnel drop at the OTP step | **Amplitude** funnel: phone-entry → OTP-sent → OTP-verified |
| Per-user OTP history (which numbers got texts, when) | **User 360 profile API** (Sandeep) |
| Twilio account state, credit balance, phone number inventory | **Not in BON's data layer.** Route to Nilesh. |
| A2P 10DLC registration status, brand tier, campaign approval | **Not in BON's data layer.** Route to Abhinav (A2P registration owner). Nilesh owns the Twilio infra wiring. |
| CIO SMS channel send attempts (post-A2P) | **Customer.io** Beta API `GET /v1/api/customers/{user_id}/messages` filtered by channel = `twilio` |
| WhatsApp setup state | **Not in any system Alaska sees.** Route to Nilesh. |

Rule of thumb: Amplitude has anything BON's app or backend fired an event for. User 360 has the per-user identity record. Twilio Console state lives with Nilesh.

---

## Events fired to Amplitude

**Verification status:** This section needs a verification pass against Amplitude taxonomy on 2026-05-30. The events below reflect what's documented in BON's onboarding funnel. If event names have drifted, Alaska should query Amplitude via MCP and update.

### OTP / authentication

| Event | Properties (expected) | Notes |
|---|---|---|
| `phone_number_submitted` | `platform`, `user_id` (when known) | User entered phone number in signup. |
| `otp_sent` | `platform`, `user_id`, `provider` (twilio / plivo) | Backend dispatched the OTP. Does NOT confirm Twilio actually delivered. |
| `otp_received` | `platform`, `user_id` | App-side event when the OTP autofill or paste lands. Optional, may not fire on all devices. |
| `otp_verified` | `platform`, `user_id` | Verification succeeded. User is authenticated. |
| `otp_failed` | `platform`, `user_id`, `reason` (expired / wrong / max_attempts) | Verification failed. |
| `otp_resent` | `platform`, `user_id`, `attempt_number` | User tapped resend. |

**Flag for Alaska:** the `provider` property is what tells you whether Twilio or Plivo delivered. If a sudden spike in `otp_failed` correlates with `provider = twilio` only, it's a Twilio issue. If both providers fail simultaneously, it's an upstream backend or A2P issue.

---

## What is NOT in Amplitude

- **Twilio-side delivery receipt.** `otp_sent` means BON's backend made the Twilio API call. It does NOT confirm the SMS landed on the user's phone. Twilio sends delivery webhooks back to BON, but those are not (currently) fired into Amplitude as their own events. Treat `otp_sent` minus `otp_verified` as a coarse upper bound on Twilio failures, not exact.
- **Carrier filtering.** Some carriers drop SMS without telling Twilio. Invisible to Amplitude.
- **A2P 10DLC throughput caps.** Once cleared, BON will get a per-second SMS cap based on brand tier. Not in Amplitude.
- **Twilio cost per message.** Lives in Twilio Console. Route to Nilesh.
- **Plivo failover decisions.** Whether a given OTP went to Plivo because Twilio timed out, or because of a config rule, lives in backend logs. Not in Amplitude unless `provider` property is reliably set.
- **WhatsApp message state.** Not in Amplitude until the integration is live.

---

## A2P 10DLC: the blocker

In the US, A2P 10DLC (Application-to-Person on 10-digit long codes) is the carrier-mandated registration for any business sending SMS to consumers from a regular phone number. Without it, carriers throttle or drop messages.

Three-step process Twilio walks you through:

1. Register the brand with The Campaign Registry (TCR). Pulls EIN data, validates business identity, assigns a brand tier (low / medium / high based on trust score).
2. Register specific campaign use cases (low-volume mixed, high-volume marketing, low-volume 2FA, etc.).
3. Wait for carrier vetting.

**BON's status as of 2026-05-26 was "submitted, pending approval, 30+ days in the queue."** As of 2026-05-30, Alaska should confirm current status by checking with Nilesh before quoting any specific timeline.

A2P only blocks the CIO transactional/marketing SMS channel. **OTP SMS uses a separate sending path** (toll-free or short-code, confirm with Nilesh) and is unaffected. This is why signup still works while CIO SMS campaigns don't.

---

## Plivo backup

Plivo is configured as the secondary SMS provider. The team decision (recorded 2026-05-20) is "Twilio primary, Plivo backup" for both SMS and WhatsApp.

Failover trigger condition is owned by Nilesh. Most likely: Twilio API timeout or 5xx → retry on Plivo. Possibly: per-region or per-carrier routing rules.

**Risk Alaska should flag if it sees confused fallback behavior:** if both providers fire for the same OTP, the user gets two texts. Tracking this requires the `provider` property on `otp_sent` to be reliable.

---

## WhatsApp (not live)

Twilio's WhatsApp Business API is the planned production path. There is also a Meta Cloud API test setup from an earlier prototype (test number `+1 555 180 7911`, 90-day temporary token, not for production).

**Status as of last update:** integration in progress, owned by Nilesh, blocked on Abhinav sync at one point. Alaska should treat WhatsApp as not available and not propose WhatsApp DMs until Nilesh signals live.

---

## Definitions used across the team

- **OTP** = One-Time Passcode. 6-digit code BON SMSes for phone-based login.
- **A2P 10DLC** = Application-to-Person messaging on 10-digit long codes. The US carrier registration regime for business SMS. Required for CIO SMS campaigns. Not required for OTP via the current sending path.
- **The Campaign Registry (TCR)** = the entity that handles A2P brand and campaign registration. Twilio submits on BON's behalf.
- **Brand tier** = A2P trust score assigned to BON's registered brand. Determines daily message volume cap and per-second throughput.
- **"Twilio primary, Plivo backup"** = the two-provider strategy. Twilio handles the bulk of sends, Plivo takes over on failure.
- **"Temporary direct method"** = legacy term from earlier docs for whatever sending path OTP uses while A2P clears. Worth retiring as a term. Replace with "OTP sending path" and confirm specifics with Nilesh.
- **Verification SID** = Twilio's identifier for a single OTP verification attempt. Useful when debugging a specific user's failed login with Twilio support.

## Known failure modes / edge cases

- **OTP SMS works, CIO SMS does not.** Two different sending paths. Don't reason about them as one channel.
- **Do not draft, propose, or assume any CIO SMS campaign is deliverable.** A2P pending. Push and email are the only live channels for CIO right now.
- **`otp_sent` is not delivery confirmation.** It's a backend dispatch event. Drop between `otp_sent` and `otp_verified` could be Twilio failure, carrier drop, user typing wrong code, or user abandoning. Don't blame one cause without provider attribution and reason properties.
- **OTP funnel drop has been misreported.** The "OTP 30% drop" number circulating from older docs is stale. Current funnel data (per [BON onboarding funnel truth](../definitions/lifecycle-events.md)) shows OTP step closer to ~5%. The real leak in onboarding is Spinwheel identity at ~15%. If asked about the OTP step, lead with the corrected number and the source.
- **Push permission step is broken at ~7.6% conversion.** Not a Twilio problem but easy to confuse with OTP since both involve "user grants something the app needs." Different step, different fix.
- **Plivo silent double-send risk.** If failover logic fires both providers, user gets two texts. Worth a Slack flag if Alaska sees `otp_sent` events with both providers within seconds for the same user.
- **WhatsApp is not a live channel.** Don't propose WhatsApp campaigns or messages.
- **A2P status drifts.** "Pending" today may be "approved" or "rejected" tomorrow. Don't quote A2P state from memory. Confirm with Nilesh before any campaign-launch decision.

## Common queries / patterns

| Query | How |
|---|---|
| OTP-step conversion (phone-entered → verified) | Amplitude funnel: `phone_number_submitted` → `otp_verified` |
| OTP failure breakdown | Group `otp_failed` by `reason` |
| Provider attribution | Group `otp_sent` or `otp_failed` by `provider` |
| Resend rate | `totals(otp_resent) / totals(otp_sent)` |
| Per-user OTP history | User 360 API (Sandeep) |
| Twilio account / phone number / cost data | Slack Nilesh, ask for Twilio Console snapshot |
| A2P 10DLC registration state | Abhinav owns A2P; Nilesh has the Twilio Console state |
| CIO SMS campaign deliverability (post-A2P only) | CIO Beta API `GET /v1/api/customers/{user_id}/messages` filtered by channel |

## People

- **Owns Twilio infra (backend wiring, account):** Nilesh.
- **Owns A2P 10DLC registration:** Abhinav.
- **Owns Plivo backup integration:** Nilesh.
- **Owns WhatsApp setup:** Nilesh.
- **Owns the OTP UX in the Flutter app:** Pankaj.
- **Owns onboarding funnel and A2P escalation:** Abhinav.
