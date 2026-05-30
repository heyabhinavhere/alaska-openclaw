# V4 Session Handoff — 2026-05-27 → 05-30

> **Purpose:** Durable continuation record for the V4 build effort. If you're a fresh session picking up Alaska V4, read this top-to-bottom, then the two specs + the KB principle below. Everything here is current as of 2026-05-30.
> **What "V4" means:** the next-gen Alaska — proactive, ambient "rest of your startup team." Foundation = the v2 task model (Phases A–E) + Watchers + the BON Knowledge Base + the 360 profile. There is a *bigger* "complete new Alaska" vision Abhinav has planned but **has not fully shared yet** — that's the single biggest unknown (see §9).

---

## 1. THE IMMEDIATE NEXT THING — co-build the BON Knowledge Base

**Decision (2026-05-30):** Abhinav + Claude build the KB *together*, not independently. Rationale: Claude has the rich session context + knows the exact consumer needs (Watchers, skills), so co-building avoids bloat/unnecessary files. This is the active workstream.

**KB status:**
- ~24 files seeded locally in `workspace/knowledge/` but **untracked + rough** (Abhinav is rewriting them properly, with help from another Claude agent).
- **Done:** `README.md`, `architecture.md`, all `integrations/*` (plaid, amplitude, customerio, github, notion, slack, fireflies, moneyline, array, spinwheel, twilio).
- **Remaining:** `data-models/*` (user, credit-profile, card-linkage, financial-coaching, budgeting), `definitions/*` (metrics, lifecycle-events, personas), `playbooks/*` (common-queries, failure-modes, escalation-tree).
- **Missing entirely:** `integrations/user-profile-api.md` — the doc for Sandeep's BON admin API behind the 360 profile. Claude offered to draft it from the live `user-profile-360` skill code (`client.py`/`sections.py`) since that's code-derived, not tribal.
- **The KB is UNTRACKED LOCAL** → it must be committed to main to unblock Watchers V1 (W.1 gates on it being git-tracked).

## 1a. KB co-build — review outcome + immediate next (2026-05-30)

Abhinav's `knowledge-v2/` drafts (canonical copy: `BON Credit Project/knowledge-v2/`, OUTSIDE the repo — the prep area; a duplicate in `code/agents/alaska/` was deleted) were reviewed against the principle. Report: `docs/superpowers/research/2026-05-30-knowledge-v2-review.md`.

- **Verdict: strongly aligned — 12 of 13 files clean.** External-systems half done well, no factual errors (MoneyLion correct, User-360 referenced, Real Users filter present).
- **The one fix:** `integrations/fireflies.md` over-documents the operating model (6-step MI pipeline, cron cadence, anti-hallucination rules, Watchers-as-live, "SQLite is source of truth" asserted as current fact). `architecture.md` is currently pure BON-PRODUCT architecture (app/backend/Spinwheel-Array-Plaid pipelines/AI layer) and carries NO Alaska operating model.
- **The decided fix (IMMEDIATE NEXT — do this first when resuming the KB work):**
  1. Add a section to `architecture.md` — "## Alaska's operating model (the standup pipeline)" — the ONE canonical home for: MI pipeline summary, source-of-truth model **with the current-vs-V4 caveat** (V4 target = SQLite source of truth; current pre-cutover = MI writes DAILY_STATE directly, SQLite dormant/0-rows; Phase E flips it), the standup cadence table. Cross-reference the meeting-intelligence SKILL for the detailed extraction/anti-hallucination rules (don't duplicate those — they live in the skill).
  2. Trim `fireflies.md` to Fireflies system-facts + a 2-line pointer to that architecture.md section + the MI skill.
  This needs careful current-vs-V4 writing — best done with fresh context, not at the tail of a full session.
- **"Dead links" clarified:** several files (plaid, amplitude, metrics, lifecycle-events, personas) forward-reference not-yet-created files (`playbooks/common-queries.md`, `data-models/user.md`, `integrations/user-profile-api.md`). The files exist + are readable; the refs resolve once we create the targets. Not a bug — a to-do list.
- **Owner header decided:** Owner = Abhinav, full stop (KB maintained by Abhinav now → Alaska in future). Drop per-file `Owner:` (always Abhinav, redundant); keep per-file `Status:`; state "KB Owner/Maintainer: Abhinav (→ Alaska future)" once in README; domain expert (e.g., Sandeep/Plaid) goes in each file's `People` as SME. This standardizes toward the 12-file `Status` convention (only fireflies.md had `Owner`).
- **Still to create:** `data-models/*` (5; `user.md` is the anchor → points to user-profile-360), `playbooks/*` (3), integrations `notion`/`slack`/`moneyline`/`user-profile-api`. Then copy `knowledge-v2/` → repo `workspace/knowledge/` + commit → unblocks Watchers V1.

## 1b. D.1 KICKOFF — the locked rule + execution checklist (read this to start D.1)

**The KB rule, FINAL form (capability vs. workflow) — supersedes the looser framing in §2:**
> Every KB file answers: **"What is this, and what can Alaska DO with it?"** (the capabilities/affordances of BON's systems + integrations + APIs). It NEVER answers "how does Alaska's workflow use it." Workflow lives in skills + `docs/`, which the KB points to.

- **KB (`knowledge/`) = "what can be done" + BON knowledge.** Fireflies API + what's queryable; Amplitude Real Users filter; Plaid affordances; BON's product/system architecture (`knowledge/architecture.md`). Alaska reads it to know her toolbox.
- **Alaska workflow = "how Alaska does it"** (MI pipeline, task graph, feeders, cadence, source-of-truth) → **skills** (each skill IS a workflow) + a `docs/alaska-operating-model.md` overview. **NOT the KB.**
- **Integration files bridge:** end with "→ used by the [X] skill; see it / `docs/alaska-operating-model.md` for the pipeline."
- **CORRECTION to §2 below:** the operating model does NOT belong in `knowledge/architecture.md` (that file = BON *product/system* architecture, pure BON — leave it as Abhinav wrote it). The "Alaska's operating model" section drafted in the 2026-05-30 chat goes to `docs/alaska-operating-model.md`, NOT the KB. (§2's "operating model lives in architecture.md" line is the thing this corrects.)

**D.1 execution checklist (fresh session — do in this order):**
1. **Re-home** the operating-model section (drafted in the 2026-05-30 chat; content = the write-path map: one writer `task-handler` + 5 feeders, the cadence table, the current-vs-V4 caveat) → create `docs/alaska-operating-model.md`. Leave `knowledge/architecture.md` pure BON.
2. **Trim** `knowledge-v2/integrations/fireflies.md` → external-system facts + a pointer to the MI skill / operating-model doc. Same trim for `notion.md`, `slack.md` if they carry pipeline detail.
3. **Draft** `knowledge-v2/integrations/user-profile-api.md` from the live `user-profile-360` skill code (`skills/user-profile-360/client.py`, `sections.py`) — the capability/contract of Sandeep's BON admin API.
4. **Co-build** (Abhinav + Claude): `data-models/*` (5; `user.md` anchors → points to `user-profile-360`), `definitions/*` (review the 3 existing), `playbooks/*` (3 — the query recipes ARE capabilities), integration `moneyline.md`.
5. **Owner-header cleanup:** drop per-file `Owner:` → state "KB Owner/Maintainer: Abhinav (→ Alaska future)" once in README; keep per-file `Status:`; domain SME in each file's `People`.
6. **Reconcile + commit:** the canonical KB-in-progress is `BON Credit Project/knowledge-v2/` (OUTSIDE the repo — Abhinav's prep area). Copy it into the repo's `workspace/knowledge/` and commit (git-tracked) → **this unblocks D.2 (Watchers V1).**

## 2. THE KB AUTHORING PRINCIPLE (settled 2026-05-30 — apply to every file)

**The test for every line:** *"Is this a fact about the external system / BON's domain, or a fact about how Alaska works?"*
- External-system/domain fact (Fireflies API, "failed Plaid user" def, MoneyLion transcription drift, credit-score buckets) → **belongs in the KB integration/data-model/definition file.**
- "How Alaska works" fact (the MI 6-step pipeline, the standup cadence, "SQLite is source of truth", anti-hallucination rules) → **does NOT go in integration files.** It lives ONCE in `architecture.md` + the relevant skill file.

**Each integration file = (a) the external system (API, auth, quirks, failure modes), (b) BON-specific usage + agreed definitions, (c) a 2-line POINTER to how Alaska uses it ("Fireflies → Meeting Intelligence → SQLite graph; see architecture.md").** NOT a re-description of the pipeline.

**Why:** if the MI pipeline / "SQLite is source of truth" gets copied into fireflies.md + notion.md + slack.md + architecture.md + the MI skill, then a pipeline change (Phase E *will* change it) means updating 5 places → 4 go stale. Same drift disease as v2.2/v2.3. **The operating model needs exactly one home: `architecture.md`.**

**Current-vs-V4 honesty (critical):** Abhinav's KB drafts describe the V4 end-state ("SQLite is source of truth, DAILY_STATE is a generated view, Phase E complete"). **That is NOT production today** — currently MI still writes DAILY_STATE directly and the SQLite task tables are EMPTY (0 rows — Phase B dormant, see §7). So `architecture.md` must mark target-vs-current explicitly: *"V4 target: SQLite is source of truth. Current (pre-cutover): MI writes DAILY_STATE directly; SQLite runs in parallel, not yet authoritative. Phase E flips this."* Integration files stay V4-independent (Fireflies' API doesn't change with the cutover).

**Open offer:** Claude to draft the `architecture.md` operating-model section (the single home for MI pipeline + source-of-truth model + cadence + current-vs-V4 framing). Once it exists, integration files get SHORTER (they point at it).

**KB authoring authority: Abhinav only** (locked). Freshness: warn at 60 days, don't refuse.

## 3. V4 state of the world (what's live / designed / pending / dormant)

| Component | Status |
|---|---|
| Phase A.1 schema (migration 0001) | 🟢 LIVE |
| Phase A.2 intent-classifier (observation mode) | 🟢 LIVE |
| Phase A.3 classifier v1.1 tuning (migration 0002, secondary_intents) | 🟢 LIVE |
| Phase B task lifecycle (task-handler, MI Step 5b, Slack DM handlers, pre-call-brief SQLite) | 🟢 LIVE but 🔴 **DORMANT** — 0 rows in prod tasks tables (§7) |
| Phase C scheduling (reminder-dispatcher, RRULE, lib/rrule_helper.py) | 🟢 LIVE |
| 360 profile (`user-profile-360` skill, migration 0003, BON admin API, 4 cache tables) | 🟢 LIVE (Sandeep's work) — a prime `invoke_skill` target for Watchers |
| Watchers V1 | 🟡 Designed + plan reconciled to main (PR #26). NOT built. Gated on KB committed. |
| BON Knowledge Base | 🟡 Co-build in progress (§1) |
| Phase D (cross-person TASK_ASSIGN) | ⚪ Pending — becomes a watcher template |
| Phase E (DAILY_STATE → SQLite cutover) | ⚪ Pending |
| Bigger "complete new Alaska" vision | ⚪ In Abhinav's head, not shared (§9) |

## 4. Open PRs + branch state (as of 2026-05-30)

- **PR #24** — entrypoint config-corruption guard → **MERGED** (dcda1c7). Guard is on main + deploying.
- **PR #26** — `docs/watchers-v1-plan-reconciliation`: Watchers V1 plan reconciled to current main (9 deltas: migration 0003→0004, identity-resolver→user-profile-360, cron payload shape→agentTurn WITH delivery:{mode:none}, KB gated on git-tracked, etc.) + the 2026-05-30 audit/reconciliation research docs. **OPEN, mergeable.** Merge to make the plan execution-ready on main.
- **Stale branch `feat/watchers-v1-plan`** — 32+ commits behind main, its 2 valuable commits (entrypoint guard, upgrade research) already salvaged into #24/#26. **DELETE it** (nothing unsalvaged). Do NOT ever `railway up` from it.
- Latest main: dcda1c7 (PR #24 merge) + PR #25 (docs/restore-final-wrap, Abhinav's doc work).

## 5. The incident + the deploy-hygiene lessons (2026-05-27)

What happened: a bad OpenClaw-dashboard config edit added top-level keys (`commands`, `meta`) → gateway crash-loop → "Application failed to respond." Recovery: `railway up` redeployed; the entrypoint's existing merge logic stripped the unknown keys → gateway recovered. THEN an OpenClaw upgrade attempt (v2026.3.13→v2026.5.26) crashed on a `channels.slack.streaming` schema break → rolled back in ~2 min.

**The near-miss:** during recovery, work was on `feat/watchers-v1-plan` (32 commits behind main, missing the 360 skill + migration 0003). `railway up` from there deployed stale code. **Production was saved only because GitHub auto-deploy from main superseded the stale `railway up` — luck, not design.** The entrypoint mirror-sync would otherwise have wiped the live 360 skill.

**Lessons (locked):**
1. **Never `railway up` from local** unless local == origin/main. Canonical deploy = GitHub push → Railway auto-deploy.
2. **Branch off CURRENT origin/main**, always. `git fetch` + verify `0 behind` before any work.
3. Main moves FAST while Abhinav is active — re-sync at the start of every work block.

**Production integrity: CLEAN.** A forensic audit (`docs/superpowers/research/2026-05-30-post-incident-integrity-audit.md`) + independent spot-checks confirmed: skills byte-identical to main, runtime-only config keys preserved (slack.mode=socket, userTokenReadOnly, channelHealthCheckMinutes=10), migrations 0001/0002/0003 applied, workspace symlink intact, cron jobs intact, zero corruption archives. No residual damage.

## 6. A recurring discipline that paid off — verify subagent factual claims

Two subagents this session gave confident-but-WRONG factual claims, both caught by checking ground truth:
1. The OpenClaw upgrade research said the Slack config was unchanged → it wasn't (schema break crashed prod).
2. The plan reconciliation said "live crons have no delivery field" → all 14 actually carry `delivery:{mode:none}` (verified against config/cron-jobs-backup.json; fixed in PR #26).
**Rule going forward: verify subagent claims about config shapes / live state against the actual files before acting on them.**

## 7. Key finding to resolve — the task model is DORMANT

The v2 task tables (`tasks`, `task_events`, `task_mentions`, `blockers`, `scheduled_actions`) are **0 rows in production.** Not data loss (no delete path; DB persisted; migrations applied) — they were simply never populated. Means **Phase B has never actually created a task in prod** (nobody used the DM task flow; MI commitments still flow to DAILY_STATE.md). **Before V4 leans on this substrate (Watchers build on it), confirm Phase B actually fires in prod** — otherwise we're building on an unexercised foundation. Worth a deliberate check, not urgent.

## 8. Deferred: OpenClaw upgrade retry (task #48)

v2026.3.13 → v2026.5.26 crashed on `channels.slack`: `streaming` changed boolean→object, `nativeStreaming` removed. Retry requires: pre-fix `config/openclaw.json` channels.slack schema OR add `openclaw doctor --fix` as an entrypoint pre-flight (preferred — handles future schema changes). Then bump the Dockerfile pin. Full analysis: `docs/superpowers/research/2026-05-27-openclaw-upgrade-v2026.3-to-v2026.5.md`. Not urgent — v3.13 is stable. Do it on a low-traffic window.

## 9. The biggest gap — the "complete new Alaska" vision

Abhinav has a larger vision planned ("a complete new Alaska... Watchers and Phases A–E is just part of it"). He's confirmed Alaska becomes load-bearing AFTER the **June 10 product launch** (the team is heads-down on data-accuracy for launch right now — a separate track from V4). The full V4 destination is NOT yet captured anywhere. **Ask Abhinav to brain-dump it** so Watchers + D + E get built as deliberate stepping stones toward it. Related: the locked "alaska-v2-thesis" ("the rest of your startup team") in `~/.claude/projects/.../memory/`.

### V5 vision shared 2026-05-30 — the KB self-maintenance agent (it's a Watcher!)

Abhinav's first concrete piece of the bigger vision: **a V5 agent that maintains the KB itself.** Triggers on a schedule (e.g., every Sunday), scans the week's Slack + Meeting Intelligence + DMs for what changed, decides what KB files need updating, and proposes the changes.

**Architecturally this is a Watcher** — trigger = cron weekly; action chain = scan week's activity → diff against current KB → draft proposed KB edits → DM Abhinav for approval; memory = what it already proposed. **It rides directly on the V4 Watchers substrate.** This validates the whole foundation: the user's own V5 vision is a watcher template, so building Watchers V1 well *is* building toward V5. KB ownership trajectory: Abhinav (now) → Alaska-assisted → V5 self-maintaining watcher.

## 10. Forward sequence

```
[NOW] Co-build the BON KB (data-models, definitions, playbooks) + architecture.md operating-model section
   ↓
Commit KB to main (unblocks Watchers V1)
   ↓
Merge PR #26 (execution-ready plan) + delete stale feat/watchers-v1-plan branch
   ↓
Build Watchers V1 (Phase W.0 → W.4) via subagent-driven-development
   ↓
Phase D (cross-person, as a watcher template) → Phase E (DAILY_STATE cutover)
   ↓
[parallel/deferred] OpenClaw upgrade retry (#48); verify Phase B fires in prod
   ↓
The bigger "complete new Alaska" vision (once Abhinav shares it)
```

## 11. Research/spec doc index (all from this arc)

- `docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md` — Watchers V1 design (16 locked decisions)
- `docs/superpowers/specs/2026-05-26-bon-knowledge-base.md` — KB design
- `docs/superpowers/plans/2026-05-27-alaska-watchers-v1.md` — build plan (reconciled version on PR #26)
- `docs/superpowers/research/2026-05-27-openclaw-native-primitives.md` — per-watcher cron pattern confirmed
- `docs/superpowers/research/2026-05-27-openclaw-upgrade-v2026.3-to-v2026.5.md` — upgrade analysis + correction
- `docs/superpowers/research/2026-05-27-live-alaska-state-and-360-profile.md` — how the 360 profile is wired
- `docs/superpowers/research/2026-05-30-post-incident-integrity-audit.md` — CLEAN verdict
- `docs/superpowers/research/2026-05-30-watchers-v1-plan-reconciliation.md` — the 9 deltas
- Task tracker: #44 (blocker dedup), #46 (KB Tier-1), #47 (Watchers build), #48 (OpenClaw upgrade)
