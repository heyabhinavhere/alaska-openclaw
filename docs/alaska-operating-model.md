# Alaska Operating Model

> **What this is:** the single canonical description of *how Alaska works as a system* — **how she decides which source to trust for a question (the source-router, §1)**, the write path into her task graph (§2), the source-of-truth model (§3), the data-store map (§4), the core/PMF/shared boundaries (§5), and the daily cadence (§6). One home so it never drifts across files.
>
> **What this is NOT:** not BON domain knowledge (that's the KB at `workspace/knowledge/` — *"what a thing is and what Alaska can DO with it"*), and not the step-by-step logic of any single agent (that lives in each `skills/*/SKILL.md` — every skill *is* a workflow). The KB and skills point *here* for routing + pipeline; this doc points *out* to them for the detail.
>
> **Why this exists:** the KB answers *"what is this."* This doc answers *"for a given question or trigger, which source does Alaska use, and how does the work flow."* Keeping it in exactly one place means a change updates one file, not five — the v2.2/v2.3 "five-places-go-stale" disease.
>
> **Last updated:** 2026-06-04 · **Owner:** Abhinav

---

## 1. The Source-Router — how Alaska answers any question (read first)

Alaska has many places to look — Amplitude, the 360 User Profile API, the PMF cohort store, case files, Watchers, the KB, memory, the task graph. The single biggest reliability risk is **answering from the wrong source — or from her own memory instead of a source at all** (the failure the 2026-06-03 grounding work fixed). So every question or trigger resolves the same way:

> **Mode → Source (primary → fallback) → owning Skill → GROUND** (retrieve from that source *this session*; never state from parametric memory).

Alaska is **internally aware of every mode** and pattern-matches the question to one. Where a teammate's intent is genuinely ambiguous, they disambiguate with an **explicit command** (today: `/pmf`). The command removes *her* guesswork — it does not limit what she knows.

| Mode | Triggered by | Source: primary → fallback | Owning skill | Never use |
|---|---|---|---|---|
| **Specific-user intel** | "what's up with user X", "who is jane@…", "why isn't this user engaging" | **360 User Profile API** (credit / Plaid / raw chat) → Amplitude (fallback) | `user-profile-360` | BON's product-layer interpretations (`user_kpis`, `detected_needs`, `financial_profile_v2`, `opportunities`, `budgeting`…) — Alaska forms her *own* read from raw signal |
| **PMF cohort** — `/pmf` | `/pmf <question>` (explicit) | **PMF cohort store** (`alaska_pmf.db`: registry, daily snapshots, case files, funnel, operating queues, interventions) + surveys + PMF Watchers + `definitions/pmf-cohort-os.md` | `pmf-cohort-os` | the default path's 360/Amplitude conclusions *as* PMF truth (it's a different lens) |
| **Aggregate analytics** | "how many…", DAU/WAU, funnels, distributions, cohorts | **Amplitude** (Real-Users filter mandatory — `integrations/amplitude.md`) | `amplitude-analyst` | per-user claims from aggregate numbers |
| **Tasks / PM status** | "what's on my plate", "T-42 done", "any blockers" | **task graph** (`alaska.db`) — source of truth since the Phase E cutover (2026-06-12); `DAILY_STATE.md` is its generated view (§3) | `task-handler` / `slack-commands` | hand-editing the generated `## Per Person` / `## Active Blockers` (the graph wins) |
| **Ongoing watch** | "every Monday show me…", "alert when a user below 580 signs up" | Watchers pipeline (`watchers`, `watcher_fires`) | `watcher-creator` / `watcher-dispatcher` | answering once (that's a query, not a watch) |
| **Messaging** | campaigns, push/email, delivery metrics | Customer.io | `customerio-ops` | sending without the guard + human approval |
| **BON domain fact** | "how does Plaid linking work", "what counts as a real user" | **KB** (`workspace/knowledge/`) | (any skill loads the KB) | inventing system behavior from memory |

**The grounding rule (non-negotiable).** Before stating a fact, Alaska retrieves it from the source the router selects, *this session*. She never answers a user / metric / PMF question from parametric memory. Runtime enforcement lives in the grounding contract (`workspace/SOUL.md` + `workspace/AGENT_RULES.md`) and the concise routing table in `skills/alaska-core/SKILL.md`; **this doc is the canonical reference they point to.**

**Cross-aware pointer (one system, clean seams).** For a *plain* specific-user question where that user is in the **active PMF cohort**, Alaska answers from 360 + Amplitude as usual and appends one line — *"this user is in the PMF launch cohort (stage X) — `/pmf` for their cohort case file."* Awareness of depth, **without blending sources**; PMF detail only arrives via `/pmf`.

**Why explicit `/pmf`.** "What's up with user 1414?" means different things depending on whether the asker wants the user's *financial/behavioural* profile (default) or their *PMF-cohort* story (case file, funnel stage, queues, interventions, survey). Making the mode explicit makes the source unambiguous; the pointer keeps Alaska's two lenses connected.

---

## 1.5 The command layer — `!verb` (OM-4)

> **Status:** rolling out (OM-4, from 2026-06-05). `!case`/`!help`/`!ping` land first; `!pmf`/`!audit` follow, one verb per PR. This is the **human reference**; the runtime authority is `SOUL.md` → "STEP 0 — Command Router" + the concise rule in `skills/alaska-core/SKILL.md`, and the deterministic verb dispatch in `lib/alaska_command_gateway/execute.py` (`ROUTES`). This doc is **not** read by the live agent (see §0 note: `docs/` is not shipped to the container).

§1 is the **source-router** — for a *free-form question* it picks which data source to trust. §1.5 is the **command layer** — for an *explicit command* it routes deterministically, *before* §1 runs. They are complementary: a message is either a command (`!verb`) or it falls through to the source-router.

**The grammar — `!` + a CLOSED whitelist.** A leading `!` alone is **not** a command. The trigger is: the first meaningful token (after any @mention, or at DM start) is `!<verb>` **and** `<verb>` is whitelisted. Otherwise → normal chat (or, for a non-whitelisted `!token`, a one-line *"unknown command — try `!help`"*, never an improvised answer). `!` is the explicit, always-reliable form.

**Bare verbs (decided 2026-06-05 — "accept unambiguous bare verbs").** A *clear, unambiguous* bare command — just the verb + its target, like `audit 1453`, `case 2762`, `pmf likely lovers` — is also accepted as that command (the intent is obvious; the model runs it regardless, so the prose matches reality rather than fighting it). The guardrail is on the **fuzzy** cases: a *sentence* that merely mentions a verb ("can you audit user 1453", "what does an audit show", "case file for user X", "how's pmf going") is NOT a command — answer it, or ask *"did you mean `!audit 1453`?"*. **Boundary:** a bare `user 2762` / "what's up with user X" stays the source-router **360 summary**, NOT the `!case` command (`user` is only a back-compat alias inside the explicit `!case`/`/alaska user` forms).

| Command | Routes to | How |
|---|---|---|
| `!case <user_id>` | `command-gateway` → `alaska_command_gateway.execute "case <id>"` | deterministic Python (relay `text`); posts the case-file DOCX in the channel it was run in |
| `!audit <user_id>` | `bon-internal-audit` skill → `audit_agent.py` | model reads the skill, runs its CLI |
| `!pmf <sub> <args>` | `pmf-cohort-os` skill (owns its own sub-dispatch) | model reads the skill, runs its CLI |
| `!help` / `!ping` | `command-gateway` executor | deterministic |

`/pmf` and `/audit` continue to work as **aliases** during migration. The whitelist is the source of truth — a verb may only join it if it is **read-only or carries its own confirm-before-write handshake** (no destructive verb in the command layer). Reliability is measured, not assumed: every dispatch is logged to `command_audit`, and a verb only goes live once it clears the 4-part bar (known commands ≥95% routed · plain chat 0 false-routes · task/reminder/decision 0 regressions · unknown `!thing` → helpful error). See `docs/platform/command-gateway.md` → "Reliability & observability".

**Native `/alaska` Slack slash commands are deferred** (not dead) — see `docs/superpowers/research/2026-06-05-slack-native-command-postmortem.md`.

---

## 2. The write path — one writer, many feeders

Alaska's task graph lives in SQLite at `/data/queue/alaska.db` (`tasks`, `task_events`, `task_mentions`, `task_categories`, `blockers`; plus `scheduled_actions` for Phase C reminders). **Exactly one skill writes to it — `task-handler`.** Everything else *feeds* task-handler a structured intent; task-handler does match-or-create dedup and is the sole writer. One writer means every task mutation lands in one auditable place.

| Surface | Feeder | `source` | Acts today? |
|---|---|---|---|
| Call transcripts | meeting-intelligence | `meeting` | ✅ active |
| Slack DM to Alaska | slack-commands → intent-classifier → task-handler | `slack_dm` | ✅ |
| Standup-sheet / thread replies | pre-call-brief reply parser → task-handler | `standup_reply` | ✅ |
| Channel messages | intent-classifier → task-handler (gated ≥0.85, incl. TASK_ASSIGN) | `slack_channel` | ✅ |
| Direct / operator | slack-commands / manual | `manual` | ✅ |

**Readers** (write nothing to the graph): Daily Pulse, Follow-Through, Risk Radar, Thinker. Pre-call-brief is a *hybrid* (reads to build standup sheets, writes via task-handler by parsing replies). Extraction/dedup/anti-hallucination detail lives in `skills/task-handler/`, `skills/meeting-intelligence/`, `skills/intent-classifier/` — this is the map; the skills are the territory.

---

## 3. Source of truth — the graph (CUTOVER COMPLETED 2026-06-12)

**The SQLite task graph is the source of truth** — `tasks`/`blockers`/`person_status` on `/data/queue/alaska.db`, written only via task-handler (+ the person_status write-paths). `DAILY_STATE.md` is now a **hybrid view**:

- `## Per Person` + `## Active Blockers` are **GENERATED from the graph** by `/opt/lib/generate_daily_state.py`, which runs at the end of every Meeting-Intelligence pipeline run and every Standup-Reply-Parser pass. **Nothing hand-writes these sections** — a hand edit is overwritten on the next run.
- The narrative sections (Current Focus/Sprint, Goals, Decisions, Metrics, What Changed, Upcoming) remain **Meeting-Intelligence-written**.
- Readers may use `DAILY_STATE.md` as a convenient view; **on any disagreement, the graph wins.**

*(History: dual-write ran 2026-06-01 → 06-12; parity verified twice on 06-12 — the first run found 4 P0s, all fixed systemically; the re-run came back clean. Rollback = revert the cutover PR; MI resumes hand-writing the two sections.)*

---

## 4. The data-store map — what lives where, and what's authoritative

| Store | Location | Holds | Authoritative for | Written by |
|---|---|---|---|---|
| **`alaska.db`** | `/data/queue/` | V4 task graph + ops: `tasks`, `task_events`, `blockers`, `intent_inbox`, `classifier_audit`, `scheduled_actions`, `watchers`, `watcher_fires`, `agent_memory`, `outbox` | tasks/PM (post-Phase-E), watchers, classifier, reminders | V4 skills |
| **`alaska_pmf.db`** | `/data/queue/` | the V5 PMF store (the `pmf_*` + `credgpt_quality_*` tables) | everything PMF | `lib/pmf_os/store.py` (`DEFAULT_DB_PATH`) only |
| **`DAILY_STATE.md`** | `workspace/` | generated view of the graph (Per Person/Blockers) + MI narrative | a convenient summary; the graph is the source of truth (§3) | `generate_daily_state.py` (Per Person/Blockers) + meeting-intelligence (narrative) |
| **KB** | `workspace/knowledge/` | BON domain facts (integrations, definitions, playbooks) | "what a thing is / what Alaska can do with it" | Abhinav (solo) |
| **Core memory** | `workspace/MEMORY.md` (~20k cap, always-injected) + `workspace/memory/*` | identity, roster, lessons, history | who's who + how Alaska operates over time | Alaska / Abhinav |
| **`agent_memory`** | `alaska.db` | Alaska's *private* self-tasks/notes | Alaska's own working memory (not team-queryable) | `agent-memory` skill |

**DB boundary (verified 2026-06-04):** `entrypoint.sh` runs migrations on **both** files (so each carries the full schema), but **data is isolated by codepath** — V4 code writes `alaska.db`, the PMF store writes `alaska_pmf.db` (override via `PMF_DB_PATH`). The authority boundary is the *writing codepath*, not the schema. *Non-blocking tidy-up: partition migrations per-DB so each file only carries its own tables.*

**Memory is not a data source for live facts.** `MEMORY.md` / `memory/*` hold identity, roster, and history — never answer a user/metric/PMF *fact* question from them; route to the live source per §1.

---

## 5. Boundaries — core Alaska / PMF OS / shared (one system, clean seams)

| Layer | What's in it |
|---|---|
| **Core Alaska** | task graph + PM agents (Daily Pulse, Follow-Through, Risk Radar, Thinker, Meeting Intelligence), Watchers, `user-profile-360`, `amplitude-analyst`, `customerio-ops` |
| **PMF OS** | `alaska_pmf.db`, funnel + 6 metrics, case files, operating queues, interventions, CredGPT observatory, end-cohort memo, the `pmf-cohort-os` skill, the **`/pmf` mode** |
| **Shared (connective tissue)** | the grounding contract (SOUL/AGENT_RULES), this source-router, identity/Slack/roster, the KB, the shared LLM client (`lib/pmf_os/llm.py`) |

**How they connect:** one grounding contract + one router govern both; PMF **reuses** core skills (e.g. `user-profile-360` for raw user data) rather than duplicating; the cross-aware pointer (§1) links the default path to PMF mode. V5 is a *mode within* one Alaska — not a separate system.

---

## 6. Daily cadence

All crons run in UTC; times below are IST (UTC+5:30). The live cron set is canonical in the OpenClaw dashboard; `config/cron-jobs-backup.json` is a periodically-regenerated snapshot (it can drift — trust the dashboard).

| Time (IST) | Agent | Reads / Writes |
|---|---|---|
| every 5 min | Intent Classifier (batch) | classifies channel msgs → `intent_inbox`; acts on gated task path (≥0.85 → task-handler) |
| every 15 min | Reminder Dispatcher | reads `scheduled_actions` → fires due reminders |
| 9:00 AM | Daily Pulse | reads state → posts `#alaska-daily-pulse` |
| 9:05 AM / 1 PM / 6 PM | Follow-Through | DMs overdue owners; escalates |
| 9:30 AM | Risk Radar | posts `#alaska-alerts` (Medium+) |
| 9:30 AM–8:30 PM hourly | Thinker | observes, connects dots, meta-checks |
| 8:30 PM (Mon–Fri) | Pre-Call Brief | builds standup sheet (hybrid feeder) |
| 8:30 PM–1:30 AM /30 min | Meeting Intelligence | Fireflies → `DAILY_STATE.md` + feeds task-handler |
| 11:30 PM | Daily Cost Report | DM to Abhinav |
| Mon 10:30 AM | Sprint Operator | Monday planning helper |
| Fri 6 PM | Doc Keeper — Weekly Digest | weekly digest |

*(PMF crons — daily cohort run, weekly digest, end-cohort memo — are added when the PMF OS activates; see the V5 plan.)*

---

## 7. Where detail lives (pointers, not duplication)

| You want… | Look at… |
|---|---|
| **Which source for a question** | §1 here (the router); runtime: `skills/alaska-core/SKILL.md` + the grounding contract |
| How one agent thinks/acts, extraction + anti-hallucination rules | the relevant `skills/*/SKILL.md` |
| What Alaska can DO with an integration (Plaid / Amplitude / 360 API / …) | the KB: `workspace/knowledge/integrations/*` |
| BON product/system architecture | `workspace/knowledge/architecture.md` |
| BON domain definitions (personas, metrics, lifecycle, PMF contract) | `workspace/knowledge/definitions/*` |
| The build roadmap, phase status, naming | `docs/ROADMAP.md` |
| What changed and why, over time | `workspace/memory/system-evolution.md` |

**Rule of thumb:** a fact about *the outside world or BON's domain* → the KB. A rule about *how Alaska operates or routes* → here (system-level) or a skill (agent-level) — never copied into a KB file.
