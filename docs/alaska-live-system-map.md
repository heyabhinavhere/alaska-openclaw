# Alaska Live System Map — VERIFIED ground truth

> ⚠️ **HISTORICAL — PRE-CUTOVER LIVE AUDIT (2026-06-03).** Verified-live on its date, but predates the Phase E cutover (2026-06-12). Two findings are superseded (corrected inline below): DAILY_STATE.md's Per Person/Blockers are now GENERATED from the graph (the graph is the source of truth, not a single MI writer), and the Standup-Reply Parser cron is LIVE. **Current source-of-truth docs:** `docs/alaska-operating-model.md` §3, `workspace/AGENT_RULES.md`.

> **What this is:** the first description of Alaska built from the **actual live system**, not from the repo/docs/assumptions. Produced 2026-06-03 from a ground-truth audit Alaska ran in the live container (`cron.list`, live `/data/skills`, live `/root/.openclaw/workspace`, live `/data/queue/alaska.db`).
>
> **Why it exists:** we repeatedly shipped to the repo and *assumed* it was live. It wasn't always — the live **cron** layer drifts from the repo because it's hand-maintained on the OpenClaw dashboard and nothing reconciles it. This doc is the reconciliation. **When this doc and a repo snapshot disagree, this doc (or a fresh `cron.list`) wins.**
>
> **Verification basis:** ✅ = confirmed live this audit · ⚠️ = drift (live ≠ repo) · ❓ = not yet verified live.

---

## 1. The load model — what each session actually sees

| Session type | Loads | Verified |
|---|---|---|
| **Synchronous (DM + channel @-mention)** | `SOUL.md` + `MEMORY.md` + `TOOLS.md` + `AGENTS.md`. **No skills, no KB, no task graph** unless SOUL tells it to go read them. | ✅ |
| **Cron agents** | their cron `payload.message` (the operative fat prompt) + the files/skills it names as MANDATORY READS (incl. `AGENT_RULES.md`). | ✅ |

**The operative reality for crons is the dashboard `payload.message`, which OVERRIDES the SKILL it references** unless the prompt explicitly defers ("execute the SKILL verbatim"). This is the #1 drift source.

**Confirmed reaching Alaska (CONFIG/skill deploy path WORKS):** live `SOUL.md` has "Ground before you speak" + "agent-memory"; `MEMORY.md` has "My knowledge base" + "Capturing facts"; `AGENT_RULES.md` has "Grounding (all agents)". So CONFIG files refresh from git on deploy as intended — **the drift is NOT here, it's in the crons.**

---

## 2. Live crons — 22 (repo snapshot has only 19 ⚠️)

All enabled, all `delivery.mode = none` (agents post via explicit `action=send`; the cron layer mis-marks `none` as "failed" — the known phantom).

| Cron | Schedule (UTC) | IST | Notes |
|---|---|---|---|
| Intent Classifier — Batch | `*/5 * * * *` | every 5m | name still says "Phase A obs mode" but acts per SKILL 1.4.1 |
| Event Poller — new_signup | `*/15 * * * *` | 15m | ⚠️ not in snapshot |
| Event Poller — bug_closed / task_status_changed / pr_merged | `*/30 * * * *` | 30m | ⚠️ not in snapshot |
| Thinker — Hourly Observation | `30 3-15 * * *` | 9 AM–9 PM | **reads ALL channels via `users.conversations`** (not 4) ⚠️ snapshot stale |
| Pre-Call Brief — Fireflies Check | `30 14 * * 1-5` | 8 PM wkdays | posts sheets to #daily-standup; does NOT read replies |
| Meeting Intelligence Pipeline | `*/30 15-20 * * *` | 8:30 PM–1:30 AM | thin prompt — defers to SKILL verbatim (timeout 600) ✅ |
| Daily Cost Report | `0 18 * * *` | 11:30 PM | DM to Abhinav |
| Daily Pulse | `30 3 * * *` | 9 AM | fat prompt, inline staleness guard |
| User Profile 360 — Cache Purge | `35 3 * * *` | 9:05 AM | ⚠️ not in snapshot (V5) |
| Follow-Through — 9AM IST | `35 3 * * *` | 9:05 AM | DMs + posts to #alaska-daily-pulse |
| Follow-Through — 6PM IST | `30 12 * * *` | 6 PM | check-in to #alaska-daily-pulse; Fri weekly DM |
| Risk Radar | `0 4 * * *` | 9:30 AM | |
| Watcher Janitor | `0 4 * * *` | 9:30 AM | |
| Watcher W-1 — daily metrics | `30 9 * * 1-5` IST-tz | 9:30 AM | ⚠️ not in snapshot (user watcher) |
| Watcher W-1 — expiry | one-shot Jun 7 | — | ⚠️ |
| Watcher W-2 — weekly sub-600 | `0 9 * * 1` IST-tz | Mon 9 AM | ⚠️ |
| Watcher W-3 — weekly card linkage | `0 10 * * 6` IST-tz | Sat 10 AM | ⚠️ |
| Doc Keeper — Event-Driven | `0 4,6,8,10,12 * * *` | 5×/day | |
| Doc Keeper — Weekly Digest | `30 12 * * 5` | Fri 6 PM | |
| Sprint Operator — Monday | `0 5 * * 1` | Mon 10:30 AM | |

---

## 3. The write-path reality (corrected)

**Post-cutover (2026-06-12): `DAILY_STATE.md` is a generated view of the task graph.** Its `## Per Person` / `## Active Blockers` are rendered by `generate_daily_state.py` from the `tasks`/`blockers` graph (fed via task-handler from MI, standup replies, the channel classifier, and DM commands); MI writes only the narrative sections. The old "single MI writer → chronic staleness" fragility is **resolved** — the graph is the source of truth, so a missed call no longer freezes per-person state.

**The task graph (`tasks`/`blockers`) is written by `task-handler`, fed by:**
- Meeting Intelligence Step 5b (from transcripts) ✅
- intent-classifier gated channel→task (≥0.85 + resolved owner, from `intent_inbox`) ✅
- slack-commands DM handlers ✅
- pre-call-brief reply parser (`source=standup_reply`) — ✅ **LIVE** (Standup-Reply Parser cron, `0 3,16 UTC` — two passes; built #102, cron wired post-#104)

**`intent_inbox` is fed by the Thinker's hourly `users.conversations` sweep** of all 12 channels + DMs + MPIMs (711 rows, growing).

**So standup replies (#daily-standup) flow:** Thinker sweep → `intent_inbox` → classifier → (if ≥0.85 + resolved owner) task-handler → task graph. They are **NOT** structured-parsed (the standup grammar is dormant) and do **NOT** reach `DAILY_STATE.md`. Terse status updates that don't clear the ≥0.85 gate are classified as observations and go no further.

---

## 4. Live skills — 28 (all expected present ✅)

Key versions live: `intent-classifier 1.4.1`, `meeting-intelligence 2.3.1`, `task-handler 1.2.0`, `follow-through 2.1.0`, `agent-memory 1.0.0`, `slack-commands 1.3.0`, `daily-pulse 1.1.0`, `alaska-core 2.1.0`, `thinker 1.0.0`, `pre-call-brief 1.0.0`, `risk-radar 1.1.0`, `watcher-creator 1.1.0`, `watcher-janitor 1.1.0`, `pmf-cohort-os 0.1.0`. (Full list in the audit.) No missing skills.

> Note: the **live Thinker CRON** uses an all-channel `users.conversations` sweep that is **not** reflected in the `thinker` SKILL (1.0.0) text or the snapshot — another cron-vs-repo gap.

---

## 5. Live DB — `/data/queue/alaska.db`, 50 tables (migrations 0001–0006 all applied ✅)

| Table | Rows | Note |
|---|---|---|
| tasks | 9 | growing (T-9 from the Nilesh channel TASK_ASSIGN — handshake confirmed working) |
| blockers | 0 | ⚠️ no blockers in the graph — write-path may not be firing |
| agent_memory | 3 | table live (0006 applied); starved until 2026-06-12 — its SOUL remember/recall triggers sat in the truncated middle (recall wiring never live before #151/#152); self-task review loop ships with PR-A |
| intent_inbox | 711 | Thinker sweep feeding it |
| classifier_audit | 715 | classifier actively processing |
| scheduled_actions | 1 | |
| watchers | 3 | W-1/2/3 |

---

## 6. Drift list (live ≠ repo) — what to fix

1. **🔴 The cron snapshot (`config/cron-jobs-backup.json`, 19) does not mirror live (22), and key prompts differ (Thinker).** Until fixed, the snapshot must NOT be trusted to describe live behavior. → **Regenerate the snapshot FROM `cron.list`** and keep it a generated mirror.
2. **🟡 No structured standup-reply parser fires.** The pre-call-brief Step 4 grammar is dormant (no trigger). Replies are only generically classified.
3. **🟡 `DAILY_STATE.md` single-writer (MI/transcripts).** No transcript = stale. Structural fix = Phase E (graph → source of truth).
4. **🟡 SOUL 19,121 / MEMORY 19,605 chars — at the ~20k injection cap.** Trim before further injected-context additions.
5. **🟡 agent_memory starved, not broken (3 rows lifetime as of 2026-06-12).** Root cause found: the SOUL.md remember/recall triggers were middle-truncated out of every live session (recall from day one) until #151/#152 landed. Post-deploy smoke + the morning self-task review cron (PR-A) make it a working loop.
6. **🟢 Thinker ingests #daily-standup → its own Pre-Call sheets loop into `intent_inbox`.** Confirm the bot-self pre-filter excludes them.
7. **🟢 blockers = 0.** Confirm the blocker write-path actually fires from MI / task-handler.

---

## 7. Keeping this map true (the closed loop)

- **The cron snapshot is a GENERATED mirror, not hand-maintained.** After ANY dashboard cron change, regenerate `config/cron-jobs-backup.json` from `cron.list`.
- **Every behavior change declares its reach** (auto-deploy CONFIG/skill vs. dashboard cron) **and is verified live**, not assumed.
- **A standing drift check** re-runs this audit on a cadence and flags live-vs-repo deltas.
- **Claude never reports live behavior from the repo/snapshot/docs** — verify live, or caveat explicitly.
