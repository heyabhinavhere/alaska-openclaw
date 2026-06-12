---
name: event-poller
description: Shared cron skill — polls ONE event source for events since its last poll, finds active event-watchers subscribed to that event type whose filter matches, and runs the watcher-dispatcher for each (watcher, event) pair. One poller cron per event type; the watcher-dispatcher does the actual acting + dedup + logging.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3, python3]
      env: [AMPLITUDE_API_KEY, BON_GITHUB_TOKEN]
    emoji: "📡"
---

# Event Poller

Read `/data/skills/shared-toolkit/SKILL.md` for queue patterns, Section 7 graceful-degradation, and SQL-escape rules. This is the **event-trigger half** of the watcher system: cron-type watchers get their own per-watcher cron, but event-type watchers all ride these shared pollers (one cron per event type) so we scan each source once and fan out to every subscriber. You do NOT act on events yourself — you find matching watchers and hand each one to the **watcher-dispatcher**, which owns acting, memory dedup, per-fire approval, and `watcher_fires` logging.

## When you're invoked

A shared poller cron fires with: `Run /data/skills/event-poller/SKILL.md procedure for event_type=<new_signup|bug_closed|pr_merged|task_status_changed>.` Extract `event_type`. If it isn't one of the four known Gen-1 types, exit (malformed payload). (`deploy_succeeded` is a Gen-2 addition — no poller for it yet.)

## Procedure

### Step 1: Read the watermark + capture the poll window

```bash
sqlite3 /data/queue/alaska.db "SELECT last_polled_at FROM event_pollers WHERE event_type='<event_type>';"
```

Let `POLL_START` = now (UTC). You will query events in the half-open window `(last_polled_at, POLL_START]` and advance the watermark to `POLL_START` only at Step 5 — **after** processing. A crash mid-poll leaves the watermark un-advanced, so the next run re-queries the window; the dispatcher's strict-entity memory dedups any re-delivery.

### Step 2: Any subscribers? (cheap short-circuit before hitting the source)

```bash
sqlite3 /data/queue/alaska.db \
  "SELECT watcher_id, trigger_config, created_by_slack_id, volume_cap FROM watchers \
   WHERE status='active' AND trigger_type='event' \
     AND json_extract(trigger_config, '\$.event_name')='<event_type>';"
```

If 0 rows: `UPDATE event_pollers SET last_polled_at='<POLL_START>', last_run_count=0 WHERE event_type='<event_type>';` and exit. No point querying an external API if nobody's listening.

### Step 3: Pull new events from the source since `last_polled_at`

Dispatch by `event_type`. **Load the relevant KB integration file for the real query mechanics — never fabricate an API shape.** Degrade per shared-toolkit Section 7: if an external source is down, do NOT advance the watermark — exit so the next run retries the same window.

| `event_type` | Source | How (load this KB file) | Event payload exposed as `{{event}}` |
|---|---|---|---|
| `new_signup` | Amplitude | `integrations/amplitude.md` — signup events since `last_polled_at`, Real-Users filter. If a subscriber's filter needs `credit_score` and the event lacks it, enrich via `user-profile-360` (`lookup.py`, narrowest `--intent`). | `{user_id, email?, credit_score?, signed_up_at}` |
| `bug_closed` | Notion bugs DB | `integrations/notion.md` — bug pages whose status moved to closed since `last_polled_at` | `{bug_id, title, closed_at, topic?}` |
| `pr_merged` | GitHub | `integrations/github.md` — merged PRs across the BON repos since `last_polled_at` (read-only token) | `{repo, pr_number, title, merged_at, author}` |
| `task_status_changed` | local `task_events` | `SELECT task_id, old_value, new_value, actor_slack_id, created_at FROM task_events WHERE event_type='status_changed' AND created_at > '<last_polled_at>';` | `{task_id, old_value, new_value, actor_slack_id, changed_at}` |

`task_status_changed` is the only local-DB source — it stays quiet until Phase B task data flows (wired but dormant). The other three hit external APIs.

If 0 new events: advance the watermark (`last_run_count=0`) and exit.

### Step 4: Match each event to subscribers, then dispatch

For each new event × each subscribed watcher:

1. **Apply the watcher's `trigger_config.filter`** to the event (see Filter semantics). No match → skip this pair.
2. **Match → run the watcher-dispatcher** for this watcher with the event in scope: read `/data/skills/watcher-dispatcher/SKILL.md` and execute its procedure for `watcher_id=W-N` with `{{event}}` = this event payload. The dispatcher applies that watcher's memory dedup, per-fire approval, volume_cap, and `watcher_fires` logging — the poller re-implements none of it.

Respect each watcher's `volume_cap` across a single poll: don't hand one watcher more than `volume_cap` events in one run; note the overflow for the next window.

### Step 5: Advance the watermark

```bash
sqlite3 /data/queue/alaska.db \
  "UPDATE event_pollers SET last_polled_at='<POLL_START>', last_run_count=<events_seen> \
   WHERE event_type='<event_type>';"
```

If anything dispatched, log one stdout line: `[event-poller <event_type>] <events_seen> events, <dispatches> dispatched.` Otherwise stay silent.

## Filter semantics

`trigger_config.filter` is a JSON map of `field → {op, value}` where `op ∈ <, >, <=, >=, ==, !=, in`. All conditions are AND-ed: an event matches only if every condition holds against its payload. Example (Example 5 — low-score signups): `{"credit_score": {"op": "<", "value": 580}}` matches a `new_signup` event whose `credit_score` is below 580. An absent field on the event = no match (don't guess).

## Anti-patterns

1. **Never advance the watermark before processing.** Advance only at Step 5; a pre-advance would skip events on a crash. Overlap on re-run is safe — the dispatcher dedups.
2. **Never re-implement dispatch logic.** Memory, per-fire approval, volume_cap, and logging belong to the watcher-dispatcher — always invoke it per match, never act directly.
3. **Never hit the source with zero subscribers.** Step 2 short-circuits first — saves API budget.
4. **Never hard-fail the whole poll on one source outage.** Degrade per shared-toolkit Section 7; leave the watermark; retry next run.
5. **Never fabricate a source's API shape.** Load the integration KB file for the real query; if it doesn't resolve, flag `[NEEDS CLARIFICATION]` rather than guessing.
6. **Never dispatch to a non-active watcher.** The Step 2 query already filters `status='active'` — don't widen it.

## Frequency and cost

One cron per event type: `new_signup` every 15 min, `bug_closed` / `pr_merged` / `task_status_changed` every 30 min (UTC). With no active event-watchers, every run short-circuits at Step 2 (one SQLite read — near-free). With subscribers: one source query + 0..N dispatcher runs. Cost scales with active event-watchers × event volume, and each dispatch's own cost was projected + gated at creation.
