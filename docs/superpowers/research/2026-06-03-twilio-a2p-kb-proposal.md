# Proposal: A2P campaign-registration section for `knowledge/integrations/twilio.md`

> **Status:** Drafted by Claude for **Abhinav to review, fill the blanks, and paste** into the KB. The KB is Abhinav-owned — Claude does not edit `workspace/knowledge/`. This is Phase 3 of the grounding & memory-discipline plan (`docs/superpowers/plans/2026-06-03-alaska-grounding-and-memory-discipline.md`).
>
> **Why this exists:** During A2P registration (2026-06-03), Alaska was asked to help fill the campaign form. `twilio.md` documents the A2P *blocker* but nothing about *filling the form*, so Alaska **fabricated** — invented `boncredit.co/...` URLs, a generic consent flow, and sample messages containing **credit-score and billing content** (which Abhinav correctly flagged as risky). Phase 1's grounding contract stops her from inventing; this proposal gives her something real to retrieve instead.

---

## What's already in `twilio.md` (do NOT duplicate)

The existing **"A2P 10DLC: the blocker"** section already covers: A2P is carrier-mandated; the 3-step TCR process; SMS-via-CIO is blocked until A2P clears; **OTP uses a separate sending path** and is unaffected; status drifts (confirm with Nilesh); Abhinav owns registration, Nilesh owns the console. Keep all of that. This proposal **adds a new sibling section** about *filling the registration form*, plus a flag in the failure-modes list.

---

## Proposed new section (paste after "A2P 10DLC: the blocker")

> ⚠️ Before pasting: fill every **[ABHINAV: …]** blank. Claude must never invent these — leaving them blank is correct until you supply them.

```markdown
## A2P campaign registration — filling the form compliantly

This is the **unblocking** action for the SMS-via-CIO channel (the blocker above). Abhinav owns the registration; Alaska's job is to help fill the form from documented facts — **never invent URLs, consent language, or sample content.** If a field needs a value that isn't here, say so and ask, don't fabricate.

**Use case:** Account Notification (transactional). NOT marketing/promotional. Every form answer must stay inside that scope.

**Sample-message content rules** (this is where registrations get rejected):
- **Stay in the Account Notification scope.** Keep samples to account-status, security/login verification, profile-update confirmations, linked-account re-auth, and "your report is ready" (no score values).
- **Avoid, in the sample messages, anything outside that scope:** credit-score numbers, payment/billing amounts, lending/loan/credit offers, debt or collections language, and any promotional copy. Per the BON registration decision (2026-06-03), this content is kept out — it reads as financial-services/marketing rather than account notification and is the most likely rejection trigger. (Note: OTP itself runs on the separate sending path, so OTP is not what's being registered here.)
- **Every sample must include:** the brand name "BON Credit", variable content in [square brackets], a real link on the registered domain, and an opt-out ("Reply STOP").

**Consent / opt-in answer** (how end-users consent — a required form field):
- Opt-in mechanism: BON's only auth method is **phone number + 6-digit OTP**, so every user has a verified phone number by design. [ABHINAV: confirm the exact onboarding consent moment — the conversation referenced an onboarding disclaimer step (`credit_report_disclaimer_accepted`); confirm against `definitions/lifecycle-events.md` / the app.]
- Frequency: [ABHINAV: confirm the documented SMS frequency cap — the figure referenced was "2–3/day"; confirm against `integrations/customerio.md`.]
- Opt-out: reply STOP, plus in-app notification settings.

**URLs the form requires** (Alaska does NOT have these — Abhinav supplies):
- Terms of Service URL: [ABHINAV: fill]
- Privacy Policy URL: [ABHINAV: fill]
- Registered domain used in SMS links: [ABHINAV: fill]
- [ABHINAV: confirm the ToS/Privacy pages explicitly contain SMS-consent language — carrier reviewers check the public-facing pages, and missing SMS-consent language is a common rejection reason.]

**Owner:** Abhinav (registration); Nilesh (Twilio console state). Alaska helps draft answers from this section only.
```

## Proposed addition to the failure-modes list (one bullet)

Add under "Known failure modes / edge cases":

```markdown
- **A2P sample messages must stay in Account-Notification scope.** When helping fill the A2P form, do NOT draft sample messages with credit-score numbers, payment/billing amounts, or lending language — that's the top rejection trigger. Pull the rules from "A2P campaign registration" above; never invent URLs or consent language for the form.
```

---

## What Abhinav must do before this goes live in the KB

1. Fill the four **[ABHINAV: …]** blanks (the two consent confirmations, the three URLs, the SMS-consent-language check).
2. Sanity-check the content rules against your A2P submission experience (these are framed as BON's registration stance, not as quoted carrier law).
3. Paste the approved section + the failure-mode bullet into `workspace/knowledge/integrations/twilio.md`.

Once it's in the KB, Phase 1's grounding contract means Alaska will **retrieve** this on the next A2P question instead of inventing — verifiable by re-asking her the A2P registration questions.

## Out of scope
A broader audit of the other 10 integration files for similar "Alaska would fabricate here" gaps is worth doing but is a separate KB pass (Abhinav-owned). Phase 2's capture reflex now has Alaska *flag* such gaps to you as she hits them, so the KB improves incrementally without a big audit.
