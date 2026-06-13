# Workbench — Alaska's workshop bench

This directory is **Alaska's private workshop**: everything about *building and running Alaska herself* — system-health findings, debug notes, builder breadcrumbs. It is the file-system companion to the **`builder`** notebook in `agent_memory` (migration 0009).

**Rules:**
- **STATE, not CONFIG.** Lives on the persistent `/data` volume; seeded once from git, then runtime-owned — never refreshed from git each deploy (see `lib/sync_workspace.sh`: `workbench/` is not in the CONFIG allowlist, so it's preserved). Alaska's runtime writes here persist.
- **Never injected, never team-indexed.** Not a bootstrap file (not loaded into sessions) and excluded from any team-facing memory search. Coworker-mode (Slack / team-cron) sessions never read or write here — workshop content cannot leak into a team answer, by construction.
- **Owner:** Abhinav (builder) + Alaska's workshop-mode / system-health sessions.

## Contents

| Path | What lives there |
|---|---|
| `journal/YYYY-MM-DD.md` | One line per significant workshop event — audits, debug sessions, system-health findings, build decisions. Written by the HEARTBEAT closing-note check (dashboard/main session) and the system-health crons (Watcher Janitor, Thinker). Format: `HH:MM — <what> — <where it lives>`. |
| → `/data/workspace/audit_artifacts/` | **Pointer (not moved).** The deep-audit reports (e.g. `2026-06-12_MASTER_audit.md`) stay under `audit_artifacts/` so the audit skill's paths keep working; this row is the index to them. |

Add a row when a new workshop artifact area appears.
