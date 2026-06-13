# Alaska Roadmap — naming + phases (living doc)

> **What this is:** the single, canonical map of Alaska's build. One naming scheme so Abhinav + Claude never get lost. Living doc — update status here as phases land. Detail lives in `docs/superpowers/specs|plans|research/`; history in `workspace/memory/system-evolution.md`.
> **Last updated:** 2026-06-02

---

## Version eras (the top level)

| Era | What it is | Status |
|---|---|---|
| **v1–v3** | The reactive PM era + the stabilization patches (v2.0 → v2.3). Alaska as a meeting/standup/follow-up bot. | History — see `memory/system-evolution.md` |
| **V4** | **The proactive-coworker foundation.** Turns Alaska from reactive → ambient teammate. Built as Phases A→E. | ✅ A–E complete; **E: CUTOVER COMPLETE (2026-06-12, PR #157)** — the task graph is the source of truth |
| **V5** | **PMF Cohort Operating System.** The headline/current focus of the V5 era: Alaska becomes the active PMF cohort operator for BON's V2 launch cohort, inside the larger AI-coworker arc. | 🟡 foundation merged (#59); implementation phases in progress |

**Naming rules (so we stay consistent):**
- **Phase A–E** = the V4 build stages. Use these going forward (not "vX.Y").
- **vX.Y** (v2.0–v2.3) = historical stabilization patches to the *pre-V4 live system*. Frozen as history.
- **`.N` sub-stages** = steps within a phase (A.1/A.2/A.3, D.1/D.2).
- **Ops-N** = cross-cutting operational work (infra, upgrades, incident fixes) — runs in parallel, not a V4 phase.

---

## V4 — the phases

### Phase A — Schema + Intent Classifier ✅ DONE
The substrate: the SQLite task graph + the message classifier.
- **A.1** — migrations + runner (`0001_v2_task_model.sql`) ✅
- **A.2** — intent-classifier in observation mode (9 intents) ✅
- **A.3** — classifier v1.1 tuning + `secondary_intents` (`0002`) ✅

### Phase B — Task Lifecycle ✅ DONE + ACTIVATED (2026-06-01)
The write path. **`task-handler` is the single writer; everything else feeds it.**
- **B1** shared-toolkit Task Write Contract · **B2** task-handler (match-or-create dedup) · **B3** Meeting Intelligence → task-handler · **B4** Slack DM intent handlers → task-handler · **B5** pre-call-brief reads SQLite + parses standup/thread replies → task-handler.
- ✅ **ACTIVATED 2026-06-01 (P1, #50):** the MI cron was thinned to run the SKILL verbatim (incl. Step 5b → task-handler) — it had been a *fat cron prompt* that overrode the SKILL and never called task-handler, which is why the graph sat 0-row. Gated channel→task + the DM/standup feeders also write now. The graph is **populating**; the real "B is alive" proof is the tasks-landing verification (in progress, ~Jun 2 AM). DM action path live since 05-31 (#36/#37).

### Phase C — Scheduling Engine ✅ DONE
- reminder-dispatcher skill + RRULE (`lib/rrule_helper.py`) + REMINDER_REQUEST handler + routine-proposal approval. Phase C's `scheduled_actions`/`routine_proposals` get migrated into Watchers (Phase D.2), then deprecated.

### Phase D — The Proactive Layer 🟡 IN PROGRESS
This is where "proactive ambient coworker" actually gets built. **Two sub-phases, ordered by dependency:**

- **D.1 — BON Knowledge Base** ✅ DONE (PR #33; co-built Abhinav + Claude)
  - Gives Alaska domain fluency (knows "failed Plaid user", credit buckets, personas) so watcher/skill drafting stops interrogating.
  - **Prerequisite for D.2** — watchers read the KB.
  - Status: ✅ **18 files committed** to `workspace/knowledge/` (git-tracked) — README, architecture, 3 definitions (personas / metrics / lifecycle-events), 11 integrations (amplitude, array, customerio, fireflies, github, notion, plaid, slack, spinwheel, twilio, user-profile-api), 2 playbooks (common-queries, failure-modes). Ongoing completeness/quality is Abhinav's call (KB owner).
  - Principle (capability-vs-workflow): KB files = "what is this + what can Alaska DO with it" (BON capabilities); the **operating model lives once in `docs/alaska-operating-model.md`** (with current-vs-V4 framing), NOT in the KB. `knowledge/architecture.md` stays pure BON product/system architecture. Integration files = external-system facts + a pointer to the operating-model doc / skill. KB owner = Abhinav.
  - Spec: `docs/superpowers/specs/2026-05-26-bon-knowledge-base.md`. Review: `docs/superpowers/research/2026-05-30-knowledge-v2-review.md`.
  - **Done:** KB committed → D.2 unblocked (and built — see below).

- **D.2 — Watchers V1** ✅ BUILT + LIVE
  - The proactive-agency primitive: trigger + action-chain + recipient + memory + approval. User-requested only in V1 (autonomy stays with Thinker).
  - **Absorbs the old "cross-person TASK_ASSIGN" (the original Phase D) as a watcher template** — no longer a separate phase.
  - Spec: `docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md` (16 locked decisions). Plan: `docs/superpowers/plans/2026-05-27-alaska-watchers-v1.md` (reconciled in PR #26). Build = sub-phases W.0→W.4 inside D.2.
  - Status: ✅ shipped as **Watcher Gen 1** (PR #35); hardened — plain-English drafts + dates (#38), channel activation + PII guard (#39), read-state-not-assume (#40), timezone/delivery/janitor (#46). **W-1/W-2/W-3 running in prod** (tz-corrected 06-01). Skills: `watcher-creator`, `watcher-dispatcher`, `event-poller`, `watcher-janitor`. The **task-dependent templates** (`stale-task`, `cross-person-assign`) were **un-gated in V4 P3 (#52)** — handlers built (task-handler `query_stale`, follow-through `escalate_unacked_assignments`, the cross-person assign handshake). They produce results as the graph fills.

### Phase E — Cutover ✅ COMPLETE (2026-06-12, the operating-model flip)
- **DONE (PR #157):** SQLite is the **source of truth**; `DAILY_STATE.md` is a hybrid view (MI-written narrative + generated `## Per Person` / `## Active Blockers` via `lib/generate_daily_state.py`). MI no longer hand-writes the generated sections. Parity verified twice on 2026-06-12 (first run found 4 P0s, all fixed systemically; re-run clean). Rollback = revert #157 (MI resumes hand-writing).

### Deferred V4 capstone — KB self-maintenance watcher ⚪ GATED
The watcher that keeps the BON Knowledge Base updated is a **V4 capstone**, not V5. Owner: **V4 track**. Build it only after both gates are true:
- **Gate 1:** V4 validates in live end-to-end testing, including Ops-4 tasks-landing proof.
- **Gate 2:** ✅ MET (2026-06-12) — Phase E activated; SQLite is the source of truth and `DAILY_STATE.md` is generated/read-only for its Per Person / Blockers sections.

Shape: a scheduled Watcher scans recent Slack, Meeting Intelligence, DMs, and product/system changes; diffs them against `workspace/knowledge/`; drafts proposed KB edits; and asks Abhinav for approval before any write. Keep this item visible so it is not lost, but do not route it through the V5/PMF track.

---

## The complete V4 write-path map (what feeds the task graph)

ONE writer (`task-handler`), MANY feeders. This is the spine of the operating-model doc (`docs/alaska-operating-model.md`).

| Surface | Feeder | `source` | Phase | Acts today? |
|---|---|---|---|---|
| Call transcripts | meeting-intelligence (Step 5b) | `meeting` | B3 | ✅ active (06-01) |
| Slack DM to Alaska | slack-commands → classifier → task-handler | `slack_dm` | B4 | ✅ active |
| Standup-sheet / thread replies | pre-call-brief reply parser → task-handler | `standup_reply` | B5 | ✅ active |
| Channel messages | intent-classifier → task-handler (gated) | `slack_channel` | A→D | ✅ active — gated ≥0.85 (incl. TASK_ASSIGN) |
| Direct / operator | slack-commands / manual | `manual` | B4 | ✅ |

Readers (write nothing to tasks): Daily Pulse, Follow-Through, Risk Radar, Thinker. (Pre-call-brief is hybrid — reads to build sheets, writes via reply parsing.)

---

## Ops track (parallel, not V4 phases)

| ID | Item | Status |
|---|---|---|
| Ops-1 | entrypoint config-corruption guard | ✅ merged (PR #24) |
| Ops-2 | OpenClaw upgrade v2026.3.13 → **v2026.5.28** (5.26 crash-looped on the Slack streaming schema; 5.28 is the slack-plugin floor) | ✅ DONE — live at 2026.5.28 (Dockerfile pinned) |
| Ops-3 | deploy hygiene: never `railway up` from local; branch off current main; GitHub→Railway is the deploy path | ✅ lesson locked |
| Ops-4 | **verify Phase B fires in prod** (was 0-row/dormant — write path activated 06-01 via #50) | 🟡 write path live; **tasks-landing verification in progress** |
| Ops-5 | MI extraction-quality validation (May 25–29 transcript replay): speaker attribution, implicit blockers, inferred-task flag, signal-weighting | ✅ done (#42, #43 + re-replay) |

> **⚠️ Naming note (resolves a real mix-up):** the PR #42/#43 commit messages call the MI extraction work **"Ops-4"** — that was a mislabel. **Ops-4 is the prod-verification above (still pending); the MI extraction work is Ops-5 (done).** They are unrelated. Don't conflate them.

---

## Self-Improvement Loop (SIL) — parallel track (postdates the 05-30 roadmap)

The "self-improving" half of the coworker thesis: Alaska learns from feedback and proposes her *own* skill improvements via PR. Built by a **separate executor agent** in an isolated worktree (fenced from in-flight skill files).
- **Mechanism:** `skill_feedback` capture → daily self-improver → one PR/day editing only "Principles" zones (never 🔒 Guardrails, never KB / migrations / config). Least-privilege `GITHUB_SELF_IMPROVE_TOKEN` scoped to `alaska-openclaw` + branch protection + CODEOWNERS.
- **Spec:** `docs/superpowers/specs/2026-06-01-alaska-self-improvement-loop-design.md` · **Plan:** `docs/superpowers/plans/2026-06-01-alaska-self-improvement-loop.md`.
- **Status:** Phase 0 ✅ (PR #45 — `lib/open_self_pr.py` proves PR-from-container works). Phases 1–4 in progress on the executor track.

---

## V5 — PMF Cohort Operating System 🟡 STARTED

V5 is the **PMF Cohort Operating System**: Alaska's current top-priority evolution from useful Slack coworker into an active operator for BON's focused PMF cohort. This is the headline of the V5 era and the thing to build now.

This sits inside the larger horizontal AI-coworker arc: Alaska should eventually feel like "the rest of your startup team." V5 does not mean Alaska is only ever a cohort tool. It means the high-leverage teammate job V5 is centered on now is operating the PMF cohort end to end.

Canonical plan: `docs/superpowers/plans/2026-06-02-alaska-v5-pmf-cohort-os.md`. Runtime contract: `workspace/knowledge/definitions/pmf-cohort-os.md`. Skill: `skills/pmf-cohort-os/SKILL.md`.

**PR #59 completed the foundation layer, not the full rollout.** It added PMF SQLite tables, the PMF OS Python core/CLI, PMF Funnel engine, user case-file primitives, operating queues, CredGPT Quality Observatory deterministic review, Customer.io safety gates, artifact scaffolding, KB contract, skill wrapper, and tests.

**Remaining implementation phases:**

| Phase | Name | Status |
|---|---|---|
| 0 | Contracts and guardrails | Mostly done (#59 + docs follow-up) |
| 1 | Cohort Registry | Partially done — live Amplitude extraction pending |
| 2 | Signal Spine and Case Files | Partially done — full User 360 normalization pending |
| 3 | PMF Funnel Engine | Mostly done — real-data calibration pending |
| 4 | Artifact Generation | Partially done — DocFlow spec contract + artifact runtime smoke check added; deploy-time smoke check, Slack delivery, and polished templates pending |
| 5 | Customer.io Execution | Guardrails done — live email/push execution pending |
| 6 | CredGPT Quality Observatory | Partially done — live chat ingestion + LLM judging pending |
| 7 | End-Cohort Intelligence | Not started beyond storage/report foundation |

Recommended next PR sequence after the artifact runtime slice is deployed and smoke-tested: live cohort intake → User 360 enrichment/case files → daily cockpit delivery → CredGPT live observability → Customer.io execution → end-cohort intelligence.

---

## Current status snapshot (updated 2026-06-12 — Phase E cutover landed)

```
V4:  A ✅   B ✅ ACTIVATED 06-01 (graph populating)   C ✅   D.1 ✅   D.2 ✅ live (task-templates un-gated)   E ✅ CUTOVER COMPLETE 06-12 (#157)
Ops: Ops-1 ✅   Ops-2 ✅ upgrade live (2026.5.28)   Ops-3 ✅   Ops-4 ✅ write path activated (#50)   Ops-5 ✅
Build: V4 COMPLETE (A–E coded). P1–P4.1 = PRs #50/#51/#52/#53. Live-test hardening = #54 (channel TASK_ASSIGN) / #55 (DM action-honesty) / #56 (cross-session memory).
Source of truth: the SQLite task graph (✅ authoritative since the Phase E cutover, 2026-06-12). DAILY_STATE.md is its generated view + MI narrative.
Now: 24h E2E test. Verify tomorrow AM — tasks landing by source (real "B alive" proof), W-1 clean 9:30 fire, 6 PM pulse double-fire.
Next: ✅ cutover shipped 2026-06-12 (#157); Ops-2 upgrade done (live 2026.5.28).
```

## Dependency chain (the critical path)

```
V4 spine: D.1 ✅ ──→ D.2 ✅ ──→ [ Ops-4: does the prod task graph populate? ] ──→ E (cutover) + #49 (watcher task-actions) ──→ V4 capstone: KB self-maintenance watcher
V5 spine: PMF Cohort Operating System, running as the current top-priority focus inside the larger AI-coworker arc
```
**Ops-4 cleared; Phase E shipped (2026-06-12).** The task graph populates and is the source of truth. Everything non-task — the live reactive cadence, DM actions, channel/customer-signal watchers, reminders — is already running.
