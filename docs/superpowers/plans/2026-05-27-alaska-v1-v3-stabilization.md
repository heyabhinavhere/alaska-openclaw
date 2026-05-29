# Alaska V1-V3 Stabilization — Cross-Agent Coordination Doc

> **Audience:** the parallel V4 Claude agents (KB, Watchers V1, 360-profile) + any future session.
> **Purpose:** make the V1-V3 stabilization scope visible so we don't collide on shared files.
> **Status:** COMPLETE — A–E + G + H shipped & live; channel-scope (PR #22); Issue I root-caused + MoneyLion naming/Issue J fixed (PR #23 + live writes); F deferred (Abhinav's call).
> **Branches/PRs:** Wave 1 = PR #16 (merged), Wave 2 = PR #18 (merged), Wave 3 = PR #20 (merged), Wave 4 = PR #22 (channel-scope + final wrap), Wave 5 = PR #23 (MoneyLion naming + Issue I follow-on). Worktree: `.claude/worktrees/fix+v1-v3-stabilization`, base `origin/main`.
> **Owner:** Abhinav + stabilization agent
> **Deploy posture:** PR → review → merge to `main` → Railway auto-deploys
> **Last updated:** 2026-05-30

---

## Why this exists

Alaska is live (v2.4) and serving the team while three V4 streams build in parallel:

- **KB** — `workspace/knowledge/` content, Abhinav-author-only (not yet on `main`).
- **Watchers V1** — design+plan on `main` (PR #15, docs-only); build not started.
- **360-profile** — worktree `.claude/worktrees/feat+user-profile-360/`; migration 0003 + `sections.py`.

This branch fixes **current production issues** (reliability, output quality, team trust) that V4 may not address. It is deliberately isolated so V4 work stays clean.

---

## Scope

**In scope (safe):** V1-V3 skill SKILL.md files (`meeting-intelligence`, `daily-pulse`, `follow-through`, `pre-call-brief`, `risk-radar`, `doc-keeper`, `thinker`, `sprint-operator`, `task-handler`, `proposal-loop`, `report-health`, `log-usage`, `onboarding`, `amplitude-analyst`, `customerio-ops`, `alaska-core`, `reminder-dispatcher`, `whatsapp-send`); workspace state files (`SOUL.md`, `AGENT_RULES.md`, `DAILY_STATE.md`, `TOOLS.md`, `USER.md`, `IDENTITY.md`); cron payload prompts in `config/cron-jobs-backup.json` + matching OpenClaw dashboard sync.

**Sensitive (touch only when required; flagged in register):** `intent-classifier`, `slack-commands`, `shared-toolkit`, `entrypoint.sh`, `workspace/MEMORY.md` (factual sections only).

**Out of scope (will not touch):** `workspace/knowledge/**`; the Watchers + KB specs/plans/research docs; `.claude/worktrees/feat+user-profile-360/**`; new `watcher-*` / `user-profile-*` / `event-poller` skills; the `migrations/0003_*.sql` slot.

---

## Sensitive Surfaces — read before you edit

| File | Why | Stabilization posture |
|---|---|---|
| `migrations/0003_*.sql` | Contested between Watchers V1 + 360-profile | Stabilization adds NO migration. Escalates to Abhinav if schema change needed. |
| `skills/intent-classifier/SKILL.md` | Watchers bumps 1.1→1.2 (WATCHER_REQUEST); runs every 5 min | Stabilization stays on v1.1.x patches; will rebase under Watchers when it lands |
| `skills/slack-commands/SKILL.md` | Watchers + 360-profile both add handlers | Stabilization adds handlers in marked sections w/ stable anchors |
| `skills/shared-toolkit/SKILL.md` | Foundational — every skill reads it | Append-only where possible |
| `entrypoint.sh` | Fragile config-restore logic; Watchers adds Phase C migration call | Additions in separate `if` blocks; no reordering |
| `workspace/MEMORY.md` | Watchers owns "Currently working on" | Stabilization edits roster/decisions/evolution facts only — NOT "Currently working on" |

If you (another agent) change a section a stabilization commit just touched, leave a one-line marker comment and note it here.

---

## Issue + Fix Register

Status values: `investigating` · `proposed` · `approved` · `shipped` · `declined` · `deferred-to-V4`

**Source of A–F:** the Nilesh ↔ Alaska debt-discrepancy conversation (BON user 2756), 2026-05-26 → 27.

| # | Issue (one-line) | Decision | Status | PR |
|---|------------------|----------|--------|----|
| A | Code/repo RCA hallucination (fabricated findings, self-contradiction across sessions) | Fix now — grounded reading | ✅ **LIVE** | #16 |
| B | Autonomous session acted after explicit "don't send" + public @tag (root cause verified in session logs: an isolated channel-mention session with no memory of the DM) | Fix now — third-person restraint | ✅ **LIVE** | #16 |
| C | Internals/architecture leak ("automated session picked it up…") | Fix now — apology/disclosure guard | ✅ **LIVE** | #16 |
| D | Sycophancy + over-claiming ("Day 1", "I'll delete it") | Fix now (light) | ✅ **LIVE** | #16 |
| E | Capability dishonesty — "never say I don't have access" overshoot | Both — discipline (now) + KB map (later) | ✅ **LIVE** (discipline half) | #16 |
| H | Workspace persistence — `/root/.openclaw/workspace` was ephemeral, re-seeded from git every deploy (THE root cause of "memory keeps going stale") | Fix now — move to `/data` volume via symlink + `lib/sync_workspace.sh` (CONFIG refresh / STATE preserve) | ✅ **LIVE + verified across 2 deploys** | #18 |
| G | MEMORY.md (~30.5K) exceeded the 20K inject cap → silently truncated (lost the whole Lessons section) | Fix now — tiered memory (lean core + `memory/system-evolution.md`) | ✅ **LIVE + verified** | #20 |
| — | Notion User IDs captured (all 8 internal members) + Owner-field writes re-enabled (graceful fallback) | — | ✅ **LIVE** | #20 |
| — | Channel-scope policy (membership = access control, no allowlist) + MEMORY-in-channels guidance reconciled | — | 🟦 in PR #22 | #22 |
| F | Over-scoped GitHub token — full `repo` read+WRITE, not read-only | DEFERRED — Abhinav owns the read-only token swap | ⏸️ **deferred** | — |
| I | Blocker/context propagation broken — channel blockers seen but never captured (classifier still observation-only), stale blockers (Play Store) linger in DAILY_STATE, no lifecycle/resolution | Root-cause + honest data fix now; **pipeline DEFERRED to Watchers** (it absorbs the never-built v2-task-model Phase D/E) | ✅ root-caused; live data corrected; pipeline deferred | #23 |
| J | "MoneyLine" naming hallucination — real partner is **MoneyLion** (moneylion.com); Fireflies mis-transcription + a seed typo propagated into memory/skills/state | Fix now — correct everywhere + a Meeting-Intelligence normalization rule (recurrence-stopper) | ✅ **repo LIVE via #23; live DAILY_STATE + system-evolution + `task_categories` DB corrected directly** | #23 |

### Waves shipped
- **Wave 1 (PR #16):** A–E behavioral guardrails. Spine in `alaska-core`: *bold in thinking; honest about facts & limits; restrained about actions & disclosure.* New `slack-commands` sections (`Code & repo questions`, `Action restraint`) sit below the `Intent-driven actions` block — no overlap with Watchers/360 handlers.
- **Wave 2 (PR #18):** Issue H — workspace on the persistent `/data` volume (symlink + `lib/sync_workspace.sh` + `tests/test_workspace_persistence.sh`); `DAILY_STATE.md` reconstructed from the May-28 call + Slack as the seed.
- **Wave 3 (PR #20):** Issue G — tiered memory (lean `MEMORY.md` ~13K + `memory/system-evolution.md` archive); Notion User IDs captured; Owner-field writes re-enabled.
- **Wave 4 (PR #22):** channel-scope policy made explicit; `AGENTS.md` MEMORY-in-channels guidance reconciled; this final wrap.
- **Wave 5 (PR #23, 2026-05-30):** Issue J — corrected "MoneyLine" → **MoneyLion** across `MEMORY.md` roster, `task-handler`/`sprint-operator` skills, STATE seeds, cron snapshot; added a Meeting-Intelligence normalization rule (Fireflies mis-transcribes "MoneyLion"→"Moneyline" → always write MoneyLion — the recurrence-stopper). Live runtime writes (approved, sha256-guarded + backed up): live `DAILY_STATE.md` (removed the resolved Play-Store blocker, which Abhinav confirmed live, + spelling fix), live `system-evolution.md`, and the `task_categories` DB row rename (0 tasks referenced it). **Issue I** root-caused: only v2-task-model Phases A–C shipped; **Phase D (classifier observe→act) + E never built** → channel blockers are seen-not-acted. That pipeline is Watchers V1's scope (Watchers absorbs Phase C), so stabilization did NOT build it — only the honest data corrections above.

### V4 coordination outcome — CLEAN, no collisions
Watchers V1 (PR #15, docs) and 360-profile (PR #19) both landed on `main` alongside the waves; 360 even **extended** the Wave-1 `TOOLS.md` capability manifest (added the User-Profile-360 access + boundary) — coordination worked. The `migrations/0003` slot went to 360-profile (stabilization never took it). `intent-classifier` left untouched by stabilization (Watchers' v1.2 bump unblocked).

### Open follow-ups (Abhinav's call)
- **Issue F:** swap the GitHub token to a fine-grained read-only one (Contents:read + commit/PR read). Stabilization agent supplies the exact scopes on request. (Currently the "READ ONLY" red line is enforced only by instructions, not the token.)
- **Owner-writes:** confirm the first real blocker Owner-write populates the people field (graceful first-name-in-Notes fallback makes it safe regardless).
- **KB coordination:** KB agent to add a capability/access dimension (`architecture.md` + `integrations/github.md`) converging with the `TOOLS.md` "What you can and cannot reach" manifest (Issue E knowledge-half).
- **MoneyLion naming — 3 residual flags (from Wave 5):** (a) KB spec references `integrations/moneyline.md` → should be `moneylion.md` (KB owner); (b) live OpenClaw cron-prompt dashboard still says "MoneyLine" in Sprint Operator + Pre-Call Brief (repo snapshot fixed in #23; live dashboard synced via Alaska on 2026-05-30); (c) `migrations/0001` seed row literally says `'MoneyLine'` — applied/immutable, live DB already renamed, only matters for a from-scratch DB reseed (→ a future migration, not an edit to 0001).

---

## Per-issue protocol

For each issue Abhinav raises, the stabilization agent: (1) inspects the real code/live state read-only, (2) checks all three V4 streams for collisions, (3) proposes in a fixed format (Issue / Current Impact / Likely Root Cause / Relation to V4 Work / Decision / Reasoning / Recommended Fix / Parallel Work Risks / Validation Plan), (4) waits for approval, (5) commits minimally + updates this register, (6) validates incl. one adjacent-behavior regression check, (7) rolls fixes into a batched PR every ~3-5 fixes.

Full operating plan: `~/.claude/plans/cool-let-s-create-a-delightful-dragon.md` (local to the stabilization session).
