# Alaska Roadmap — naming + phases (living doc)

> **What this is:** the single, canonical map of Alaska's build. One naming scheme so Abhinav + Claude never get lost. Living doc — update status here as phases land. Detail lives in `docs/superpowers/specs|plans|research/`; history in `workspace/memory/system-evolution.md`.
> **Last updated:** 2026-06-01

---

## Version eras (the top level)

| Era | What it is | Status |
|---|---|---|
| **v1–v3** | The reactive PM era + the stabilization patches (v2.0 → v2.3). Alaska as a meeting/standup/follow-up bot. | History — see `memory/system-evolution.md` |
| **V4** | **The proactive-coworker foundation.** Turns Alaska from reactive → ambient teammate. Built as Phases A→E. | 🟡 In progress (A,B,C,D built; **E pending, gated on Ops-4**) |
| **V5** | The "complete new Alaska" — Abhinav's larger vision (not fully shared yet). First concrete piece: a KB self-maintenance agent (which is itself a Watcher). | ⚪ Future |

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

### Phase B — Task Lifecycle ✅ DONE (but DORMANT in prod)
The write path. **`task-handler` is the single writer; everything else feeds it.**
- **B1** shared-toolkit Task Write Contract · **B2** task-handler (match-or-create dedup) · **B3** Meeting Intelligence → task-handler · **B4** Slack DM intent handlers → task-handler · **B5** pre-call-brief reads SQLite + parses standup/thread replies → task-handler.
- ⚠️ **DORMANT (0-row as of 05-30):** the pipeline is wired but may never have been exercised on real data. **Ops-4 = verify it actually fires in prod** — the gate for Phase E and the task-dependent watcher templates (#49). The DM action path was activated 05-31 (#36/#37: classify→route, no improvised crons); whether real task rows have landed is exactly what Ops-4 checks (re-running 2026-06-01).

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
  - Status: ✅ shipped as **Watcher Gen 1** (PR #35); hardened — plain-English drafts + dates (#38), channel activation + PII guard (#39), read-state-not-assume (#40), timezone/delivery/janitor (#46). **W-1/W-2/W-3 running in prod** (tz-corrected 06-01). Skills: `watcher-creator`, `watcher-dispatcher`, `event-poller`, `watcher-janitor`. ⚠️ The **task-dependent templates** (`stale-task`, `cross-person-assign`, `task_status_changed` poller) stay inert until **Ops-4** confirms tasks flow (#49).

### Phase E — Cutover ⚪ PENDING (the operating-model flip)
- Flip SQLite to the **source of truth**; `DAILY_STATE.md` becomes a generated read-only view; retire direct MI writes to it. This is the change that makes the KB's "SQLite is source of truth" framing TRUE (it's currently target-not-actual). Dual-write window first, then hard-cut.

---

## The complete V4 write-path map (what feeds the task graph)

ONE writer (`task-handler`), MANY feeders. This is the spine of the operating-model doc (`docs/alaska-operating-model.md`).

| Surface | Feeder | `source` | Phase | Acts today? |
|---|---|---|---|---|
| Call transcripts | meeting-intelligence (Step 5b) | `meeting` | B3 | ✅ wired (dormant) |
| Slack DM to Alaska | slack-commands → classifier → task-handler | `slack_dm` | B4 | ✅ wired |
| Standup-sheet / thread replies | pre-call-brief reply parser → task-handler | `standup_reply` | B5 | ✅ wired |
| Channel messages | intent-classifier (observe) → [task-handler] | `slack_channel` | A→**D** | ⏳ observe-only until D |
| Direct / operator | slack-commands / manual | `manual` | B4 | ✅ |

Readers (write nothing to tasks): Daily Pulse, Follow-Through, Risk Radar, Thinker. (Pre-call-brief is hybrid — reads to build sheets, writes via reply parsing.)

---

## Ops track (parallel, not V4 phases)

| ID | Item | Status |
|---|---|---|
| Ops-1 | entrypoint config-corruption guard | ✅ merged (PR #24) |
| Ops-2 | OpenClaw upgrade v2026.3.13 → v2026.5.26 (needs config pre-fix + `doctor --fix` pre-flight; crashed on Slack streaming schema) | ⚪ deferred (#48) |
| Ops-3 | deploy hygiene: never `railway up` from local; branch off current main; GitHub→Railway is the deploy path | ✅ lesson locked |
| Ops-4 | **verify Phase B fires in prod** (task tables 0-row as of 05-30 — is the write path actually alive?) | ⚪ pending → **running 2026-06-01** |
| Ops-5 | MI extraction-quality validation (May 25–29 transcript replay): speaker attribution, implicit blockers, inferred-task flag, signal-weighting | ✅ done (#42, #43 + re-replay) |

> **⚠️ Naming note (resolves a real mix-up):** the PR #42/#43 commit messages call the MI extraction work **"Ops-4"** — that was a mislabel. **Ops-4 is the prod-verification above (still pending); the MI extraction work is Ops-5 (done).** They are unrelated. Don't conflate them.

---

## Self-Improvement Loop (SIL) — parallel track (postdates the 05-30 roadmap)

The "self-improving" half of the coworker thesis: Alaska learns from feedback and proposes her *own* skill improvements via PR. Built by a **separate executor agent** in an isolated worktree (fenced from in-flight skill files).
- **Mechanism:** `skill_feedback` capture → daily self-improver → one PR/day editing only "Principles" zones (never 🔒 Guardrails, never KB / migrations / config). Least-privilege `GITHUB_SELF_IMPROVE_TOKEN` scoped to `alaska-openclaw` + branch protection + CODEOWNERS.
- **Spec:** `docs/superpowers/specs/2026-06-01-alaska-self-improvement-loop-design.md` · **Plan:** `docs/superpowers/plans/2026-06-01-alaska-self-improvement-loop.md`.
- **Status:** Phase 0 ✅ (PR #45 — `lib/open_self_pr.py` proves PR-from-container works). Phases 1–4 in progress on the executor track.

---

## V5 — preview (after V4)

The "complete new Alaska." Not fully scoped — Abhinav to brain-dump. First concrete piece shared 2026-05-30:
- **V5.x — KB self-maintenance agent.** Weekly trigger → scans the week's Slack/MI/DMs → diffs against the KB → proposes updates → Abhinav approves. **This is a Watcher** — it rides on the D.2 substrate. Proof the V4 foundation is right: the V5 flagship is just a watcher template.

---

## Current status snapshot (2026-06-01)

```
V4:  A ✅   B ✅(dormant — Ops-4)   C ✅   D.1 ✅   D.2 ✅ built+live   E ⚪ pending
Ops: Ops-1 ✅   Ops-2 ⚪ deferred(#48)   Ops-3 ✅   Ops-4 ⚪ running   Ops-5 ✅
Also live: DM intent-action layer (#36/#37)  ·  Self-Improvement Loop: spec #41, Phase 0 #45 (separate executor track)
Recent hardening (06-01): MI attribution+extraction (#42/#43=Ops-5), watcher tz/janitor (#46), blocker dedup (#47)
Open PRs: none (all merged through #47)
Immediate next: run Ops-4 (does the prod task graph populate?) → then Phase E planning or wire watcher task-actions (#49). Hold #48 until post-launch.
```

## Dependency chain (the critical path)

```
D.1 ✅ ──→ D.2 ✅ ──→ [ Ops-4: does the prod task graph populate? ] ──→ E (cutover) + #49 (watcher task-actions) ──→ V5 (KB-agent + bigger vision)
```
**Ops-4 is now the gate.** Phase E (SQLite→source-of-truth) and the task-dependent watcher templates both need a populated graph. Everything non-task — the live reactive cadence, DM actions, channel/customer-signal watchers, reminders — is already running and does NOT wait on Ops-4.
