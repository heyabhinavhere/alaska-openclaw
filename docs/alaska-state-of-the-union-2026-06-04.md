# Alaska — State of the Union (2026-06-04)

> **What this is:** the single, grounded source of truth for where Alaska stands — built from a 5-agent audit of the repo + docs + git history + PRs, **calibrated against verified-live state** (the 2026-06-03 live audit `docs/alaska-live-system-map.md` and live checks run this session). It exists because knowledge had fragmented across agents, conversations, and disagreeing docs, and we'd lost a clear picture.
>
> **Grounding tags used throughout:** ✅ **verified-live** · 📄 **repo/built only (unverified live)** · ⚠️ **drift (docs/live disagree)** · 🔴/🟡/🟢 risk.
>
> **The one-line truth:** Alaska is **architecturally broad and genuinely well-engineered, but operationally shallow in spots.** The recurring failure mode is **"merged ≠ live"** — a lot is built and tested; less is verified *running*. The "drift" feeling is real and has a name: the **open loop** between the git repo and the hand-maintained live cron layer, plus state docs that disagree with each other.
>
> **Owner:** Abhinav · **Authoring basis:** repo `heyabhinavhere/alaska-openclaw` @ `origin/main` = PR #96.

---

## 0. TL;DR (read this if nothing else)

- **What's solid:** the V4 input pipeline (intent-classifier → task-handler, Meeting-Intelligence), the source-router architecture (V5/OM-1→3), the one-writer task graph, the grounding contract, and V5's deterministic-core PMF OS. The Thinker cron is now the **first fully closed-loop example** (SKILL edit → live, no dashboard logic) — proven this session.
- **What's fragile:** the **open-loop cron layer** (the #1 structural weakness), the **single-writer `DAILY_STATE.md`** (no call = stale), and a large pile of **built-but-dormant** capability — `agent_memory` (0 rows), `blockers` (0 rows), the standup-reply parser (no trigger), and **all of V5** (no cron, no keys, no cohort).
- **What's genuinely dangerous:** 🔴 the GitHub token has **read+write** scope guarded only by an instruction; 🔴 `SOUL.md`/`MEMORY.md` sit ~400 chars from the **silent 20k truncation cap**; 🔴 three docs imply **Phase E is "cutting over ~Jun 4–5"** but git shows it **never started past groundwork** — cutting `DAILY_STATE` to a generated view of today's *incomplete* graph would be actively harmful.
- **The meta-fix:** stop opening new fronts; **close the loop** on what's built (apply the thinning, verify the dormant paths, activate V5 deliberately), make **this doc + the live-system-map** the only state docs, and never state live behavior from a doc again.
- **Deadlines:** BON V2 launch ~**Jun 10**; the PMF launch cohort window is ~**Jun 11–15**. Both press on V5 activation and on closing the V4 loop *before* we lean on either.

---

## 1. Current State Assessment

**What Alaska is today:** a multi-agent PM + product-intelligence bot on OpenClaw (Railway), Slack-fronted, backed by two SQLite stores + Notion (largely deprecated) + a markdown knowledge base. ~**28 skills**, **22 live crons** (✅ audit), 2 DBs.

**Live and actively firing** (✅, evidenced by row counts / live crons):
- **Input pipeline:** `intent-classifier 1.4.1` (711 `intent_inbox` / 715 `classifier_audit` rows), `task-handler 1.2.0` (9 tasks; cross-person assign confirmed via T-9), `meeting-intelligence 2.3.1` (sole `DAILY_STATE.md` writer).
- **PM agents:** `daily-pulse`, `follow-through` (2 crons), `risk-radar`, `thinker` (just thinned + verified), `sprint-operator`, `doc-keeper`, `slack-commands 1.3.0` (DM path).
- **Capability layer:** `user-profile-360` (cache-purge cron live), `watcher-creator/janitor` + `event-poller` (3 watchers W-1/2/3 live), `amplitude-analyst 2.0.0` + `customerio-ops` (on-demand).
- **Grounding contract:** live in `SOUL.md` + `AGENT_RULES.md` + `alaska-core 2.1.0` (2026-06-03 work).

**Source of truth today:** `DAILY_STATE.md` — **not** the task graph. The graph dual-writes in parallel but is **not yet authoritative** (Phase E not cut over).

**Known limitations / bottlenecks:**
1. ⚠️🔴 **Open-loop cron drift** — live cron behavior = the dashboard `payload.message`, hand-maintained, no git reconcile. SKILL edits don't reach a "fat" cron until it's manually thinned. This is the structural root of most drift.
2. 🔴 **`DAILY_STATE.md` single-writer staleness** — only Meeting-Intelligence (from Fireflies transcripts) writes it. No call → stale → every reader can serve stale state.
3. 🟡 **Large dormant surface** — `agent_memory` (0 rows), `blockers` (0 rows), the standup-reply parser (no cron), and the entire V5 PMF OS are built but not exercised.
4. 🔴 **SOUL/MEMORY at the ~20k injection cap** — silent truncation risk on the very rules everything relies on.
5. 🔴 **Security exposures** — over-scoped GitHub token; `dangerouslyDisableDeviceAuth: true` on the gateway.
6. 🟡 **Doc fragmentation** — ROADMAP, operating-model, CLAUDE.md, and the cron snapshot disagree on cadence and Phase-E status.

---

## 2. V4 Status Breakdown

| Phase | Scope | Status | Notes |
|---|---|---|---|
| **A** — schema + intent classifier | migrations 0001/0002, gated classifier | ✅ complete + live | classifier firing hard (715 audits) |
| **B** — task lifecycle | `task-handler` sole writer; MI/DM/standup/channel feeders | ✅ built + **write-path activated 06-01**; ⚠️ tasks-landing verification ongoing | MI + channel + DM feeders fire; **standup feeder dormant** (no trigger) |
| **C** — scheduling | `reminder-dispatcher`, RRULE, REMINDER_REQUEST | ✅ complete; 🟡 barely exercised (`scheduled_actions` = 1 row) | |
| **D.1** — BON Knowledge Base | 18 files in `workspace/knowledge/` | ✅ complete | Abhinav-solo-owned |
| **D.2** — Watchers V1 | creator/dispatcher/janitor + event-poller; W-1/2/3 live | ✅ complete + live; 🟡 **event-watcher *actions* unproven** | cron-watchers fire; `task_status_changed` poller source dormant |
| **E** — cutover (graph → source of truth) | flip SQLite authoritative; `DAILY_STATE.md` → generated view | ⚠️🔴 **NOT done** — only **P4.1 generator** shipped (`lib/generate_daily_state.py`); **no P4.2 parity, no P4.3 cut commits exist in git (`--all`)** | every doc says "~Jun 4–6"; **all aspirational** |
| **Capstone** — KB self-maintenance watcher | scheduled KB-diff → propose edits | ⏸️ gated, never started | blocked on E + healthy graph |

**Blocked:** Phase E cutover (correctly should be — gated on a *healthy* graph, which we don't have yet); OpenClaw upgrade (Ops-2, crashes on Slack-streaming schema).

**Technical debt accumulated during V4** (all cited in `live-system-map`/`system-evolution`/`ROADMAP`):
- Cron snapshot stale (19 vs 22 live); not a generated mirror.
- Standup-reply parser dormant; `agent_memory` + `blockers` write-paths unproven (0 rows).
- SOUL/MEMORY at the 20k cap.
- Dual-DB shared migrations (both DBs carry full schema; isolation by codepath only).
- Notion-era skills (`doc-keeper`, `report-health`, `proposal-loop`) still target Notion, which the live write-path no longer centers on — likely degraded.
- `thinker` SKILL text understated live behavior (now corrected via #85).
- Over-scoped GitHub token (Issue F, deferred).

---

## 3. Issue Registry

Status legend: **fixed** (properly) · **partial** (coded, unverified-live or open tail) · **patched** (band-aid) · **open** (unresolved). Calibrated against this session's live checks.

| # | Issue | Root cause | Status | Risk |
|---|---|---|---|---|
| 1 | **Open-loop cron drift** | live = dashboard prompt, no git reconcile | **partial** — Thinker ✅ thinned+applied+**verified-live this session**; Daily-Pulse(#87)/Pre-Call(#88) SKILLs merged, **dashboard apply pending/held**; MI+classifier already thin | 🔴 High |
| 2 | **`DAILY_STATE.md` single-writer staleness** | only MI/transcripts write it | **open** (structural fix = Phase E, undelivered) | 🔴 High |
| 3 | **Standup-reply parser dormant** | grammar built, **no cron triggers it**; 0 `standup_reply` rows | **open** | 🟡 Med (launch-relevant) |
| 4 | **`agent_memory` 0 rows** | capture reflex shipped (0006), never exercised | **partial** (built, unproven) | 🟡 Med |
| 5 | **`blockers` 0 rows** | MI/task-handler blocker write-path may not fire | **partial** (path coded, unverified) | 🟡 Med |
| 6 | **Fabrication / grounding** (facts from memory, invented A2P URLs, wrong dates/owners) | no grounding contract historically | **partial** — contract live (#77/#78/#80) + source-router (#92); **enforcement is instruction-only**; A2P KB content (#79) still OPEN with fill-in slots | 🔴 High |
| 7 | **Identity-roster drift** (stale hardcoded rosters; missing Tarun/Nilesh) | inline rosters in fat prompts | **partial** — Thinker fixed (#90, merged+deployed); **Daily-Pulse fix #91 OPEN** | 🟡 Med |
| 8 | **`{delivery:mode:none}` phantom** (good runs marked "failed") | OpenClaw cron layer mis-marks `none` delivery | **patched** (worked around via `action=send`; platform bug unfixed, needs the blocked upgrade) | 🟡 Med (alert fatigue masks real failures) |
| 9 | **SOUL/MEMORY at ~20k injection cap** | growing injected context hits silent-truncation cap | **open** (acute) — SOUL ≈19.9k after OM-2, MEMORY ≈19.6k | 🔴 High |
| 10 | **Over-scoped GitHub token (Issue F)** | token has full `repo` read+**write**; "READ ONLY" is instruction-only | **open** (deferred) | 🔴 High (security) |
| 11 | **OpenClaw upgrade blocked (Ops-2)** | v2026.5.x crashes on `channels.slack.streaming` schema change | **open** (deferred #48) | 🟡 Med |
| 12 | **Cron snapshot stale (19 vs 22)** | hand-maintained, not generated from `cron.list` | **open** | 🟡 Med |
| 13 | **`due_at` sparse + thinned-cron runtime inflation** | many tasks lack `due_at`; thin crons read SKILLs at runtime → slower (Thinker ran **~279s/300s** on a *quiet* run, ✅ observed this session) | **partial** — `due_at` rule fixed (#51); runtime fix = bump timeouts to 600s (**queued, not confirmed applied**) | 🟡 Med |
| 14 | **`dangerouslyDisableDeviceAuth: true`** on the gateway | build-time convenience flag | **open** | 🔴 Med-High (security) |
| 15 | **Dual-DB shared migrations** | `entrypoint.sh` runs all migrations on both DBs; isolation by codepath | **partial** (works, untidy) | 🟢 Low |
| 16 | **Stale branch + "never `railway up` from local" footgun** | a local deploy once crash-looped prod | **patched** (discipline-only; Ops-3 lesson) | 🟢 Low-Med |

**Scorecard:** of 16, **~0 are cleanly fixed end-to-end**, ~7 partial, ~3 patched, ~6 open. **The meta-pattern: every "fix" that touches live behavior (cron thinning #1, grounding #6, roster #7) is gated on a manual dashboard apply or an open PR — the exact open loop it's meant to cure.** Highest-risk open items: **#10 (token write scope)** and **#9 (SOUL truncation)**, then **#2/Phase-E premature-cutover risk**.

---

## 4. Capability Inventory

### Datastores & memory layers
| Store | Holds | Authoritative for | Writer | Reality |
|---|---|---|---|---|
| `alaska.db` (`/data/queue/`) | task graph + ops (tasks, blockers, intent_inbox, classifier_audit, scheduled_actions, watchers, watcher_fires, agent_memory, outbox) | tasks/PM (post-E), watchers, classifier, reminders | V4 skills (`task-handler` sole task writer) | ✅ live; 50 tables total (PMF tables also migrated here but unused) |
| `alaska_pmf.db` (`/data/queue/`) | 12 `pmf_*` + `credgpt_quality_*` tables | everything PMF | `lib/pmf_os/store.py` only | 📄 built; **population unverified-live** |
| `DAILY_STATE.md` (`workspace/`) | per-person operational state | operational state **until Phase E** | meeting-intelligence | ✅ authoritative today |
| KB (`workspace/knowledge/`) | BON domain facts (18 files) | "what a thing is / can do" | Abhinav (solo) | ✅ |
| `MEMORY.md` + `memory/*` | identity, roster, history | who's who + how Alaska evolved | Alaska/Abhinav | ✅ but at cap |
| `agent_memory` (in `alaska.db`) | Alaska's private notes | her own working memory | `agent-memory` skill | 📄 0 rows — never exercised |

### Skills (grouped; maturity is the honest column)
- **Input (firing):** meeting-intelligence 2.3.1, intent-classifier 1.4.1, task-handler 1.2.0.
- **PM agents (firing):** daily-pulse 1.1.0, follow-through 2.1.0, risk-radar 1.1.0, thinker 1.0.0 *(SKILL text now matches live after #85/#90)*, sprint-operator 2.0.0, doc-keeper 1.0.0 *(⚠️ still writes Notion — likely degraded)*.
- **Capability:** user-profile-360 1.0.0 (firing), amplitude-analyst 2.0.0 (on-demand), customerio-ops 1.0.0 (on-demand), watcher-creator/janitor 1.1.0 + watcher-dispatcher 1.0.0 + event-poller 1.0.0 (firing; **event actions unproven**), reminder-dispatcher 1.0.0 (barely used), slack-commands 1.3.0 (firing), pre-call-brief 1.0.0 *(brief posts; **Step-4 reply parser dormant**)*, agent-memory 1.0.0 *(**never exercised**)*, **pmf-cohort-os 0.1.0 (built, NOT activated)**.
- **Core/infra:** alaska-core 2.1.0, shared-toolkit 1.0.0 (foundational, always-loaded). **Dead/deprecated:** whatsapp-send (deprecated), report-health + proposal-loop (Notion-era, likely dormant).

### V5 / PMF systems (built, code-complete through P9, **dormant**)
- **Cohort:** one ~3-day signup window (~1,000 signups / ~750 real users), per-user tracked.
- **Funnel (6 stages):** signed_up → onboarded_real_user → activated_user → activated_saver → likely_lover → confirmed_lover (failed link ≠ activation).
- **6 PMF metrics:** **4 computed deterministically** (activation_depth, repeat_engagement, financial_action, linked_financial_context); **2 deferred** (qualitative_positive_signal — no sentiment source; retained_value — time-gated).
- **Case files, 9 operating queues, gated interventions, CredGPT Quality Observatory** (deterministic triage + gated LLM judge), **end-cohort memo**.
- **`/pmf` command + cross-aware pointer:** routing is **markdown/governance** (intent-classifier short-circuit + alaska-core DM path + SOUL table) + **one read-only lookup** (`store.get_active_cohort_membership`). Fires nothing until a cohort is activated. Not a native Slack slash-command (deferred infra spike).
- **lib/pmf_os/**: store, funnel, orchestrator, collectors (amplitude/user360/identity), credgpt_quality, customerio_exec+guard, daily_briefing, end_cohort, queue_actions, slack_delivery, dogfood (synthetic), artifacts/docflow. **138 tests pass.**

---

## 5. Architecture Review

**Solid (keep + build on):**
- **The source-router (V5/OM-1→3)** — `Mode → Source → Skill → GROUND`, with an explicit "never use" per mode. The right answer to "5–7 sources, nothing decides." Genuinely good design.
- **One-writer task graph** (`task-handler` sole writer) — clean, auditable.
- **Skill-as-workflow** model + thin-cron deferral — when applied, it closes the drift loop (Thinker proves it).
- **Grounding contract** (SOUL/AGENT_RULES/alaska-core) — the right discipline; reflexes + router.
- **V5 engineering** — deterministic core + injectable/key-gated LLM, synthetic dogfood, strong tests. "One Alaska, a mode within" is the correct framing; PMF reuses `user-profile-360` rather than forking.

**Fragile:**
- **The open-loop cron layer** — the single biggest structural weakness. Hand-maintained dashboard prompts that diverge from SKILLs. Everything downstream inherits it (a PMF cron would too).
- **Single-writer `DAILY_STATE.md`** — chronic staleness root.
- **Doc fragmentation** — multiple state docs that disagree (cadence, Phase-E). This *is* the "drift" the user feels.
- **SOUL/MEMORY at cap** — fragile to silent truncation.
- **Dual-DB shared migrations** + dangling **Notion-era skills**.

**Architectural mistakes we're making (brutally honest):**
1. **Building ahead of verifying.** We accumulate built-but-dormant capability (agent_memory, blockers, standup, all of V5) faster than we prove any of it runs. "Code-complete" is being treated as "done."
2. **Docs as source of truth instead of the live system.** We've repeatedly stated live behavior from stale docs (it bit this very review twice). The live system must be the source; docs are generated/verified mirrors.
3. **Patching crons by hand** instead of finishing the structural fix (thin them all + generate the snapshot).
4. **Carrying dead weight** (Notion-era skills) that confuses the picture.

**Where complexity is increasing unnecessarily / what to simplify:**
- Make the cron snapshot a **generated mirror**; thin **all** crons → kill the open loop.
- Collapse state docs to **two**: this report (state) + `live-system-map` (verified topology); everything else points to them.
- Retire/clearly-mark the Notion-era skills.
- Resolve the dual-DB migration partition (low priority).

---

## 6. Current Workstream Map

| Workstream | What | Status | Owner | Priority | Depends on |
|---|---|---|---|---|---|
| **W1 cron-thinning** | Thinker | ✅ applied + verified-live | Claude+Alaska | — | done |
| | Daily-Pulse (#87) | SKILL merged; **dashboard apply pending** | you+Alaska | 🔴 P0 | verify Thinker (done) |
| | Pre-Call (#88) | SKILL merged; **apply held for W2** | you+Alaska | P1 | W2 |
| | Thinker timeout 300→600 (instruction ①) | **queued, unconfirmed** | Alaska | 🔴 P0 | — |
| | Daily-Pulse identity (#91) | **PR OPEN** | you | P1 | merge |
| **W2 standup feeder** | trigger cron → pre-call Step-4 parser → task-handler (+ fuzzy match) | not started | Claude | 🔴 P0 (launch-critical) | — |
| **W4 verify dormant paths** | smoke-test agent_memory + blockers; re-verify grounding/A2P/dates | not started | Claude | 🔴 P0 | — |
| **Snapshot regen** | regenerate `cron-jobs-backup.json` from `cron.list` | not started | Claude+Alaska | P1 | W1 applies |
| **Phase 3 thinning** | follow-through, risk-radar, sprint-operator, doc-keeper, + new daily-cost-report SKILL | not started | Claude | P2 (post-launch) | — |
| **Phase E** | P4.2 parity → P4.3 cutover | **HOLD** | Claude | P2 (post-launch) | healthy graph (W2) |
| **Security** | GitHub token least-privilege (#10); device-auth (#14) | not started | **you** (owns token swap) | 🔴 P0 | — |
| **SOUL/MEMORY trim** (#9) | trim below cap before any further injected context | not started | Claude | 🔴 P0 | — |
| **V5 activation** | deploy keys → dogfood calibration → cron → activate cohort | not started | you+v5 agent | 🔴 P0 for Jun 11–15 | keys, calibration |
| **V5 features P10–P12** | on-demand case file, weekly digest+cron, calibration | not started | v5 agent | P1 | activation |
| **OpenClaw upgrade** (Ops-2/#48) | config pre-fix + doctor pre-flight + bump | deferred | Claude | P2 (post-launch) | — |
| **A2P KB content** (#79) | fill `twilio.md` slots; merge | PR open | **you** | P1 | your paste |
| **KB self-maint capstone** | scheduled KB-diff watcher | gated | Claude | P3 | Phase E |

---

## 7. V4 → V5 Transition Analysis

**V4 problems V5 *architecturally solves*:**
- **Source-confusion / "answer from the wrong source or from memory"** → the OM-1→3 source-router gives a deterministic Mode→Source→Skill→Ground path with explicit per-mode "never use." (Caveat: enforcement is governance-doc + one lookup, validated "in spirit," **not yet by a live cohort**.)
- **"A human can't track 1,000 cohort users"** → the deterministic ETL→store→judgment→delivery loop is the real new capability.

**V4 problems V5 does *not* touch (still need dedicated V4 fixes):**
- **Cron drift** — V5 adds zero reconciliation; a PMF cron would inherit the same open loop.
- **`DAILY_STATE.md` single-writer / Phase E** — untouched by design.
- **Standup-reply parser dormant, `agent_memory` 0, `blockers` 0** — orthogonal to V5; still need W2/W4.

**Stop / Accelerate / Hold:**
- 🛑 **Stop** opening new build fronts before activating + verifying what's built. The risk isn't quality — it's a growing dormant surface against a hard deadline.
- ⏩ **Accelerate** (a) closing the V4 loop (W1 applies + W2 + W4) and (b) **V5 activation** (keys → calibration → cron → cohort) for the Jun 11–15 window.
- ✋ **Hold** Phase E cutover until the graph is healthy (W2 feeding it) and parity (P4.2) is proven. **Do not** cut `DAILY_STATE` to a generated view of an incomplete graph, regardless of the dates in any doc.

---

## 8. Recommended Plan

**Single consolidated roadmap, launch-aware (V2 ~Jun 10, cohort ~Jun 11–15):**

**Immediate (pre-launch, this week) — close the loop + de-risk:**
1. 🔴 **Apply Thinker timeout 600s + apply Daily-Pulse thin prompt (#87, with #91 merged first).** Lands the stuck weekend/freshness fixes. (W1)
2. 🔴 **Build W2 — the standup-reply trigger cron.** Launch-critical (daily standups feed the graph) and it heals issue #3 + feeds Phase E.
3. 🔴 **W4 smoke-tests:** prove `agent_memory` and `blockers` write-paths actually fire; re-verify grounding (A2P/dates/owners). Converts "partial/unproven" → "fixed or known-broken."
4. 🔴 **Security:** swap the GitHub token to least-privilege (#10); decide on `dangerouslyDisableDeviceAuth` (#14). *Your* call/ownership.
5. 🔴 **Trim SOUL/MEMORY below the 20k cap (#9)** before any further injected context.
6. 🔴 **V5 activation track (parallel, with v5 agent):** set+validate deploy keys (Slack/Anthropic/Customer.io) → run historical-backfill calibration (not just synthetic) → wire the PMF cron → activate the cohort for the window. Confirm the DOCX/PDF runtime check.
7. 🟡 Merge A2P KB content (#79); regenerate the cron snapshot from `cron.list`.

**Post-launch:**
8. Finish thinning (Phase 3: follow-through, risk-radar, sprint-operator, doc-keeper, + daily-cost-report SKILL) → regenerate snapshot.
9. **Phase E** once the graph is healthy + parity proven (P4.2 → P4.3).
10. OpenClaw upgrade (unblocks the delivery phantom); retire Notion-era skills; KB self-maintenance capstone.

**Biggest risks (ranked):** (1) premature **Phase E cutover** onto an incomplete graph; (2) the **read+write GitHub token**; (3) **SOUL truncation** silently dropping safety rules; (4) **launching on dormant/unverified paths** (standup, blockers, agent_memory, all of V5) and discovering they don't fire under load.

**Biggest leverage points:** (1) **closing the open loop** — thin all crons + generated snapshot + a "verify-live, never assert-from-doc" discipline, so *merged = live*; (2) **this doc + the live-system-map as the only two state docs**; (3) **V5's source-router** — once activated, it's the spine that makes "one Alaska" coherent.

---

## 9. Keeping this true (the closed loop, applied to ourselves)

- This report + `docs/alaska-live-system-map.md` are the **two** state docs. ROADMAP/operating-model/CLAUDE.md point here; they don't re-assert state.
- **Never state live behavior from a doc** — verify against `cron.list` / the live DB / a live check, or label it "repo says X (unverified live)."
- Re-run the 5-agent audit on a cadence (and after each launch milestone); flag any live≠repo delta.
- The cron snapshot is a **generated mirror**, regenerated after any cron change — never hand-maintained.
- "**Merged ≠ live**" is the standing reminder: a fix isn't done until it's verified running.
