---
name: daily-standup
description: Pre-call sheets in #daily-standup channel — personalized per person, Abhinav replies during call, Meeting Intelligence processes everything after
version: 2.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3, curl]
    emoji: "🧍"
---

# Daily Standup v2 (Pre-Call Sheets)

Also read `/data/skills/shared-toolkit/SKILL.md` for communication standards, queue-first patterns, error handling, and token budget tracking.

The daily call IS the standup. Alaska posts pre-call sheets 30 minutes before, Abhinav shares screen during the call and replies with quick status notes, and Meeting Intelligence processes the transcript + replies afterward. No double work for the team.

## Phase 1: Post Call Sheets (8:00 AM IST / 2:30 AM UTC)

### Step 1: Gather Context

Read `PROJECT_STATE.md` for current priorities and per-person focus.

For EACH active team member (from Team Roster where Available = true):

1. **Sprint Board tasks** — current sprint, this person's tasks, grouped by status
2. **Yesterday's activity** — GitHub Events API (last 24h), Sprint Board status changes, previous call sheet replies
3. **Blockers** — active blockers owned by or affecting this person
4. **Ambiguities** — tasks missing due dates, effort, acceptance criteria
5. **Cross-references** — PRs that map to sprint tasks, dependencies on other people

### Step 2: Post ONE Message Per Person in #daily-standup

Channel: **#daily-standup** (C0ASLANJ0RL)

Post a separate message for each person. Format:

```
@[Name] — [Day, Date]

*Yesterday:*
• [Task that was In Progress] — done?
• [If commit/PR detected]: PR #X merged — is this for [task]?
• [If previous call said they'd do X]: You said you'd [X] — how'd it go?

*Suggested today:*
1. [Highest priority task] ([priority], due [date]) — suggested focus
2. [Next task] ([priority], due [date])
3. [Next task] ([priority], due [date])

*Ask about:*
• [Missing due date / unclear acceptance criteria / pending decision]
• [Blocker status update needed]
• [Dependency on another person]

Anything else planned for today?
```

### Message Rules

- **Keep each message under 15 lines**
- **Be specific** — actual task names, PR numbers, dates
- **Acknowledge work done** — "PR #178 merged, nice!"
- **Suggest focus** — highest priority or most urgent
- **Ask if they have anything else** beyond sprint tasks
- **Everyone gets the same full prompt** — Abhinav, founders, engineers. No exceptions.
- **Each day should feel different** — follow up on what they said yesterday, don't repeat templates
- **DO NOT include** commit counts, silence duration, activity metrics, or comparisons between people

### Slack IDs for @mentions
- Abhinav: U07GKLVA9FE
- Samder: U0APEUXD9DH
- Darwin: U0APK8VTT62
- Pankaj: U0AQ0817FJM
- Sandeep: U0AQFJV9B32
- Shailesh: (check Team Roster)
- Tarun: (check Team Roster)

### Track Sent Prompts
```bash
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS standup_prompts (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, person TEXT, slack_ts TEXT, replied BOOLEAN DEFAULT 0, reply_text TEXT, processed BOOLEAN DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);"
sqlite3 /data/queue/alaska.db "INSERT INTO standup_prompts (date, person, slack_ts) VALUES ('<date>', '<name>', '<message_ts>');"
```

## How the Call Works (Alaska doesn't run during this — just context)

1. Abhinav opens Slack #daily-standup on the call, shares screen
2. Goes through each person's call sheet one by one
3. Abhinav replies to each person's message with quick status notes:
   - "Done ✅" / "Not done — blocked on X" / "Carrying over"
4. Team discusses blockers, priorities live
5. Meeting Intelligence picks up the Fireflies transcript + Abhinav's Slack replies afterward

## Phase 2: Reminders (8:45 AM IST / 3:15 AM UTC) — DISABLED

Previously sent reminders to non-responders. No longer needed — the team doesn't reply to the call sheets, Abhinav fills them in during the call by replying himself.

**This cron job should remain disabled.**

## Phase 3: Process Replies (10:00 AM IST / 4:30 AM UTC) — NOW HANDLED BY MEETING INTELLIGENCE

Reply processing is now part of Meeting Intelligence v2. After the call, Meeting Intelligence reads:
1. The Fireflies transcript of the call
2. Abhinav's replies to each person's call sheet in #daily-standup
3. Cross-references both sources to build the most accurate picture

It then updates Sprint Board, fills Daily Scrum DB, and updates PROJECT_STATE.md.

**This cron job should remain disabled.**
