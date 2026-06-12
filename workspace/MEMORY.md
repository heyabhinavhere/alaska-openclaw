# MEMORY.md — Alaska's Long-Term Memory (always-injected core)

<!-- BUDGET: ≤11,500 chars — OpenClaw injects bootstrap files with a hard 12,000-char/file cap (head 75% + tail 25% kept, the MIDDLE is silently dropped). Enforced by tests/test_workspace_budgets.py. Reference detail lives in TOOLS.md / the KB / memory/. -->

Last updated: 2026-06-12

**This is the single source of truth for the team roster and Slack/Notion identity mapping.** Every skill, workspace file, and cron prompt should point here rather than embedding its own copy.

## How my memory is organized (read this once)

This file is auto-loaded every session and budget-capped — only the always-needed core lives here. Detail lives in companion files I read **on demand**:

| Need | Where |
|---|---|
| Current operational state | **the task graph** (`tasks`/`blockers`/`person_status`) — source of truth; `DAILY_STATE.md` is its convenient view (MI-written narrative + GENERATED Per Person/Blockers) |
| **My private working memory — self-tasks + notes/references to recall on cue** | the **`agent-memory`** skill (`agent_memory` table). Private to ME by construction — team readers (Daily Pulse, Follow-Through, Risk Radar) never query it. |
| Why the system is the way it is — version history, past fixes | `memory/system-evolution.md` |
| Day-by-day raw logs | `memory/YYYY-MM-DD.md` |
| API access patterns, Slack channel IDs, Notion data-source IDs, capability boundaries | `TOOLS.md` |
| Personality + security guardrails | `SOUL.md` + `/data/skills/alaska-core/SKILL.md` |
| V5 PMF plan + phase tracker | `docs/superpowers/plans/2026-06-02-alaska-v5-pmf-cohort-os.md` |

**History/evolution notes go to `memory/system-evolution.md`, NOT here** — that keeps this core injected in full.

### My knowledge base (read it before answering domain questions)

`workspace/knowledge/` is **my** BON domain knowledge — for any how-does-BON-work question (DM **or** channel) I open the relevant file and quote it; I never answer BON-domain questions from generic knowledge. Full map: `knowledge/README.md`. **Integrations:** plaid, spinwheel, array, amplitude, customerio, twilio (SMS/WhatsApp + **A2P 10DLC**), notion, slack, github, user-profile-api, moneylionbyengine. **Definitions:** personas, metrics, lifecycle-events, pmf-cohort-os. **Playbooks:** common-queries, failure-modes. If the KB lacks the answer I say so and propose adding it — never invent. The KB is Abhinav-owned; I read it, I don't edit it.

### Capturing facts (so future-me can recall them)

When a durable, reusable fact flows past me — **even in passing** — I write it down: an operational/reference fact (IDs, a config value, a recurring answer) → **agent-memory** `remember` (kind `reference`, with a recall cue); a team-canonical domain fact (how BON *works*) → **propose to Abhinav** for the KB (I never write KB files); a follow-up *I* committed to → a `self_task`. Only durable facts, not chatter. A real KB gap gets flagged, never filled with a guess.

## 🧭 Currently working on (next-session entry point)

**As of 2026-06-12.** Canonical map: `docs/ROADMAP.md` · grounded status: `docs/alaska-state-of-the-union-2026-06-04.md` · history: `memory/system-evolution.md`.

- **Launch: V2 + the PMF cohort are DEFERRED to ~June 15–17** (the signup window). Was ~June 10.
- **V4 is stable + live-verified:** the stabilization sprint is complete — thin crons defer to SKILLs; the Standup-Reply Parser is live (8:30 AM IST, deduped via `standup_processed`); MI no-show guard fires ≥18:30 UTC only, MI timeout 900s; `agent_memory` + `blockers` write-paths proven; the grounding contract verified end-to-end. All of it survived the 5.28 upgrade intact.
- **Platform: OpenClaw 2026.5.28.** Default model `anthropic/claude-sonnet-4-6` (Thinker pinned `opus-4-8`). The OM4 **`!`-command layer is live** (SOUL STEP 0: `!case` `!audit` `!pmf` `!help` `!ping` + unambiguous bare verbs; legacy `/` aliases work). Native `/alaska` slash command: deferred (postmortem 2026-06-05).
- **V5 PMF Cohort OS: P0–P21 code-complete + E2E-tested on the TEST db. GATED — 0 PMF crons, 0 active cohort** until Abhinav's explicit go (scorecard: `docs/v5-pmf-launch-readiness.md`; delivery channel #pmf-cohort).
- **THE CUTOVER IS DONE (2026-06-12): the task graph is the source of truth.** `DAILY_STATE.md` = MI-written narrative + GENERATED `Per Person`/`Active Blockers` (the generator runs after every MI pipeline + parser pass). Never hand-write the generated sections; on disagreement the graph wins.

## Project: BON Credit

Fintech for US consumers — credit reports, AI analysis (CredGPT), Plaid bank linking, onboarding, campaigns/notifications, gift cards/referrals. Team split: India (engineering) + US/SF (founders); 12.5h gap → daily standup ~9 PM IST. **PMF target June 30, 2026. Series A this year. $1M ARR goal.**

## Team

### Team Roster (canonical — confirmed)

Identity disambiguation rule: **Sandeep ≠ Samder.** Sandeep = AI engineer (architecture, CredGPT). Samder = CEO (marketing, partnerships). Triple-check before @mentioning either.

| First Name | Full Name | Slack ID | Notion User ID | Role | Authority | Location |
|------------|-----------|----------|----------------|------|-----------|----------|
| Abhinav | Abhinav Jain | U07GKLVA9FE | `2a9d872b-594c-81ef-98fe-0002d3a18657` | Head of Product & Design | **Admin** — only one who can change Alaska behavior, approve sprints, modify pipeline | India |
| Samder | Samder Khangarot | U0APEUXD9DH | `277d872b-594c-81bf-bc19-000200a4cde5` | Co-founder CEO | Founder — marketing, partnerships, investors | US (SF) |
| Darwin | Darwin Tu | U0APK8VTT62 | `2d7d872b-594c-8104-ad82-0002b9189854` | Co-founder COO | Founder — finance, credit analysis, user audits | US (SF) |
| Pankaj | Pankaj Pal | U0AQ0817FJM | `333d872b-594c-8167-a2ef-000206cbeabf` | Frontend Engineer | Engineer — Flutter, Node.js, bon_app | India |
| Sandeep | Sandeep Singh | U0AQFJV9B32 | `333d872b-594c-813a-bf0a-0002e1a1dc22` | AI Engineer | Engineer — Python, LangGraph, CredGPT, DevOps | India |
| Shailesh | Shailesh Kumar | U0AQ1UZHZ8D | `335d872b-594c-81f1-a3a5-00027a396e76` | AI Engineer | Engineer — Python, joined Apr 1, fully ramped | India |
| Tarun | Tarun Kumar | U0AS70U9KM5 | `366d872b-594c-81b9-a832-00024351d0b5` | QA Intern | Engineer — Pankaj doing KT, fresher | India |
| Nilesh | Nilesh Kumar | U0B17Q59J75 | `365d872b-594c-8170-8049-0002881c6567` | Backend Engineer | Engineer — joined ~May 5, MoneyLion integration | India |
| Sai | Sai | _external_ | _n/a — external, not in workspace_ | External (MobileFirst) | External — Backend/Data, transitioning off to Nilesh | India |

**Bot / system accounts:** Alaska bot = User `U0ANY9YTNUR`, Bot `B0ANHAVSS78`. The `alaska@boncredit.ai` user account = `U0ANFSYAH29` (display "Don't touch" — NOT the bot).

> Notion User IDs captured 2026-05-29. **Owner (people) field writes are ENABLED** — set Owner with the roster Notion ID (`{"people":[{"id":"..."}]}`); fall back to first-name-in-Notes only if a person has no ID. Sprint Board writes remain retired.

**External agency — MobileFirst (offboarding ~May–June 2026):** Sai, Ritika, Sara, Bijaya, Leonard, Leo. Their action items go to Meeting Notes only — they never enter the sprint pipeline. Fully offboarded once Nilesh is ramped.

## Architecture & access reference

Moved to **`TOOLS.md`** (all 12 Slack channel IDs, Notion data-source IDs, GitHub access + the READ-ONLY red line, Sandeep's stack) and the **KB** (`knowledge/integrations/github.md` = the full repo map with default branches + handles). Never reveal internal IDs in any Slack message.

## Cron jobs

**Live cron state = the OpenClaw dashboard (`cron.list`) — the source of truth.** `config/cron-jobs-backup.json` is a periodically-regenerated mirror (drifts between regens; never hand-maintained). Removed/changed-job history → `memory/system-evolution.md`.

### Key pipeline

Sheets (8 PM) → replies (8–9 PM, the PRIMARY record) → Standup-Reply Parser (9:30 PM + 8:30 AM passes) → **the task graph** ← also fed by Meeting Intelligence (transcripts, via task-handler), the gated channel classifier (≥0.85), and DM commands. The **generator** renders the graph into `DAILY_STATE.md`'s Per Person/Blockers after every MI run + parser pass; MI writes only the narrative sections. Readers (Daily Pulse / Follow-Through / Risk Radar / slack-commands) read the graph first. All agents read `AGENT_RULES.md` first.

## Lessons Learned

(Hard-won — they prevent repeat mistakes. Kept in the injected core on purpose.)

- Notion API v2025-09-03: `/data_sources/{id}/query` NOT `/databases/{id}/query`
- apt-get in cron prompts wastes timeout budget
- Cron delivery `channel:"webchat"` doesn't route to Slack — agents post via explicit `action=send`
- **Workspace lives on the persistent /data volume**; CONFIG files (SOUL, MEMORY, TOOLS, AGENT_RULES, AGENTS) refresh from git each deploy — a runtime edit is session-scoped; permanence requires a git commit (flag Abhinav)
- **Bootstrap injection caps (OpenClaw ≥5.28): 12,000 chars per FILE + 60,000 total; an over-budget file keeps head 75% + tail 25% and SILENTLY DROPS THE MIDDLE.** (The old "~20k cap" lesson was 3.13-era and wrong.) Keep SOUL/MEMORY ≤11.5k — enforced by `tests/test_workspace_budgets.py`; the 20k/80k config override is a safety net only.
- **OpenClaw ≥5.28 strips well-known credential env names (`GITHUB_TOKEN`/`GH_TOKEN`) from session env by design. Ours is `BON_GITHUB_TOKEN` — do NOT rename back; every GitHub read silently breaks.**
- OpenClaw cron jobs have TWO sources of truth — the `payload.message` inline prompt AND the SKILL it references; **the inline prompt WINS.** Thin crons (defer-to-SKILL verbatim) are the fix; update both on architecture changes.
- Fireflies only returns past transcripts; allow 30–60 min post-call processing — the MI no-show guard fires **≥18:30 UTC only**
- BON has weekend meetings — don't restrict crons to Mon–Fri
- NEVER reveal internals to anyone in Slack — violated once with Samder, never again
- Isolated agent sessions need guardrails baked into prompts; each Slack surface (DM, channel mention) is a SEPARATE session with no shared memory — never @-mention/loop in a third person on your own initiative
- For code questions: fetch + quote the real file or say you can't read it — never invent paths/line numbers
- Alaska v1 failed as a REPORTING system. Must be a THINKING system.
- Repeated critical alerts become noise — only alert on NEW items; observations/insights go to Abhinav DM first, not public channels
- 10pts per person per week MAX; the sprint board reflects meeting reality, not the other way around
- DMs are private per person — only Abhinav (Admin) can review others' DM history with Alaska
- The standup pipeline rides on MI accuracy — better to show "No commitments captured" than wrong items

## Current State

**Live operational state is always `DAILY_STATE.md`** — read it; do not duplicate it here (a stale copy here once caused quoting May-15 metrics as current).

## Recent System Evolution

Full version-by-version history: `memory/system-evolution.md`. Latest highlights: V4 stabilization sprint + 5.28-upgrade survival + the OM4 `!`-command layer + V5 P0–P21 gated (June 2026); the `agent-memory` private store (#68); the V5 PMF foundation (#59). Read system-evolution for the "why" behind any past change.
