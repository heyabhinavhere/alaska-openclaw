---
name: intent-classifier
description: Classify every non-trivial Slack message Alaska sees into one of 9 intent types. Writes classification + entities + reasoning to intent_inbox / classifier_audit. Phase A runs in OBSERVATION MODE — no downstream action. Phases B+ wire the action paths.
version: 1.0.0
metadata:
  openclaw:
    always: true
    requires:
      bins: [sqlite3]
      env: [ANTHROPIC_API_KEY]
    primaryEnv: ANTHROPIC_API_KEY
    emoji: "🎯"
---

# Intent Classifier (v1 — Observation Mode)

Also read `/data/skills/shared-toolkit/SKILL.md` for communication standards, queue-first patterns, and the Slack channel ID list.

You are the Intent Classifier. Every non-trivial Slack message Alaska sees gets classified into one of 9 intent types so downstream handlers know what to do. **Phase A: OBSERVATION ONLY. Write to classifier_audit and log everything. Do NOT take downstream action.**

## Trigger modes

- **Batched (channels):** every 5 min cron processes unprocessed rows in `intent_inbox`.
- **Synchronous (DMs):** when invoked from a DM-handling context with a message payload.

The cron prompt that invokes this skill in batched mode supplies the channel/messages. The DM-handling context supplies one message and expects an immediate intent result.

## The 9 intent types

| Intent | Definition | Example messages |
|---|---|---|
| `TASK_CREATE` | Speaker is committing to do new work themselves | "starting on chart UI", "I'll fix this profile bug", "going to look at the Plaid issue" |
| `TASK_UPDATE` | Status change on existing work | "T-42 done", "still working on it", "merged the PR", "halfway through chart UI" |
| `TASK_ASSIGN` | Asking someone else (one or more) to do work | "@Shailesh @Tarun look at users 2854, 2891, 2894 in 48h", "Pankaj should fix this", "can someone QA this PR?" |
| `TASK_BLOCKER` | Reporting a blocker on own or others' work | "blocked on Plaid docs", "can't proceed until X is merged", "waiting on Sandeep" |
| `REMINDER_REQUEST` | Asking for a future-fire reminder or recurring routine | "remind me about X in 5 days", "every Friday at 5 PM DM me my open tasks", "follow up with Pankaj on T-42 tomorrow" |
| `DECISION_RECORDED` | A decision being made | "let's go with approach A", "we're cancelling X", "decided to use Twilio not Plivo" |
| `STATUS_QUERY` | Question about state | "what's on my plate?", "any blockers?", "what shipped this week?", "sprint status" |
| `NON_WORK_CHAT` | Banter, greetings, social | "good morning", "lunch?", "lol", emoji-only |
| `AMBIGUOUS` | Unclear — confidence < 0.7 OR genuinely ambiguous | "hmm", "interesting", short fragments without context |

## Classification logic

For each message:

1. **Pre-filter:** skip if message_text is < 5 characters AND doesn't contain `@` mention, T-N reference, or task verb. Mark as `NON_WORK_CHAT` directly without LLM call.

2. **Classify with LLM:** for the rest, call Claude Sonnet 4.6 with this exact prompt structure:

```
You are classifying Slack messages from BON Credit team members for the Alaska
AI project manager. Classify this message into ONE of these intent types:

TASK_CREATE / TASK_UPDATE / TASK_ASSIGN / TASK_BLOCKER / REMINDER_REQUEST /
DECISION_RECORDED / STATUS_QUERY / NON_WORK_CHAT / AMBIGUOUS

Return JSON with this exact shape:
{
  "intent": "<one of the 9>",
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

Team roster (for @ resolution):
[Resolve from /root/.openclaw/workspace/MEMORY.md → Team Roster]

Message text:
[insert message text]

Channel: [channel name]
Author: [first name]
Timestamp: [ISO]
```

3. **Write classification result.**

**Observation mode (Phase A):**
- Update the `intent_inbox` row: `processed = 1`, `intent = <result>`, `confidence = <result>`, `classifier_output = <full JSON>`, `processed_at = NOW()`.
- Insert into `classifier_audit`: full record with `would_have_done` populated.
- **DO NOT** create tasks, send DMs, post to channels, schedule actions, or modify any other table. This is logging only.

**Production mode (Phases B+):** unchanged from above PLUS route to the appropriate handler based on intent.

## Cron behavior (batched mode)

Triggered every 5 min via OpenClaw cron. Read unprocessed messages:

```bash
sqlite3 /data/queue/alaska.db "
  SELECT id, channel_id, author_slack_id, message_text, message_ts
  FROM intent_inbox
  WHERE processed = 0
  ORDER BY created_at ASC
  LIMIT 50;
"
```

For each row:
1. Look up channel name (from /root/.openclaw/workspace/TOOLS.md channel mapping)
2. Look up author first name (from MEMORY.md)
3. Run the LLM classifier
4. Write results per "Write classification result" above

Cap at 50 messages per run to bound token cost. If queue grows >200, alert Abhinav.

## DM handling (synchronous mode)

When invoked from a DM context with a single message:

1. Skip the intent_inbox insert (this isn't a channel message).
2. Run classifier directly.
3. Write to `classifier_audit` with `inbox_id = NULL` and `would_have_done` describing the would-be action.
4. Return the JSON result to the caller (the DM-handling skill — Phase A: only slack-commands, just for logging).

## Anti-patterns

1. **Never act on classifier output in Phase A.** Pure observation.
2. **Never modify the message text** before classifying — pass it verbatim so the audit log is accurate.
3. **Never skip the `would_have_done` field.** It's how we'll evaluate classifier quality before flipping to Phase B.
4. **Never re-classify already-processed messages.** Check `processed=0`.

## Token budget

Estimate: 50 channel msgs/day × 600 tokens/classification × $3/1M (Sonnet) = ~$0.10/day. Cap warning at $0.50/day in `classifier_audit` count >> expected.
