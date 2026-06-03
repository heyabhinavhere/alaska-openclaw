# Alaska Grounding & Memory Discipline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Alaska *retrieve* facts from the sources she already has (KB, task graph, roster, Decision Log, system clock, live APIs) and *capture* durable facts when they flow by — instead of fabricating answers from the model's memory.

**Architecture:** Two structural reflexes, installed as prompt contracts in the paths that matter. **Reflex 1 (Ground-before-you-speak)** goes in `SOUL.md` (the synchronous DM/@-mention path) and `AGENT_RULES.md` (the cron agents), with a compact **KB index** in `MEMORY.md` (auto-injected everywhere). **Reflex 2 (Capture-when-it-flows)** routes durable facts to `agent_memory` (operational) or a propose-to-Abhinav KB suggestion (domain-canon). A small **stale/missing-data** cluster hardens the no-fresh-data case. No new code modules — this is prompt engineering plus drafted KB proposals Abhinav applies himself.

**Tech Stack:** OpenClaw prompt files (Markdown), the live cron dashboard (for fat-prompt reinforcements), `agent_memory` (migration 0006), the BON KB (`workspace/knowledge/`, Abhinav-owned).

---

## Problem (why this plan exists)

Across ~8 observed failures, one principle is being violated: **Alaska generates facts she could have looked up.** The sources exist; the discipline to consult them does not.

| Observed failure | Source that existed | Reflex broken |
|---|---|---|
| A2P/Twilio: fabricated URLs, consent flow, **non-compliant** sample messages | `knowledge/integrations/twilio.md` (already documents the A2P blocker, OTP-separate-path, owners) | **R1 retrieve** — and worse, fabricated instead of admitting |
| "Zero git activity" while Sandeep pushed 9 commits (develop) | live GitHub API | **R1 retrieve** (inferred from stale state / wrong branch) |
| "videos/images → Pankaj" (should be Samder) | roster role map (marketing = Samder) | **R1 retrieve** (didn't apply roles) |
| Demo Day "Fri June 6" (Sat); W-1 "Tuesday June 3" (Wed) | system clock (`date`) | **R1 retrieve** (mental date math) |
| "I don't have the 10 AI-testing user IDs" | nothing — never captured | **R2 capture** (honest, but amnesiac) |
| Duplicate June-1 standup re-sent June 2; weekend staleness noise | — | Stale/missing-data handling |

**Root cause (technical):** the DM session preloads only `SOUL.md` + `MEMORY.md` + `TOOLS.md` + `AGENTS.md` — **none** of the stores (KB, task graph, agent_memory, Decision Log) or skills. So unless SOUL explicitly says "go retrieve from X," Alaska answers from parametric memory = fabrication by default. We built memory **stores** but never the memory **discipline**, and the KB in particular was wired "for watchers," never for Alaska's own conversational use.

**Design principle being installed:** *Pull, don't generate. Capture, don't forget. When you can't pull, say so — never fabricate.* Enforced structurally (a contract + a forcing self-check), because prose ("don't hallucinate") has already failed and recurred.

---

## File structure (what changes, and why there)

| File | Loaded by | Responsibility for this plan | Deploy |
|---|---|---|---|
| `workspace/SOUL.md` | DM / @-mention session | Reflex 1 + Reflex 2 contract, in Alaska's first-person voice | auto (CONFIG refresh on deploy) |
| `workspace/AGENT_RULES.md` | every cron agent (mandatory read #1) | Reflex 1 contract for the scheduled agents | auto (CONFIG refresh) |
| `workspace/MEMORY.md` | DM **and** cron sessions (auto-injected) | the compact **KB index** (what exists + how to find it) | auto (CONFIG refresh) |
| Live cron prompts (dashboard) for **W-1/Daily-Pulse**, **Meeting Intelligence**, **Pre-Call Brief** | the cron engine (fat prompt overrides SKILL) | one-line date-anchoring + grounding reinforcement (fat prompts override AGENT_RULES) | **manual (dashboard)** + snapshot in `config/cron-jobs-backup.json` |
| `workspace/knowledge/integrations/twilio.md` | KB readers | A2P sample-content rules + consent specifics + ToS/Privacy URL slots | **Abhinav-only** — this plan *drafts* a proposal; Abhinav pastes |
| `skills/meeting-intelligence/SKILL.md` | MI cron | Fireflies-no-show detection (Cluster 3) | auto |
| `skills/pre-call-brief/SKILL.md` | Pre-Call Brief cron | no-duplicate / no-new-data guard (Cluster 3) | auto |
| `skills/daily-pulse/SKILL.md` | Daily Pulse cron | weekend-aware staleness (Cluster 3) | auto |

**Hard boundary:** This plan never edits KB content — `workspace/knowledge/` is Abhinav-owned. Tasks that improve the KB produce a *drafted proposal* for Abhinav to paste.

**Verification note:** Alaska is prompt-driven; these changes can't be unit-tested. Each task's verification is (a) a `grep`/`python3 -c json.load` that the text landed and parses, and (b) a **live-observation test** — re-run the real scenario and confirm the behavior changed. Live tests are run by Abhinav/Alaska in prod after deploy.

---

# Phase 1 — Reflex 1: The Grounding Contract

The centerpiece. One canonical contract, placed in the two operative paths, plus a KB index Alaska can navigate.

### Task 1.1: Add the compact KB index to MEMORY.md

**Files:**
- Modify: `workspace/MEMORY.md` (in the "How my memory is organized" section, after the table)

**Why:** MEMORY.md is auto-injected into **both** DM and cron sessions, so the index reaches every path. It must be compact (MEMORY.md has a ~20k-char cap) — names + one-line "what's in it" + the navigation rule. The full map already lives in `knowledge/README.md`; this is the pointer so Alaska knows the KB exists and which file to open.

- [ ] **Step 1: Insert the KB index block** immediately after the memory-organization table in `MEMORY.md`:

```markdown
### My knowledge base (read it before answering domain questions)

`workspace/knowledge/` is **my** domain knowledge — not just a watcher input. For any question about how BON works, I open the relevant file and quote it; I do not answer BON-domain questions from generic knowledge. Full map: `workspace/knowledge/README.md`.

- **Integrations** — `knowledge/integrations/<system>.md`: `plaid`, `spinwheel`, `array`, `amplitude`, `customerio`, `twilio` (SMS/WhatsApp + **A2P 10DLC**), `notion`, `slack`, `github`, `user-profile-api`, plus `moneylionbyengine` (in progress).
- **Definitions** — `knowledge/definitions/`: `personas`, `metrics`, `lifecycle-events`.
- **Playbooks** — `knowledge/playbooks/`: `common-queries`, `failure-modes`.

If the KB file doesn't contain the answer, I say so (and propose adding it) — I never invent it. The KB is Abhinav-owned; I read it, I don't edit it.
```

- [ ] **Step 2: Verify it landed and MEMORY.md is still lean**

```bash
grep -n "My knowledge base" workspace/MEMORY.md
wc -c workspace/MEMORY.md   # expect well under 20000
```
Expected: the heading matches; char count < 20000.

- [ ] **Step 3: Commit**

```bash
git add workspace/MEMORY.md
git commit -m "feat(memory): add KB index so Alaska knows her knowledge base exists + to consult it"
```

---

### Task 1.2: Add the Grounding Contract to SOUL.md (DM path)

**Files:**
- Modify: `workspace/SOUL.md` (new section, placed right after the "Action Requests" / reference-handling area so it sits with the other conversational-discipline rules)

**Why:** SOUL.md is the only behavioral file the DM session loads. The A2P / wrong-owner / date failures all happened in DM or DM-like contexts. This is the contract that makes Alaska retrieve.

- [ ] **Step 1: Insert the Grounding Contract** into `SOUL.md`:

```markdown
## Ground before you speak — pull facts, never generate them

My value is being RIGHT. A right answer is *retrieved*, not *composed*. Before I state or act on any fact, I pull it from its source THIS turn. If the source doesn't have it, I say so or go find out. I never invent a fact that has a lookup.

**"A fact" = anything with a source of truth:** a URL, a user/account ID, a date or day-of-week, who-owns-X, the status of a task/blocker, a metric or activity figure, a compliance/policy detail, an integration behavior, a file path or line.

**Where each fact lives — retrieve from here:**

| The question is about… | I pull from… |
|---|---|
| A BON system / integration / compliance (Twilio/**A2P**, Plaid, Amplitude, Customer.io, Array, Spinwheel, app architecture, personas, metrics, lifecycle events) | the **KB** — `workspace/knowledge/` (index in `MEMORY.md`; open `integrations/<system>.md` / `definitions/<x>.md` / `playbooks/<x>.md` and quote it) |
| Who owns / should do something | the **roster** (`MEMORY.md` → Team) by **role** — marketing/partnerships/investors → **Samder**; finance/credit/audits → **Darwin**; product/design → Abhinav; engineering → the relevant engineer — cross-checked with the task graph |
| Status of work / a blocker | the **task graph** (`tasks`/`blockers`) + `DAILY_STATE.md` |
| Was X decided | the **Decision Log** + `DAILY_STATE.md` Active Decisions |
| Today's date, a day-of-week, or a relative date ("this Friday") | the **system clock** — run `date` and use its output; for relative dates compute in `python3` from the real today. **Never do calendar math in my head.** |
| Live activity / metrics (git commits, DAU, deliverability) | the **live API** (GitHub events **across branches**, Amplitude, Customer.io) — never infer activity from a stale `DAILY_STATE.md` |
| Something I was asked to remember | my **agent-memory** (`recall`) |

**Never fabricate.** No invented URLs (e.g. `boncredit.co/...` unless it's documented), no invented IDs, no guessed dates, no assumed owners, no made-up compliance language. **"I don't have that — want me to find out?" beats a confident wrong answer every time.** A confident wrong compliance line or a wrong date is worse than a missing one.

**Pre-send self-check (every factual answer):** *Did I state any fact above that I did NOT pull from its source this turn? Did I invent a URL, an ID, a date, an owner, or a compliance line?* If yes — pull it now, or replace it with "I don't have that." This check is not optional.
```

- [ ] **Step 2: Verify it landed**

```bash
grep -n "Ground before you speak" workspace/SOUL.md
grep -c "Never fabricate" workspace/SOUL.md   # expect >= 1
```

- [ ] **Step 3: Commit**

```bash
git add workspace/SOUL.md
git commit -m "feat(soul): grounding contract — retrieve from source, never fabricate, self-check"
```

---

### Task 1.3: Add the Grounding Contract to AGENT_RULES.md (cron path)

**Files:**
- Modify: `workspace/AGENT_RULES.md` (new top-level section)

**Why:** Cron agents (Daily Pulse, Follow-Through, Risk Radar, Thinker, MI, Pre-Call Brief) read `AGENT_RULES.md` as mandatory read #1, but do NOT load SOUL. The git-zero and date failures came from cron agents. Same contract, framed for the scheduled agents.

- [ ] **Step 1: Insert the contract** into `AGENT_RULES.md` (reuse Task 1.2's table verbatim — do not paraphrase; identical routing prevents drift), under a heading:

```markdown
## Grounding (all agents): pull facts, never generate them

Every scheduled agent retrieves facts from their source before stating them. This is the same contract Alaska follows in DMs (`SOUL.md` → "Ground before you speak"). The rules below are binding for cron runs too.

- **Dates/days:** run `date` for today's date and day-of-week; compute relative dates in `python3`. Never write a day-of-week from memory. (A header like "Tuesday, June 3" must come from `date`, which would have caught June 3 = Wednesday.)
- **Git/metric activity:** query the live API (GitHub events **across all branches**, Amplitude, Customer.io). Never report "zero git activity" or any activity figure inferred from a stale `DAILY_STATE.md` — pull it live or don't claim it.
- **Ownership:** resolve owners by **role** from the roster (marketing → Samder, finance/credit → Darwin, engineering → the relevant engineer), not by proximity in the text.
- **Domain facts:** open the relevant `workspace/knowledge/` file; never paraphrase BON system behavior from memory.
- **Never fabricate** a URL, ID, date, owner, metric, or compliance line. "Not available / couldn't pull it" is the correct output when the source is silent.
```

- [ ] **Step 2: Verify it landed**

```bash
grep -n "Grounding (all agents)" workspace/AGENT_RULES.md
```

- [ ] **Step 3: Commit**

```bash
git add workspace/AGENT_RULES.md
git commit -m "feat(agent-rules): grounding contract for scheduled agents (dates, git, ownership, domain)"
```

---

### Task 1.4: Reinforce date-anchoring in the date-emitting cron prompts (dashboard + snapshot)

**Files:**
- Modify (snapshot): `config/cron-jobs-backup.json` — the **Daily Pulse**, **W-1 watcher**, **Meeting Intelligence**, and **Pre-Call Brief** jobs' `payload.message`
- Modify (LIVE, manual): the same jobs on the OpenClaw dashboard

**Why:** Cron prompts are **fat prompts that override** AGENT_RULES (the recurring lesson — MI dormancy, classifier TASK_ASSIGN, Thinker boundary). The date failures came from W-1/Daily-Pulse (the "Tuesday June 3" header) and MI (mapping "Friday" → wrong date). A one-line reinforcement in those specific prompts ensures the date rule actually fires.

- [ ] **Step 1: Add this exact line** near the top of each of those four jobs' `payload.message` (after their MANDATORY READS / before they compose any dated output):

```
DATE DISCIPLINE: before writing ANY date or day-of-week, run `date` (e.g. `date +"%A, %B %d, %Y"`) and use its output verbatim; for relative dates ("this Friday", "Monday after X") compute with python3 from the real today. NEVER compute a day-of-week or date in your head — that has produced wrong headers (e.g. "Tuesday June 3" when June 3 was Wednesday).
```

- [ ] **Step 2: Verify the snapshot still parses + carries the line**

```bash
python3 -c "import json; jobs=json.load(open('config/cron-jobs-backup.json'))['jobs']; print('valid;', sum('DATE DISCIPLINE' in (j.get('payload',{}).get('message','')) for j in jobs), 'jobs carry it')"
```
Expected: `valid; 4 jobs carry it`.

- [ ] **Step 3: Commit the snapshot**

```bash
git add config/cron-jobs-backup.json
git commit -m "fix(cron): add DATE DISCIPLINE line to Daily Pulse / W-1 / MI / Pre-Call Brief prompts"
```

- [ ] **Step 4 (Abhinav, dashboard — ops handoff):** apply the same `DATE DISCIPLINE` line to the four LIVE cron prompts on the OpenClaw dashboard (the snapshot is not auto-applied). Without this the live behavior does not change.

---

# Phase 2 — Reflex 2: Capture discipline

So facts like the 10 test user IDs are written down when they flow by, and recallable later.

### Task 2.1: Add the Capture Reflex to SOUL.md

**Files:**
- Modify: `workspace/SOUL.md` (immediately after the Grounding Contract from Task 1.2)

**Why:** The 10-user-IDs failure was a capture gap — the info flowed by weeks ago and landed in no recall store. `agent_memory` (migration 0006, the store we just built) is the home for operational reference facts; KB-canon facts get proposed to Abhinav.

- [ ] **Step 1: Insert the Capture Reflex** into `SOUL.md`:

```markdown
## Capture durable facts (so future-me can recall them)

When a reusable fact flows past me that someone will plausibly ask about again — a set of IDs ("the 10 AI-testing user IDs are …"), a config value, a live URL, a domain rule — I write it down so future-me retrieves it instead of saying "I don't have that":

- **Operational / reference fact** (recall on cue) → the `agent-memory` skill → `remember` it as a `reference` with a recall cue. Example: someone states this week's test user IDs → I `remember` them with cue `"AI testing user IDs"`, so the next "which users are we testing?" is answered, not deflected.
- **Team-canonical, durable domain fact** (how BON *works*) → that belongs in the KB, which **only Abhinav edits** → I **propose it to Abhinav** ("worth adding to the KB?"), I do not write it myself.

I capture only durable, reusable facts — not chatter. When I retrieve from the KB and find a real gap (e.g. the live ToS/Privacy URLs aren't documented), I flag that gap to Abhinav rather than inventing a value.
```

- [ ] **Step 2: Verify it landed**

```bash
grep -n "Capture durable facts" workspace/SOUL.md
```

- [ ] **Step 3: Commit**

```bash
git add workspace/SOUL.md
git commit -m "feat(soul): capture reflex — durable facts to agent_memory; KB-canon facts proposed to Abhinav"
```

---

# Phase 3 — KB completeness proposals (Abhinav applies)

The A2P episode exposed real KB gaps. **This phase produces a drafted proposal only** — Abhinav pastes into `twilio.md` (KB is Abhinav-owned).

### Task 3.1: Draft the twilio.md A2P additions

**Files:**
- Create: `docs/superpowers/research/2026-06-03-twilio-a2p-kb-proposal.md` (a drafted proposal, NOT a KB edit)

**Why:** `twilio.md` already covers the A2P *blocker* and OTP-separate-path, but is missing (a) the sample-content rules that make a campaign compliant, and (b) the live ToS/Privacy URLs. Without these, even a grounded Alaska answers "I don't have that" for the URLs — which is correct but unhelpful. Abhinav supplies the URLs (only he knows them); the content rules are drafted from the A2P episode.

- [ ] **Step 1: Write the proposal file** with this content:

```markdown
# Proposal: A2P content rules + consent specifics for knowledge/integrations/twilio.md

Drafted for Abhinav to review and paste into the KB (Alaska does not edit the KB).
Context: during A2P registration, Alaska fabricated sample messages containing credit-score
and billing content (SHAFT-adjacent) and invented ToS/Privacy URLs.

## Add a section "A2P campaign content rules (when registering / drafting samples)"

- Use case: **Account Notification** (transactional), NOT marketing.
- **Forbidden in sample messages** (SHAFT-adjacent / will fail review): credit-score numbers,
  loan/credit offers, payment amounts, billing/collections language, anything promotional.
- **Allowed**: account-status, security/login verification (note: OTP itself runs on the
  separate sending path), profile-update confirmations, linked-account re-auth, "report ready"
  (no score values).
- Every sample must include: the brand name "BON Credit", variable content in [square brackets],
  a real link on the registered domain, and an opt-out ("Reply STOP").

## Add to the consent section

- Opt-in mechanism: phone + 6-digit OTP is the ONLY auth method → every user has a verified,
  consented number. Onboarding includes `credit_report_disclaimer_accepted` (the consent moment).
- SMS frequency cap (per Customer.io guardrails): document the actual cap.
- **[ABHINAV TO FILL]** the live, correct URLs — these are NOT currently documented anywhere
  and Alaska must not invent them:
  - Terms of Service URL: __________
  - Privacy Policy URL: __________
  - Marketing/registered domain used in SMS links: __________
  - Confirm the ToS/Privacy pages explicitly contain SMS-consent language (carriers check this).
```

- [ ] **Step 2: Verify the proposal file exists**

```bash
test -f docs/superpowers/research/2026-06-03-twilio-a2p-kb-proposal.md && echo "proposal drafted"
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/research/2026-06-03-twilio-a2p-kb-proposal.md
git commit -m "docs: draft A2P content-rules + consent KB proposal for twilio.md (Abhinav to apply)"
```

- [ ] **Step 4 (Abhinav):** review, fill the URL slots, and paste the approved content into `workspace/knowledge/integrations/twilio.md`.

---

# Phase 4 — Cluster 3: stale / missing-data handling

Distinct from the reflexes; these guard the "no fresh data" case. Lower priority than 1–3.

### Task 4.1: Fireflies-no-show detection in Meeting Intelligence

**Files:**
- Modify: `skills/meeting-intelligence/SKILL.md` (add a "no-show" check at the start of the run)

**Why:** Fireflies missed the June 1 call → no transcript → downstream produced stale duplicates with no flag. MI should detect "a call was expected in this window but no transcript exists" and surface it.

- [ ] **Step 1: Add this step** to `meeting-intelligence/SKILL.md` near the top of the processing flow:

```markdown
### Step 0b: No-show / no-transcript guard

If this run finds NO new Fireflies transcript in the expected window (and the team standup is a daily ~9 PM IST fixture), do NOT silently produce or refresh standup output from stale state. Instead:
- DM Abhinav once: "No Fireflies transcript found for the [date] call. Either the call didn't happen or Fireflies didn't join. DAILY_STATE.md was NOT refreshed — want me to flag the team?"
- Do not re-write DAILY_STATE.md, and do not let Pre-Call Brief re-emit yesterday's sheet as if it were today's (see pre-call-brief no-duplicate guard).
```

- [ ] **Step 2: Verify**

```bash
grep -n "No-show / no-transcript guard" skills/meeting-intelligence/SKILL.md
```

- [ ] **Step 3: Commit**

```bash
git add skills/meeting-intelligence/SKILL.md
git commit -m "fix(mi): Fireflies no-show guard — flag a missed call instead of producing stale output"
```

---

### Task 4.2: No-duplicate / no-new-data guard in Pre-Call Brief

**Files:**
- Modify: `skills/pre-call-brief/SKILL.md`

**Why:** On June 2 the standup sheet was a verbatim copy of June 1 (no new call data). The sheet must reflect the real day and not silently duplicate.

- [ ] **Step 1: Add this guard** to `pre-call-brief/SKILL.md`:

```markdown
### Freshness guard (before posting the sheet)

Stamp the sheet with today's date from `date` (never a remembered date). If the underlying state (DAILY_STATE.md + the task graph) has NOT changed since the last sheet — e.g. no call was processed (a Fireflies no-show) — do NOT re-post an identical sheet. Instead post a short note: "No new call data since [last-update date] — yesterday's items still stand. Reply with today's update." This prevents the team from receiving the same sheet two days running.
```

- [ ] **Step 2: Verify**

```bash
grep -n "Freshness guard" skills/pre-call-brief/SKILL.md
```

- [ ] **Step 3: Commit**

```bash
git add skills/pre-call-brief/SKILL.md
git commit -m "fix(pre-call-brief): freshness guard — date-stamp + no identical re-post on stale data"
```

---

### Task 4.3: Weekend-aware staleness in Daily Pulse

**Files:**
- Modify: `skills/daily-pulse/SKILL.md` (the staleness-gate logic added in FU3)

**Why:** The "⚠️ State data is ~N days old" warning fired over the May 30–31 weekend, where low activity is expected — it read as an alarm for a non-issue.

- [ ] **Step 1: Adjust the staleness gate** in `daily-pulse/SKILL.md`:

```markdown
**Weekend-aware staleness:** compute the staleness window using `date` for today and the last-update day. If the days in between are only weekend days (Sat/Sun) with no scheduled call, treat the staleness as EXPECTED and either omit the warning or soften it to one line: "Quiet weekend — last call data [date]." Only surface the prominent ⚠️ warning when a *weekday* with an expected call passed without a DAILY_STATE refresh. (BON does sometimes meet on weekends — so base "expected call" on whether a transcript/standup actually occurred, not purely on the calendar.)
```

- [ ] **Step 2: Verify**

```bash
grep -n "Weekend-aware staleness" skills/daily-pulse/SKILL.md
```

- [ ] **Step 3: Commit**

```bash
git add skills/daily-pulse/SKILL.md
git commit -m "fix(daily-pulse): weekend-aware staleness — don't alarm on expected quiet weekends"
```

---

# Verification Plan (live, post-deploy)

Prompt fixes are proven by observation, not unit tests. After each phase deploys (and the Phase 1.4 / KB dashboard+paste steps are applied), run the real scenarios:

### Phase 1 (grounding) — the headline proof
1. **A2P re-test:** DM Alaska an A2P question ("help me with the A2P campaign description / sample messages"). PASS = she opens `knowledge/integrations/twilio.md`, reflects its facts (SMS A2P-blocked, OTP separate path, Abhinav/Nilesh own it), and does **not** invent URLs or include credit-score/billing sample content. If she lacks the ToS URLs, she says so (until Phase 3 lands them).
2. **Date re-test:** trigger W-1 / Daily Pulse; the header day-of-week matches the real calendar (cross-check with `date`). Ask "what's the date this Friday?" — she runs `date`/python, not mental math.
3. **Owner re-test:** mention a marketing deliverable ("we need product videos for marketing"); she attributes it to **Samder**, not an engineer.
4. **Git re-test:** when there are commits on a non-default branch, Daily Pulse/Thinker reflect them (no false "zero git activity").

### Phase 2 (capture)
5. State a fact in a DM ("this week's AI-testing user IDs are A, B, C…"). Later, in a fresh DM, ask "which users are we testing?" — PASS = she `recall`s and answers, instead of "I don't have that."

### Phase 4 (stale-data)
6. Simulate / observe a Fireflies no-show → Abhinav gets the no-show DM; Pre-Call Brief does not re-post an identical sheet.
7. Next weekend → no alarming staleness warning in Daily Pulse.

### What "done" looks like
- Three consecutive days with **no fabricated fact** observed (URL, ID, date, owner, compliance line).
- The A2P scenario is grounded in `twilio.md`.
- Dates in scheduled output match the real calendar.
- A captured fact is successfully recalled in a later session.

---

# Rollout Order

1. **Phase 1 first** (grounding) — biggest leverage, fixes A2P/dates/owner/git, and it's actively biting the live A2P registration. Tasks 1.1→1.3 auto-deploy on merge; **Task 1.4 needs the dashboard step** to take effect on the date-emitting crons.
2. **Phase 2** (capture) — small, complements Phase 1; makes the KB and agent_memory actually accumulate value.
3. **Phase 3** (KB proposal) — Abhinav applies; unblocks fully-grounded A2P answers (the URLs).
4. **Phase 4** (stale-data) — guards; lowest urgency.

One PR per phase (consistent with the project's phase-by-phase review rule). Phase 1 is the critical one to land and verify before the others.

---

# Out of scope (deferred)

- A full **V5 "KB self-maintenance" agent** (weekly scan → diff → propose KB updates). Phase 2's "propose to Abhinav" reflex is the manual, lightweight precursor; the automated agent stays in the V5 backlog.
- **Phase E** (graph → source of truth) — reduces DAILY_STATE staleness structurally, but is its own workstream; Cluster 3 guards are worth having regardless.
- Rewriting cron prompts to "defer to SKILL" wholesale (a good structural direction, but a separate cleanup; Task 1.4 only adds a targeted line).

---

# Boundaries & risks

- **KB is Abhinav-owned.** No task here edits `workspace/knowledge/`. Phase 3 drafts; Abhinav applies.
- **Cron fat-prompt override.** Tasks 1.1–1.3 + Phase 2/4 auto-deploy (CONFIG + skills), but the date-emitting **cron prompts must be updated on the dashboard** (Task 1.4 Step 4) or the live date behavior won't change. This is the same gotcha as the classifier/Thinker fixes.
- **Risk: contract bloat in SOUL.** SOUL is already long; two new sections add length. Mitigation: the routing table is compact, the KB index lives in MEMORY (not SOUL), and the contract replaces vague anti-hallucination prose rather than stacking on it. If SOUL length becomes a problem, that's a separate prioritization pass.
- **Risk: over-retrieval latency.** Telling Alaska to open KB files / run `date` adds steps to DM replies. Acceptable — correctness > a few seconds. The self-check is scoped to *factual* answers, not casual chat.
