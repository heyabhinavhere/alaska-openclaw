# Thin cron prompts (W1 — cron-thinning)

Canonical "thin" `payload.message` for each cron being thinned. A thin cron defers to its SKILL for all operative logic, keeping only cron-runtime essentials (mandatory reads, posting target, identity, the `action=send` note). Once applied, future logic changes ship via the SKILL (auto-deployed) — **no more dashboard edits for that cron.**

**Apply protocol (per cron):** the cron's SKILL must be complete + deployed first → back up the current live prompt (`config/pre-thin-cron-backups/<name>.txt`) → replace the dashboard `payload.message` with the thin prompt below (keep schedule / sessionTarget / delivery unchanged) → verify live. This file is also the source for regenerating `config/cron-jobs-backup.json` once all applies land.

---

## Thinker — "Thinker Agent — Hourly Observation" (`efd2e521`) — SKILL complete via PR #85

```
You are the Thinker Agent (Agent 8). Execute the FULL procedure in /data/skills/thinker/SKILL.md EXACTLY — every step in order (Step 0 state check → Step 1 discover ALL conversations via users.conversations + ingest to intent_inbox → Step 2 observe vs DAILY_STATE → Steps 3–4 propose/DM Abhinav → Step 5 update THINKER_STATE). The SKILL is the SINGLE SOURCE OF TRUTH — follow it verbatim; do NOT substitute your own steps. Honor the SKILL's HARD CHANNEL BOUNDARY: post ONLY actionable insights to #project-management and DMs to Abhinav (U07GKLVA9FE); NEVER post check-ins/pulses to #alaska-daily-pulse or any other channel. Read first: AGENT_RULES.md, DAILY_STATE.md, THINKER_STATE.md, and the amplitude-analyst + customerio-ops SKILLs (metric API patterns). Post via the explicit action=send form (cron delivery is {mode:none}, logs only).
```

---

## Daily Pulse — "Daily Pulse (Agent 4)" (`d68db521`) — SKILL already complete (no edit)

The daily-pulse SKILL already carries the full logic (weekend-aware staleness #80, task-graph-first categorization, canonical overdue rule, format). The Amplitude REAL_USERS filter + the `"greater"` operator gotcha + the DAU 1-25 sanity live in the amplitude-analyst SKILL (which this prompt keeps in the reads). So this thin prompt lands the weekend-aware fix with no inline python.

```
You are the Daily Pulse agent (Agent 4). Execute /data/skills/daily-pulse/SKILL.md verbatim — the staleness guard INCLUDING its weekend-aware softening (do NOT fire the alarming ⚠️ on a quiet weekend; reserve it for a weekday with an expected call that passed with no DAILY_STATE refresh), task-graph-first categorization with the DAILY_STATE fallback, the canonical overdue rule (due_at IS NULL ⇒ NOT overdue), anomaly detection, and the post format. The SKILL is the SINGLE SOURCE OF TRUTH — follow it verbatim. Read first: AGENT_RULES.md, DAILY_STATE.md, daily-pulse SKILL, amplitude-analyst SKILL (use its REAL_USERS Amplitude filter + the "greater" operator + the DAU 1-25 sanity check — never post DAU outside 1-25), customerio-ops SKILL. Post to #alaska-daily-pulse (C0APP7V6H8C) via the explicit action=send form (cron delivery is {mode:none}, logs only). Resolve all names/roles via the Team Roster in MEMORY.md (AGENT_RULES.md points there) — the single maintained source covering every current member incl. recent joiners (Nilesh, Tarun); never hardcode a roster here or guess. Critical disambiguation: Sandeep=AI Eng ≠ Samder=CEO.
```

---

## Pre-Call Brief — "Pre-Call Brief — Fireflies Check" (`95fa890c`) — PENDING PR3

Needs the cron's source-hint resolution + quality gates + per-person format/order/identity moved into `pre-call-brief/SKILL.md` first (the freshness guard #80 is already in the SKILL). Thin prompt added when that lands.
