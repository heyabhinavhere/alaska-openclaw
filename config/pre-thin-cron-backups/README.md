# Pre-thin cron backups + rollback protocol

When a "fat" cron (one that carries its full operating logic inline in the dashboard `payload.message`) is **thinned** — its prompt replaced with a short "run `/data/skills/<X>/SKILL.md` verbatim" that defers to the SKILL — the old inline prompt **cannot be recovered from `cron.list` afterward**. This directory is the rollback path.

## Protocol (per cron, at thinning time)

1. **Before** applying a thin prompt on the dashboard, capture the cron's CURRENT live prompt via `cron.list` and save it here as `<cron-name>.txt` (this is the authoritative pre-thin copy — captured from live, zero transcription error).
2. Apply the thin prompt on the dashboard.
3. **Verify** the thinned cron behaves (see the thinning PR's verification steps).
4. If it misbehaves, restore the saved `.txt` to the dashboard cron.

## Notes

- The full pre-thin prompts for all 22 live crons (as of 2026-06-03) are also preserved in the session cron-dump record.
- The **thin prompt to apply** for each cron lives in that cron's thinning PR description.
- After a cron is thinned, future logic changes ship via its SKILL (auto-deployed) — **no more dashboard edits needed for that cron.** That is the whole point.
