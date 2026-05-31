# Alaska Roadmap — naming + phases (living doc)

> **What this is:** the single, canonical map of Alaska's build. One naming scheme so Abhinav + Claude never get lost. Living doc — update status here as phases land. Detail lives in `docs/superpowers/specs|plans|research/`; history in `workspace/memory/system-evolution.md`.
> **Last updated:** 2026-05-30

---

## Version eras (the top level)

| Era | What it is | Status |
|---|---|---|
| **v1–v3** | The reactive PM era + the stabilization patches (v2.0 → v2.3). Alaska as a meeting/standup/follow-up bot. | History — see `memory/system-evolution.md` |
| **V4** | **The proactive-coworker foundation.** Turns Alaska from reactive → ambient teammate. Built as Phases A→E. | 🟡 In progress (A,B,C done; D,E pending) |
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
- ⚠️ **DORMANT:** prod task tables are 0-row — the pipeline is wired but never exercised. **Verify it actually fires before V4 leans harder on it** (tracked).

### Phase C — Scheduling Engine ✅ DONE
- reminder-dispatcher skill + RRULE (`lib/rrule_helper.py`) + REMINDER_REQUEST handler + routine-proposal approval. Phase C's `scheduled_actions`/`routine_proposals` get migrated into Watchers (Phase D.2), then deprecated.

### Phase D — The Proactive Layer 🟡 IN PROGRESS
This is where "proactive ambient coworker" actually gets built. **Two sub-phases, ordered by dependency:**

- **D.1 — BON Knowledge Base** 🟡 IN PROGRESS (co-build: Abhinav + Claude)
  - Gives Alaska domain fluency (knows "failed Plaid user", credit buckets, personas) so watcher/skill drafting stops interrogating.
  - **Prerequisite for D.2** — watchers read the KB.
  - Status: README + architecture + integrations drafted (`BON Credit Project/knowledge-v2/`, rough, untracked); remaining: `data-models/*`, `definitions/*`, `playbooks/*`, + integrations `notion`/`slack`/`moneyline`/`user-profile-api`.
  - Principle (capability-vs-workflow): KB files = "what is this + what can Alaska DO with it" (BON capabilities); the **operating model lives once in `docs/alaska-operating-model.md`** (with current-vs-V4 framing), NOT in the KB. `knowledge/architecture.md` stays pure BON product/system architecture. Integration files = external-system facts + a pointer to the operating-model doc / skill. KB owner = Abhinav.
  - Spec: `docs/superpowers/specs/2026-05-26-bon-knowledge-base.md`. Review: `docs/superpowers/research/2026-05-30-knowledge-v2-review.md`.
  - **Done when:** KB committed to repo `workspace/knowledge/` (git-tracked) → unblocks D.2.

- **D.2 — Watchers V1** 🟡 DESIGNED, gated on D.1
  - The proactive-agency primitive: trigger + action-chain + recipient + memory + approval. User-requested only in V1 (autonomy stays with Thinker).
  - **Absorbs the old "cross-person TASK_ASSIGN" (the original Phase D) as a watcher template** — no longer a separate phase.
  - Spec: `docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md` (16 locked decisions). Plan: `docs/superpowers/plans/2026-05-27-alaska-watchers-v1.md` (reconciled in PR #26). Build = sub-phases W.0→W.4 inside D.2.

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
| Ops-4 | verify Phase B fires in prod (task tables dormant at 0 rows) | ⚪ pending |

---

## V5 — preview (after V4)

The "complete new Alaska." Not fully scoped — Abhinav to brain-dump. First concrete piece shared 2026-05-30:
- **V5.x — KB self-maintenance agent.** Weekly trigger → scans the week's Slack/MI/DMs → diffs against the KB → proposes updates → Abhinav approves. **This is a Watcher** — it rides on the D.2 substrate. Proof the V4 foundation is right: the V5 flagship is just a watcher template.

---

## Current status snapshot (2026-05-30)

```
V4:  A ✅   B ✅(dormant)   C ✅   D.1 🟡 in progress   D.2 🟡 designed/gated   E ⚪ pending
Ops: Ops-1 ✅   Ops-2 ⚪   Ops-3 ✅   Ops-4 ⚪
Open PRs: #26 (D.2 plan, mergeable)   #28/#29 (memory, mergeable)
Immediate next: finish D.1 (KB) — co-build remaining files, draft architecture.md operating-model section, commit to repo → unblocks D.2.
```

## Dependency chain (the critical path)

```
D.1 (BON KB committed) ──→ D.2 (Watchers V1) ──→ E (cutover) ──→ V5 (KB-agent + the bigger vision)
                                  ↑
        (cross-person TASK_ASSIGN folds in here as a watcher template)
```
