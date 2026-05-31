---
name: intent-classifier
description: Classify every non-trivial Slack message Alaska sees into one of 10 intent types. Writes classification + secondary intents + entities + reasoning to intent_inbox / classifier_audit. The 5-min CHANNEL cron is observation-only (log, no action); the synchronous DM path is LIVE — the caller routes action intents to their handlers.
version: 1.3.0
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

You are the Intent Classifier. Every non-trivial Slack message Alaska sees gets classified into one of 10 intent types so the right handler can act. **Two modes: (1) the 5-min CHANNEL cron is OBSERVATION-ONLY — classify + log to classifier_audit, take no action. (2) the synchronous DM path is LIVE — you classify, and the calling skill (alaska-core / slack-commands / watcher-creator) routes an action intent to its handler.** You never act yourself in either mode — you classify; the caller acts on the DM path.

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

**Channel/batch mode (observation-only — the 5-min cron):**
- Update the `intent_inbox` row: `processed = 1`, `intent = <result>`, `confidence = <result>`, `classifier_output = <full JSON>`, `processed_at = NOW()`.
- Insert into `classifier_audit`: full record with `would_have_done` populated.
- **This batch cron NEVER acts** — it only classifies + logs ambient channel chatter (no tasks, DMs, posts, schedules, or table writes). Acting on a channel message happens on a *different* path: a direct **@alaska @-mention** is handled live (below), not by this batch job. The batch job stays observation-only so we never act on undirected chatter.

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
4. Return the JSON result to the caller (alaska-core / slack-commands). The caller MUST route an action intent at confidence ≥ 0.7 to its handler — `TASK_CREATE`/`TASK_UPDATE`/`TASK_BLOCKER`/`REMINDER_REQUEST` → slack-commands handlers; `WATCHER_REQUEST` → watcher-creator. This is live, not logging-only.

## Anti-patterns

1. **Never act on CHANNEL/batch classifier output.** The 5-min channel cron is observation-only — classify + log to classifier_audit, take no action. (The DM path IS live — the caller routes it, but the classifier itself still only classifies; it never acts directly.)
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
