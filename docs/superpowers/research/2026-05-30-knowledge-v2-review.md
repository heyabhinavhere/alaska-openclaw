# knowledge-v2 KB Review — 2026-05-30

Reviewed: 13 files in `/Users/abhinavjain/Downloads/My Mac/BON/BON Credit Project/knowledge-v2/`. READ-ONLY review. Rubric = the per-line "external-system/BON-domain fact vs how-Alaska-works fact" test, plus current-vs-V4 honesty, format consistency, and BON factual accuracy.

## Overall verdict

**Strong overall — 12 of 13 files are clean and genuinely good.** The definitions/ files and 7 of 8 integration files are exactly what the principle wants: tight external-system facts, BON-specific definitions, and short pointers to the User 360 API / `playbooks` / `architecture.md`. They correctly use **MoneyLion**, the **User 360 profile API**, the **Real Users filter**, and never re-document Alaska's pipeline. **There is exactly ONE serious violator: `integrations/fireflies.md`**, which re-documents the entire Meeting-Intelligence pipeline, the full standup cron cadence, the anti-hallucination rules, the watcher/intent-classifier model, and asserts the V4 end-state ("SQLite is the source of truth") as current fact. The biggest *systemic* issue is structural mismatch: per the principle the operating model should live in `architecture.md`, but `architecture.md` doesn't describe it at all — the operating model leaked into fireflies.md instead. Fix = move the operating model out of fireflies.md into architecture.md (marked target-vs-current) + the MI skill file, and shrink fireflies.md's Alaska section to a ≤3-line pointer.

## Per-file findings

### README.md — GOOD (one caveat)
- Clean index + template spec. Killed-features list (§ "Killed features") is excellent guardrail content. Correctly tells files to mark legacy columns `LEGACY`/`DEAD`.
- Template (lines 76-101) specifies headers `Last updated` + `Status` — **NOT `Owner`**. Note this contradicts the review rubric's "Owner header" expectation. Since the template is the team's own spec, the inconsistency is that fireflies.md *added* `Owner:`/`Backup:` while all 12 others follow the template (no Owner). Pick one and apply uniformly (recommend adding `Owner` to the template + backfilling, since single-owner SME is useful).
- Minor: structure block (lines 51-66) lists `data-models/` (5 files) and `playbooks/` (3 files) as if present. **Both directories are empty.** README advertises files that don't exist yet — fine as a target map, but worth a "(planned)" marker so Alaska doesn't try to load a missing file.

### architecture.md — NEEDS-WORK (by omission, not by error)
- As BON product-stack documentation it's **excellent**: correct MoneyLion (lines 36-38), correct hub-and-spoke AI model, correct User 360 API references (lines 184, 242, 262), good pipeline diagrams, accurate repo map, no invented detail.
- **The gap:** principle #3 says "the operating model lives in exactly ONE place — architecture.md." This file describes **zero** of Alaska's operating model — `grep` confirms no mention of Meeting Intelligence, standup, SQLite, DAILY_STATE, Daily Pulse, Follow-Through, or task graph. So when fireflies.md documents the MI pipeline, there's no canonical home it's duplicating *from* — the home is simply missing. **This is the root cause of the fireflies.md bloat.**
- **Recommended:** add an "Alaska operating model" section here (or confirm it lives in a separate Alaska-specific architecture doc — note README cross-refs point operating context to `workspace/MEMORY.md`, `SOUL.md`, `skills/alaska-core/`, which may be the real intended home). Either way it must carry the **target-vs-current caveat** (principle #4): "V4 target: SQLite task graph is source of truth, DAILY_STATE.md is a generated read-only view. **Current pre-cutover reality: Meeting Intelligence writes DAILY_STATE.md directly; SQLite task tables are empty/dormant (0 rows, per forensic audit); Phase E flips this.**" Without that caveat, do not state SQLite-as-truth anywhere.

### definitions/lifecycle-events.md — GOOD
- Textbook example of the principle. Pure BON event taxonomy: 9-step funnel, activation/engagement/conversion/churn events, reliability flags, legacy-event quarantine. Every line is a fact about BON's Amplitude data, none about Alaska's internals.
- "watcher" appears once (line 13: "A watcher subscribes to an event") — acceptable; it's a "use this file when" trigger, not a claim that watchers are built/operating.
- Correct: dormant=14d, churned=30d, "Onboarded" requires `onboarding_complete` AND `gp:credit_score > 0`. No fabrication.

### definitions/metrics.md — GOOD
- Best file in the set for canonical-definition discipline. Real Users filter marked foundational/mandatory with the test-user IDs, DAU range 12-22 (matches the corrected verified range), Activated Saver composite, cohort framework. All BON-domain.
- Correctly routes per-user/PMF lookups to the **User 360 profile API** (lines 259, 277, 345-346). No identity-resolver reference. No operating-model leakage.

### definitions/personas.md — GOOD
- Clean. ICP (deep subprime), Single Mom / Veterans / Credit Rebuilder segments, honestly flags **"No reliable filter exists today"** for Single Mom (line 40, 98) — exactly the anti-hallucination posture the principle wants. Credit-score buckets present. "watcher" used once as a trigger (line 13), acceptable.

### integrations/amplitude.md — GOOD
- Model integration file. (a) external system: org/project IDs, auth, endpoints, operators, taxonomy, user properties; (b) BON usage: Real Users filter, chat data access; (c) pointers to metrics.md / personas.md / playbooks. Correctly states the User 360 API is the **primary** path for chat content with Amplitude `chat_thread_processed` as fallback (lines 60-66). No MI-pipeline re-doc. No V4 claims.

### integrations/array.md — GOOD
- Clean. "Array is BON's credit report source of truth" (line 10) is a legitimate **external-domain** fact (Array vs Spinwheel-vs-Equifax), NOT the Alaska source-of-truth model — do not confuse with the fireflies.md violation. 20-day refresh, score=0 nuance, PII handling, User 360 pointer for report content. Correct.

### integrations/customerio.md — GOOD (long but justified)
- Largest integration file (~20KB) but the length is legitimate external-system surface (segments CNF shape, campaign types, in-app, goals, A/B). All CIO facts + BON usage (31 campaigns, 9 stock segments, frequency caps zero). Approval gates are a BON-usage policy, not Alaska-pipeline internals — acceptable. The "natural-language workflows" section (lines 268-340) edges toward how-Alaska-works but stays framed as CIO capability + approval flow, not the MI/standup operating model. Acceptable; trim only if tightening for size.

### integrations/fireflies.md — NEEDS-WORK (the one heavy violator)
This is the file the earlier draft flagged, and it still violates the principle heavily on multiple axes:

- **Re-documents the MI pipeline in full.** § "What Meeting Intelligence does with a transcript (V4 flow)" (lines 76-91) is the entire 6-step pipeline — fetch, dedup, comprehend, write-to-SQLite, re-render, Notion writes — plus the anti-hallucination + normalization rules (lines 85-90). Per principle #2 this belongs in `architecture.md` + the MI skill file, NOT in an integration file. **Trim to a ≤3-line pointer.**
- **Re-documents the standup cron cadence.** § "The standup pipeline — cadence" table (lines 22-30): Pre-Call Brief, team call, MI poll schedule, Daily Pulse, Follow-Through, Thinker. This is the operating model, duplicated. A cadence change would now require editing this file too → drift. **Remove; point to architecture.md.**
- **V4-as-current violations (principle #4).** States the end-state as flat current fact in at least 4 places:
  - Line 7 (scope note): *"The SQLite task graph at `/data/queue/alaska.db` **is the source of truth** for tasks, blockers, and decisions. `DAILY_STATE.md` is a generated, read-only view."*
  - Line 13: *"it writes the extracted tasks, blockers, and decisions into the **SQLite task graph** … — **the source of truth.**"*
  - Line 110-111 (definitions): *"Source of truth = the **SQLite task graph**. `DAILY_STATE.md` is a generated, read-only view."*
  - Line 121: *"Owns the SQLite task model (**the source of truth** MI writes to)."*
  - **All currently FALSE.** Per the forensic audit, MI still writes DAILY_STATE.md directly and the SQLite task tables are empty (0 rows, dormant). Each needs the target-vs-current caveat or removal. As written, Alaska reading this file would believe SQLite is authoritative today and act on empty tables.
- **Describes unbuilt Watchers as operating (principle #5).** Line 17: *"Channel/DM activity feeds the same graph through the intent-classifier (active) + **Watchers** (Alaska's event-monitoring/automation layer)."* Line 101: *"in V4 that's covered: channel/DM events reach the same SQLite graph via the intent-classifier + Watchers."* Watchers are not built. The "(active)" tag on intent-classifier + present-tense Watchers reads as live. **Flag and remove/mark-as-planned.**
- **Owner header inconsistency.** Only file with `**Owner:** _TBD_ | Backup: _TBD_` (line 4). Either the template gains Owner everywhere or this conforms to the others.
- **What's actually GOOD here and must be KEPT:** the genuine Fireflies external-system facts — GraphQL-only/no-webhooks/no-REST (line 36), the API/auth table + curl examples, the capabilities table, summary-is-an-object-not-scalar, "past transcripts only / no reliable currently-recording," polling-only, the **MoneyLion↔"Moneyline" transcription drift** (lines 89, 95 — correct and valuable), Hinglish, speaker-attribution drift, the write-scope-but-read-only-by-discipline caveat, the no-transcript health check, "Fred" notetaker, Zoom+Meet. This is the real KB content. The fix is to keep this layer and strip the operating-model layer.

### integrations/github.md — GOOD
- Excellent. All external GitHub facts: 9-repo map with **verified default branches** (`bon_webservices` = `dev_testing`, the rest `main`), Contents API read pattern, team handles, MobileFirst authorship caveat, rate limits. The READ-ONLY rule + grounded-reading discipline are repo-access policy (legitimately belongs in the integration file), not a re-doc of the MI pipeline. Honest token-scope caveat. Correctly routes live-runtime/DB/User-360 questions away from GitHub to Sandeep/Nilesh.

### integrations/plaid.md — GOOD
- Clean two-path access model (Amplitude for "what happened," User 360 for "what they have"), rich event-property tables, "Failed Plaid user" definition matches the rubric (initiate without success in 24h window, line 121), `is_linking_from_agentic` nuance. No Plaid-API fabrication (explicitly says Alaska has no direct Plaid access). Correct.

### integrations/spinwheel.md — GOOD
- Strong. Dual-role (identity + bill pay), the mandatory-pull-but-discard Spinwheel-credit-report nuance, **corrects the prior KB's wrong field** (`spinwheel_failed.error` not `failure_reason`, lines 46, 98 — good factual correction), ~15% failure = biggest onboarding drop, no Real Users filter on pre-user_id events, PII handling on SSN. AfterSpinwheel chain documented with the source typo noted. Correct.

### integrations/twilio.md — GOOD
- Clean. OTP vs CIO-SMS path distinction, A2P 10DLC blocker with dated status + "confirm with Nilesh" honesty (lines 81, 124), Plivo failover, WhatsApp-not-live. Notably **self-corrects a stale stat**: the "OTP 30% drop" is flagged as stale, real OTP drop ~5%, real leak is Spinwheel ~15% (line 120). Honest "needs a verification pass" note on the events table (line 43). Good anti-hallucination posture.

## Cross-file issues

- **Operating-model duplication:** Only **1 file** re-describes the pipeline/source-of-truth: `integrations/fireflies.md`. `grep` confirms "Meeting Intelligence," "standup pipeline," "SQLite," and "DAILY_STATE" (as operating-model) appear in no other integration/definition file. Good containment — but the duplication is *against a canonical home that doesn't exist yet*, because `architecture.md` carries none of the operating model. So this is "duplication + missing canonical" rather than "duplication across N files." Fix both: add the model to architecture.md (caveated), strip it from fireflies.md.
- **Current-vs-V4 honesty violations:** Confined to `fireflies.md` (lines 7, 13, 110-111, 121 assert SQLite-as-source-of-truth as current; lines 17, 101 present Watchers as active). No other file makes V4-as-current claims. metrics.md/personas.md/amplitude.md are correctly V4-independent.
- **Format inconsistencies:** (1) `Owner` header present only in fireflies.md; the README template doesn't include it and the other 12 files omit it. (2) README advertises `data-models/` (5 files) and `playbooks/` (3 files) that don't exist — no "(planned)" marker. (3) Every file's "Common queries / patterns" section links into `playbooks/common-queries.md`, which **does not exist** — every such link is currently dead. (4) Minor: fireflies.md is the only file with an "Open questions" section (fine, but non-template).
- **Factual issues:** **None found, and several positive corrections.** "Moneyline" appears only as the explicitly-flagged mis-transcription of **MoneyLion** (correct usage, fireflies.md 89/95). **No `identity-resolver` reference anywhere** (grep clean) — canonical per-user source is correctly the User 360 profile API across metrics/personas/plaid/spinwheel/array/amplitude. **Sandeep (AI engineer) and Samder (CEO) never conflated** — the only co-mention is fireflies.md's explicit anti-conflation rule. Real Users filter present and correct in metrics.md + amplitude.md. spinwheel.md and twilio.md actively *fix* stale facts from the prior KB.
- **Duplicate knowledge-v2 folder:** Confirmed. `diff -rq` between `/BON Credit Project/knowledge-v2/` and `/code/agents/alaska/knowledge-v2/` returns **zero differences — the two copies are byte-identical.** Reconcile to ONE source of truth (recommend the `BON Credit Project/` copy as canonical, or symlink) before edits begin, or fixes will have to be applied twice and will drift.

## Completeness gaps

Against the designed structure in README:

- **`data-models/` — entirely absent (empty dir).** Missing all 5: `user.md`, `credit-profile.md`, `card-linkage.md`, `financial-coaching.md`, `budgeting.md`. **This is the most important gap** — `user.md` is the anchor the per-user data story hangs on, and it's where the User 360 / `user-profile-360` skill pointer must live. Multiple files already cross-reference `data-models/user.md` (architecture.md line 256, README line 111) and `data-models/card-linkage.md` (metrics.md line 203, architecture.md line 250) as if they exist — those links are dead today.
- **`playbooks/` — entirely absent (empty dir).** Missing all 3: `common-queries.md`, `failure-modes.md`, `escalation-tree.md`. Note: **nearly every file's "Common queries / patterns" table links into `playbooks/common-queries.md`** (and architecture.md links `playbooks/failure-modes.md` for auth tech debt) — so this absence makes a large number of cross-references dead links right now.
- **`integrations/` — 4 missing:** `notion.md`, `slack.md`, `moneyline.md` (the MoneyLion offers rail — README lists it at line 44 as `moneylion.md`; note the README's own intended filename is `moneylion.md`), and `user-profile-api.md` (the 360 admin API contract). The 360 API is referenced as the canonical per-user source by ~6 files but has **no contract file documenting its actual shape/endpoints/auth** — high-value gap given how much depends on it.

## Recommended changes (prioritized)

1. **[BLOCKER] Reconcile the duplicate knowledge-v2 folder before any edits.** The two copies are byte-identical now; pick one canonical location (suggest `BON Credit Project/knowledge-v2/`) and delete/symlink the other. Editing the wrong copy = silent drift.
2. **[BLOCKER] Fix `fireflies.md` V4-as-current false claims.** Remove or caveat every "SQLite is the source of truth" / "DAILY_STATE is a generated read-only view" assertion (lines 7, 13, 110-111, 121). Current reality: MI writes DAILY_STATE.md directly; SQLite task tables are empty/dormant. Until Phase E cutover, the file must not state SQLite-as-truth as present tense.
3. **[BLOCKER] Strip the operating model out of `fireflies.md`.** Remove the standup cadence table (22-30), the 6-step MI flow (76-91), the anti-hallucination rules (85-90), and the Watchers-as-active claims (17, 101). Replace with a ≤3-line pointer: "Fireflies feeds Meeting Intelligence → see architecture.md for the pipeline and the MI skill file for extraction rules." **Keep** all genuine Fireflies API/quirk/failure-mode content (incl. the MoneyLion↔Moneyline normalization fact).
4. **[IMPORTANT] Give the operating model a real home in `architecture.md`** (or confirm the intended home is the Alaska skill docs / MEMORY.md and point fireflies.md there). Add an "Alaska operating model" section with the explicit target-vs-current caveat (principle #4). This is what makes step 3 a *move* rather than a *deletion*.
5. **[IMPORTANT] Create `data-models/user.md`** — anchor file; document the user object + state flags and make it the canonical pointer to the `user-profile-360` skill / User 360 admin API. Resolves the most dead cross-references.
6. **[IMPORTANT] Create `playbooks/common-queries.md`** — every integration/definition file links to it; its absence makes ~40 query-table links dead.
7. **[IMPORTANT] Create `integrations/user-profile-api.md`** (the 360 admin API contract) — ~6 files route per-user lookups here with no documented contract.
8. **[MINOR] Resolve the `Owner` header inconsistency** — either add `Owner` to the README template + backfill all 12 files, or drop it from fireflies.md to match the others.
9. **[MINOR] Mark not-yet-created files as "(planned)"** in README's structure block, and add the remaining missing integration files (`notion.md`, `slack.md`, `moneylion.md`, plus `credit-profile.md`, `financial-coaching.md`, `budgeting.md` in data-models; `failure-modes.md`, `escalation-tree.md` in playbooks).
10. **[MINOR] Normalize the Watcher language in lifecycle-events.md / personas.md / amplitude.md** — currently fine (framed as a hypothetical consumer), but once a Watchers-built/not-built status is settled, keep these as "when a watcher needs X" triggers and never as "watchers do X today."
