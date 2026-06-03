# V4 Reckoning — planned vs. achieved vs. left (grounded)

> **What this is:** an honest, **verification-marked** accounting of V4 — what we set out to build, what's actually running, what's dormant or drifted, and what's left. Built against the live ground-truth audit (2026-06-03) + the [Live System Map](alaska-live-system-map.md), not against aspirational docs. Where this disagrees with `ROADMAP.md`'s status claims, **this wins** (ROADMAP predates the audit and overstates "active").
>
> **Legend:** ✅ **live-verified** (audit confirmed running) · ☑️ **merged to repo, live status not separately verified** · ⚠️ **dormant / drift** (built but not actually running, or repo ≠ live) · ⚪ **not done**
>
> **⚠️ Update — full live-cron verification (post `cron.list` dump):** **NONE of this session's dashboard-cron edits landed.** `HARD CHANNEL BOUNDARY` (#74 Thinker), `DATE DISCIPLINE` (Phase 1.4), and `WEEKEND-AWARE` + `FRESHNESS` (#80) are **ABSENT from every live cron**. The auto-deploy path IS live (SOUL/MEMORY/AGENT_RULES markers, classifier 1.4.1, MI + classifier defer-to-SKILL). **Confirmed split: CONFIG files + SKILL-deferring crons reach Alaska; fat-prompt cron edits do not** — those crons carry their own logic and the dashboard edits were never applied. **Decided structural fix: thin the fat crons to defer to their SKILLs** (as MI/classifier already do) so the auto-deployed repo is the single source of truth and the dashboard stops drifting. Until then, every "needs dashboard" item below is **NOT live** — including #74 (Thinker can still post check-ins → the 6 PM double-fire can recur) and #80's Pre-Call freshness / Daily-Pulse weekend guards. *(Live now via auto-deploy: #77 grounding, #78 capture, #73 classifier 1.4.1, #80 MI no-show [SKILL-defer].)*

---

## 1. What V4 was meant to be

Turn Alaska from a reactive meeting/standup bot into a **proactive, grounded coworker**: a SQLite task graph as the spine, a message classifier feeding it, proactive watchers, a domain KB she actually uses, and a cutover making the graph the source of truth. Load-bearing for the BON V2 launch (~June 10).

---

## 2. Phase scorecard (A–E)

| Phase | Goal | Status | Grounded evidence |
|---|---|---|---|
| **A — Schema + Classifier** | SQLite task graph + intent classifier | ✅ **live** | 50 tables, migrations 0001–0006 applied; classifier 1.4.1 live; `intent_inbox`=711, `classifier_audit`=715 (actively processing) |
| **B — Task Lifecycle** | `task-handler` sole writer; feeders MI / channel / DM / standup-reply | ✅ mostly · ⚠️ 1 feeder dormant | task-handler 1.2.0 live; `tasks`=9 growing (T-9 from a channel TASK_ASSIGN — handshake verified). Feeders live: MI ✅, channel→task ✅ (1.4.1, fixed #73), DM ✅. **Standup-reply feeder ⚠️ DORMANT — built in pre-call-brief Step 4 but NO cron triggers it.** |
| **C — Scheduling** | reminder-dispatcher + RRULE | ✅ live (lightly used) | reminder-dispatcher 1.0.0; `scheduled_actions`=1 |
| **D.1 — KB** | Domain fluency for Alaska | ✅ exists · ⚠️ was unused in conversation | 19 KB files live. Until this session Alaska did NOT consult it (the A2P fabrication) → now wired into the DM path via the grounding contract (#77). |
| **D.2 — Watchers** | Proactive trigger→action primitive | ✅ **live** | watcher-creator/dispatcher/janitor + event-poller live; `watchers`=3 (W-1/2/3) + 4 event-poller crons live; hardened #46 (tz), #74 (Thinker lane boundary) |
| **E — Cutover** | Graph → source of truth; `DAILY_STATE.md` → generated view | ⚪ **NOT DONE** | generator built (`lib/generate_daily_state.py`, #53); P4.2 parity + P4.3 hard-cut never done. **The audit reinforced why this matters: `DAILY_STATE.md` has a single writer (MI/transcripts) — that's the staleness root.** |

**One-line V4 truth:** A–D are built and (mostly) live; **E is the real unfinished piece**, and the standup-reply feeder inside B is dormant.

> **Note (added after review):** the phase table above is *coarse* — it collapses several distinct capabilities into phase rows. The capability list below is the complete one. In particular, **cross-person assignment** was the original "Phase D — cross-person workflow" before it was absorbed into D.2 as a watcher template.

## 2b. V4 capabilities — the COMPLETE list (this is what was actually built)

| Capability | Status | Notes |
|---|---|---|
| SQLite task graph (migrations 0001–0002) | ✅ live | 50 tables |
| Intent classifier — 10 intents, observe + gated action | ✅ live | 1.4.1 |
| `task-handler` — sole writer, match-or-create dedup | ✅ live | 1.2.0 |
| Feeders → graph: Meeting Intelligence / channel (gated ≥0.85) / Slack DM | ✅ live | |
| Feeder → graph: **standup-reply parser** | ⚠️ **dormant** | built (pre-call-brief Step 4), no cron triggers it |
| **Cross-person assignment + accept/decline handshake** (the original "Phase D") | ✅ live | `pending_acceptance` → ack/pass, owner-only guard; **T-9 proved it end-to-end**; #73 fixed the channel path |
| ↳ Unacked-assignment **escalation** (2h/24h/48h) | ☑️ built | follow-through `escalate_unacked_assignments`; fires as the graph fills — not yet observed |
| **Graph-aware reads + NL queries** ("what's X working on") | ☑️ built | Daily Pulse / Follow-Through / Risk Radar / slack-commands read the graph (1.3.0 / 2.1.0); live behavior not separately re-verified |
| **DM intent-action layer** (DM → classify → route to handler) | ✅ live | slack-commands 1.3.0 |
| **DECISION_RECORDED capture** → Notion Decision Log + `task_event` | ☑️ built | #52/#56; live status not separately verified |
| Scheduling — reminders (RRULE) + routine-proposal approval (Phase C) | ✅ live | reminder-dispatcher; `scheduled_actions`=1 |
| BON Knowledge Base (D.1) | ✅ live | 19 files; **now wired into conversation** (was unused) |
| Watchers V1 (D.2): creator / dispatcher / event-poller / janitor | ✅ live | |
| ↳ Watcher templates: `stale-task`, `cross-person-assign` | ☑️ un-gated (#52) | produce as graph fills |
| ↳ Event-pollers: `new_signup`, `bug_closed`, `task_status_changed`, `pr_merged` | ✅ live | 4 crons |
| ↳ User watchers: W-1 (metrics), W-2 (sub-600 signups), W-3 (card linkage) | ✅ live | `watchers`=3 |
| **Phase E** — graph → source of truth; `DAILY_STATE.md` → generated view | ⚪ **not done** | the big remaining piece |
| **KB self-maintenance watcher** — deferred V4 **capstone** | ⚪ gated on E | scans Slack/MI/DMs → diffs KB → proposes edits → Abhinav approves |
| *(hardening-window adds, not original phases)* agent_memory; grounding + capture reflexes | ✅ live | agent_memory ⚠️ 0 rows / unexercised |

---

## 3. The 24-hour observation test — findings & dispositions

| # | Finding | Disposition |
|---|---|---|
| A | Task graph filling | ✅ confirmed (tasks growing) |
| B | Classifier alive | ✅ confirmed (715 classified) |
| C | Channel TASK_ASSIGN classified but **didn't create the task** | ✅ fixed #73 (was a skippable side-branch; T-9 then fired) — 1.4.1 live |
| D | 6 PM "double-fire" in #alaska-daily-pulse | ✅ root-caused: **Thinker overstepping its lane** (posted a check-in); fixed #74 (live cron dashboard apply pending verify) |
| E | W-1 "error" | ✅ cosmetic — the `{mode:none}` delivery phantom; DM actually landed; janitor doesn't disable on it |

**Plus your 24–48h observations** → became the grounding & memory workstream (§5): A2P fabrication, wrong dates, false git-zero, wrong owner, un-captured test-user-IDs, duplicate standup, weekend staleness.

---

## 4. This session's shipped fixes (PR log)

| PR | What | Live status |
|---|---|---|
| #68/#69 | agent_memory — private working memory (migration 0006 + skill + memory docs) | ✅ live (skill 1.0.0, table exists) · ⚠️ **0 rows — never exercised in real use** |
| #73 | classifier TASK_ASSIGN actually fires (1.4.1) | ✅ live-verified (1.4.1) |
| #74 | Thinker hard channel boundary (no check-ins to pulse) | ☑️ merged · live-cron apply unverified |
| #76 | the grounding & memory-discipline plan | ✅ merged |
| #77 | **Reflex 1** — grounding contract (SOUL + AGENT_RULES + MEMORY KB index) | ✅ **live-verified** (all markers present) |
| #78 | **Reflex 2** — capture reflex (MEMORY) | ✅ live-verified (marker present) |
| #79 | Phase 3 — A2P KB proposal for `twilio.md` | ⚪ **not merged; needs your paste** |
| #80 | Phase 4 — stale-data guards (MI no-show, pre-call freshness, weekend staleness) | ☑️ merged · MI auto (defers to SKILL); Daily-Pulse/Pre-Call need dashboard apply |
| #82 | Live System Map (verified ground truth) | ☑️ this PR |

*(Earlier in the broader arc: #46 watcher tz/janitor, #47 blocker dedup, #50–53 V4 completion P1–P4, #54 channel TASK_ASSIGN activate, #55 DM honesty, #56 cross-session memory, #57/58 docs, #67 SOUL reading-fix.)*

---

## 5. The grounding & memory-discipline workstream (this session's arc)

Root cause behind ~8 of your observations: **Alaska generated facts she could have looked up, and forgot facts she should have written down.** Two structural reflexes installed:
- **Reflex 1 (ground before you speak)** — #77, ✅ live: retrieve from KB / roster-by-role / task graph / Decision Log / `date` / live API; never fabricate; pre-send self-check.
- **Reflex 2 (capture durable facts)** — #78, ✅ live: operational → agent_memory; domain-canon → propose to you for the KB.
- Plus date-anchoring (#77), stale-data guards (#80), and the A2P KB proposal (#79, pending your paste).

---

## 6. What's LEFT — the honest list

**Big rocks:**
1. ⚪ **Phase E cutover** — graph → source of truth; retire `DAILY_STATE.md`'s single-writer fragility. The audit makes the case stronger than ever.
2. ⚠️ **Standup-reply structured capture** — the dormant B feeder. (Replies *are* ingested + classified via the Thinker sweep, but not structured-parsed and don't reach `DAILY_STATE.md`.) Design fork: re-wire the parser vs. lean on Phase E.

**Drift list (from the live audit):**
3. 🔴 **Cron snapshot stale** (repo 19 vs live 22; Thinker content differs) → regenerate from `cron.list`.
4. 🟡 SOUL 19.1k / MEMORY 19.6k — at the ~20k injection cap → trim.
5. 🟡 agent_memory unexercised (0 rows) → live smoke-test.
6. 🟢 Thinker self-loop (ingests its own #daily-standup posts) → confirm bot-self pre-filter.
7. 🟢 `blockers`=0 → confirm the blocker write-path fires.

**Verification debt (this session's dashboard handoffs — NOT confirmed live):**
8. ☑️→? Did the live crons receive: the `DATE DISCIPLINE` lines (#77/Phase-1.4 — MI/Daily-Pulse/Pre-Call/W-1), the `WEEKEND-AWARE`/`FRESHNESS` lines (#80), the Thinker boundary (#74)? **Unknown** — needs the full live-payload diff (folds into #3).

**Your queue:** merge #80/#82; merge #79 + paste A2P content into `twilio.md`; apply the pending dashboard cron lines.

---

## 7. Prioritized next actions

| Pri | Action | Rationale |
|---|---|---|
| **1** | **Regenerate the cron snapshot from live** (Alaska dumps all 22 full payloads → I rebuild the file) | Foundation of the closed loop; also resolves the verification debt (#8) in one pass |
| **2** | **Standup / `DAILY_STATE` design fork** — short brainstorm: re-wire structured parser vs. accelerate Phase E | The real recurring product wound (June 1–2) |
| **3** | SOUL/MEMORY trim · agent_memory smoke-test · blockers/self-loop confirms | cheap drift-list closers |
| **4** | Phase E cutover proper | the last big V4 piece |

---

## 8. The methodology shift (so this stays true)

Open-loop → closed-loop. **(1)** cron snapshot = generated mirror of `cron.list`, never hand-edited; **(2)** every behavior change declares its reach (auto-deploy vs. dashboard) and is *verified live*; **(3)** a standing drift-check re-runs the audit on a cadence; **(4)** Claude never reports live behavior from repo/docs without verifying or caveating. (Full detail in [the Live System Map](alaska-live-system-map.md) §7.)
