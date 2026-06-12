---
name: pre-call-brief
description: Personal briefing DM to Abhinav 30 minutes before each meeting — agenda, unresolved items, context, talking points
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3]
    emoji: "📞"
---

# Pre-Call Briefing

You run two distinct outputs with **different transports — never mix them**:

1. **Daily standup sheets (Step 3, the team-facing mode):** ONE numbered sheet per team member, posted **publicly to #daily-standup (`C0ASLANJ0RL`)** before the ~9 PM IST call. This is the daily-scrum surface; the team replies in-thread and those replies are the primary record.
2. **Personal meeting-prep briefs (non-standup meetings — externals, 1:1s, investor calls):** a concise prep **DM to Abhinav** with everything he needs to walk in prepared. **This mode is PRIVATE to Abhinav only — never post a prep brief to any channel.**

## Triggers

### Automatic (when Google Calendar is connected)
- Check calendar every 30 minutes for upcoming meetings
- If a meeting starts within the next 30-45 minutes, generate and DM the brief
- Don't brief the same meeting twice (track in SQLite)

### Manual
- "brief me for the 3 PM call"
- "what should I discuss in the team call?"
- "prep me for the meeting with [person/group]"

### Track Briefed Meetings
```bash
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS briefed_meetings (id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id TEXT UNIQUE, meeting_title TEXT, briefed_at DATETIME DEFAULT CURRENT_TIMESTAMP);"
```

## Step 1: Identify the Meeting

From calendar event or manual request, extract:
- Meeting title
- Attendees (map to Team Roster for context)
- Scheduled time
- Meeting type (infer: team call, product discussion, external partner, interview, 1:1)

## Step 2: Gather Context

Pull relevant data based on attendees and meeting type:

### For Team Calls (Abhinav, Darwin, Samder, Sandeep, Pankaj, Sai)
- `DAILY_STATE.md`: current sprint status, per-person commitments and progress
- Blockers (Notion DB + DAILY_STATE.md `Active Blockers`): active blockers relevant to attendees
- Decision Log: pending decisions that need resolution
- Previous Meeting Notes: unresolved items from last team call
- Follow-Through data: overdue tasks for attendees
- Proposals: any pending proposals awaiting confirmation
- Risk Radar: active High/Critical risks

### For Product Discussions (Abhinav, Darwin, Samder)
- Recent feature decisions and their status
- User metrics (if Amplitude connected): DAU, activation, retention
- Pending product decisions from Decision Log
- Scope changes from recent proposals
- Strategic context from memory

### For External Partner Calls (e.g., Plaid, MobileFirst, Fintegration)
- Active blockers related to the partner
- Previous meeting notes with this partner
- Pending tasks that depend on the partner
- Any relevant Slack discussions mentioning the partner

### For 1:1s
- That person's task status and recent activity
- Any nudges or overdue items
- Recent meeting notes where they were mentioned
- Any concerns flagged by Thinker Agent about this person

### For Interviews
- The candidate's previous interview notes (if in Fireflies)
- Role requirements from Team Roster / hiring context
- Team capacity gaps that this hire would fill

## Step 3: Generate the Brief (Phase B — SQLite-aware)

**Freshness guard (before you build or post the sheet).** Date-stamp the sheet with today's date from `date` (never a remembered date — run `date +"%A, %B %d, %Y"` and use it). If the underlying state hasn't changed since the last sheet — e.g. Meeting Intelligence flagged a Fireflies no-show, so there's no new call data and the task graph is unchanged — do NOT re-post an identical sheet. Post a short note instead: "No new call data since [last-update date] — yesterday's items still stand. Reply with today's update." This stops the team getting the same sheet two days running (the 2026-06-02 duplicate).

For each team member who's active today, query SQLite for their task state. Use the canonical patterns in `/data/skills/shared-toolkit/SKILL.md` Section 1.7. Three queries per person:

```bash
# 1. Active + blocked + pending_acceptance tasks
# Includes tasks where the person is a secondary owner (additional_owners JSON contains their ID),
# matching the canonical pattern in shared-toolkit Section 1.7 "Query: active tasks for a person".
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, status, priority, due_at, updated_at, source, owner_slack_id \
  FROM tasks \
  WHERE (owner_slack_id = '$OWNER' OR additional_owners LIKE '%\"$OWNER\"%') \
    AND status IN ('active', 'blocked', 'pending_acceptance') \
  ORDER BY \
    CASE status WHEN 'pending_acceptance' THEN 0 WHEN 'blocked' THEN 1 ELSE 2 END, \
    CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, \
    due_at ASC NULLS LAST;"

# 2. New since yesterday — tasks created in the last 24h (so team sees what got added).
# Includes updated_at so the formatter can apply the stale-marker rule uniformly (brand-new
# tasks won't be stale, but the column has to be selected for the rule to evaluate).
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT task_id, title, source, source_ref, creator_slack_id, assigner_slack_id, created_at, updated_at \
  FROM tasks \
  WHERE (owner_slack_id = '$OWNER' OR additional_owners LIKE '%\"$OWNER\"%') \
    AND created_at > datetime('now', '-1 day') \
  ORDER BY created_at DESC;"

# 3. Reminders due today — Phase C wires this. In Phase B the query returns 0 rows by design (no scheduled_actions are written yet); the section heading is conditionally suppressed.
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT action_id, payload FROM scheduled_actions \
  WHERE recipient_slack_id = '$OWNER' \
    AND status = 'pending' \
    AND fire_at BETWEEN date('now') AND date('now', '+1 day');"
```

Format the brief in the thread reply (or DM, depending on meeting type — preserve existing meeting-type discrimination from Step 2):

**Number the task lines explicitly — `1.` `2.` `3.` … in ONE continuous sequence across TODAY → SUGGESTED FOR TOMORROW → BLOCKED** (ACK + reminder lines stay bulleted, unnumbered). The numbers are the reply contract: "1 done, 4 drop it" must map to exactly one task with zero guessing (team decision 2026-06-12: written replies are the primary record, so the sheet is a form — make it machine-unambiguous). Section mapping from the Step-1a queries: **TODAY** = the person's `active` tasks · **SUGGESTED FOR TOMORROW** = due-soon + stale-needs-confirmation + new-since-yesterday items (Alaska's suggestions — the sheet must always ASK about tomorrow, and suggest) · **BLOCKED** = blocked tasks/blockers.

```text
[FirstName] — [Day, Date abbrev]

TODAY — what happened? (reply by number):
1. T-N  [Title] — due [date]        ← the "— due [date]" part ONLY when due_at exists; otherwise just the title. NO source hints ("from Wed standup/meeting") — confusing + redundant (Abhinav, 2026-06-12).
2. T-N  [Title]

SUGGESTED FOR TOMORROW (confirm, change, or add):
3. T-N  [Title] — due tomorrow
4. T-N  [Title] — no update in [N] days, still yours?
• T-N — assigned to you by [name]: reply 'ack' to accept or 'pass' to decline  (omit if none)

BLOCKED:
5. T-N  [Title] — [blocker title] (day [N]) — still blocked?

REMINDERS DUE TODAY:  (omit heading if 0)
• [reminder text]

Reply (one line per number + your tomorrow):
  <number> done / in progress / yes / drop it / still blocked / blocked by X
  new: <anything you did or will do that isn't listed>
  tomorrow: <your plan in one line>

_Reply by 9 PM — anything I missed, just tell me._
Team call in [N] min.    ← compute N as `(meeting_start_ts − now())` rounded to the nearest minute (from Step 1's calendar lookup; if the calendar is missing, omit this line rather than guess).
```

### Source-hint resolution

**As of 2026-06-12 (Abhinav): source hints are NOT rendered on the sheets** — they read as confusing/redundant to the team. Sheets show `due [date]` only (when present). The mapping below remains for INTERNAL attribution only (logs, summaries, answering "where did this task come from"):

- `source='meeting'`: hint = `"from [day abbrev] meeting"` — derive day-of-week from created_at
- `source='slack_dm'`: hint = `"committed [day abbrev] DM"` — short form
- `source='slack_channel'`: hint = `"in #[channel] [day abbrev]"` — resolve channel name from `/root/.openclaw/workspace/TOOLS.md` Channel ID mapping (the canonical channel-ID-to-name table; mirrored in MEMORY.md but TOOLS.md is the single source per Alaska's tool config)
- `source='standup_reply'`: hint = `"from [day abbrev] standup"`
- `source='manual'`: hint = `"added manually"` (rare path; usually Abhinav)

If the `assigner_slack_id` is set and DIFFERENT from `creator_slack_id`, prepend it: `"<assigner first name> → you, from ..."`.

### Fallback: zero tasks in SQLite for this person

If all three queries return zero rows for a person, fall back to the OLD DAILY_STATE.md per-person section read. The DAILY_STATE.md format uses `## <First Name>` as the section header (e.g., `## Pankaj`), with sub-bullets under "WORKING ON", "DONE RECENTLY", and "BLOCKERS" lines — read just that person's section and render those three buckets as ACTIVE / NEW SINCE YESTERDAY / BLOCKED respectively (T-IDs absent in fallback mode). This is a Phase B transition state and should disappear within ~2 weeks of going live. Append a footer note to the brief:

```
_(I'm switching to a new task system. DM me anything you're working on and I'll start tracking it — you'll get T-IDs next call.)_
```

### Quality gate — DAILY_STATE.md fallback path ONLY

The SQLite path above uses **structured** task rows — trust them as-is (no filtering). But when you fall back to DAILY_STATE.md prose for a person (their graph is empty), that text can carry Meeting-Intelligence extraction errors, so filter every item before showing it:

1. **Role relevance** — drop items that don't match the person's role: Samder=CEO (marketing/partnerships/investors, NOT engineering); Darwin=COO (finance/credit/user-audits, NOT code); Pankaj=Frontend/Flutter; Sandeep=AI Eng (CredGPT/V2/Python/DevOps); Shailesh=AI Eng (testing/agents); Nilesh=Backend (MoneyLion/KT); Tarun=QA. If a task doesn't fit the role, drop it.
2. **Non-work filter** — drop logistics/personal (flights, cabs, trip coordination) and status-updates-masquerading-as-tasks ("pushed X to next week" is an update, not a commitment).
3. **Staleness** — drop any commitment whose stated due date is >7 days in the past.
4. **Frankenstein check** — if an item looks like several tasks mashed into one (an MI hallucination, e.g. "finish activities section, integration testing with Pankaj, filter web app"), drop it and note "one item unclear — will verify on call."
5. If everything filters out for a person → show "No clear commitments from last call — will establish today."

(These gates exist because the OLD DAILY_STATE-only brief was hallucination-prone; the SQLite path makes them unnecessary for tracked tasks, but the fallback still needs them.)

### Rules for the brief

- **Omit empty section headings.** If ACTIVE has 0 items, do not print "ACTIVE (0):" — drop the section entirely.
- **Stale-task suppression.** Tasks with `updated_at < now - 30 days` get a dimmed marker `[stale]` in the title to flag them for owner review.
- **Cap section length.** If ACTIVE has >7 items, show top 7 by sort order and add `… +N more (DM me for full list)` as the final bullet.
- **Mirror Slack mrkdwn.** Use single asterisks for bold (`*T-42*`), not double.
- **No internal narration.** Per shared-toolkit Slack discipline, the brief is the final output — no "Let me pull your tasks…" preface.

## Step 4: Parse standup replies (runs as the Standup-Reply Parser cron, not inside the brief run)

Reply-parsing does NOT run inside the brief-posting cron (that run ends after posting the sheets). It runs as its own **Standup-Reply Parser** cron — one job, two daily fires (`0 3,16 * * *` UTC): the **evening pass ~9:30 PM IST** (right after the mandatory 8–9 PM reply window — parses the replies into the graph BEFORE the call ends, so Meeting Intelligence later synthesizes transcript + replies together; also runs the mandatory-reply check) and the **morning catch-up pass 8:30 AM IST** (stragglers only, silent — no nudges). Each pass:

**(a) Gather** recent #daily-standup (`C0ASLANJ0RL`) human activity — `conversations.history` (limit ~40, last ~16h); for any message with replies, also `conversations.replies`. **Exclude Alaska's own posts** (bot `U0ANY9YTNUR` / user `U0ANFSYAH29`) — the brief sheets are hers; only parse human messages/replies.

**(b) Dedup by reply `ts`** with a dedicated marker — `CREATE TABLE IF NOT EXISTS standup_processed (reply_ts TEXT PRIMARY KEY, processed_at DATETIME DEFAULT CURRENT_TIMESTAMP);` skip a `ts` already present; INSERT it after handling. **Do NOT reuse `intent_inbox` as the dedup flag** — the Thinker's hourly sweep also ingests #daily-standup there, so it is not a reliable processed-marker for this parser. (This makes the "never re-process a reply" anti-pattern concrete.)

**(c) Parse** each new human reply. **The printed grammar is a CONVENIENCE, never a requirement** — the team may reply in ANY format: paragraphs, bullets, Hinglish, half-sentences, voice-note transcriptions. Read the reply like a smart teammate would: map its content to the sheet's numbered items **by meaning** (the grammar patterns are just fast paths), extract statuses, new work, and dates. NEVER respond "couldn't parse" to a genuine status update — extract what's there and act on it; ask only when something is truly ambiguous (two tasks it could equally mean). **Date capture:** when a reply states any time ("by Friday", "tomorrow", "next week"), compute the ISO date with `python3` and pass `due_at_iso` to task-handler — on updates as well as creates. Grammar fast-paths:

**(c2) Coverage check + acknowledgment (per reply, evening pass).** After parsing a member's reply, compare what it addressed against THEIR sheet's numbered items:
- **Everything covered → ONE concise, factual acknowledgment** in the thread — confirm what was logged, zero flattery: *"Logged — T-44 done, T-36 in progress, tomorrow noted."* Never "great job!"-style praise, never follow-up questions when nothing is missing. A complete reply earns a crisp receipt, not an interview.
- **Items missing → ONE warm follow-up** in the thread naming only the gaps: *"And what about 3 (CTA testing)?"* One message, all gaps together, no repetition. **The thread is the state:** your own follow-up message in the thread marks "already asked" — never re-ask what a previous pass already asked (re-read the thread before posting).

**(d) Mandatory-reply DM — EVENING PASS (the ~9:30 PM IST fire, right after the 8–9 PM reply window).** Compare the people who got a sheet this cycle against the people whose replies you just processed (or that sit in `standup_processed`). For each roster member with a sheet but NO reply: send ONE gentle DM — *"Quick reminder — your standup sheet is waiting for a reply. 30 seconds in the thread: `1 done, 2 in progress, tomorrow: …`"* (warm coworker tone — no process explanations, no rule citations). One DM per person per cycle; externals excluded; list non-repliers in the run summary. No public post in the evening — people get the night to respond to DMs and follow-ups.

**(e) Morning consolidation — MORNING PASS ONLY (the 8:30 AM IST fire).** Parse overnight stragglers + follow-up answers first, then **recompute coverage from each whole thread** (sheet + all replies + your own follow-ups). Then post **ONE calm consolidated message** to #project-management (`C0ANKDD664A`) covering BOTH kinds of gaps, **@-mentioning each member with a real Slack mention (`<@U…>`)** — un-pinged messages get ignored (Abhinav-confirmed team pattern): *"Standup gaps today: <@U_PANKAJ> (no reply), <@U_SHAILESH> (item 3 — CTA testing) — drop an update in #daily-standup when you get a sec 🙏"*. One combined message, friendly tone, never per-person posts; skip the post entirely when there are no gaps. *(The public mention is by Abhinav's explicit instruction 2026-06-12 — a standup-compliance exception to the default no-public-individual-tracking rule; it applies to standup-reply compliance ONLY. Repeated-miss escalation belongs to Follow-Through, not this parser.)*

**(f) Regenerate the daily state — BOTH passes, after all processing:** run `python3 /opt/lib/generate_daily_state.py` (real run) so `DAILY_STATE.md`'s `## Per Person` + `## Active Blockers` reflect the replies just parsed — the graph is the source of truth (cutover 2026-06-12); the generator splices only those two sections and bumps the Last-compiled header.

```text
Regex patterns (try in order, first match wins). Each verb anchors with \b to avoid swallowing
trailing tokens — "T-42 done by EOD" still matches `done` and the suffix is captured as the
reply text passed to task-handler (which extracts the actual due hint from it):
  ^T-(\d+)\s+done\b.*$                        → mark_done(T-N)              [is_status_update=true]
  ^T-(\d+)\s+blocked\s+by\s+(.+)$             → mark_blocked(T-N, reason)   [is_status_update=true]
  ^T-(\d+)\s+active\b.*$                      → confirm_active(T-N)         [is_status_update=FALSE — logs a mention only, no status flip]
  ^T-(\d+)\s+(.+)$                            → log_mention(T-N, free_note) [is_status_update=false]
  ^new:\s*(.+)$                               → create_new_task(description) [is_status_update=false, no explicit_task_id]
  ^(ack|accept)(\s+T-(\d+))?\s*$              → accept_assignment           [→ task-handler acceptance='accept']
  ^(pass|decline)(\s+T-(\d+))?\s*$            → decline_assignment          [→ task-handler acceptance='decline']
  ^on\s+leave\b                               → mark_on_leave (deferred — see note below)
```

**`ack` / `pass` routing (the sheet's PENDING-ACK lines instruct exactly these words):** route to task-handler with `acceptance='accept'|'decline'` and `explicit_task_id` — taken from the named `T-N`, or, when bare, from the replier's own sheet **if it shows exactly ONE pending-acceptance line**; several pending and none named → ask which one ("ack which — T-12 or T-19?"). **Never treat a bare `ack`/`pass` as a free-form work note** — it's an assignment handshake, not a status update.

**`on leave` handling:** availability is a PERSON-level fact — record it in **`person_status`** (migration 0008), never as a task_events comment on an arbitrary task (the old Phase-B hack misattributed the signal and lost it entirely for taskless people). Ack one line — `Got it — noted you're on leave. I'll skip your tasks in tomorrow's brief.` — then upsert:

```bash
# Three branches, in priority order:
#   1. a stated end date in the reply ("on leave till Friday") -> use it;
#   2. a bare "on leave" -> default to tomorrow (compute with python3, never calendar math);
#   3. explicitly open-ended ("on leave indefinitely") -> SQL NULL, UNQUOTED.
UNTIL_ISO="$PARSED_UNTIL_ISO"        # branch 1: from the reply, if explicitly stated
if [ -z "$UNTIL_ISO" ] && [ "$OPEN_ENDED" != "1" ]; then
  UNTIL_ISO=$(python3 -c "import datetime; print((datetime.date.today()+datetime.timedelta(days=1)).isoformat())")   # branch 2
fi
UNTIL_SQL="NULL"                     # branch 3 default
if [ -n "$UNTIL_ISO" ]; then UNTIL_SQL="'$UNTIL_ISO'"; fi
sqlite3 /data/queue/alaska.db "INSERT OR REPLACE INTO person_status (slack_id, status_text, until_date, set_by, updated_at) VALUES ('$REPLIER_ID', 'On leave', $UNTIL_SQL, '$REPLIER_ID', CURRENT_TIMESTAMP);"
```

The generator renders it as their STATUS line, and the next sheet run posts the short "_[Name] — on leave_" note instead of a full sheet.

### Resolving bare numbered replies (the common case — nobody uses `T-N`)

In practice the team almost never types `T-N`. They reply with **bare item numbers** keyed to their *own* pre-call sheet — e.g. *"1 currently working, 2 all bugs fixed, 3 working on it, 4 this is done"* or *"1. Done 2. Done"*. A bare number has no text to fuzzy-match, so resolve it **positionally against the sheet the reply is threaded under** (NOT by guessing):

1. **Fetch the parent sheet** — the bot pre-call post this reply threads under (the person's own sheet). **Modern sheets number their task lines explicitly (`1. T-N [Title]` …, one sequence across TODAY → SUGGESTED FOR TOMORROW → BLOCKED) — trust the printed numbers.** For an older bulleted sheet (`• T-N`), enumerate the task-bearing lines positionally in section order (skip headings, ACK/reminder bullets, and the reply-format footer) as item 1, 2, 3, … A `tomorrow: <plan>` line routes like a free-form reply (fuzzy-match to an existing task, else `new:` semantics with the plan as the description).
2. **Map the reply's number → that item → its `T-N`,** then apply the stated action (`done`→mark_done · `working`/`in progress`/`active`→confirm_active, log only · `blocked by X`→mark_blocked · a free phrase→log_mention).
3. **Corroborate with any free text.** If the reply carries a phrase (*"1 currently working — streaming validation"*), check it against the mapped item's title: **position + text agree → high confidence.** Only one signal, or they disagree → **lower confidence.**
4. **Hard rails (never close the wrong task):**
   - Parent sheet unfetchable, number > item count, or two readings plausible → **do NOT guess.** Log the reply and DM Abhinav one line: *"[Name] said '[N] done' but I couldn't pin it to a task — which one?"*
   - **Marking a task `done` (closing it) requires an unambiguous mapping** (clean single sheet, N in range, action explicit). On any doubt → **propose, don't auto-close.** Affirming or creating is recoverable; a wrongly-closed task is not.

*(Forward note: once the Pre-Call cron is thinned (#88 applied) and the sheet is generated from this SKILL, number the sheet lines `1. … 2. …` to make this round-trip unambiguous by design. Until then, enumerate the existing `•` bullets by position.)*

For each matched reply (other than `on leave`):

1. Route to `/data/skills/task-handler/SKILL.md` with the appropriate inputs:
   - `extraction`: the reply text verbatim
   - `owner_slack_id`: the reply author
   - `creator_slack_id`: same
   - `source`: `standup_reply`
   - `source_ref`: `slack:thread:<channel_id>:<parent_ts>:<reply_ts>`
   - `is_status_update`: per the per-pattern column above — `true` for `done` and `blocked by`, `false` for `active`, free_note, and `new:` (task-handler still logs a `task_mentions` row for the false cases, so the audit trail is preserved either way)
   - `explicit_task_id`: the matched T-N (omit for `new:`)
2. task-handler returns `{task_id, action, status}`. Post a ONE-LINE thread acknowledgment:
   - For `mark_done`: `T-N marked done. Will show in tomorrow's shipped list.`
   - For `mark_blocked`: `T-N marked blocked (B-N logged). I'll check back tomorrow.`
   - For `create_new_task`: `Tracking as T-M: <title>.`
   - For ambiguous/no match: do NOT guess — reply: `Couldn't parse that. Try "T-N done", "T-N blocked by X", or "new: <description>".`
3. **Free-form replies (no `T-N`) — the common case.** The team rarely cites `T-N`; real replies look like *"streaming's done, on MoneyLion now."* Route these to `/data/skills/task-handler/SKILL.md` with `extraction`=the reply text, `owner_slack_id`=the reply author, `creator_slack_id`=same, `source=standup_reply`, `source_ref` as above, and **no** `explicit_task_id` — let task-handler's match-or-create **fuzzy dedup (its Step 2)** bind the update to the author's existing task by title/topic (≥0.8 → update that task; <0.8 → it creates a new task tagged `[NEEDS LINK?]`). **Work-relevance gate (anti-garbage), apply BEFORE routing:** skip pure chatter — greetings, "thanks", "👍", "sounds good", reactions — these are not status updates; log nothing (at most a `task_mentions` row). Only route replies that describe work (a deliverable, a verb like done/shipped/working/blocked/merged, or an impediment). **When in doubt, log — do not create.** A missed update is recoverable next standup; a hallucinated task erodes trust. (This replaces the old "invoke intent-classifier" fallback: a #daily-standup reply is already known to be a status update, so it goes straight to task-handler with `source=standup_reply` rather than through generic 10-intent classification.)

### Anti-patterns for the parser

- **Never silently match an ambiguous reply.** If two T-Ns could plausibly apply, ask for clarification — don't pick one.
- **Never re-process a reply.** Track replied-to-message ts in a dedup set so duplicate parses don't double-mark.
- **Never call task-handler with `owner_slack_id` of a different person than the reply author.** Even if the brief was about Sandeep's tasks, Pankaj's reply to it gets handled as Pankaj's input — possibly a TASK_BLOCKER on a shared task.

## Step 5: Post-Meeting Reminder

After the meeting time has passed (30 minutes after scheduled end), if Meeting Intelligence hasn't processed it yet:
- DM Abhinav: "The [meeting name] should be in Fireflies by now. Want me to process the transcript when it's ready?"

This catches meetings where Fireflies is delayed or wasn't recording.

## Edge Cases

### Back-to-Back Meetings
If two meetings are within 30 minutes of each other:
- Combine into one DM with clear separation
- Brief for the first meeting, then add: "Also coming up: [second meeting] at [time]. Key context: [1-2 lines]"

### No Relevant Data
If a meeting has no relevant DAILY_STATE.md, Blocker, or Decision Log data:
- Still brief with what you know: "Light agenda — no active blockers or decisions pending for this group. Might be a good time to discuss [suggestion based on memory/context]."

### Recurring Meetings
Track patterns across recurring meetings:
- "This is the 4th team call where [topic] was discussed without resolution. Consider making a decision today."
- "Last 3 team calls averaged 81 minutes. If you want shorter calls, consider time-boxing agenda items."

### Meeting Without Calendar
If Google Calendar isn't connected yet, the manual trigger still works:
- "brief me for the team call" → Alaska pulls context based on the typical attendees and recent data

Follow the Communication Standards in the shared toolkit. Additionally:
- Prep briefs (this mode): PRIVATE DM to Abhinav only — never channel. (The daily standup sheets are the separate PUBLIC mode — see the transport contract at the top of this skill.)
- Concise — this is a prep doc, not a report
- Opinionated — suggest what to discuss, don't just list data
- If you don't have enough context for a good brief, say so: "I don't have much context on this meeting's attendees. Want to tell me what it's about?"
