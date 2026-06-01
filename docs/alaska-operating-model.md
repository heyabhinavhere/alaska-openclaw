# Alaska Operating Model

> **What this is:** the single canonical description of *how Alaska works as a system* — the write path into her task graph, the source-of-truth model, and the daily cadence. This is the one home for the operating model so it never drifts across files.
>
> **What this is NOT:** it is not BON domain knowledge (that's the KB at `workspace/knowledge/`), and it is not the step-by-step logic of any single agent (that lives in each `skills/*/SKILL.md` — every skill *is* a workflow). KB integration files and `knowledge/architecture.md` point *here* for the pipeline; this doc points *out* to the skills for the detail.
>
> **The capability-vs-workflow line (why this file exists):** the KB answers *"what is this, and what can Alaska DO with it"* (BON's systems + integrations + APIs as a toolbox). This doc and the skills answer *"how Alaska actually does it"* (workflow). Keeping the operating model in exactly one place means a pipeline change — Phase E **will** change it — updates one file, not five. (That five-places-go-stale drift was the v2.2/v2.3 disease.)
>
> **Last updated:** 2026-06-01 · **Owner:** Abhinav

---

## 1. The write path — one writer, many feeders

Alaska's task graph lives in SQLite at `/data/queue/alaska.db` (task-model tables: `tasks`, `task_events`, `task_mentions`, `task_categories`, `blockers`; plus `scheduled_actions` for Phase C reminders — all verified present in the migrations). **Exactly one skill writes to it — `task-handler`.** Everything else *feeds* task-handler a structured intent; task-handler does match-or-create dedup and is the sole writer. One writer means every task mutation lands in one auditable place.

| Surface | Feeder | `source` | Phase | Acts today? |
|---|---|---|---|---|
| Call transcripts | meeting-intelligence (Step 5b) | `meeting` | B3 | ✅ wired (dormant) |
| Slack DM to Alaska | slack-commands → intent-classifier → task-handler | `slack_dm` | B4 | ✅ wired |
| Standup-sheet / thread replies | pre-call-brief reply parser → task-handler | `standup_reply` | B5 | ✅ wired |
| Channel messages | intent-classifier (observe) → [task-handler] | `slack_channel` | A→D | ⏳ observe-only until Phase D |
| Direct / operator | slack-commands / manual | `manual` | B4 | ✅ |

**Readers** (write nothing to the task graph): Daily Pulse, Follow-Through, Risk Radar, Thinker. Pre-call-brief is a *hybrid* — it reads to build standup sheets and writes (via task-handler) by parsing the replies.

The detailed extraction logic, dedup rules, and anti-hallucination guards are **not** repeated here — they live in `skills/task-handler/SKILL.md`, `skills/meeting-intelligence/SKILL.md`, and `skills/intent-classifier/SKILL.md`. This section is the map; the skills are the territory.

---

## 2. Source of truth — current vs. V4 target (read carefully)

⚠️ **This is the one place where "current reality" and "V4 target" genuinely differ.** Anyone reading this — human or agent — must not state the V4 end-state as if it were live today.

- **V4 target (after Phase E):** the SQLite task graph is the source of truth. `DAILY_STATE.md` becomes a generated, read-only *view* of it. task-handler is the only writer; everything reconciles to the graph.
- **Current (pre-cutover, last confirmed 2026-05-30):** `DAILY_STATE.md` is still the operative source of truth. **Meeting Intelligence writes it directly** after each nightly standup; every other agent reads it before acting. The SQLite task graph is wired and runs in parallel but is **not yet authoritative — its tables were empty (0 rows; Phase B dormant) as of 05-30.** ⚠️ **Ops-4 is re-verifying this on 2026-06-01** — treat the 0-row state as last-confirmed-05-30, not a standing fact; update this bullet with Ops-4's result.
- **Phase E flips this:** a dual-write window (MI writes both `DAILY_STATE.md` and the graph) to prove parity, then a hard cut where `DAILY_STATE.md` is generated from the graph.

Until Phase E lands, treat `DAILY_STATE.md` as truth and the task graph as a parallel substrate being proven out. Tracked as **Ops-4** (verify Phase B actually fires in prod) before V4 leans harder on the graph — see `docs/ROADMAP.md`.

---

## 3. Daily cadence

All crons run in UTC; times below are IST (UTC+5:30). The nightly team standup is ~9 PM IST, which is why the evening agents (Pre-Call Brief → Meeting Intelligence) bracket it.

| Time (IST) | Cron (UTC) | Agent | Reads / Writes |
|---|---|---|---|
| every 5 min | `*/5 * * * *` | Intent Classifier (batch, Phase A obs) | reads channel msgs → `intent_inbox` (observe-only) |
| every 15 min | `*/15 * * * *` | Reminder Dispatcher | reads `scheduled_actions` → fires due reminders |
| 9:00 AM | `30 3 * * *` | Daily Pulse | reads `DAILY_STATE.md` → posts `#alaska-daily-pulse` |
| 9:05 AM | `35 3 * * *` | Follow-Through (AM) | reads per-person state → DMs overdue owners |
| 9:30 AM | `0 4 * * *` | Risk Radar | reads state → posts `#alaska-alerts` (Medium+ only) |
| 9:30 AM – 8:30 PM, hourly | `30 3-15 * * *` | Thinker | observes outputs, meta-checks, connects dots |
| 9:30/11:30 AM, 1:30/3:30/5:30 PM | `0 4,6,8,10,12 * * *` | Doc Keeper (event-driven) | maintains Decision Log / Changelog |
| 11:30 AM | `0 6 * * *` | Routine Proposal Watch | expires stale routine proposals (>7 days) |
| 6:00 PM | `30 12 * * *` | Follow-Through (PM) | reads state → DMs |
| 8:30 PM (Mon–Fri) | `0 15 * * 1-5` | Pre-Call Brief | reads SQLite + builds standup sheet (**hybrid feeder**) |
| 8:30 PM – 1:30 AM, every 30 min | `*/30 15-20 * * *` | Meeting Intelligence | processes Fireflies → **writes `DAILY_STATE.md`** + feeds task-handler |
| 11:30 PM | `0 18 * * *` | Daily Cost Report | DM to Abhinav (captures full-day spend) |
| 10:30 AM (Mon) | `0 5 * * 1` | Sprint Operator | Monday planning helper |
| 6:00 PM (Fri) | `30 12 * * 5` | Doc Keeper — Weekly Digest | weekly digest |

The 5-minute Daily-Pulse → Follow-Through offset (9:00 → 9:05) and the end-of-day Cost Report (11:30 PM, not 11:30 AM) are deliberate — they're the v2.3 stabilization fixes (cron decoupling + full-day spend capture).

---

## 4. Where detail lives (pointers, not duplication)

| You want… | Look at… |
|---|---|
| How one agent thinks/acts, extraction + anti-hallucination rules | the relevant `skills/*/SKILL.md` — each skill **is** a workflow |
| What Alaska can DO with an integration (Fireflies / Plaid / Amplitude / …) | the KB: `workspace/knowledge/integrations/*` |
| BON's product + system architecture (the app, backend, data pipelines) | `workspace/knowledge/architecture.md` (pure BON — no Alaska workflow) |
| BON domain definitions (personas, metrics, lifecycle events) | `workspace/knowledge/definitions/*` |
| The build roadmap, phase status, naming scheme | `docs/ROADMAP.md` |
| What changed and why, over time | `workspace/memory/system-evolution.md` |

**Rule of thumb:** if a fact is about *the outside world or BON's domain*, it belongs in the KB. If it's about *how Alaska operates*, it belongs here (system-level) or in a skill (agent-level) — never copied into a KB integration file.
