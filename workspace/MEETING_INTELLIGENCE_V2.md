# Meeting Intelligence v2 — Design Doc
# Alaska's meeting comprehension system
# Created: 2026-04-13

## Philosophy
Meetings are the single source of truth for a startup that moves fast. Alaska doesn't just extract tasks from transcripts — it deeply understands each meeting, updates its own understanding of the project, and then acts on that understanding.

## The 5-Step Pipeline

### Step 1: Deep Comprehension
Before extracting ANY tasks, Alaska reads the full transcript and writes an internal "Meeting Understanding" answering:

**What happened:**
- What topics were discussed and in what depth?
- What did each person say/commit to?
- What progress was reported verbally (even if board doesn't reflect it)?

**What changed:**
- Did priorities shift from last meeting? (e.g., "card linking is now #1")
- Did scope change? Features added/dropped/deprioritized?
- Did timelines change? Sprint length? Release dates?
- Did roles/responsibilities change? (e.g., "Shailesh takes over bugs")
- Did strategy change? (e.g., "WhatsApp redirect instead of full support system")

**Team dynamics:**
- Who was engaged? Who was quiet?
- Were there disagreements? What was the resolution?
- What commitments were made and by whom?
- What's the team energy/morale signal?

**Implicit signals:**
- What should have been discussed but wasn't?
- Who wasn't in the meeting that should have been?
- What deadlines were ignored or not mentioned?
- Are there contradictions between what people said and what data shows?

### Step 2: Compare Against Current State
Read PROJECT_STATE.md and compare:

- **Board vs. meeting:** Did anyone mention work that's further along than the board shows? → Flag for board update
- **Decisions vs. previous:** Did any decision contradict or modify a previous one? → Update decisions list
- **Priorities vs. sprint:** Does the sprint reflect the priorities discussed? → Flag misalignment
- **Blockers vs. discussed:** Were blockers resolved in discussion? New ones surfaced? → Update blocker list
- **People vs. tasks:** Did assignments change? → Flag for sprint update

### Step 3: Update PROJECT_STATE.md
Rewrite the relevant sections of PROJECT_STATE.md with new understanding:
- Current priorities (in order discussed in meeting)
- Per-person focus (what they committed to)
- Board vs reality gaps (what the meeting revealed vs. what board says)
- Recent decisions (add new ones, note reversals)
- What changed (one line per meeting summarizing the shift)

### Step 4: Extract Actions (contextual)
NOW extract tasks/decisions/blockers — but contextually:
- Only create tasks for NEWLY decided work (not rehashed items)
- If a task already exists, UPDATE it (don't create duplicate)
- If a feature was deprioritized, note it — don't create tasks for it
- If scope changed, adjust existing tasks
- Respect capacity: don't propose more than 10pts per person

**Dedup rules:**
- Check existing proposals from last 48hrs for same-meeting duplicates
- Check sprint board for similar tasks before creating
- If same meeting generated a previous proposal, supersede it

### Step 5: Post Summary
One message to #project-management. Format:

```
_Meeting: [Title] — [Date]_
[Attendees] | [Duration]

_Key changes:_
• [What shifted from previous understanding — most important]
• [Priority/scope/role changes]

_Progress confirmed:_
• [What people reported as done/in-progress, even if board doesn't show it]

_Decisions:_
1. [Decision] — [who decided]

_New/updated tasks:_ [only genuinely new items]

_Blockers:_ [new or status-changed]
```

Keep it SHORT. 15-20 lines max. The deep understanding is internal — the team only sees the summary.

### Daily Reconciliation (no-meeting days)
On days with no new meetings, run a lighter version:
1. Read last 3 meeting comprehension docs
2. Read PROJECT_STATE.md
3. Check sprint board current state
4. Flag contradictions to Abhinav DM
5. Update PROJECT_STATE.md if board changed

## What this replaces
- Old Meeting Intelligence: shallow extraction → duplicates, missed context
- Old Thinker observations (most of them): now baked into meeting comprehension
- Old Follow-Through nudges (most of them): now contextual based on meeting commitments

## Data flow
```
Fireflies transcript
  → Step 1: Deep comprehension (internal doc)
  → Step 2: Compare against PROJECT_STATE.md
  → Step 3: Update PROJECT_STATE.md
  → Step 4: Extract contextual actions → Notion
  → Step 5: Post summary → #project-management
```

All other agents READ PROJECT_STATE.md before acting — so they inherit the meeting understanding without running their own analysis.
