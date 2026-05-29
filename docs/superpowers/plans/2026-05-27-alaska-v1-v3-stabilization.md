# Alaska V1-V3 Stabilization — Cross-Agent Coordination Doc

> **Audience:** the parallel V4 Claude agents (KB, Watchers V1, 360-profile) + any future session.
> **Purpose:** make the V1-V3 stabilization scope visible so we don't collide on shared files.
> **Status:** ACTIVE
> **Branch:** `fix/v1-v3-stabilization` (worktree: `.claude/worktrees/fix+v1-v3-stabilization`, base: `origin/main`)
> **Owner:** Abhinav + stabilization agent
> **Deploy posture:** PR → review → merge to `main` → Railway auto-deploys
> **Last updated:** 2026-05-28

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

| # | Date | Issue (one-line) | Decision | Status | Files | Commit / PR | Validation |
|---|------|------------------|----------|--------|-------|-------------|------------|
| — | — | _(none yet — awaiting first issue)_ | — | — | — | — | — |

---

## Per-issue protocol

For each issue Abhinav raises, the stabilization agent: (1) inspects the real code/live state read-only, (2) checks all three V4 streams for collisions, (3) proposes in a fixed format (Issue / Current Impact / Likely Root Cause / Relation to V4 Work / Decision / Reasoning / Recommended Fix / Parallel Work Risks / Validation Plan), (4) waits for approval, (5) commits minimally + updates this register, (6) validates incl. one adjacent-behavior regression check, (7) rolls fixes into a batched PR every ~3-5 fixes.

Full operating plan: `~/.claude/plans/cool-let-s-create-a-delightful-dragon.md` (local to the stabilization session).
