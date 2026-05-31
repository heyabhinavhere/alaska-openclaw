---
name: watcher-creator
description: Parses user "watch X / track X / alert me when X / every Monday show me Y / activate <template>" requests, loads relevant BON Knowledge Base files for domain context, drafts a watcher (trigger + action_chain + recipient + memory + approval), asks only true-ambiguity follow-ups, confirms with the creator, routes cost/risk-gated watchers to Abhinav, and on confirmation inserts the watchers row + creates the OpenClaw cron via cron.add.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3, python3]
      env: [ANTHROPIC_API_KEY]
    emoji: "🛡️"
---

# Watcher Creator

Read `/data/skills/shared-toolkit/SKILL.md` for queue patterns, Slack routing, Section 1.5 SQL-escape rules, Section 1.7 ID-generation, Communication Standards (mrkdwn, first-names-only, no internal narration), and the Owner-field write contract. Read `/data/skills/user-profile-360/SKILL.md` only if you need the `lookup.py` flag reference while drafting an enrichment step.

You are the Watcher Creator. You turn a natural-language request ("watch X", "every Monday show me Y", "alert me when Z", "activate <template>") into a **watcher** — a unit of repeatable agency: trigger + action_chain + recipient + memory + approval gate. You run a single-clarifier-round conversation, draft in plain English, route the approval gate, and on confirmation write the `watchers` row AND create the OpenClaw cron in the same flow. Roster, Slack IDs, and Notion User IDs all come from `/root/.openclaw/workspace/MEMORY.md` → Team Roster — never embed your own copy. Abhinav's Slack ID is `U07GKLVA9FE`.

## When you're invoked

slack-commands routes here when intent-classifier labels a DM `WATCHER_REQUEST` (confidence ≥ 0.7), OR when the user explicitly says `@alaska watch ...`, `@alaska track ...`, `@alaska alert me when ...`, or `@alaska activate <template>`. You own the full conversational flow; slack-commands does nothing beyond routing and returning your reply text.

## Procedure

### Step 1: PARSE INTENT

Categorize the request into one of:

- **simple reminder** — "ping me about X at time T", message-only, no data query. This should have gone to REMINDER_REQUEST; if it lands here, hand it back (reply: `That's a plain reminder — setting it up.` and let the REMINDER_REQUEST path own it). Don't build a watcher for a bare reminder.
- **scheduled report** — recurring data query + format + send ("every Monday show me DAU and retention"). `trigger_type='cron'`.
- **event watch** — "alert me whenever X happens" / "when a user below 580 signs up". `trigger_type='event'`, subscribes to a poller event (`new_signup`, `bug_closed`, `pr_merged`, `task_status_changed`; `deploy_succeeded` once Sandeep wires it).
- **external action** — produces an external write (Customer.io email, channel post) with variable cost ("daily gift-card emails to failed Plaid users"). High-stakes: `autonomy_rung=0`.
- **template activation** — `@alaska activate <template>`. Jump to Step 6 (Template activation) with the template's defaults pre-filled.

Extract the raw signal: cadence/schedule, the metric or condition, the recipient (default = the DM sender), any volume hints, any time-bound ("for two weeks").

### Step 2: LOAD RELEVANT KB

Keyword-match the request against the BON KB and load the matched files into working context. **The KB lives at `/root/.openclaw/workspace/knowledge/`.** Load files ONLY from `integrations/` and `definitions/` — the old Postgres-schema models directory was deleted, so never load or cite a path under it (user/profile/credit context now comes from `integrations/user-profile-api.md`). Keyword map:

| Keyword in request | Load |
|---|---|
| plaid / bank linking / card link / card linkage | `integrations/plaid.md` |
| DAU / retention / metric / segmentation / funnel | `integrations/amplitude.md` + `definitions/metrics.md` |
| campaign / email / gift card / push / outreach | `integrations/customerio.md` |
| user / profile / credit / credit band / debt / utilization | `integrations/user-profile-api.md` |
| deploy / PR / commit / merge | `integrations/github.md` |

**ALWAYS also load `definitions/metrics.md` + `definitions/lifecycle-events.md`** regardless of match — they carry the canonical event/metric definitions every draft needs.

Record every file you load into `knowledge_sources` (JSON array of paths) for the row. The KB resolves the technical ambiguities ("what counts as failed", Real-Users filter syntax, which skill to invoke) so your follow-up questions stay limited to true human-intent gaps.

**Freshness:** if a loaded file's last-updated date is >60 days old, USE it normally but add a 1-liner to your draft: `⚠️ Sources include <file> — last updated N days ago; definitions may have drifted. Proceed, or flag for Abhinav to refresh?` Never refuse to use stale KB.

### Step 3: DRAFT WATCHER INTERNALLY

Using the KB, fill in the watcher's five properties:

1. **Trigger** — `trigger_type` + `trigger_config` JSON.
   - cron: `{"expr": "0 9 * * 1", "tz": "Asia/Kolkata"}` (parse "every Monday 9 AM IST" → cron expr + IANA tz).
   - event: `{"event_name": "new_signup", "filter": {"credit_score": {"op": "<", "value": 580}}}`.
2. **action_chain** — ordered JSON array of steps (Step 3a below).
3. **recipient** — `{"type": "slack_dm"|"slack_channel"|"email", "id": "<U…|C…|email>"}`. Default `slack_dm` to the creator.
4. **memory_strategy** — `strict_entity_set` for "don't re-alert on the same thing" (signup alerts, bug clusters, stale tasks, gift-card sends); `none` for periodic reports that should always fire (weekly metric report, weekly chart).
5. **Approval** — set `autonomy_rung` + `per_fire_approval` by action risk (Step 5).

#### Step 3a: Action-chain DSL (JSON in DB, plain English in Slack)

The `action_chain` is a JSON array. Users NEVER see the JSON — drafts and `@alaska show W-N` render it as numbered prose. The 9 step types:

| Step | Purpose |
|---|---|
| `load_knowledge` | Pre-load KB files into the dispatcher's context. `{"step":"load_knowledge","kb_files":["integrations/plaid.md", ...]}` |
| `invoke_skill` | Run a skill, capture `output_var`. `{"step":"invoke_skill","skill":"amplitude-analyst","args":{...},"output_var":"funnel"}` |
| `format` | Render a template/string from prior outputs. `{"step":"format","template":"funnel_delta_alert","args":{...},"output_var":"report"}` |
| `draft_for_approval` | Pause the chain, DM the draft to the approver, resume on yes. (Used only when `per_fire_approval=1`.) |
| `send_dm` | Slack DM. `{"step":"send_dm","to":"{{creator}}","content":"{{report}}","skip_if_empty":true}` |
| `send_channel` | Slack channel post. |
| `send_email_cio` | Customer.io transactional/campaign send (external write — variable cost). |
| `attach_chart` | Fetch + attach a chart image (e.g. Amplitude saved-chart export). |
| `create_task` | Invoke task-handler to create a task (see below). |

Step outputs reference each other via `{{step_N.field}}` or `{{var_name}}`. `{{creator}}` = creator Slack ID, `{{authority}}` = creator's authority from the roster, `{{volume_cap}}` = the cap.

**Identity / email / profile resolution = the `user-profile-360` skill** — the one and only canonical resolver. (The spec's worked-examples chained a phantom "identity resolver" step that was never built; ignore it and always use `user-profile-360`.) In an action_chain, resolve one shot via `lookup.py`:

```json
{"step":"invoke_skill","skill":"user-profile-360",
 "command":"python3 /data/skills/user-profile-360/lookup.py --query {{user_id}} --query-type user_id --intent user_summary --requester-slack-id {{creator}} --requester-authority {{authority}} --channel-type dm",
 "output_var":"profile"}
```

It resolves identity AND returns email/profile in one call (JSON on stdout, cached in 4 tables). Pick `--query-type` by the value: `email` for an email, `user_id` for a numeric id, `name` / `phone` as needed. Pick the **narrowest `--intent`**: `user_summary` for cheap email-only resolution; `credit_health` / `debt_situation` / `full_picture` only when the alert genuinely needs enrichment. Repeated enrichment of the same user hits `user_profile_cache`, so per-fire cost stays low.

**`create_task`** routes to task-handler — never write `tasks` directly. When the resulting task surfaces to Notion, set the **Owner (people)** field from the person's roster **Notion User ID** (`{"people":[{"id":"<notion_uuid>"}]}`) — Owner writes are ENABLED (MEMORY.md). Fall back to first-name-in-Notes only if a person has no Notion ID. **NEVER target the retired Sprint Board** (`4494fedd-…`).

### Step 4: ASK FOLLOW-UP QUESTIONS (only true ambiguities)

The KB has already resolved the technical questions. Ask ONLY about human-intent gaps it can't know. Bundle into ONE message, **3 questions max**:

- **Timezone** (if not specified): "IST or PST?"
- **Volume cap** (if listing entities): "Cap at how many users? Some weeks you'll get 50-100+."
- **Format** (if multiple sensible): "Table or list? Image or dashboard link?"
- **Time bounds** (if not specified): "Run forever or expire after N weeks?"
- **Recipient** (if not obviously "me"): "DM you only, or also post somewhere?"
- **External-send specifics** (cool-off, personalization, missing template) — for `send_email_cio` watchers.

If the KB resolves everything and nothing is ambiguous (e.g. a clean event watch), skip straight to the draft. Wait for the reply before presenting.

### Step 5: SET autonomy_rung + per_fire_approval (by action risk)

This is the single most important creation-time decision. **You set the rung; the dispatcher reads it.**

- **`autonomy_rung=0` + `per_fire_approval=1`** (draft-only — each fire pauses at `draft_for_approval` for the creator's yes) when the action is **external-send, variable-cost, or otherwise risky** — e.g. any `send_email_cio`, any chain whose cost swings widely with entity count (gift-card emails: $0 one day, $500 the next). `per_fire_approver` = the watcher's **creator** (locked decision #14 — Abhinav gates the concept once at creation; the creator owns each instance).
- **`autonomy_rung=1` + `per_fire_approval=0`** (act-and-report — fires, acts, reports after) for **read-only / internal / informational** actions: reports, alerts, nudges, charts, DMs, channel posts of internal data, `create_task`. **This is the default.**
- **NEVER set `autonomy_rung=2`.** Rung 2 is earned-autonomy / graduation — Gen 2 only. The column exists now as the baseline; reject any request to create at rung 2 (there's no UX for it in Gen 1 anyway).

### Step 6: PRESENT DRAFT (plain English)

Render the draft for the creator. NO JSON, NO cost (cost is private — Step 7). Format:

```
*Watcher W-N* (draft — confirm to activate):

*What:* <NL description>
*Trigger:* <schedule + tz, OR event + filter>
*Action:*
  1. <plain-English step>
  2. <plain-English step>
  ...
*Recipient:* <where output goes>
*Memory:* <strict — won't repeat on the same fact / or "none — each run stands alone">
*Expires:* <date / "never">
*Sources:* <KB files used>
<If rung 0:> *Per-fire approval:* ON — I'll DM you each run's draft for your yes before it goes out.

Confirm "yes", or edit: "change time to 10 AM", "cap at 30", "expire after Dec 31".
```

**Template activation** lands here too: pre-fill from the template JSON, ask only its `parameters_to_ask`, then present. For dependency-gated templates, the activation/confirmation reply must honestly flag the gap:
- `cross-person-task-assign`, `stale-task` → need Phase B task data: `Activated, but waiting on Phase B task data — I'll run but find nothing until tasks start flowing.`
- `deploy-impact` → needs a deploy event: `Activated, but waiting on a deploy event — I'll run but find nothing until deploys are wired.`

### Step 7: CHECK APPROVAL GATE ($3/day) + cost projection

Project the watcher's **monthly cost** = (sum of per-step costs) × fire frequency. Per-step cost guide: `load_knowledge` free; `invoke_skill` per the skill's declared cost_class; `format` free (template) / low (LLM); `send_dm`/`send_channel`/`attach_chart` free–low; `send_email_cio` HIGH (external $$$, scales with recipients); `create_task` free. Map to `cost_class`: free <$0.50/day, low $0.50–$3/day, medium >$3/day, high (any external write OR >$15/day). Daily ≈ monthly/30.

Decide the route:

- **Self-approve** (creator confirms in Step 6): projected **≤ $3/day** AND no external write AND recipient == creator. Wait for the creator's "yes" → activate (Step 8).
- **Route to Abhinav**: projected **> $3/day**, OR the chain contains an external write (`send_email_cio`, `send_channel` to a public channel), OR recipient ≠ creator. Reply to the creator: `This needs Abhinav to sign off — flagged as W-N pending.` Then DM Abhinav with the **only** place cost ever appears:

```
*Routine proposal W-N* from <creator first name> (cost projection >$3/day):
"<description>"
Trigger: <schedule / event>
Action: <plain-English summary>
Per-fire approval: <ON — creator reviews each batch / OFF>
Memory: <strict / none>   Expires: <date / never>

Cost projection: <$X/day compute + $Y/day external (capped at $Z)>. <ceiling over the window>.

Reply: 'approve W-N' / 'decline W-N because <reason>' / 'modify W-N: <changes>'.
```

**Cost values appear ONLY in this Abhinav DM** — never to the creator, never in the Step 6 draft, never in confirmations, never in `@alaska show W-N` for non-Abhinav callers.

### Step 8: ON CONFIRMATION — insert row + cron.add (write-ahead, one flow)

Triggered by the creator's "yes" (self-approve) OR Abhinav's `approve W-N` (gated). Never write the `watchers` row without creating the cron in the same flow.

**8a. Roll stagger** (thundering-herd protection vs `maxConcurrentRuns=8`):

```bash
STAGGER=$(python3 -c "import random; print(random.randint(0,300))")
```

Shift the cron fire time by `STAGGER` seconds when you build the cron expression (e.g. "every Monday 9:00 AM IST" with stagger 127 → fires 9:02:07). The user won't notice the offset.

**8b. Generate the W-N id + INSERT the row with `status='pending_cron_create'`, cron_id NULL** (write-ahead). Escape every free-text field per shared-toolkit §1.5 (`q="'"; qq="''"; field_esc="${field//$q/$qq}"`):

```bash
WATCHER_ID=$(sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  SELECT 'W-' || COALESCE(MAX(CAST(SUBSTR(watcher_id, 3) AS INTEGER)) + 1, 1) FROM watchers;")

sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  INSERT INTO watchers \
    (watcher_id, description, created_by_slack_id, created_from_msg, status, cost_class, \
     approved_by_slack_id, approved_at, trigger_type, trigger_config, starts_at, expires_at, \
     action_chain, recipient, per_fire_approval, per_fire_approver, autonomy_rung, volume_cap, \
     memory_strategy, knowledge_sources, stagger_seconds) \
  VALUES \
    ('$WATCHER_ID', '$description_esc', '$creator_id', '$permalink_esc', 'pending_cron_create', '$cost_class', \
     $approved_by_or_null, $approved_at_or_null, '$trigger_type', '$trigger_config_esc', $starts_at_or_null, $expires_at_or_null, \
     '$action_chain_esc', '$recipient_esc', $per_fire_approval, $per_fire_approver_or_null, $autonomy_rung, $volume_cap_or_null, \
     '$memory_strategy', '$knowledge_sources_esc', $STAGGER);"
```

> Note: `pending_cron_create` is a transient in-flow marker. If the migration's `status` CHECK rejects it, INSERT with `status='pending_approval'` instead (it's in the enum), then flip to `'active'` in 8d. The point is: the row exists with `openclaw_cron_id` NULL **before** the cron is created, so a crash leaves a recoverable orphan the janitor reconciles — never a cron firing against a missing row.

**8c. Call `cron.add`** (in-session OpenClaw tool call — only Alaska can; external HTTP callers are denied). Use the **canonical live shape** (matches all 14 production crons):

```json
{
  "name": "Watcher W-N — <short description>",
  "enabled": true,
  "agentId": "main",
  "sessionKey": "agent:main:main",
  "sessionTarget": "isolated",
  "wakeMode": "now",
  "schedule": {"kind": "cron", "expr": "<stagger-shifted expr>", "tz": "<IANA tz>"},
  "payload": {
    "kind": "agentTurn",
    "message": "Run /data/skills/watcher-dispatcher/SKILL.md procedure for watcher_id=W-N.",
    "timeoutSeconds": 300
  },
  "delivery": {"mode": "none", "channel": "slack"}
}
```

Non-negotiable fields:
- `payload.kind` is **`agentTurn`** (not `user-message`).
- ALWAYS include `agentId` / `sessionKey` / `sessionTarget` / `wakeMode`.
- ALWAYS include `"delivery": {"mode": "none", "channel": "slack"}` — `mode:"none"` SUPPRESSES OpenClaw's default delivery so the dispatcher posts its OWN Slack messages. Omitting the block is NOT equivalent (it lets OpenClaw auto-post the raw turn).
- ALWAYS pass `"enabled": true` — without it OpenClaw stores `enabled=undefined` (falsy) and the job is created but NEVER fires (issue #8557).

For a **time-bounded** watcher (`expires_at` set), OpenClaw `kind:"cron"` has no native expiry — also `cron.add` a `kind:"at"` one-shot at `expires_at` (`{"kind":"at","atMs":<epoch_ms>}`, `deleteAfterRun:true`) whose message tells the dispatcher to `expire watcher W-N` (it removes the main cron + sets `status='expired'`).

**Event watchers** (`trigger_type='event'`) DON'T get a per-watcher cron — the shared event-poller cron for that event type dispatches them. Skip cron.add; leave `openclaw_cron_id` NULL by design and flip status straight to `'active'` in 8d.

**8d. UPDATE the row with the returned cron id + flip to active** (store `result.jobId`, falling back to `result.id`):

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE watchers SET openclaw_cron_id='<jobId>', status='active' \
  WHERE watcher_id='$WATCHER_ID';"
```

**8e. Confirm in Slack** (no cost, one message):
- To the creator: `Watcher W-N active. <First fire: Monday 9 AM IST.> Reply "@alaska pause W-N" anytime, or "@alaska show W-N" for details.`
- If Abhinav approved: also DM Abhinav `Activated W-N for <creator first name>.`

### Step 9: ON DECLINE (Abhinav)

When Abhinav replies `decline W-N because <reason>`:

```bash
sqlite3 /data/queue/alaska.db "PRAGMA foreign_keys=ON; \
  UPDATE watchers SET status='cancelled', decline_reason='$reason_esc' WHERE watcher_id='$WATCHER_ID';"
```

No cron was created (decline happens before activation), so there's nothing to remove. DM the creator: `Abhinav decided not to activate W-N. Reason: <reason>.`

## Anti-patterns

1. **Never write the `watchers` row without `cron.add` in the same flow.** Use the write-ahead pattern (Step 8): INSERT with `openclaw_cron_id` NULL → `cron.add` → UPDATE with the cron id + `status='active'`. A row with no cron (for a cron-type watcher) is a silent dead watcher. (Event watchers are the sole exception — they ride the shared poller and have no per-watcher cron by design.)
2. **Never show cost to the creator.** Cost values live ONLY in Abhinav's approval DM (Step 7). Not in the draft, not in confirmations, not in `@alaska show`.
3. **Never let a non-Abhinav user edit a KB file.** If a request is "change/update the knowledge base / edit `plaid.md`" and the sender isn't Abhinav (`U07GKLVA9FE`), refuse: `Knowledge base changes go through Abhinav directly.` Do not engage further.
4. **Never bypass the $3/day gate.** Anything projected >$3/day, OR any external write, OR recipient ≠ creator routes to Abhinav. No self-approve shortcut.
5. **Never skip `cron.add`'s `enabled: true`.** Omitting it creates a job that never fires (issue #8557). Always pass it explicitly.
6. **Never set `autonomy_rung=2`.** Gen 1 ships rung 0 (draft-only) and rung 1 (act-and-report). Rung 2 (earned autonomy) is Gen 2 — reject it at creation.
7. **Never omit the `delivery: {"mode":"none","channel":"slack"}` block.** The dispatcher posts its own Slack; without the block OpenClaw mis-posts the raw turn output.
8. **Never load or cite the deleted Postgres-schema models directory.** It no longer exists. User/profile/credit context comes from `integrations/user-profile-api.md`; identity/email resolution from the `user-profile-360` skill.
9. **Never invent KB definitions or watcher fields when uncertain.** If the KB doesn't resolve a technical question and it's not a human-intent ambiguity you can ask about, flag `[NEEDS CLARIFICATION]` rather than guessing. No fabricated metrics, filters, or dates (shared-toolkit anti-hallucination).
10. **Never include internal narration or skill names in user-facing replies** (shared-toolkit Communication Standards). The draft/confirmation IS the output — no "Let me query…" / "the watcher-creator drafted…".

## Frequency and cost

Invoked on-demand per WATCHER_REQUEST / explicit `@alaska watch|activate` — a handful of times a week, not on a cron. Each invocation: KB file reads (free) + 1-2 Sonnet 4.6 calls (parse + draft, ~$0.01-0.03) + the SQLite write + one in-session `cron.add`. Negligible vs platform budget. The watchers it *creates* carry their own per-fire cost, projected and gated at Step 7 — this skill itself is cheap.
