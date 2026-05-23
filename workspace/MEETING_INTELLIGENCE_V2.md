# MEETING_INTELLIGENCE_V2.md — SUPERSEDED

This design doc was the original v2 plan (Apr 13). It is now historical.

**Live implementation:** `/data/skills/meeting-intelligence/SKILL.md` (deployed as a skill).
**Live state file:** `/root/.openclaw/workspace/DAILY_STATE.md` (NOT `PROJECT_STATE.md` — that file was retired on 2026-05-23).

Notable evolutions since this doc was written:
- Source of truth changed from `PROJECT_STATE.md` → `DAILY_STATE.md` (Apr 20, v2.1 redesign).
- Hallucination-prevention rules added Apr 29 (strict COMMITMENT EXTRACTION, attribution, staleness, confidence > 80%).
- Standup call moved from 9 AM IST → 9 PM IST (May 15) — Meeting Intelligence cron window updated to `*/30 15-20 UTC`.
- Sprint Board writes were dropped on 2026-05-23 (board retired — see plan: `lazy-bubbling-clarke.md`).

For the philosophy and 5-step structure of comprehension, see the live SKILL.md. This file kept for archaeology only.
