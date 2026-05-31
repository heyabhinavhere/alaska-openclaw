# Failure Modes — Active Issues, Cross-Cutting Patterns, Diagnostic Chains

**Last updated:** 2026-05-30 by Abhinav
**Status:** Draft

> **What this file is:** the cross-cutting view of how things break at BON. Two layers: BON product/system issues (active and resolved) and Alaska's own internal failure patterns (how Alaska herself can fail at her job). Each section is explicitly labeled so Alaska knows whether she's reading about the product or about her own operating discipline.
>
> **What it is NOT:** intra-system gotchas. Each integration file has its own "Known failure modes" section for quirks specific to that system. This file orchestrates across them. Also NOT ad-hoc incident response (that's the operating model). Also NOT a security audit (code-level audits live in engineering reviews).

---

## How to use this file when something breaks

The discipline:

1. **Identify the symptom.** What's the user-visible signal? "Daily Pulse didn't post." "Push delivery dropped." "User got wrong credit number."
2. **Check the active BON issues list (Section 1).** If it matches a known active issue, you have context: owner, current status, mitigation.
3. **If not in Section 1, walk Alaska's diagnostic chains (Section 3).** The chain gives the ordered check sequence for common Alaska-side breaks.
4. **If still no match, check Alaska's cross-cutting patterns (Section 2).** Silent failures, identity drift, and data inconsistencies are the patterns that hide novel issues inside Alaska's own pipelines.
5. **Escalate using the three rules:**
   - For routine breaks: tell the system owner from the relevant integration file's "People" section.
   - For critical or novel issues: tell Abhinav directly.
   - For user-facing outages: also tell Samder so he can communicate externally.

Don't broadcast a diagnosis until you've walked the chain. Naming the wrong root cause publicly is more expensive than waiting an hour for ground truth.

---

## 1. Active BON product/system issues (BON)

**Scope: these are issues with BON's product and infrastructure, not Alaska.** They affect users or partners directly. Alaska reads this section to know what's currently broken in the product so she can answer questions about status accurately and avoid making promises the product can't keep.

### 1.1 Plaid card linking conversion ~21-33%

- **Symptom:** users tap "Link Card," majority don't complete Plaid Link flow.
- **Owner:** Sandeep (backend) + Pankaj (Flutter integration) + Abhinav (UX).
- **Status:** active. Last-4-digit matching priority shipped May 21 helped marginally. Funnel hasn't structurally changed.
- **Cross-reference:** `integrations/plaid.md` § failure modes for the per-step breakdown. `playbooks/common-queries.md` § 2.4 for the live conversion query and § 2.7 for the exit-step breakdown.

### 1.2 Push notification delivery ~7.6%

- **Symptom:** Customer.io push campaigns show ~7.6% delivery rate.
- **Owner:** Abhinav (opt-in UX).
- **Status:** active. **Backend fixes for both iOS and Android are done.** The remaining issue is purely permission opt-in at the OS level (~10% iOS opt-in rate). This is a UX problem, not an engineering one.
- **Cross-reference:** `integrations/customerio.md` § failure modes. `playbooks/common-queries.md` § 5.3 for the system-wide push health query that joins CIO metrics with Amplitude permission events.
- **Discipline:** if asked about push, lead with the permission framing. Don't let the team chase a backend ghost.

### 1.3 Twilio A2P 10DLC registration pending

- **Symptom:** CIO SMS campaigns are not deliverable.
- **Owner:** Nilesh.
- **Status:** active blocker. Submitted 30+ days ago, still pending TCR (The Campaign Registry) approval. OTP SMS still works (separate sending path).
- **Cross-reference:** `integrations/twilio.md` § A2P 10DLC: the blocker.
- **Discipline:** never propose, draft, or assume any CIO SMS campaign is deliverable. Push and email are the only live CIO channels.

### 1.4 MoneyLion / Engine integration not yet live

- **Symptom:** zero offers-rail data in BON systems. No leadEvents API. No SDK in Flutter app.
- **Owner:** Samder (partnership), Sandeep + Pankaj (integration), Abhinav (product surfaces).
- **Status:** active. Compliance kicked off May 14. Three-phase integration plan pending engineering confirmation. Old Array-based loan calculator events (`loan_calculator_*`, `debt_consolidation_loan_*`) are dead.
- **Cross-reference:** `integrations/moneylionbyengine.md` (to be drafted post-team-Slack-response).
- **Discipline:** do not query the dead Amplitude events. Don't surface MoneyLion-derived insights in agent responses until integration lands.

---

## 2. Alaska's cross-cutting failure patterns (Alaska)

**Scope: these are how Alaska herself can fail at her job, not how BON's product fails.** They span Alaska's pipelines (MI, watchers, Slack delivery, identity resolution) and require Alaska's own discipline to prevent.

### 2.1 Silent delivery failures

**Pattern:** an outbound message goes to an unreachable surface; Alaska reports "sent"; nobody notices for hours or days.

**Past examples:** 7 cron jobs had `delivery.channel: webchat` routing output to dead surfaces. Follow-Through 6 PM had 27 consecutive `Message failed` errors silently. Both caught only after manual inspection.

**Discipline:**
- Every outbound Slack post must be wrapped with response status check. `chat.postMessage` returns `ok: false` with an `error` field on failure. Honor it.
- Cron jobs that produce outputs need a "did the output land" verification step, not just "did the job run."
- Use `{mode: none}` + explicit `action=send,channel=slack,target=...` in agent prompts. Never rely on `delivery.channel` defaults.

**Detection signature:** for any agent that produces a daily output, count days-with-output over rolling 7 days. Zero days = silent failure.

### 2.2 Identity disambiguation drift

**Pattern:** names that look similar get conflated. The two most expensive:

- **Sandeep (AI engineer) vs Samder (CEO).** Architecture/V2/Plaid/CredGPT issues → Sandeep. Marketing/partnerships/ads → Samder. Tripled cost when @-mentioned wrong in a channel.
- **MoneyLion vs "Moneyline".** Fireflies mis-transcribes MoneyLion as Moneyline because of Hinglish-influenced phonetics. This propagated into task graph state before being caught.

**Discipline:**
- Roster cross-reference is mandatory before any @-mention. Identity-resolution rules in `workspace/SOUL.md` § Identity Resolution.
- Canonical-name normalization applies to entity names (MoneyLion → MoneyLion always) and person names (Pancaj → Pankaj).
- See `integrations/fireflies.md` § anti-hallucination + normalization rules.

### 2.3 Cross-system data inconsistency

**Pattern:** the same fact lives in multiple places and drifts. Channel IDs in code AND docs. Notion DB IDs in 9 files. GitHub repo lists scattered.

**Discipline:**
- Addresses (channel IDs, DB IDs, user IDs, repo lists) live in `workspace/MEMORY.md` as the single source. Every other file references it. See the conventions section of `playbooks/common-queries.md`.
- When a fact is documented in two places, treat the older copy as suspect and verify the newer one against live.

### 2.4 Stale data masquerading as current

**Pattern:** a number from an old snapshot looks just like a current number, so Alaska quotes it confidently.

**Past examples:**
- "OTP 30% drop" (from older docs) was wrong; current funnel data shows OTP step at ~5%. Spinwheel identity at ~15% is the real onboarding leak.
- Spinwheel credit report (signup-only, never refreshed) used as if it were current Array data.

**Discipline:**
- Always label staleness when quoting numbers from non-real-time sources. "Array (Equifax) snapshot, may be up to 20 days old." "Spinwheel signup snapshot, may be stale."
- Don't quote conversion-rate ranges from memory. Pull the live number every time.
- For canonical numbers, the corrected truth lives in `definitions/lifecycle-events.md` and `definitions/metrics.md`. Cross-check before reporting.

### 2.5 Authority-tier violations

Only Abhinav can authorize behavior changes, rule-saves, or memory edits. Anyone else → acknowledge naturally, don't save as a rule, flag for Abhinav. (Sharing factual info — repos, tools, workflows — is fine; that's data, not behavior.) Full rules → `workspace/SOUL.md`.

### 2.6 DM privacy and cross-sharing

DMs between Alaska and a team member are private to that member — never cross-share. Only Abhinav can review others' DM history, and only what's necessary for the question. Full rules → `workspace/SOUL.md`.

---

## 3. Alaska's diagnostic chains (Alaska)

**Scope: ordered check sequences for common Alaska-side breakages.** Most chains start with Alaska's own pipeline state and walk outward to BON systems if Alaska's side checks out.

### 3.1 "Daily Pulse didn't post this morning"

1. Check Slack delivery: look for the most recent `chat.postMessage` from the Alaska bot to `#alaska-daily-pulse`. If not present, the post never landed.
2. Check the SQLite task graph: was it populated overnight? Query `task_events` for entries between MI's last poll (~2:00 AM IST) and Daily Pulse's run (~9:00 AM IST).
3. Check Daily Pulse cron status: did it fire? Logs in `/data/.openclaw/`.
4. Check identity resolution: if the Pulse posted but to the wrong channel, the channel ID lookup may have drifted. Re-validate against `workspace/MEMORY.md` § Slack Channels.
5. If all checks pass and the post still didn't land, escalate to Sandeep.

### 3.2 "Push delivery dropped"

1. Pull system-wide push health: `playbooks/common-queries.md` § 5.3.
2. Check per-campaign breakdown: are all push campaigns dropping, or one specific one?
3. Check upstream permission grant rate: Amplitude `feature_used{feature_name="notification_permission_granted"}` vs `_denied` over the last 7 days. If grant rate dropped, the issue is opt-in UX, not delivery.
4. If grant rate is stable AND delivery dropped, escalate to Sandeep (backend) AND check CIO Workspace health endpoint for delivery-side issues.

### 3.3 "User reports wrong / missing credit data"

1. Verify the user has a credit report: query user-profile-api `/users/{user_id}/profile`, check `credit_report_history`. If empty, user has no Array report yet (~21% of users) and there's nothing to quote.
2. Check Array refresh window: Array refreshes every ~20 days. If the latest `credit_report_history` row (by `report_date`, not index `[0]`) is older than 20 days, the data is fresh-stale (we're in the gap before next refresh).
3. Verify the score type was reported correctly: BON's canonical credit number is Equifax (via Array), not FICO. If anyone said "FICO" in an external message, that's the bug.
4. If Plaid is linked and debt numbers look wrong, check `plaid_profiles.card_profile` (primary), not `plaid_liabilities` (often empty).
5. If both Array and Plaid look right but the surfaced number is still wrong, the bug is in the agent layer (CredGPT or whichever skill surfaced it). Escalate to Sandeep.

### 3.4 "Standup task was wrong / fabricated"

1. Identify which transcript produced the task: query SQLite `task_events` for the task's create_event, get the source `transcript_id`.
2. Pull the transcript: Fireflies `transcript(id: "...")`. Read the sentences directly.
3. Check whether the commitment was actually stated: was it a "mention" misclassified as a "commitment"?
4. Check transcription drift: was a proper noun mangled (MoneyLion → Moneyline, person name → wrong person)?
5. If fabrication: this is a violation of MI's COMMITMENT EXTRACTION rules. Escalate to Sandeep + Abhinav. The Apr 29 lesson tells us this is a discipline failure, not a model failure.

### 3.5 "Slack channel didn't get the message"

1. Verify bot membership: bots can't post to channels they aren't members of. `not_in_channel` is the error.
2. Verify the channel ID, not name. Names break if a channel is renamed. IDs in `workspace/MEMORY.md` § Slack Channels.
3. Check rate limit: 1 msg/sec per channel for `chat.postMessage`. If burst-posting, may have hit 429 + `Retry-After`.
4. Check formatting: `**bold**` renders as literal asterisks. mrkdwn uses single `*`. See `integrations/slack.md` § formatting.
5. If single message > 3000 chars, it may have been truncated mid-word. Should split into multiple clean messages.

---

## 4. Latent risks (tinder, not fire)

These don't break today but compound silently. Split by ownership: BON-side risks need engineering attention; Alaska-side risks need Alaska's own discipline.

### 4a. BON-side latent risks

- **Sequelize + Flyway dual migration system.** Two schema sources of truth. If a migration is added to one but not the other, drift accumulates.
- **Two SMS providers (Twilio + Plivo).** If both fire on naive fallback, user gets two texts. Track via `provider` property on `otp_sent`.
- **Two email providers (SendGrid + Postmark).** Same shape. SendGrid is documented primary; Postmark status unclear.
- **Mixpanel is live for attribution, but not connected to Alaska.** It actively collects source-of-user attribution (organic / web / ads) — it is **not** dead code. But Alaska has no Mixpanel access, so it's outside her data surface; she can't read it. Don't treat it as a risk or try to query it — just know attribution data lives there, unreachable to Alaska today.

### 4b. Alaska-side latent risks

- **No "no transcript processed today" health check.** A call that yields no transcript (Fireflies "Fred" didn't join, or poll failed) needs to be noticed, not silently skipped. Partial mitigation in `integrations/fireflies.md` § no-transcript health check.
- **Watchers V1 not yet shipped.** Multiple "detection signature" references in this file assume Watchers exist. Until they do, detection is manual.

---

## 5. Resolved (lessons that still matter)

Compressed history. Only the lessons that should still inform Alaska's or BON's behavior. Each entry tagged with whose lesson it is.

### 5.1 Hallucinated standup commitments (Apr 29, 2026) [Alaska]

Meeting Intelligence was fabricating commitments from transcript context. One hallucinated commitment becomes a public standup item the next morning.

**Lesson:** MI accuracy is everything. The fix was strict COMMITMENT EXTRACTION rules + attribution rules + staleness rules + confidence threshold (<80% don't include). Plus QUALITY GATE in Pre-Call Brief. Now codified in `integrations/fireflies.md` § anti-hallucination + normalization rules.

### 5.2 Sprint Board disconnected from reality (Mar-Apr 2026) [BON process]

~3 sprints where Sprint Board content didn't match real work. Sprint 2 had 3% completion. Sprint 3 never approved. Board became fiction.

**Lesson:** the artifact must reflect reality from meetings, not the other way around. Architectural fix: meetings → source-of-truth → consumers. Never write the board first. Sprint Board retired 2026-05-23. Live state now lives in the SQLite task graph.

### 5.3 Cron `delivery.channel: webchat` silent routing failure (May 25, 2026) [Alaska]

7 cron jobs had outputs routed to unreachable surfaces. Follow-Through 6 PM had 27 silent `Message failed` errors.

**Lesson:** OpenClaw cron jobs have TWO sources of truth: `payload.message` inline prompt AND the SKILL.md. Schema changes need to update BOTH. Now: `{mode: none}` + explicit `action=send,channel=slack,target=...` in prompts.

### 5.4 Customer.io "I don't have access" (Apr 28, 2026) [Alaska]

Sessions said "I don't have access" despite API keys being present.

**Lesson:** data tool availability needs to be loud, not implicit. Fixed by adding data tools to AGENT_RULES.md and TOOLS.md.

### 5.5 Bank-name vs brand-name card matching (resolved May 21, 2026) [BON]

Card matching engine compared raw strings from Array (bank names) and Plaid (brand names). Most "linked card → tradeline" matches failed.

**Lesson:** when joining records across sources, never trust string equality on names. Use stable identifiers (last-4 digits in this case) as primary key.

### 5.6 Amplitude `_active` filter `s` parameter ignored (~Apr 2026) [BON quirk, Alaska had to learn]

Filter conditions in the `s` (segments) parameter returned unfiltered data. No error. ~2 days of debugging.

**Lesson:** filters MUST go inside `e.filters`, never in `s`. Documented in `integrations/amplitude.md`.

### 5.7 Amplitude operator naming (Apr 28, 2026) [BON quirk, Alaska had to learn]

Filter operator `"greater than"` returns HTTP 400. UI says "greater than"; API requires `"greater"`. Same drift on `"less than"` vs `"less"`.

**Lesson:** UI labels don't match API parameter names for Amplitude filter operators. Verified list in `integrations/amplitude.md`.

### 5.8 Three CRITICAL security/compliance items (resolved by 2026-05-30) [BON]

- Unprotected Array routes (14 endpoints with zero auth middleware): **resolved.**
- Sample data leak in `createArrayUserAfterSpiwheel` controller: **resolved.**
- Raw JWT tokens logged in 3 middleware files (`auth.js`, `admin.auth.js`): **resolved.**

**Lesson:** security/compliance issues found in code review need their own tracking lane separate from operational issues. They don't have runtime detection signatures, so they hide. Worth a periodic code-review sweep, even if every individual issue gets fixed promptly.

### 5.9 Profile field display showing "string string String" (resolved) [BON]

User profiles surfaced literal placeholder strings instead of real values. Caught in QA May 21.

**Lesson:** field-level placeholder leaks are silent in normal logs. Worth a regex watcher on user-profile-response fields if it recurs.

### 5.10 Android Play Store review (resolved) [BON]

Android app release was queued behind Play Store review for 9+ days.

**Lesson:** Play Store review timing is unpredictable. For future releases, build a buffer.

### 5.11 MoneyLion partner-name confusion ("MoneyLine" / "Moneyline") [Alaska transcription]

The old Array-based loan calculator and debt-consolidation flow used the placeholder name "MoneyLine" in some docs and the partner has been mis-transcribed by Fireflies as "Moneyline."

**Lesson:** the real partner is MoneyLion (now Engine, owned by Gen Digital since Apr 2025). The dead Amplitude events from the old loan calc (`loan_calculator_*`, `debt_consolidation_loan_*`) should not be queried. See `integrations/moneylionbyengine.md` (when shipped).

---

## 6. People

- **Owns this catalog:** Abhinav (curator) + Risk Radar skill (consumer once live).
- **Owns critical-severity escalation:** Abhinav (Admin authority).
- **Owns code-level security review:** Sandeep + Nilesh.
- **Owns operational issue tracking:** Abhinav.
