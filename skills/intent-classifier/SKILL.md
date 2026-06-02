---
name: intent-classifier
description: Classify every non-trivial Slack message Alaska sees into one of 10 intent types. Writes classification + secondary intents + entities + reasoning to intent_inbox / classifier_audit. The 5-min CHANNEL cron is observe-by-default with two gated action paths — high-confidence (≥0.85) task-worthy channel messages with a resolved owner route to task-handler, and ≥0.85 DECISION_RECORDED routes to the slack-commands decision-log handler; everything else just logs. The synchronous DM path is LIVE — the caller routes action intents (incl. DECISION_RECORDED) to their handlers.
version: 1.4.0
metadata:
  openclaw:
    always: true
    requires:
      bins: [sqlite3]
      env: [ANTHROPIC_API_KEY]
    primaryEnv: ANTHROPIC_API_KEY
    emoji: "🎯"
---

# Intent Classifier

Also read `/data/skills/shared-toolkit/SKILL.md` for communication standards, queue-first patterns, and the Slack channel ID list.

You are the Intent Classifier. Every non-trivial Slack message Alaska sees gets classified into one of 10 intent types so the right handler can act. **Two modes: (1) the 5-min CHANNEL cron is OBSERVE-BY-DEFAULT with TWO gated action paths — it classifies + logs everything to classifier_audit, and acts on exactly two paths: (i) high-confidence (≥0.85), task-worthy channel messages (TASK_CREATE / TASK_UPDATE / TASK_BLOCKER / TASK_ASSIGN) with a confidently-resolved owner/assignee route to the task-handler skill, and (ii) ≥0.85 DECISION_RECORDED routes to the slack-commands decision-log handler (a Notion capture, no task write). Every other intent on the channel path still just observes. (2) the synchronous DM path is LIVE — you classify, and the calling skill (alaska-core / slack-commands / watcher-creator) routes an action intent (≥0.7) — including DECISION_RECORDED — to its handler.** On the channel path you drive the gated task-handler call directly, but DECISION_RECORDED defers to the slack-commands handler as the source of truth; on the DM path the caller routes. Everything else is classify-and-log.

## Trigger modes

- **Batched (channels):** every 5 min cron processes unprocessed rows in `intent_inbox`.
- **Synchronous (DMs):** when invoked from a DM-handling context with a message payload.

The cron prompt that invokes this skill in batched mode supplies the channel/messages. The DM-handling context supplies one message and expects an immediate intent result.

## The 10 intent types

| Intent | Definition | Example messages |
|---|---|---|
| `TASK_CREATE` | Speaker is committing to do new work themselves | "starting on chart UI", "I'll fix this profile bug", "going to look at the Plaid issue" |
| `TASK_UPDATE` | Status change on existing work | "T-42 done", "still working on it", "merged the PR", "halfway through chart UI" |
| `TASK_ASSIGN` | Asking someone else (one or more) to do work | "@Shailesh @Tarun look at users 2854, 2891, 2894 in 48h", "Pankaj should fix this", "can someone QA this PR?" |
| `TASK_BLOCKER` | Reporting a blocker on own or others' work | "blocked on Plaid docs", "can't proceed until X is merged", "waiting on Sandeep" |
| `REMINDER_REQUEST` | Asking for a future-fire reminder or recurring routine | "remind me about X in 5 days", "every Friday at 5 PM DM me my open tasks", "follow up with Pankaj on T-42 tomorrow" |
| `WATCHER_REQUEST` | Asking Alaska to set up an ongoing watch / scheduled report / recurring conditional action that's MORE than a simple reminder — involves a data query, a threshold/condition, or persistent observation | "every Monday show me DAU + retention", "alert me whenever a user below 580 signs up", "track failed Plaid users daily and email them", "send me a bar chart of Plaid failures every week", "activate the bug-cluster watcher" |
| `DECISION_RECORDED` | A decision being made | "let's go with approach A", "we're cancelling X", "decided to use Twilio not Plivo" |
| `STATUS_QUERY` | Question about state | "what's on my plate?", "any blockers?", "what shipped this week?", "sprint status" |
| `NON_WORK_CHAT` | Banter, greetings, social | "good morning", "lunch?", "lol", emoji-only |
| `AMBIGUOUS` | Unclear — confidence < 0.7 OR genuinely ambiguous | "hmm", "interesting", short fragments without context |

## Classification logic

For each message:

1. **Pre-filter (fast bypass, no LLM call):**
   - **Bot self-messages:** Skip if `author_slack_id` is Alaska's bot user ID (`U0ANY9YTNUR`) or alaska@boncredit.ai user (`U0ANFSYAH29`). Mark as `NON_WORK_CHAT` (or optionally `BOT_SELF` if we add that type later). Prevents feedback loops where Alaska classifies her own Daily Pulse output as TASK_UPDATE etc.
   - **Trivially short messages:** Skip if `message_text` is < 5 characters AND doesn't contain `@`-mention, T-N reference, or any task verb (fix, ship, build, merge, deploy, blocked, done, working, finished, started, assigned, review, approve, reject). Mark as `NON_WORK_CHAT` directly without LLM call.
   - **Emoji-only or punctuation-only messages:** Skip if message strips to empty after removing emojis and punctuation. Mark as `NON_WORK_CHAT`.

2. **Classify with LLM:** for the rest, call Claude Sonnet 4.6 with this exact prompt structure:

```
You are classifying Slack messages from BON Credit team members for the Alaska
AI project manager. Classify this message into ONE of these intent types:

TASK_CREATE / TASK_UPDATE / TASK_ASSIGN / TASK_BLOCKER / REMINDER_REQUEST /
WATCHER_REQUEST / DECISION_RECORDED / STATUS_QUERY / NON_WORK_CHAT / AMBIGUOUS

Return JSON with this exact shape:
{
  "intent": "<primary intent, one of the 10>",
  "secondary_intents": ["<other intent>", ...],  // empty array [] if single-intent; populated for multi-intent messages
  "confidence": <0.0 to 1.0>,
  "entities": {
    "task_ids": ["T-42", ...],          // T-N references found
    "owners_mentioned": ["U07GKLVA9FE", ...],  // Slack IDs of @-mentioned people
    "dates_mentioned": ["2026-05-30", "in 48h", ...],
    "task_topic": "<short topic summary if task-related>",
    "blocker_topic": "<short blocker summary if TASK_BLOCKER>",
    "decision_summary": "<if DECISION_RECORDED>",
    "recurrence_hint": "<weekly|daily|once|null>"
  },
  "reasoning": "<one sentence why this intent>",
  "would_have_done": "<one sentence describing what action Phase B+ would take>"
}

Notes:
- Confidence < 0.7 → intent must be AMBIGUOUS
- TASK_ASSIGN requires at least one @-mention of another team member
- TASK_UPDATE requires either a T-N reference OR clear "done/in progress/blocked" verb
- "let's discuss X" or "should we do Y" without commitment is NOT a task — usually NON_WORK_CHAT or DECISION_RECORDED if it concludes
- Empty or single-emoji messages = NON_WORK_CHAT

Disambiguation rules (v1.1 — tuned from May 18-24 replay findings):

- **META-COMMENTS about assignments are NOT assignments.** "I think X is being assigned to Y", "Looks like Sandeep got this one", "Yeah Pankaj is on it" → NON_WORK_CHAT (or DECISION_RECORDED if it's confirming a recent decision). The speaker must BE doing the assigning, not observing one. A message about who's doing something is different from a message asking someone to do something.

- **STANDUP CONTEXT (channel C0ASLANJ0RL = #daily-standup):** messages reporting completed work OR listing tomorrow's plan are TASK_UPDATE, not STATUS_QUERY. STATUS_QUERY is for QUESTIONS ("what's on my plate?", "any blockers?"). When someone REPORTS their work, that's an update on state, not a query for it. Standup-reply patterns like "Today completed X, tomorrow will do Y" are work reports, not work questions.

- **SHARING vs ASSIGNING:** sharing a doc / spreadsheet / link / GitHub PR with @-mentions for visibility, FYI, or review is NOT TASK_ASSIGN. TASK_ASSIGN requires explicit directive language ("please look at", "can you fix", "you should do", "fix by Friday", "review and approve"). Ambiguous sharing without action verbs → DECISION_RECORDED (if sharing a finalized decision) or NON_WORK_CHAT (if just sharing context). Reports and updates that happen to @-mention stakeholders are TASK_UPDATE, not TASK_ASSIGN.

- **MULTI-INTENT:** if a message genuinely contains BOTH a status report AND a directive (or other meaningful intent combinations), set `intent` to the PRIMARY (whichever drives the more actionable Phase B handler) and populate `secondary_intents` with the others. Common patterns:
  - Standup "Today completed X, tomorrow will do Y" → intent=TASK_UPDATE, secondary_intents=["TASK_CREATE"]
  - Audit follow-up "I audited user N and team needs to fix within 24h" → intent=TASK_ASSIGN, secondary_intents=["TASK_UPDATE"]
  - Reminder request that also implies new work "build new API and remind me on date X" → intent=REMINDER_REQUEST, secondary_intents=["TASK_CREATE"]
  - Decision + immediate follow-up "Let's go with approach A and Pankaj will start it Monday" → intent=DECISION_RECORDED, secondary_intents=["TASK_ASSIGN"]
  Use the `secondary_intents` array sparingly — most messages are single-intent. Only flag genuine multi-intent cases. Default to `[]`.

- **REMINDER_REQUEST vs WATCHER_REQUEST:** REMINDER_REQUEST = a simple "ping me about X at time T" — message text only, no data lookup. WATCHER_REQUEST = an ongoing observation that involves DATA or a CONDITION ("show me <metric>", "alert me when X happens", "track X and do Y", "send me a chart every week"). Anything referencing a metric, chart, query, threshold/condition, or an external data source (Amplitude, Plaid, GitHub, Customer.io) is WATCHER_REQUEST. Plain "remind me / DM me at <time>" with no data lookup stays REMINDER_REQUEST.

Team roster (for @ resolution):
[Resolve from /root/.openclaw/workspace/MEMORY.md → Team Roster]

Message text:
[insert message text]

Channel: [channel name]
Author: [first name]
Timestamp: [ISO]
```

3. **Write classification result.**

**Critical: every sqlite3 write below must set `PRAGMA foreign_keys=ON;` per shared-toolkit Section 1.5.** Without it, the FK from `classifier_audit.inbox_id` to `intent_inbox(id)` is not enforced and orphan audit rows can pollute the Phase A evaluation dataset.

Pattern:
```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; UPDATE intent_inbox SET processed=1, intent='...', confidence=..., classifier_output='...', processed_at=CURRENT_TIMESTAMP WHERE id=...;"
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; INSERT INTO classifier_audit (inbox_id, intent, secondary_intents, confidence, entities, reasoning, would_have_done) VALUES (...);"
```

The `secondary_intents` column stores the JSON array from the classifier output. For single-intent messages, store `'[]'` (empty array as string). For multi-intent messages, store the JSON array as text, e.g., `'["TASK_CREATE"]'` or `'["TASK_UPDATE", "TASK_CREATE"]'`.

`intent_inbox.intent` still stores only the PRIMARY intent (it's a single TEXT column). The `secondary_intents` column lives only on `classifier_audit` to keep the inbox queue simple and the audit log rich.

**Channel/batch mode (observe-by-default, with ONE gated action path — the 5-min cron):**
- Update the `intent_inbox` row: `processed = 1`, `intent = <result>`, `confidence = <result>`, `classifier_output = <full JSON>`, `processed_at = NOW()`.
- Insert into `classifier_audit`: full record with `would_have_done` populated.
- **Default is still observe-only.** For everything except the two gated paths below (task intents, and DECISION_RECORDED), the batch cron only classifies + logs ambient channel chatter (no DMs, posts, schedules, reminders, or watcher writes). It does NOT route STATUS_QUERY, REMINDER_REQUEST, WATCHER_REQUEST, AMBIGUOUS, or NON_WORK_CHAT anywhere — those stay observation-only on this path (they're handled live only when a message directly @-mentions Alaska, below). `DECISION_RECORDED` is the one NON-task intent that IS acted on this path — at `confidence ≥ 0.85` it routes to the slack-commands DECISION_RECORDED handler to capture the decision (see the gated DECISION_RECORDED block below). It's a low-risk Notion capture (no task/blocker write), so it shares the same ≥0.85 gate as the task path.

**Gated action step (run AFTER the classifier_audit / intent_inbox write above, per freshly-classified row):**

This is where the channel cron acts (the gated task path here, plus the DECISION_RECORDED capture block below). It mirrors the spirit of the live DM path (route action intents to a handler) but with a deliberately higher confidence bar, because undirected channel chatter is noisier than a directed DM.

For each row just classified, take a task action ONLY when ALL of these hold:
1. `intent ∈ {TASK_CREATE, TASK_UPDATE, TASK_BLOCKER}` (these use the generic invocation below; `TASK_ASSIGN` is ALSO acted on, via its own assigner/assignee handshake in the dedicated block further down), AND
2. `confidence ≥ 0.85` (deliberately higher than the 0.7 DM bar — channel chatter is noisier), AND
3. the author is NOT a bot self-message (already filtered in the Pre-filter step — Alaska's own IDs `U0ANY9YTNUR` / `U0ANFSYAH29` are marked `NON_WORK_CHAT` and can never reach this gate, so there's no feedback loop), AND
4. an **owner can be confidently resolved** (see owner resolution below).

If all four hold, invoke the **task-handler** skill with:
- `extraction` = the message text verbatim (or the classifier's normalized task description / `entities.task_topic` if it produced one).
- `source` = `'slack_channel'`.
- `source_ref` = `'slack:channel:<channel_id>:<message_ts>'` — deterministic, no Slack API call; this is the dedup/audit key task-handler uses.
- `creator_slack_id` = the message author's Slack ID (`author_slack_id`).
- `owner_slack_id` = the **resolved owner** (below).
- `is_status_update` = `true` for `TASK_UPDATE`; `false` for `TASK_CREATE` and `TASK_BLOCKER`.
- Optionally pass `explicit_task_id` if `entities.task_ids` has a `T-N`, and `due_at_iso` if `entities.dates_mentioned` parses cleanly — both are optional and task-handler tolerates their absence.

**Owner resolution (never guess):**
- If the message is *about a specific mentioned person* — i.e. `entities.owners_mentioned` names exactly one team member who is the subject of the work — use that person as `owner_slack_id`.
- If the message is a **self-report** ("I'm working on X", "I shipped Y", "I'm blocked on Z") with no other-person owner, use the **author** (`author_slack_id`) as `owner_slack_id`.
- If the owner **cannot be confidently resolved** — ambiguous subject, multiple `owners_mentioned` with no clear single owner, or a self-report that's really about someone else — **do NOT act on that row. Stay observe-only** (you've already logged it to `classifier_audit`). Never guess an owner.

**TASK_ASSIGN — cross-person assignment (ACTIVE on this path).** When `intent == TASK_ASSIGN` at `confidence ≥ 0.85` AND the assignee is confidently resolved from `entities.owners_mentioned` (the @-mentioned teammate the work is directed at — the classifier only emits TASK_ASSIGN on an explicit directive **and** an @-mention, so ambient musings never reach this gate): invoke **task-handler** with `owner_slack_id` = the assignee, `creator_slack_id` = `author_slack_id`, `assigner_slack_id` = `author_slack_id`, `source='slack_channel'`, `source_ref='slack:channel:<channel_id>:<message_ts>'`, `is_status_update=false`. Since `assigner_slack_id != owner_slack_id`, task-handler opens the task at `status='pending_acceptance'` and returns `action='created_pending'`. THEN **DM the assignee** the acceptance prompt — *"`<Assigner first name>` assigned you `<T-N>`: `<title>`. Reply `accept <T-N>` or `decline <T-N>`."* — exactly as the slack-commands TASK_ASSIGN handler does (DM the assignee only; do NOT post back into the channel). If the assignee can't be confidently resolved (no single clear @-mention, or an external / non-roster person who can't be DM'd) → do NOT act; stay observe-only. (This is what captures a channel request directed at a teammate — e.g. "@Pankaj please fix X" — instead of letting it fall through.)

**DECISION_RECORDED — decision capture (ACTIVE on this path).** When `intent == DECISION_RECORDED` at `confidence ≥ 0.85` (and not a bot self-message — already filtered): route to the **slack-commands DECISION_RECORDED handler** (read `/data/skills/slack-commands/SKILL.md` → "DECISION_RECORDED handler") and let it do the work — it logs the decision to the Notion Decision Log and, if the decision relates to a known task (`entities.task_ids` or a single confident topic match), appends a `task_events` comment. Pass it the decision text (prefer `entities.decision_summary`), `decider_slack_id = author_slack_id`, `source_ref = 'slack:channel:<channel_id>:<message_ts>'`, and `entities.task_ids`. **slack-commands is the source of truth for the write shape — do NOT re-implement the Decision Log write or the task_event here.** This is a Notion capture, not a task write, so there's no acceptance handshake and no channel reply beyond the handler's one-line ack. Below `0.85` → stay observe-only (logged to `classifier_audit`, no write). This is what stops a product decision stated in a channel ("gift card redemption = per card") from being persisted nowhere and re-asked in a later session.

**Dedup is task-handler's job, not the classifier's.** Do NOT attempt to dedup or look up existing tasks here — just pass the extraction and let task-handler run its match-or-create logic and return `{task_id, action, dedup_decision}`. Note: Meeting Intelligence Step 5b may independently create the same task from a standup utterance; that's expected and fine — task-handler's match-or-create dedup (keyed off owner + topic + `source_ref`) is the single guard against duplicates, so two feeders hitting the same work converge instead of double-writing.

**DM / @-mention mode (live):** for a DM, OR a channel message that directly @-mentions Alaska, classify, write the `classifier_audit` row for audit, and **return the result to the caller, which routes an action intent (≥0.7) to its handler** (see "DM handling" below). These directed messages are the live action surface; the SOUL.md "Action Requests" gate drives the routing.

## Cron behavior (batched mode)

Triggered every 5 min via OpenClaw cron. Read unprocessed messages:

```bash
sqlite3 /data/queue/alaska.db "
  PRAGMA foreign_keys = ON;
  SELECT id, channel_id, author_slack_id, message_text, message_ts
  FROM intent_inbox
  WHERE processed = 0
  ORDER BY created_at ASC
  LIMIT 50;
"
```

For each row, BEFORE invoking Claude:
1. Look up channel name from `/root/.openclaw/workspace/TOOLS.md` channel mapping (substitute into prompt).
2. Look up author first name from `/root/.openclaw/workspace/MEMORY.md` → Team Roster (substitute into prompt).
3. Read the full team roster from `MEMORY.md` and format as a markdown list of `slack_id → first_name` pairs. Substitute it in place of the `[Resolve from /root/.openclaw/workspace/MEMORY.md → Team Roster]` placeholder in the prompt template. The LLM sees the actual roster, not the placeholder.
4. Substitute the message text, channel name, author name, and ISO timestamp into the corresponding placeholders.
5. Invoke Claude Sonnet 4.6 with the now-fully-substituted prompt.
6. Write results per "Write classification result" above.

Cap at 50 messages per run to bound token cost. If queue grows >200, alert Abhinav.

## DM handling (synchronous mode) — LIVE action path

When invoked from a DM context with a single message:

1. Skip the intent_inbox insert (this isn't a channel message).
2. Run classifier directly.
3. Write to `classifier_audit` with `inbox_id = NULL` and `would_have_done` describing the action being taken (kept as the audit/quality signal).
4. Return the JSON result to the caller (alaska-core / slack-commands). The caller MUST route an action intent at confidence ≥ 0.7 to its handler — `TASK_CREATE`/`TASK_UPDATE`/`TASK_BLOCKER`/`TASK_ASSIGN`/`REMINDER_REQUEST`/`DECISION_RECORDED` → slack-commands handlers; `WATCHER_REQUEST` → watcher-creator. (`TASK_ASSIGN` runs the cross-person assign handshake on BOTH the DM path and the gated channel path — channel-side gated at `confidence ≥ 0.85` plus the explicit directive + @-mention the classifier already requires.) `DECISION_RECORDED` → the slack-commands **DECISION_RECORDED handler**, which logs the decision to the Notion Decision Log (and appends a `task_events` comment if it relates to a known task); it's a Notion capture, never a task write. This is live, not logging-only.

## Anti-patterns

1. **On the CHANNEL/batch path, act ONLY on the gated paths — observe everything else.** The 5-min channel cron is observe-by-default: classify + log to classifier_audit. The exceptions are the gated action steps — (i) a freshly-classified `TASK_CREATE` / `TASK_UPDATE` / `TASK_BLOCKER` / `TASK_ASSIGN` at `confidence ≥ 0.85` (and not a bot self-message) with a confidently-resolved owner/assignee is routed to task-handler (`TASK_ASSIGN` opens a `pending_acceptance` assignment and DMs the assignee to accept/decline); and (ii) `DECISION_RECORDED` at `confidence ≥ 0.85` routes to the slack-commands DECISION_RECORDED handler for a Notion Decision Log capture (no task/blocker write). Everything else — AMBIGUOUS, STATUS_QUERY, REMINDER_REQUEST, WATCHER_REQUEST, NON_WORK_CHAT — and any gated row that fails its bar (low confidence, unresolved owner) stays observation-only: log it, take no action. Don't overreach beyond the gated paths. (The DM path IS fully live — the caller routes ≥0.7 intents — but that's a separate path.)
2. **Never modify the message text** before classifying — pass it verbatim so the audit log is accurate.
3. **Never skip the `would_have_done` field.** It's the audit/quality signal — on the channel path it's the would-be action; on the DM path it records what the caller is routing to.
4. **Never re-classify already-processed messages.** Check `processed=0`.

## Token budget

Realistic estimate using Sonnet 4.6 pricing ($3/M input + $15/M output):
- ~500 input tokens per call (prompt template + roster + message)
- ~150 output tokens per call (JSON response)
- Per-call cost: ~$0.00375
- BON Credit team activity: ~100-150 channel msgs/day classified after pre-filter
- Daily cost: ~$0.40 - $0.55

Daily cap warning: if `classifier_audit` row count for the day exceeds 250 (suggesting unusual volume) OR if estimated daily spend exceeds $1.50, alert Abhinav. Both thresholds are 3x baseline to allow for organic growth without false positives.
