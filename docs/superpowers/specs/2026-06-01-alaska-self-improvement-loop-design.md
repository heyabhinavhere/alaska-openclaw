# Alaska Self-Improvement Loop — Design Spec

**Date:** 2026-06-01
**Status:** Design approved (brainstorm) — pending spec review → implementation plan
**Author context:** Abhinav (owner) + Claude (design). This spec is written **handoff-grade**: the engineer/agent who implements it has *none* of the originating conversation's context. Read the "Context you need" section first.

---

## Context you need (the executor has not seen any of this)

**What Alaska is.** Alaska is BON Credit's autonomous AI Project Manager, running on **OpenClaw** (multi-agent framework) on **Railway**, interfacing via **Slack**, backed by **Notion** (record store) + **SQLite** (`/data/queue/alaska.db`) + git-canonical workspace files. It's ~26 skills (prompt-driven `SKILL.md` files) + ~19 cron jobs. BON is a pre-PMF **fintech** handling customer **credit data + PII** — safety matters more than for a typical agent.

**Deploy model (critical).** GitHub `heyabhinavhere/alaska-openclaw` → Railway auto-redeploys on merge to `main`. `entrypoint.sh` on each deploy: (a) runs DB migrations via `run_migrations.sh` (globs `migrations/*.sql`), (b) **mirror-syncs** `/opt/default-skills/` → `/data/skills/` (skills are git-canonical; runtime edits are wiped), (c) seeds/refreshes workspace config files. **`docs/` is NOT deployed.** **`config/cron-jobs-backup.json` is a documentation SNAPSHOT — it is NOT loaded on deploy.** Live crons live in OpenClaw's own store and are registered via the in-session `cron.add` tool (or the dashboard).

**The container's real capabilities** (verified against the Dockerfile): `curl` + `python3` + `sqlite3` + Node/OpenClaw. **NO `git`, NO `gh` CLI.** Alaska talks to GitHub today *only* via the **REST API** with a **read-only** `GITHUB_TOKEN`. Therefore Alaska **cannot `git push` or `gh pr create`** — any PR it opens must go through the **GitHub REST API**.

**Why this feature exists.** Building an agent to ~80% is easy; the last 20% — judgment and taste — is where agents stall. Today, every time Alaska shows poor judgment (a bad watcher draft, an assumed recipient, a stale follow-up), a human (Abhinav) notices and Claude diagnoses + edits the skill + opens a PR. **A human is the feedback loop.** This feature builds that loop *into Alaska*: it learns from team feedback and proposes its own skill improvements as human-reviewed PRs. Inspired by Warp's "Buzz" agent talk — three lessons: **principles, not rules** (judgment, not brittle if-X-then-Y checklists); **teach how to learn** (the agent grows its own principles from feedback); **make feedback easy** (a low-friction daily loop the team barely notices).

**Hard-won lessons from recent work (the executor must respect these — they are why parts of this design look the way they do):**
1. **`always: true` skills are NOT injected into the synchronous DM/channel session.** That session only gets the auto-injected workspace files (`SOUL.md`, `MEMORY.md`, `TOOLS.md`, `AGENTS.md`) + the message. Routing/behavior rules that must fire per-message live in `SOUL.md`.
2. **A cron in `cron-jobs-backup.json` does nothing until registered live** via `cron.add`. (This burned us twice.)
3. **Alaska tends to assert state it didn't read** (assumed recipients, hand-computed dates, fabricated "live" numbers). Skills now say "read the row / compute, don't guess." The loop should *learn* this class of lesson, not re-introduce it.

**Locked constraints (non-negotiable):**
- **KB is Abhinav-authored-only.** `workspace/knowledge/` must NEVER be touched by the self-improvement loop (or any non-Abhinav path).
- **Safety/PII/money/deploy rules are frozen guardrails.** The loop sharpens *judgment*; it must never weaken a guardrail (e.g., "PII never auto-posts to a public channel", "$3/day approval gate", "never push to BON product repos", "never `cron.add` a user's request directly").
- **Never auto-merge.** Every self-edit is a PR reviewed by Abhinav + Claude.
- **Alaska never writes to BON *product* repos.** The new write token is scoped to `alaska-openclaw` (Alaska's own infra repo) ONLY.

---

## Goal

Alaska captures team feedback on its judgment, and on a daily cadence opens **one human-reviewed PR** that sharpens the **Principles** in its own skill files — improving on its own as understanding evolves, without a human manually diagnosing each miss.

## Non-goals

- Not auto-merging (humans always review).
- Not editing the KB, migrations, config, or any safety guardrail.
- Not real-time learning (daily batch, not PR-per-event).
- Not a generic eval harness — this is a feedback→principle loop, not a benchmark.

---

## Architecture (Approach B: feedback table + scan-collector + self-improver)

Five pieces. All are **new files** except a one-time, sequenced restructure of target skills.

### 1. `skill_feedback` table — migration `0005_skill_feedback.sql`

The durable audit of what was learned and why. Suggested columns:
- `id` INTEGER PK; `created_at` DATETIME.
- `source_surface` TEXT — `standup` | `dm_qa` | `watcher` | `daily_pulse` | `meeting_intelligence` | …
- `signal_type` TEXT — `correction` | `pushback` | `parse_failure` | `explicit_flag` | `brief_gap` | `outcome_failure`.
- `target_skill` TEXT — the skill the feedback is about (e.g., `pre-call-brief`).
- `excerpt` TEXT — the relevant message/context (escaped).
- `actor_slack_id` TEXT; `source_ref` TEXT — Slack permalink/thread for traceability.
- `processed` BOOLEAN DEFAULT 0; `processed_at` DATETIME; `resulting_pr` TEXT (nullable URL).

Migration auto-applies on deploy (entrypoint). Idempotent (`CREATE TABLE IF NOT EXISTS`).

### 2. `feedback-collector` skill + cron — capture (purely additive)

Runs periodically (e.g., every few hours, before the daily self-improver). It **SCANS existing audit trails** — `task_events`, `watcher_fires`, `classifier_audit`, standup threads (pre-call-brief replies), DM-Q&A threads — plus **Slack reactions/notes** on Alaska's own messages. It derives **implicit-first hybrid** feedback signals and writes `skill_feedback` rows.

- **Implicit signals:** a reply that corrects Alaska ("that's not my task"), pushback on a follow-up, a logged "couldn't parse that", a `watcher_fires` `failed`/`skipped` outcome, a brief that missed a task the reply reveals, a `classifier_audit` low-confidence/misroute.
- **Explicit signals:** an emoji reaction (a small agreed vocabulary, e.g. 👎/✏️/🚫) or a thread note addressed to Alaska ("@alaska that follow-up was redundant").
- **Crucially additive:** it READS existing logs + the Slack API. It edits **no handler skill** — so it does not collide with concurrent work on those skills.

### 3. `self-improver` skill + daily cron — learn + propose

Reads unprocessed `skill_feedback`, clusters related signals, and for each cluster runs the **7-step "teach how to learn" process**:
1. **Identify** what went wrong/right — start from the concrete signal.
2. **Ask why** — the symptom vs the underlying cause.
3. **Zoom to the pattern** — would this apply beyond this one case?
4. **Check existing principles** — sharpen / edit / delete / merge / add?
5. **Write it as a principle, not a rule** — describe how to *think*, not a brittle if-X-then-Y.
6. **Put it where it belongs** — the right skill's **Principles** zone (section matters).
7. **Edit + commit** — keep the file tight, merge overlapping principles (don't append a 14th anti-pattern).

Then it **opens ONE PR** (via the GitHub REST API + write token; see Deployment & Wiring) with the Principles-zone edits + a plain-English summary, **DMs Abhinav + Claude** the link, and marks the feedback rows processed + linked to the PR.

**It edits ONLY the Principles zone. Never a 🔒 Guardrail. Never `knowledge/`/`migrations/`/`config/` (CODEOWNERS-enforced).** If a clustered lesson is actually a *new guardrail* (safety/irreversible — e.g. a new PII rule), it does **NOT** write it; it **flags it in the PR description** for a human to codify.

### 4. The grant + CI ("smartly" = least privilege + mechanical enforcement)

- **A dedicated fine-grained PAT** (`GITHUB_SELF_IMPROVE_TOKEN`), scoped to **only** `alaska-openclaw`, permission to create branches + PRs, **NOT** merge/admin. Separate from the read-only `GITHUB_TOKEN` (so "never write to BON product repos" stays true).
- **Branch protection** on `main`: require ≥1 human review before merge → Alaska *cannot* self-merge by construction.
- **`CODEOWNERS`**: `workspace/knowledge/`, `migrations/`, `config/`, `entrypoint.sh`, `Dockerfile` require a human code-owner; any self-PR touching them is hard-gated. Makes "skills-only self-edit" a *mechanical* boundary, not just prompt text.

### 5. Structural-zone restructure of target skills (one-time, sequenced)

Each target skill is reorganized into a **"Principles (the loop may sharpen)"** zone and a **"Guardrails — FROZEN 🔒"** zone, with guardrail lines explicitly 🔒-marked. The loop edits only the Principles zone. This also pays down the "too many brittle anti-patterns" drift (e.g. `watcher-creator` is at 13).
- **`pre-call-brief`** (the standup target) — can be restructured immediately (no one else is editing it).
- **`watcher-creator` / `watcher-dispatcher` / `slack-commands` / `intent-classifier` / `SOUL.md`** — **SEQUENCED: restructure only AFTER the in-flight watcher + DM-routing PRs have merged** (see Parallel-agent boundaries). Until then, leave them alone.

---

## Data flow

Team interacts (standup replies, DM Q&A, watcher fires, reactions) → existing handlers log to existing audit trails + Slack → **feedback-collector** scans → `skill_feedback` rows → **self-improver** (daily) clusters + 7-steps → **PR** (Principles-zone edits, via REST API + write token) → DM Abhinav+Claude → human review (≈60s) → merge → Railway redeploys → Alaska runs on the sharpened principle. Every step is auditable (`skill_feedback` → PR → git history).

---

## Deployment & Wiring (what "PR merged" does NOT give you for free)

| Requirement | Auto from git? | What's actually needed |
|---|---|---|
| Migration `0005`, new skills, `lib/` helper | ✅ | entrypoint handles it |
| `CODEOWNERS` file | ✅ | it's a committed file |
| **collector + self-improver crons** | ❌ | **live `cron.add` registration** — the snapshot file is not loaded |
| **write token** `GITHUB_SELF_IMPROVE_TOKEN` | ❌ | a Railway env var (manual secret), separate from `GITHUB_TOKEN` |
| **branch protection** | ❌ | manual GitHub repo setting (UI/API) |
| openclaw.json env/tool exposure (if any) | ❌ | confirm skill `requires.env` + tool allowlist |

**PR-creation mechanism (no `git`/`gh` in the container):** open PRs via the **GitHub REST API** through a tested `lib/open_self_pr.py` helper: read base-branch SHA → create a branch ref → put file contents (Contents API) → open PR (Pulls API), using `GITHUB_SELF_IMPROVE_TOKEN`. The self-improver reads current skill content from `/data/skills/` (synced), computes the edit, and calls the helper. `lib/` is unit-tested in this repo — the helper gets tests.

**Activation checklist (post-merge, one-time):** register the 2 crons via `cron.add`; set the Railway token; enable branch protection + land `CODEOWNERS`; verify a self-PR touching `knowledge/` is blocked.

---

## Safety model (fintech)

- Skills-only self-edit; KB/migrations/config never touched (CODEOWNERS + prompt).
- Never weakens a 🔒 Guardrail; only sharpens Principles. New guardrails are *flagged for human codification*, never self-written.
- Every change is a human-reviewed PR; never auto-merge (branch protection enforces).
- The write token is least-privilege, scoped to `alaska-openclaw` only.
- Full audit chain: `skill_feedback` (what + why) → PR (the change) → git history.

---

## Parallel-agent boundaries (the handoff)

This is built by a **separate Claude agent in its own git worktree + branch**, in parallel with in-flight watcher/DM-routing hardening by another agent. To avoid collisions:
- **The executor builds NEW files** (migration `0005`, `feedback-collector`, `self-improver`, `lib/open_self_pr.py`, crons, grant/CI) **+ the `pre-call-brief` zone restructure** (free — not otherwise being edited).
- **It does NOT touch** `watcher-creator`, `watcher-dispatcher`, `slack-commands`, `intent-classifier`, `SOUL.md`, `watcher-janitor` while the watcher/DM-routing PRs are in flight. Those skills' zone-restructure is a **later phase**, sequenced after those PRs merge.
- **Merge order:** in-flight watcher/DM-routing PRs first; the loop's PRs rebase on the latest `main`.

---

## Phased rollout (observe-before-act)

- **Phase 0 — PR spike (de-risk first):** prove Alaska can open a real PR from the container via the REST API + a scoped write token. If this doesn't work, stop — the loop is moot. Deliver `lib/open_self_pr.py` + a manual end-to-end test.
- **Phase 1 — safety rails:** create the fine-grained token (Railway env), branch protection, `CODEOWNERS`. No self-edit capability yet.
- **Phase 2 — capture only:** migration `0005` + `feedback-collector` (+ its cron). Observe what it logs to `skill_feedback` for a few days; tune signal detection. No edits proposed yet.
- **Phase 3 — propose-only, one target:** `self-improver` + daily cron, scoped to the **standup (`pre-call-brief`)** only (restructured into zones). It opens real PRs; Abhinav+Claude review. Validate the quality of proposed principle edits.
- **Phase 4 — expand:** restructure + add watcher/DM-routing targets (after their PRs merge), then later Daily Pulse / Follow-Through / Meeting Intelligence.

---

## First targets

- **Standup (`pre-call-brief`, Steps 3–4)** — primary; highest-frequency two-way feedback (every weekday, every person replies, Alaska acks + asks follow-ups).
- **Watcher + DM-routing skills** — strategic; lower volume now, warms up as team usage grows.
- (Note: `pre-call-brief`'s header still says "private to Abhinav only" while Steps 3–4 do per-person team standup — a pre-existing labeling drift to clean up during its zone-restructure.)

---

## Testing / validation

Mostly prompt-driven, so:
- **`lib/open_self_pr.py`** — unit tests (branch/commit/PR API calls, error handling) + the Phase 0 live spike.
- **`feedback-collector`** — seed synthetic audit rows (task_events/watcher_fires/classifier_audit) + a synthetic standup thread; assert correct `skill_feedback` rows (right surface/signal_type/target_skill), no false positives on normal chatter.
- **`self-improver`** — dry-run against synthetic `skill_feedback`; assert it proposes a sensible Principles-zone edit, **never** touches a 🔒 line or a protected path, and flags would-be guardrails instead of writing them.
- **CI** — verify branch protection blocks an unreviewed merge and `CODEOWNERS` blocks a self-PR touching `knowledge/`.
- **Live soak** — Phase 3: real standup feedback → first real PRs reviewed for quality.

---

## Open questions / risks

1. **PR-from-container** (Phase 0 spike resolves) — fine-grained token permissions + the exact REST flow. Highest risk; de-risked first.
2. **Signal precision** — implicit mining may mistake normal chatter for feedback. Mitigations: implicit-first *hybrid* (explicit flags are high-confidence), capture-only Phase 2 to tune, and the PR-review gate as the backstop.
3. **Drift** — the loop could slowly bloat or skew skills. Mitigations: "merge, keep tight" rule, human review every PR, and Abhinav's quick-edit on the PR.
4. **Cron cadence** — daily for the self-improver; collector every few hours. Tunable.
5. **Reviewer load** — one ~60-second PR/day is the target; if it balloons, raise the feedback threshold.
