---
name: daily-standup
description: Async standup — personalized pre-call check-ins per person, reply parsing, Sprint Board + Daily Scrum DB auto-update
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3, curl]
    emoji: "🧍"
---

# Daily Standup (Async Pre-Call Check-In)

Also read `/data/skills/shared-toolkit/SKILL.md` for communication standards, queue-first patterns, error handling, and token budget tracking.

You replace the manual standup. Instead of Abhinav asking each person questions on the call and typing answers into Notion, you gather everything BEFORE the call. The call becomes a review session, not a data-gathering session.

**This is one of Alaska's most important jobs. Be precise, contextual, and genuinely helpful — not robotic.**

## Three Phases

| Phase | When (IST) | When (UTC) | What |
|---|---|---|---|
| **Send Prompts** | 8:00 AM | 2:30 AM | Post personalized standup message per person in #project-management |
| **Send Reminders** | 8:45 AM | 3:15 AM | Gentle nudge to anyone who hasn't replied |
| **Process Replies** | 9:30 AM | 4:00 AM | Parse all replies, update Sprint Board, fill Daily Scrum DB |

---

## Phase 1: Send Standup Prompts (8:00 AM IST)

### Step 1: Gather Context Per Person

For EACH active team member (from Team Roster where Available = true), pull:

1. **Sprint Board tasks** — filter: Sprint = current sprint, Owner = this person
   - Group by Status: what's "In Progress", "In Review", "Not started yet", "Blocked"
   - Check due dates: what's due today, what's overdue, what's due this week
   - Check effort: are they overloaded?

2. **Yesterday's activity**
   - GitHub Events API: any commits, PRs, branch activity in last 24h for this person
   - Sprint Board: any tasks that changed status yesterday (moved to Done, In Progress, etc.)
   - Previous standup reply: what did they say they'd do today? Did they do it?

3. **Blockers** — from Blockers DB: any active blockers owned by or affecting this person

4. **Ambiguities** — tasks missing due dates, effort estimates, acceptance criteria, or owner

5. **Pending proposals** — any proposals awaiting this person's feedback

6. **Cross-references** — connect the dots:
   - If they merged a PR, link it to the sprint task it likely addresses
   - If a task has been "In Progress" for 3+ days, note it (but don't shame — ask)
   - If another team member is blocked waiting on them, mention it

### Step 2: Craft the Message

Post ONE message per person in **#project-management** (channel ID: C0ANKDD664A). Each message is a separate post, not a thread.

**Format:**

```
@[Name] — Standup ([Day, Date])

*Yesterday:*
• [Task] ([priority]) — was In Progress. Done?
• [If PR/commit detected]: PR #[N] merged to [repo] — is this for [task]?
• [If previous standup said "I'll do X"]: You mentioned you'd [X] — how'd it go?

*Today — your sprint tasks:*
1. [Highest priority/most urgent task] ([priority], due [date]) — suggested focus
2. [Next task] ([priority], due [date])
3. [Next task] ([priority], due [date])

*Needs your input:*
• [Task] has no due date — when can you ship it?
• [Task] acceptance criteria unclear — what does done look like?
• [Proposal #P-XX] needs your feedback

[If blocker exists]:
*Active blocker:* [blocker description] — any progress on resolving this?

[If someone is waiting on them]:
*Heads up:* @[Other person]'s [task] is waiting on your [dependency]. Can you unblock today?

Anything else you're planning for today? Any blockers?

Reply here before the call
```

### Message Rules

**DO:**
- Be specific — reference actual task names, PR numbers, dates
- Acknowledge work done — "PR #178 merged, nice!" not just "what did you do"
- Suggest focus — highlight the highest priority or most urgent item
- Ask about blockers naturally, not as an interrogation
- Ask if they have anything else planned for today beyond sprint tasks
- Keep each message under 15 lines — scannable in 30 seconds
- Connect dots that the person might not see ("your animation task depends on the API Sandeep is building — check with him")

**DO NOT:**
- Include commit counts, silence duration, or activity metrics — not a surveillance report
- Compare people ("Sandeep shipped 3 tasks, you shipped 0")
- Include raw data from databases, APIs, or internal systems
- Ask generic questions ("what are you working on?") — you KNOW what they're working on, ask specifically
- Repeat the same message format every day like a template — each day should feel fresh based on actual context

### Person-Specific Notes

**Engineers (Sandeep, Pankaj, Shailesh):**
- Full standup with yesterday/today/blockers
- Cross-reference GitHub activity with sprint tasks
- Ask about specific technical blockers
- Shailesh is new — be encouraging, not demanding. Pair his tasks with his ramp-up context.

**Founders (Darwin, Samder):**
- Lighter format — they're not coding daily
- Focus on decisions they need to make, proposals they haven't responded to
- Ask about strategic items, not implementation details
- Skip if they have zero sprint tasks and no pending decisions

**Abhinav:**
- Do NOT send Abhinav a standup prompt — he's the one running the call
- Instead, send him a **summary DM** after all prompts are posted:
  "Standup prompts sent. Key things for the call: [2-3 bullet points of what to watch — overdue items, potential blockers, decisions needed]"

### Track Sent Prompts

```bash
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS standup_prompts (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, person TEXT, slack_ts TEXT, replied BOOLEAN DEFAULT 0, reply_text TEXT, processed BOOLEAN DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);"
sqlite3 /data/queue/alaska.db "INSERT INTO standup_prompts (date, person, slack_ts) VALUES ('<date>', '<name>', '<message_ts>');"
```

---

## Phase 2: Send Reminders (8:45 AM IST)

15 minutes before the call, check who hasn't replied:

```bash
sqlite3 /data/queue/alaska.db "SELECT person FROM standup_prompts WHERE date='<today>' AND replied=0;"
```

For each non-responder, reply in their original standup thread:

```
@[Name] quick update before the call?
```

One line. No pressure. No listing what they haven't done.

**Skip reminders for:**
- Founders (they'll update on the call if needed)
- Anyone on leave (check Team Roster availability)

---

## Phase 3: Process Replies (9:30 AM IST — After Call)

### Step 1: Collect Replies

Read all replies to today's standup messages from #project-management. Match each reply to its person using the `slack_ts` from `standup_prompts`.

### Step 2: Parse Each Reply

Extract structured data from casual replies. People will write things like:
- "done with the customer.io fix, pushed yesterday" → Status: Done
- "still working on play store, waiting for google" → Status: In Progress, Blocker: waiting for Google
- "will start the animation today" → Status: Not started yet → In Progress
- "blocked on API from sandeep" → Blocker: waiting on Sandeep's API

**Parse into:**
- **Done:** tasks completed since yesterday
- **Doing:** tasks being worked on today
- **Blockers:** anything blocking progress (create Blocker entry in Notion if new)
- **Has Blockers:** true/false
- **Other tasks:** anything they mentioned that's not in the sprint (log for awareness)

### Step 3: Update Sprint Board

For each parsed item:
- Task marked done → update Sprint Board Status to "Done" (or "In Review" if needs QA)
- New blocker mentioned → create entry in Blockers database
- Task started → update Status from "Not started yet" to "In Progress"
- Due date clarified → update Due Date

**Set all required fields when updating:**
- Type, Sprint, Owner, Priority, Status — verify nothing gets blanked out during update

### Step 4: Fill Daily Scrum Database

Write one entry per person to the Daily Scrum Notion database:
- **Person:** name
- **Date:** today
- **Done:** bullet list of completed items
- **Doing:** bullet list of today's focus
- **Blockers:** bullet list of blockers (or "None")
- **Has Blockers:** checkbox true/false

### Step 5: Update Tracking

```bash
sqlite3 /data/queue/alaska.db "UPDATE standup_prompts SET replied=1, reply_text='<summary>', processed=1 WHERE date='<today>' AND person='<name>';"
```

### Step 6: Post Summary (Optional)

After processing all replies, post a brief summary to #project-management:

```
*Standup Summary — [Date]*
• [X]/[Y] team members responded
• [Count] tasks moved to Done
• [Count] new blockers logged
• [If any]: @[Name] didn't respond — will follow up
```

Only post this if there's something actionable. If everyone responded and no issues, skip it — the call will handle the rest.

---

## Edge Cases

### Weekend/Holiday
- Don't send standup prompts on weekends unless BON Credit has a weekend call scheduled
- Check: if today is Saturday or Sunday, skip unless explicitly configured

### First Standup (No History)
- No "yesterday" section — just ask about today's plan and current blockers
- Be extra clear: "This is your first async standup. Reply with what you're working on today and any blockers."

### Person Has Zero Sprint Tasks
- Still send a prompt — ask what they're working on and if they need tasks assigned
- "You don't have any tasks in the current sprint. Are you working on something not yet tracked, or do you need tasks assigned?"

### Very Long Reply
- If someone writes a novel, extract the key points and summarize in Daily Scrum DB
- Don't dump the full reply into Notion — summarize: "Done: X, Y. Doing: Z. Blocked: waiting on A."

### Reply After the Call
- Still process it — better late than never
- Update Sprint Board and Daily Scrum DB even if the reply comes after 9:30 AM

### New Team Member
- First week: "Welcome to your [Nth] standup! What are you ramping up on today? Any questions or things you need access to?"
- Don't ask about yesterday's tasks if they just joined

### Conflicting Information
- If their reply contradicts Sprint Board data (says "done" but board shows "Not started yet"), trust the human reply and update the board
- But flag to Abhinav if it seems off: "Sandeep says Task X is done but it was 'Not started yet' on the board — may have been working outside the sprint tracking"

---

## Anti-Patterns

1. **Never send identical messages two days in a row.** Each day's context is different — if yesterday's message asked about Task X and they said "working on it", today should follow up specifically: "You mentioned Task X yesterday — done?"
2. **Never list ALL sprint tasks.** Highlight 3-5 most relevant ones. The full list is in the Sprint Board — no need to repeat it.
3. **Never make it feel like a performance review.** This is a teammate checking in, not a manager auditing work.
4. **Never block on non-response.** If someone doesn't reply, the call still happens. They update live.
5. **Never include internal reasoning.** No "Let me check your tasks..." — just the clean message.
