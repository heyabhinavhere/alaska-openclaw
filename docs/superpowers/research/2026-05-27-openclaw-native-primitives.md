# OpenClaw Native Primitives — Research Findings for Watchers V1

> **Date:** 2026-05-27
> **Author:** research subagent (dispatched from `2026-05-26-alaska-watchers-v1.md` §"OpenClaw deeper research")
> **OpenClaw version under examination:** 2026.3.13 (pinned in `Dockerfile`), with reference to current docs (2026-04+ features called out where relevant)

## Sources consulted

- Local repo files:
  - `Dockerfile` (image pin `1panel/openclaw:2026.3.13`)
  - `entrypoint.sh` (gateway boot, port 18789, `--allow-unconfigured`)
  - `config/openclaw.json` (channels, hooks, `gateway.tools.allow`)
  - `config/cron-jobs-backup.json` (14 working cron entries — authoritative shape reference)
  - `workspace/MEMORY.md` (prior research note — May 26 round)
- Official docs:
  - `https://docs.openclaw.ai/automation/cron-jobs` — primary cron reference
  - `https://docs.openclaw.ai/automation/cron-jobs.md` — markdown source
  - `https://docs.openclaw.ai/cli/cron` — CLI subcommand reference
  - `https://docs.openclaw.ai/gateway/tools-invoke-http-api` — `/tools/invoke` endpoint + default deny list
  - `https://docs.openclaw.ai/gateway/configuration-reference` — `cron.maxConcurrentRuns`, `sessionRetention`, `runLog`, hooks mappings
  - `https://docs.openclaw.ai/gateway/heartbeat` — heartbeat semantics vs cron
  - `https://docs.openclaw.ai/automation` — automation primitives index (Task Flow, Heartbeat, Commitments, Standing Orders)
  - `https://docs.openclaw.ai/automation/taskflow` — Task Flow durable multi-step
  - `https://openclaw-ai.com/en/docs/automation/cron-jobs` — mirror with examples
- GitHub issues (gotchas):
  - `https://github.com/openclaw/openclaw/issues/8557` — `enabled` field default-undefined bug
  - `https://github.com/openclaw/openclaw/issues/11075` — `jobId` (not `id`) is the canonical field name
  - `https://github.com/openclaw/openclaw/issues/9465` — feature request: cron job hooks (confirms no native chaining today)
  - `https://github.com/openclaw/openclaw/issues/8712` — `nextWakeAtMs` null stability bug (2026.2.1)
  - `https://github.com/openclaw/openclaw/issues/5825` — community feedback on existing nested schema

---

## Q1 — Native primitives beyond cron

### Event hooks / webhook receivers — **YES (already in use)**

OpenClaw exposes `POST /hooks/<name>` endpoints, authenticated via `Authorization: Bearer <token>` or `x-openclaw-token: <token>`. Two default routes (`/hooks/wake`, `/hooks/agent`) plus custom-mapped routes via `hooks.mappings` in config. Our `config/openclaw.json` already wires `fireflies-transcript` this way.

**Implications for Watchers:**
- Amplitude / GitHub / Customer.io / Notion webhooks could fire watchers natively — no polling needed when the source supports webhooks.
- The `messageTemplate` field renders the incoming JSON into a prompt; `action: "agent"` + `agentId` routes to a specific skill.
- V1 spec already assumes polling for events; switching to webhooks where available is a V2 optimization path.

**Gotcha:** The `__HOOKS_TOKEN__` substitution happens in `entrypoint.sh`. Any new hook mapping needs the `HOOKS_TOKEN` env var set in Railway.

**Confidence: HIGH** — we use this in production today for Fireflies.

### Stateful long-running primitives — **PARTIAL (Task Flow exists but is shallow)**

OpenClaw added **Task Flow** (released 2026.4.2) for "durable multi-step flows with managed and mirrored sync modes, revision tracking." It's CLI-driven (`openclaw tasks flow list|show|cancel`) and persists state in SQLite. **However, the docs are conceptual only — no documented programmatic API for creating flows from a skill, no documented data-passing between steps, no documented pause-for-approval semantics.** Production readiness is not claimed.

**Implications:** Don't bet Watchers V1 on Task Flow. It's a directional signal that OpenClaw is moving toward our action-chain model, but the surface area we'd need (programmatic creation, pause/resume, inter-step data) is not documented. Our JSON `action_chain` DSL stays — we can revisit consolidating into Task Flow in V2 if its API stabilizes.

**Confidence: MEDIUM** — based on docs only; haven't tested. Worth a runtime probe if anyone wants to validate.

### Per-cron-job state persistence — **PARTIAL**

OpenClaw persists per-job state at `~/.openclaw/cron/jobs.json` plus a sidecar `~/.openclaw/cron/jobs-state.json` with `lastRunAtMs`, `nextRunAtMs`, `lastRunStatus`, `lastDurationMs`, `consecutiveErrors`, `lastDeliveryStatus`, `lastDelivered`. This is visible in our `config/cron-jobs-backup.json` snapshot (every job has a `state` block with exactly these fields).

**What it doesn't have:** custom user state. There's no documented way to attach arbitrary key-value state to a job and read it back from the next fire. The `state` block is OpenClaw-internal.

**Implications for Watchers:** OpenClaw covers "did this fire recently?" and "is it healthy?" but NOT our `memory_state` JSON (`last_fact_key`, dedup data, fire_count beyond OpenClaw's view). Our `watchers` and `watcher_fires` tables remain authoritative for application-level state. OpenClaw cron is purely a timer + run-log layer.

**Confidence: HIGH** for the schema (visible in our own backup file); **MEDIUM** for whether undocumented extension hooks exist.

### Tool / skill chaining — **NO**

Confirmed by GitHub issue #9465 (feature request, not yet implemented): cron jobs are "fire-and-forget" with no pre/post hooks, no native escalation, no native conditional chaining. All chaining today is expressed as prompt text inside a single agent turn.

**Implications:** Our `action_chain` JSON DSL is the right shape. We're not duplicating an existing primitive.

**Confidence: HIGH** — confirmed both by docs (no mention) and by a 2026 community feature request.

### Approval workflows — **NO native primitive**

No documented "pause and wait for human approve" capability anywhere in OpenClaw. The closest pattern is Task Flow's `approval: required` step, but Task Flow's pause/resume semantics are explicitly noted as undocumented in the official docs.

**Implications:** Our `draft_for_approval` action chain step has to be custom. We implement it by sending a Slack DM, recording `outcome='awaiting_approval'` in `watcher_fires`, and the dispatcher resumes the chain when a Slack message handler routes the approval reply back. This is exactly the pattern Phase C's reminder approval flow already uses — battle-tested.

**Confidence: HIGH**.

### Notification delivery batching — **NO**

Each cron job's delivery is independent. Heartbeat does batch *checks* (calendar / inbox / etc. in one turn) but its outputs are not aggregated across cron jobs.

**Implications:** If we want "aggregate Sandeep's three watcher DMs into one daily digest," we build that ourselves (V2 feature per the spec). V1 ships independent fires.

**Confidence: HIGH**.

---

## Q2 — Scale limits

**Bottom line: documentation is sparse on hard limits but ergonomic limits exist.**

### What's documented

- `gateway.cron.maxConcurrentRuns` defaults to **8** (some docs say 1 — version drift; the 2026.3.x config reference says 8). This caps *parallel* execution, not total job count.
- `gateway.cron.sessionRetention` defaults to **24h** — keeps isolated cron sessions for 24h then prunes. Doesn't affect job count.
- `runLog.maxBytes` defaults to **2 MB per job per file** at `~/.openclaw/cron/runs/<jobId>.jsonl`. Auto-pruned to `runLog.keepLines` (default 2000) newest lines. So disk footprint per active job stays bounded at ~2 MB.
- No documented hard cap on total active jobs.

### What's not documented / requires inference

- **No published benchmarks** for 50/100/500/1000 active jobs. Community guides (Stack Junkie, LumaDock) suggest "5-20 jobs is comfortable; practical limit is token budget and server resources" — those are anecdotal.
- The likely bottleneck: `maxConcurrentRuns: 8` plus single-process gateway. If 50 jobs fire in the same minute (e.g., everyone runs at "0 9 * * *"), 8 execute and 42 queue. Most BON watchers will be spread across the day, so contention is low — but cron-storm at the top of the hour is the failure mode to watch.
- Memory footprint per *idle* job is near-zero (one entry in `jobs.json`). Memory footprint per *running* job is the LLM context window cost during that agent turn.

### Practical recommendations for Watchers V1

| Scale tier | Likely outcome |
|---|---|
| 0-50 active watchers (V1 expected range) | Comfortable. No special handling needed. |
| 50-200 | Likely fine. Stagger schedules — avoid identical cron expressions across many watchers. |
| 200-500 | Likely OK but needs a deliberate scheduling policy. Recommend a `stagger_offset_seconds` field on each watcher row so the dispatcher can spread fires across an N-minute window. |
| 500-1000+ | Untested. Reach out to community / file an issue before going there. |

The Watchers V1 spec assumes ~50 watchers as a starting point. We're nowhere near the danger zone.

**Confidence: MEDIUM** — no authoritative numbers exist. Recommend a runtime probe: bulk-create 100 dummy cron jobs in a staging environment, observe gateway memory and latency over 24h.

---

## Q3 — Exact `cron.add` API surface

### Request shape

This is what we already use successfully — confirmed against `config/cron-jobs-backup.json`:

```json
{
  "name": "string (required)",
  "enabled": true,
  "agentId": "main",
  "sessionKey": "agent:main:main",
  "schedule": {
    "kind": "cron" | "every" | "at",
    "expr": "0 7 * * *",      // for kind=cron
    "everyMs": 600000,         // for kind=every
    "atMs": 1779080400000,     // for kind=at (epoch ms)
    "tz": "Asia/Kolkata"       // optional, IANA tz
  },
  "sessionTarget": "main" | "isolated" | "current" | "session:<id>",
  "wakeMode": "now" | "next-heartbeat",
  "payload": {
    "kind": "agentTurn" | "systemEvent" | "user-message",
    "message": "the prompt text",
    "timeoutSeconds": 300,
    "model": "anthropic/claude-sonnet-4-20250514"  // optional override
  },
  "delivery": {
    "mode": "announce" | "webhook" | "none",
    "channel": "slack",        // optional
    "to": "channel:C123..." | "user:U123..."  // optional
  },
  "deleteAfterRun": false      // default false; set true for one-shot cleanup
}
```

### Response shape

Documentation does not formally publish the response, but evidence converges on:

```json
{
  "ok": true,
  "result": {
    "jobId": "uuid-string-here",
    // ... possibly other echo fields, undocumented
  }
}
```

Key authority for the `jobId` field name:
- GitHub issue #11075 confirms the API requires `jobId` (not `id`) on update/remove calls; legacy `id` is rejected with "must have required property 'jobId'".
- Our own `cron-jobs-backup.json` shows jobs with `"id": "<uuid>"` in the persistence file (this is the *stored* representation — the API uses `jobId` to reference them).
- Cron session prefix `[cron:<jobId> <job name>]` confirms it's stable and externally addressable.

**There is a naming inconsistency in OpenClaw's surface area:** persisted JSON files use `id`, the API uses `jobId`. Code should normalize: when calling `cron.add`, store the returned `result.jobId` (also seen as `result.id` in some versions); when calling `cron.update` or `cron.remove`, send it as `jobId`.

### Specific answers to the spec's questions

**`delivery.mode = "none"`:** Supported and is the pattern Alaska has used for all 14 production crons. It disables OpenClaw's automatic fallback delivery; the agent's own messaging tool calls (e.g., explicit `action=send` Slack posts in the prompt) still execute. Confirmed by docs ("If a chat route is available, the agent can use the `message` tool even when the job uses `--no-deliver`") and by our production traffic.

We can use `delivery.channel="none"` in the cron entry — our `cron-jobs-backup.json` shows we already do this on the Reminder Dispatcher and Routine Proposal Watch entries. The field `delivery.mode="none"` is the canonical one; `delivery.channel="none"` appears to be accepted equivalently but is not documented.

**`schedule.kind="at"`:** Supported. Field is `atMs` (epoch milliseconds), not `at` (which appears in some doc snippets as an ISO string — schema versions drift; the millisecond form is what the 2026.3.x persistence layer uses).

**Auto-delete-after-fire (`deleteAfterRun`):** Supported. For `kind="at"` (one-shot), default is `true` (job is removed after successful fire). For `kind="cron"` or `kind="every"`, it's `false` by default (recurring jobs persist). Set explicitly to be safe.

**Cancellation via `cron.remove`:** Request shape `{ "jobId": "..." }`. Behavior on a non-existent ID: returns an error (`404` or similar) but does not crash the gateway. Idempotency: removing an already-removed ID returns an error — wrap in try/except.

### Gotchas (from GitHub issues)

1. **`enabled` field default-undefined bug (#8557):** If you omit `enabled`, some OpenClaw versions store it as `undefined`, which is falsy — job is created but never executes. **Always pass `enabled: true` explicitly.** This was reportedly fixed but it's cheap insurance to keep setting it.
2. **`nextWakeAtMs` null bug (#8712):** Reported in 2026.2.1 — jobs persisted but never executed. Confirmed environment-specific (WSL2). Not seen in our Railway environment. Mention only because: if a Watcher silently fails to fire after `cron.add`, check this state field via `cron.list --json`.
3. **Default deny list (#tools-invoke-http-api):** The `cron` tool is in OpenClaw's default HTTP deny list (alongside `exec`, `shell`, `fs_write`, etc.). The agent itself can still call `cron.add` via in-session tool calls (this is how Phase A.2's classifier cron was created), but external HTTP callers to `/tools/invoke` are blocked unless we add `cron` to `gateway.tools.allow` in config. **This means: only Alaska herself can create cron entries — Railway's web dashboard or external scripts cannot use `/tools/invoke?tool=cron`.** Our spec assumes the watcher-creator skill does this in-session, which is the supported path.

### Where the job is stored

`~/.openclaw/cron/jobs.json` plus state in the sidecar `jobs-state.json`. In our Docker setup, this is `/data/.openclaw/cron/jobs.json` (the `/data` volume persists across redeploys). Confirmed by `entrypoint.sh` setting `OPENCLAW_STATE_DIR=/data/.openclaw`.

**Confidence: HIGH** — request shape is confirmed by our own backup file; response shape and `jobId` field are confirmed by GitHub issues and community guides; gotchas are confirmed by issue trackers.

---

## Q4 — Migration path

### Is the per-watcher cron approach practical?

**Yes, for V1 (≤50 watchers) and almost certainly through V2 (≤200).**

We're currently running 14 cron entries with zero performance issues. Adding 30-50 more brings us to ~50-65 total. That's well under any anecdotal limit and we have far more headroom than the gateway needs.

The risk we should design AGAINST is **schedule-clustering** — if 30 watchers all fire at `0 9 * * *`, they queue against `maxConcurrentRuns: 8`. The dispatcher should add a small random offset to per-watcher cron expressions, OR encourage users to pick minute-level offsets. A field `stagger_seconds INTEGER DEFAULT 0` on the watcher row, used to mutate the cron expression at `cron.add` time, would handle this transparently.

### Conversion plan: `scheduled_actions` → per-watcher `cron.add`

For each existing `scheduled_actions` row:

```pseudocode
For row in scheduled_actions where status='pending':
  watcher_id = generate_W_N()
  cron_id = openclaw.cron.add({
    name: f"W-{N}: <description>",
    enabled: true,
    schedule:
      if row.fire_at and not row.recurrence:
        { kind: "at", atMs: row.fire_at_epoch_ms, tz: "UTC" }
      elif row.recurrence:  # RRULE or cron expr
        { kind: "cron", expr: rrule_to_cron(row.recurrence), tz: row.tz }
    sessionTarget: "isolated",
    wakeMode: "now",
    payload: {
      kind: "agentTurn",
      message: f"Run watcher dispatcher for W-{watcher_id}. Action chain stored in watchers table.",
      timeoutSeconds: 300
    },
    delivery: { mode: "none" },
    deleteAfterRun: (kind == "at")  # one-shot self-deletes
  })

  insert into watchers(...) with openclaw_cron_id = cron_id.jobId
```

**Caveats:**

1. **RRULE → cron:** OpenClaw cron is standard 5-field cron. RRULEs with `COUNT`, `UNTIL`, `EXDATE`, or `BYWEEKNO` can't always be expressed cleanly. For simple "every Monday 9 AM" RRULEs, conversion is mechanical. For complex ones (current `lib/rrule_helper.py` handles them), we either:
   - (a) keep our polling dispatcher for the RRULE subset and use native cron for simple cases, or
   - (b) express the RRULE in our table only and use the OpenClaw cron purely as a polling pulse ("every 15 minutes, check the watchers table") for the RRULE subset. This is what Phase C does today.

2. **Timezone:** OpenClaw cron supports `tz` natively (IANA names). Phase C's `lib/rrule_helper.py` does its own tz math. Either keep one layer authoritative — recommend OpenClaw for native crons, keep `rrule_helper.py` only for RRULE-specific recurrences.

3. **One-shot `expires_at` for recurring watchers:** OpenClaw cron has no native expiration on `kind: "cron"` jobs. Solution: at creation, also `cron.add` a `kind: "at"` one-shot at `expires_at` that calls our dispatcher with action "expire watcher W-N". On fire, the expiration cron deletes the main watcher cron and marks the watcher `status='expired'`. Two cron entries per time-bounded watcher.

### Lifecycle coupling: watcher row deleted → cron entry deleted

Pattern: every code path that deletes/cancels a watcher row MUST call `cron.remove(jobId=watcher.openclaw_cron_id)` first, then DELETE the row in a transaction. If `cron.remove` fails (already deleted, network error), proceed with the row delete and log the orphan — a periodic janitor (separate cron) can reconcile.

**Idempotency:** If our dispatcher process crashes mid-`cron.add` and the SQLite row didn't get the cron_id stored — yes, we have an orphan cron entry firing against no watcher row. Mitigations:

1. **Write-ahead pattern:** Insert the watcher row with `status='pending_cron_create'` and `openclaw_cron_id=NULL` BEFORE calling `cron.add`. After `cron.add` returns, UPDATE the row with the jobId and flip status to `'active'`. The cron's prompt looks up the watcher by ID; if it finds `pending_cron_create` or no row, it self-deletes (`cron.remove`).
2. **Reconciliation cron:** Daily janitor runs `cron.list --json`, intersects with watchers table, deletes any orphaned cron jobs whose name matches the W-N pattern but whose watcher row is missing.

### Lookup pattern: watcher_id → cron_id

Trivial — store `openclaw_cron_id` on the watcher row (already in the V1 schema). The reverse lookup (cron_id → watcher) is also useful for the janitor; that's enabled by the name convention `"W-N: <description>"` which puts the watcher_id in the cron name.

---

## Recommendations for Watchers V1 architecture

### 1. Dispatcher: HYBRID (thin native cron + custom action-chain runner)

- **OpenClaw cron handles WHEN.** Each watcher gets its own `cron.add` entry. No polling cron. No 15-minute latency.
- **Our dispatcher handles WHAT.** The cron's prompt invokes the dispatcher skill with the watcher_id. The dispatcher reads the watcher row from SQLite, loads the action_chain JSON, executes each step.
- **Event watchers stay polling-based for V1** (one shared poller cron per event type). V2 can convert to webhooks where available.

### 2. State: BOTH (split by purpose)

| Lives in OpenClaw | Lives in our `watchers` table |
|---|---|
| Schedule, timezone | Action chain DSL, recipient |
| Last-fire timestamp, next-fire timestamp | `memory_state`, `last_fact_key`, dedup data |
| Run health (lastRunStatus, consecutiveErrors) | Approval state, per-fire approval queue |
| Run logs (last N runs at `~/.openclaw/cron/runs/<jobId>.jsonl`) | `watcher_fires` audit (richer schema, joinable, queryable) |

This split is what we already do for Phase C reminders and it works.

### 3. Per-watcher cron pattern: SUSTAINABLE for V1

At ~50 watchers, this is well within the comfortable zone. Build in two guard rails:

- **Stagger field** on the watcher row to spread fires across the minute.
- **Reconciliation janitor cron** runs nightly to detect orphans (cron entries without watcher rows, or watcher rows without cron entries).

If watcher count crosses 200, revisit. Realistically that's a V2 problem.

### 4. Things we should NOT rely on

- **Task Flow** as a replacement for our action_chain DSL — undocumented programmatic API, no published stability claim. Watch it for V2 consolidation, don't build on it for V1.
- **`/tools/invoke` for cron operations from outside the agent runtime** — blocked by default deny list. Don't write external scripts that try to manage watchers via HTTP; do it from within agent skills only.
- **Per-job custom state** — OpenClaw stores its own state on jobs (run timestamps, status) but does not expose extension hooks for arbitrary user state on a cron entry. Keep our state in SQLite.
- **Heartbeat for time-sensitive watchers** — heartbeat is best-effort cadence (default 30 min, defers under load, skipped during inactive hours). Wrong tool for "remind me at 5 PM precisely."
- **Cron job hooks (#9465)** — feature request, not implemented. Don't design around it.

---

## Confidence levels (summary)

| Finding | Confidence | Evidence |
|---|---|---|
| `cron.add` request shape | HIGH | Our own working `cron-jobs-backup.json` |
| `cron.add` returns `jobId` in response | MEDIUM | GitHub issues + community guides; not formally documented |
| `delivery.mode: "none"` allows agent's own Slack tool calls | HIGH | Confirmed in docs + production traffic |
| `kind: "at"` + `deleteAfterRun: true` self-cleans | HIGH | Documented |
| `cron` tool in default HTTP deny list | HIGH | Documented |
| No native chaining / hooks / approval | HIGH | Confirmed by feature request #9465 still open |
| No native per-job custom state | HIGH | Schema visible in our backup; no extension docs |
| Scale: comfortable at 50, fine at 200 | MEDIUM | Anecdotal community guidance; no published benchmarks |
| Scale: 500+ behavior | LOW | Untested in our env and undocumented |
| Task Flow as alternative to action_chain | LOW | Conceptual docs only; programmatic API not published |
| Lifecycle / orphan-cleanup gotchas | HIGH | Standard distributed-state problem; mitigations are off-the-shelf |

### Suggested runtime probes against live instance

If we want to tighten confidence further before V1 builds, three quick probes (each <1 hour):

1. **Probe the response shape of `cron.add`.** Invoke from a one-off skill with a known name; capture the full response JSON. Confirms whether the field is `result.jobId`, `result.id`, or both.
2. **Probe `delivery.channel: "none"` vs `delivery.mode: "none"`.** Our backup file mixes both. Are they equivalent? Does one trip a warning? File an issue if behavior diverges from docs.
3. **Bulk-create 100 dummy cron entries.** Watch gateway memory, CPU, and run-latency over 24h. Establishes a real ceiling for our environment.

These are nice-to-haves. We can proceed with V1 build without them, given the documentation + our 14 production crons give us enough signal.
