---
name: slack-commands
description: Handle team queries in Slack — status checks, blocker reports, shipped items, sprint info, and ad-hoc questions
version: 1.0.0
metadata:
  openclaw:
    always: true
    emoji: "💬"
---

# Slack Commands

When team members message Alaska in Slack (DM or channel mention), respond intelligently by pulling live data from Notion and SQLite.

**You are always-on for these.** No cron needed — respond when asked.

## Command: Status Check

**Triggers:** "status of [feature]", "where are we on [task]", "update on [thing]"

**Response:**
1. Search Sprint Board for matching tasks (by name similarity)
2. Return:
```
*[Task Name]*
Status: [status] | Owner: @[name] | Priority: [priority]
Effort: [effort] | Due: [date] | Sprint: [N]
[If blocker exists]: Blocked by: [blocker]
[If overdue]: ⚠ Overdue by [X] days
```
3. If multiple matches, list all with brief status
4. If no match: "I don't see a task matching '[query]' in the current sprint or backlog. Want me to search meeting notes?"

## Command: Blocker Report

**Triggers:** "who's blocked?", "what's blocked?", "active blockers", "blockers"

**Response:**
1. Read Blockers database (Status: "Active")
2. Return:
```
*Active Blockers* ([count])
• [Blocker] — blocking @[owner]'s [task] — raised [date] ([X] days ago)
  Resolution owner: @[name]
```
3. If no active blockers: "No active blockers right now."

## Command: Shipped Report

**Triggers:** "what shipped this week?", "what did we ship?", "changelog", "what's done?"

**Response:**
1. Read Changelog for entries in the last 7 days
2. Return:
```
*Shipped This Week* ([count])
• [What shipped] — @[name] — [date]
```
3. If nothing shipped: "Nothing marked as shipped this week. [X] tasks are in progress."

## Command: Sprint Status

**Triggers:** "sprint status", "how's the sprint?", "sprint health", "sprint progress"

**Response:**
1. Read Sprint Board for current sprint
2. Calculate:
   - Tasks by status (Done / In Progress / In Review / Not started yet / Backlog)
   - Effort points completed vs planned
   - Days remaining
   - Per-person load
3. Return:
```
*Sprint [N] — [X] days remaining*
Done: [count] ([points] pts) | In Progress: [count] | Blocked: [count] | Not Started: [count]
Completion: [%] of tasks, [%] of effort points
[If behind pace]: At current velocity, we'll complete ~[X]% by sprint end.

*Per Person:*
• @[Name]: [done]/[total] tasks — [status: on track / behind / blocked]
```

## Command: My Tasks

**Triggers:** "my tasks", "what's on my plate", "what should I work on"

**Response:**
1. Identify who's asking (from Slack user → Team Roster mapping)
2. Read their Sprint Board tasks
3. Return prioritized by due date:
```
*Your Tasks — Sprint [N]*
1. [Task] — [priority] — due [date] — [status]
2. [Task] — [priority] — due [date] — [status]

Suggested focus: [highest priority or nearest deadline task]
```

## Command: Decisions

**Triggers:** "what did we decide about [topic]?", "decisions from [meeting]", "decision log"

**Response:**
1. Search Decision Log by topic or meeting
2. Return:
```
*Decisions about [topic]:*
• [Decision] — by [who] — [date]
  Context: [why]
  Status: [active/superseded]
```

## Command: Help

**Triggers:** "help", "what can you do?", "commands"

**Response:**
```
Here's what you can ask me:

• *status of [feature]* — current task status
• *who's blocked?* — active blockers
• *what shipped this week?* — recent changelog
• *sprint status* — sprint health and progress
• *my tasks* — your current assignments
• *what did we decide about [topic]?* — decision history
• *plan next sprint* — trigger sprint planning
• *process latest meeting* — run Meeting Intelligence on newest transcript

Or just ask me anything about the project — I'll pull from Notion, Fireflies, and sprint data to answer.
```

## Analytics & Campaign Queries

**Metric questions** — read `/data/skills/amplitude-analyst/SKILL.md` and query Amplitude:
- "what's DAU?" / "show me retention" / "conversion funnel" / "who are our power users?"
- "compare this week vs last week" / "what happened to DAU on [date]?"
- "distribution of credit scores" / "user property breakdown"

**Campaign questions** — read `/data/skills/customerio-ops/SKILL.md` and query Customer.io:
- "list active campaigns" / "what's push delivery rate?" / "campaign metrics for [name]"
- "pause [campaign]" / "resume [campaign]"
- "create a push campaign for [segment]" → drafts for Abhinav approval
- "what messages did user [X] receive?"

**User lookup** — queries BOTH Amplitude + Customer.io:
- "tell me about user [X]" → Amplitude events + CIO messages + Notion context in one answer
- Uses the same user_id across both systems

**Cross-system questions:**
- "did users who got [campaign] open the app?" → CIO recipients + Amplitude app_opens
- "is the push fix working?" → CIO delivery rate + Amplitude push-attributed events

## General Questions

For anything not matching a specific command, use your judgment:
1. Search relevant Notion databases
2. Check recent meeting notes
3. Check Fireflies transcripts if relevant
4. **Query Amplitude** for metric questions (read amplitude-analyst skill)
5. **Query Customer.io** for campaign/messaging questions (read customerio-ops skill)
6. Respond with data, not guesses
7. If you don't know: "I don't have data on that. Want me to check [specific source]?"

Follow the Communication Standards in the shared toolkit. Additionally:
- Always respond within the same channel/thread you were asked in
- Keep responses concise — data, not paragraphs
- If a question requires checking multiple sources, just do it — don't narrate each step
