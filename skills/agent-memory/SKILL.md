---
name: agent-memory
description: Alaska's private working memory — her own self-tasks plus notes/references she's been asked to remember. A SIBLING store to the team task graph and the BON KB, not a route through either. Self-managed: Alaska creates, recalls, completes, and archives these rows herself. Private by construction — team-facing readers (Daily Pulse, Follow-Through, Risk Radar, "what's X working on") NEVER query this table. Writes to the `agent_memory` table per migration 0006.
version: 1.1.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3]
    emoji: "🧠"
---

# Agent Memory

`agent_memory` is Alaska's own **private working memory**: the things *she* needs to remember or do, kept separate from everybody else's work. Two kinds of content live here:

- **self_task** — Alaska's own follow-ups and to-dos. "I'll follow up with Sandeep about the Plaid keys" is a commitment Alaska made; it becomes a tracked self-task instead of a dropped promise.
- **note / reference** — something a teammate asked Alaska to keep handy and surface on cue. The motivating case: "show this CTA table whenever someone asks about CTAs." Not a team task, not durable domain knowledge — just a private reference Alaska stores and recalls when the cue fires.

This skill is the **sole reader/writer of the `agent_memory` table** (migration `0006_agent_memory.sql`). It does NOT route through `task-handler` — that skill owns the `tasks` table; this one owns `agent_memory`. They are siblings. Schema lives in `migrations/0006_agent_memory.sql`; the live table is on `/data/queue/alaska.db`.

## The three-store boundary

Alaska keeps three separate memory stores. Knowing which one a piece of information belongs to is the most important decision this skill makes.

| Store | What lives there | Who owns it | Who reads it |
|---|---|---|---|
| **BON KB** (`workspace/knowledge/`) | Curated, durable, team-canonical **domain knowledge** about BON Credit | Abhinav-only (curated) | Alaska, when answering domain questions |
| **Team task graph** (`tasks` / `blockers`) | **Team members' real work** — tasks, owners, deadlines, blockers | `task-handler` (sole writer) | Team-facing readers (Daily Pulse, Risk Radar, Follow-Through, slack-commands) |
| **agent_memory** (this table) | Alaska's **own** self-tasks + private notes/references she must remember or recall | This skill (Alaska, self-managed) | **Alaska only** — never surfaced to the team as a store |

### The boundary test

When something arrives that Alaska might want to keep, ask in this order:

1. **Is it a durable, team-canonical domain fact** about BON Credit (a product decision, a pricing rule, a permanent how-things-work fact)? → It belongs in the **KB**. The KB is Abhinav-curated; do not write it here. (At most, leave a self_task for Alaska to suggest the KB addition to Abhinav.)
2. **Is it a teammate's piece of work** — something *they* will do, with an owner and (often) a deadline? → It belongs in the **task graph**, via `task-handler`. Do not write it here.
3. **Is it something *Alaska herself* must remember, recall on cue, or do?** → It belongs **here**, in `agent_memory`. A reference a teammate asked her to surface, an observation she wants to keep, or a follow-up she committed to.

If it isn't durable team-canonical knowledge and it isn't a teammate's work, but Alaska needs it later, it's `agent_memory`.

### PRIVACY GUARD (read this before any read)

`agent_memory` is private to Alaska **by construction** — that's the entire reason it's a separate table (see the PRIVACY GUARD comment in migration 0006). The guarantees:

- **Team-facing readers NEVER query `agent_memory`.** Daily Pulse, Follow-Through, Risk Radar, and slack-commands' "what's X working on" read `tasks`/`blockers` and ONLY `tasks`/`blockers`. A private self-task or note therefore *cannot* leak into a team report — safety by construction, not by remembering a filter. Keep it that way.
- **self_tasks and notes are private.** Alaska's own to-dos and observations are never listed, dumped, or announced to the team.
- **A reference's CONTENT is recalled to ANSWER a relevant question — the store is never dumped.** When the recall cue fires (someone asks about CTAs), Alaska pulls the matching reference's `content` and uses it to answer. She surfaces *that one answer*, never a listing of "here's everything in my memory." The store is queried internally and read out as an answer, never exposed as a catalog.

---

## Operations

Every operation runs against `/data/queue/alaska.db` and includes `PRAGMA foreign_keys=ON;` per shared-toolkit Section 1.5 (the `agent_memory` table has no outgoing foreign keys, so the pragma is a harmless no-op here — included for consistency, exactly as Section 1.6/1.7 do).

**Escape all free-text before interpolation** (`title`, `content`, `recall_cue`, `source`, `source_ref`) per shared-toolkit Section 1.5: double every apostrophe. Messages routinely contain `'` ("I'll", "let's", "don't") and an unescaped quote breaks the SQL. The canonical escape:

```bash
q="'"; qq="''"
title_esc="${title//$q/$qq}"
content_esc="${content//$q/$qq}"
recall_cue_esc="${recall_cue//$q/$qq}"
source_esc="${source//$q/$qq}"
source_ref_esc="${source_ref//$q/$qq}"
```

Slack IDs / channel IDs are alphanumeric and safe to interpolate directly, matching task-handler's convention.

### remember — store a self-task, note, or reference (INSERT)

**When to use:** a teammate says "remember this," "show X whenever someone asks about Y," or "keep this handy" (→ `kind='reference'`, or `'note'` for a looser observation); OR Alaska makes her own follow-up commitment — "I'll follow up with Sandeep," "I should check the deploy tomorrow" (→ `kind='self_task'`, with an optional `due_at` if a time was implied).

Generate the next `mem_id` with the canonical `M-N` MAX/CAST/SUBSTR pattern (same shape as task-handler's `T-N`, shared-toolkit Section 1.7):

```bash
NEXT_ID=$(sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; SELECT 'M-' || COALESCE(MAX(CAST(SUBSTR(mem_id, 3) AS INTEGER)) + 1, 1) FROM agent_memory;")
```

Then INSERT. Set `kind` to one of `self_task` / `note` / `reference` (CHECK-constrained — never invent a value). `recall_cue` holds the retrieval keywords/tags (e.g. `'CTA, chat, agent'`); `due_at` is set only for a time-bound self_task, else pass `NULL` unquoted. `source` records origin (`'self'`, `'<person> DM'`, `'Abhinav'`, `'channel:<id>'`); `source_ref` is the deterministic message ref if applicable, else `NULL`. `status` defaults to `'open'`.

```bash
# free-text already escaped per the block above; $due_at_or_NULL is an ISO 'string' or unquoted NULL,
# $source_ref_or_NULL is a 'string' or unquoted NULL.
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO agent_memory ( \
    mem_id, kind, title, content, recall_cue, status, source, source_ref, due_at \
  ) VALUES ( \
    '$NEXT_ID', '$kind', '$title_esc', '$content_esc', '$recall_cue_esc', 'open', \
    '$source_esc', $source_ref_or_NULL, $due_at_or_NULL \
  );"
```

`created_at` / `updated_at` default to `CURRENT_TIMESTAMP` — do not set them manually.

Filing a suggest-to-Abhinav KB proposal (boundary test #1 / anti-pattern #3)? Make it a `self_task` with `recall_cue='kb-proposal'` — the morning `review` bundles all of those into ONE DM to Abhinav instead of letting them rot in the table.

### recall — retrieve by cue to ANSWER a question (read-only)

**When to use:** a question or topic surfaces that might match something Alaska was asked to remember (someone asks about CTAs; Alaska wonders if she has a relevant note). Derive a keyword `<kw>` from the question, then run the recall query. This is the lookup behind "show the CTA table when asked about CTAs." Match is broad: it checks `recall_cue`, `title`, AND `content`, and excludes archived rows. Use the recalled `content` to **answer** — never read the result list out to the team.

Use this **exact** verified shape (escape the keyword too — derived keywords can contain apostrophes):

```bash
kw_esc="${kw//$q/$qq}"

sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT mem_id,kind,title,content FROM agent_memory \
  WHERE status!='archived' \
    AND (recall_cue LIKE '%$kw_esc%' OR title LIKE '%$kw_esc%' OR content LIKE '%$kw_esc%') \
  ORDER BY updated_at DESC;"
```

Read-only — the `PRAGMA foreign_keys=ON` is harmless on a SELECT (FKs aren't enforced on reads, per Section 1.5) and kept only for consistency. If nothing matches, Alaska simply has no stored reference for that topic — answer from her other knowledge or say she doesn't have it; never fabricate a memory.

### list_self_tasks — Alaska's own open to-dos (read-only)

**When to use:** Alaska reviews her own outstanding follow-ups (e.g. at the start of a work cycle, to act on commitments she made). This is for Alaska's *internal* use only — the result is NEVER posted to a team channel or report.

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT mem_id,title,due_at FROM agent_memory \
  WHERE kind='self_task' AND status='open' \
  ORDER BY COALESCE(due_at,created_at);"
```

Ordering puts dated follow-ups first (by `due_at`), falling back to creation order for undated ones via `COALESCE`.

### review — morning sweep of open self-tasks (cron-invoked)

**When to use:** the "Agent Memory — Morning Self-Task Review" cron, or Abhinav explicitly asking for a review. This is Alaska working through her own to-do list. Alaska-internal: the result is NEVER posted as a listing to any channel or person — the privacy guard applies in full.

Pull every open self_task, due-first (dated before undated):

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT mem_id, title, content, recall_cue, due_at, source FROM agent_memory \
  WHERE kind='self_task' AND status='open' \
  ORDER BY (due_at IS NULL), due_at, created_at;"
```

Then work the list, item by item:

- **Due or overdue** (`due_at <= now`): DO the follow-up now, through its proper channel (the relay, the check, the DM it represents), then `complete` it. Genuinely can't act on it today → re-date it (`UPDATE agent_memory SET due_at='<new ISO>' WHERE mem_id='M-N';`) — never silently drop a commitment.
- **KB proposals** (`recall_cue LIKE '%kb-proposal%'`): bundle ALL of them into ONE DM to Abhinav — "KB suggestion(s): …" — never one DM per item. Leave each row open until he rules; `complete` on accept or reject.
- **Undated and stale** (open > 7 days, no `due_at`): still relevant → keep it open; overtaken by events → `complete` or `archive` it, with judgment.

Nothing open or due → do nothing and post nothing (the watcher-janitor stay-silent rule). Acting on an item means acting through its proper channel — the list itself is never read out to anyone.

### complete — mark a self-task done (UPDATE)

**When to use:** Alaska finishes a self-task ("I followed up with Sandeep" → close the matching `M-N`). `self_task` rows flow `open` → `done`.

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE agent_memory SET status='done' WHERE mem_id='M-N';"
```

The `trg_agent_memory_updated_at` trigger (migration 0006) bumps `updated_at` automatically — do not set it manually.

### archive — retire a note/reference (UPDATE)

**When to use:** a note or reference is no longer relevant (the CTA table is superseded; an observation is stale). `note` / `reference` rows flow `open` → `archived` rather than `done`. Archived rows are excluded from `recall` (it filters `status!='archived'`), so they stop surfacing without being deleted — history is preserved.

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE agent_memory SET status='archived' WHERE mem_id='M-N';"
```

The trigger bumps `updated_at` automatically.

---

## Anti-patterns

1. **Never surface self_tasks or dump `agent_memory` to the team.** It must NEVER appear in Daily Pulse, Risk Radar, Follow-Through, or "what's X working on" — those read `tasks`/`blockers`, and that's the whole point of the privacy guard. Keep them reading `tasks`; never wire a team-facing surface to this table. Alaska's self-tasks are her private business.

2. **Recall a reference to ANSWER, never dump the store.** When a cue fires, pull the matching `content` and answer the specific question with it. Do not read out a listing of stored memories, and do not expose `agent_memory` as a browsable catalog to anyone on the team.

3. **This is NOT the KB.** Durable, team-canonical domain knowledge about BON Credit belongs in `workspace/knowledge/` (the KB), which is Abhinav-curated. Don't smuggle domain facts in here as "references." If you spot something genuinely KB-worthy, file a self_task to suggest it to Abhinav — don't unilaterally treat `agent_memory` as a second KB.

4. **Don't route through `task-handler`, and don't put teammates' work here.** `task-handler` is the sole writer of the `tasks` table and owns team work + dedup; `agent-memory` writes its own table directly and never calls it. Conversely, a teammate's task ("Pankaj will fix the chart bug") is NOT an `agent_memory` self_task — send it to `task-handler`. Only Alaska's *own* commitments are self_tasks here.

5. **Never invent a `kind` or `status` value.** `kind` is CHECK-constrained to `{self_task, note, reference}` and `status` to `{open, done, archived}` (migration 0006) — any other value is rejected by the constraint. self_tasks resolve to `done`; notes/references retire to `archived`.

6. **Never fabricate a memory on recall.** If the recall query returns nothing, Alaska has no stored reference for that topic — answer from other knowledge or say she doesn't have it. Don't invent a remembered instruction or reference that was never stored.

7. **Always escape free-text per Section 1.5, and never set timestamps manually.** Apostrophes in `title`/`content`/`recall_cue`/`source` will break the SQL if unescaped. `created_at`/`updated_at` are owned by the schema default and the update trigger — leave them alone.
