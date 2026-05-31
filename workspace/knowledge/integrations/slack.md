# Slack — Alaska's Primary Interface

**Last updated:** 2026-05-30 · **Status:** Draft. API facts verified against docs.slack.dev (May 2026) + our live config.

> **What this file is:** what Slack is for Alaska, how she authenticates, and **what she can DO with it** — the API methods, token model, channels, rate limits, formatting. The capability + reference layer.
> **What it is NOT:** how she *decides* what to say or *classifies* what comes in — that's workflow. Incoming-message classification lives in `skills/intent-classifier/`; identity resolution + message discipline live in `workspace/SOUL.md`; which agent posts where + when lives in `docs/alaska-operating-model.md`.

---

## What it is

Slack is **Alaska's primary interface to the team** — DMs for per-person interaction, channels for broadcasts (Daily Pulse, Risk Radar, pre-call sheets, alerts). The team keeps WhatsApp for casual chat; Slack is the operational PM surface.

## Auth + connection

Alaska is a Slack **bot**, connected through OpenClaw's Slack plugin (`channels.slack` in the gateway config: `enabled`, `dmPolicy: open`, `groupPolicy: open`, message `streaming: false`). The one **confirmed** credential is the bot token **`$SLACK_BOT_TOKEN`** (`xoxb-…`) — all Web API calls (post / DM / read / lookup) run as the bot user.

> **Connection mode + any extra tokens are NOT confirmable from the committed config.** A prior runtime audit recorded the live gateway running in **Socket Mode** with a **read-only user token** — but those are runtime-layer settings (in `/data/.openclaw/`, not in git), so treat them as *likely-but-unverified*; confirm against the live gateway before relying on the detail. (Socket Mode = a WebSocket, no public URL; it would also require an app-level token.) What's certain: the bot token above, via the OpenClaw plugin.

**Scopes** — these are the scopes the actions below *require* (general Slack); the bot's actual granted scopes aren't enumerated in-repo: post `chat:write`; read history `channels:history`/`groups:history`; list `channels:read`; DMs `im:write`/`im:history`; reactions `reactions:write`; user lookup `users:read`.

## Bot identity (don't confuse these)

Alaska is **a bot user** — and there's *also* a separate human-style account `alaska@boncredit.ai` (display "Don't touch") that is **NOT the bot**. They're easy to confuse; keep them separate. The exact user/bot IDs for both live in `workspace/MEMORY.md` § Bot / system accounts (single source — don't embed them here).

WhatsApp Cloud API is retained only as a dormant backup; Slack is the only path that matters.

## Channels

**The canonical channel list (all 12, with IDs) lives in `workspace/MEMORY.md` § Slack Channels** — the single source, verified via Slack `users.conversations`. Don't embed IDs here; look them up there and use the ID (not the name) in API calls. The model (membership = access, no allowlist):

- **Posts proactively to 4 output channels:** `#project-management` (meeting summaries / team work), `#alaska-daily-pulse` (Daily Pulse + Weekly Digest), `#alaska-alerts` (Risk Radar — NEW only), `#daily-standup` (pre-call sheets before the ~9 PM IST call).
- **Member of ~8 other team channels** (`#agentic-ai`, `#backend`, `#front-end`, `#bugs`, `#design`, … — full list in `MEMORY.md`). There she **observes** (Thinker hourly + intent-classifier) and **responds when mentioned or relevant** — she doesn't broadcast into them unasked.

*(Which agent posts/reads which channel, and when → `docs/alaska-operating-model.md`.)*

## Core methods — what Alaska can do

All are Web API POSTs with `Authorization: Bearer $SLACK_BOT_TOKEN`. This is Slack's *available* surface; the skills today actively use **`chat.postMessage`**, **`users.info`**, **file upload** (charts), and **threaded replies** (`thread_ts`) — the rest are capability she can reach for.

- **Post** — `chat.postMessage` (`channel`, `text`, `blocks`, `thread_ts`). Always send `text` even with `blocks` (notifications/accessibility). `chat.update` / `chat.delete` edit/remove a bot message by `channel`+`ts`. `chat.postEphemeral` shows a message to one user (can't be edited/deleted; vanishes on reload).
- **DM** — the canonical path is `conversations.open` with a user ID → returns an **IM channel ID** → post to *that*. Shortcut: `chat.postMessage` also accepts a `U…` user ID directly as `channel` and auto-opens the IM (what BON's helpers use).
- **Read** — `conversations.history` (channel messages), `conversations.replies` (a thread, by parent `ts`), `conversations.list` (enumerate channels).
- **React** — `reactions.add` (`channel`, `timestamp`, `name` without colons).
- **Users** — `users.info` (`profile.real_name` / `display_name` — used in the identity self-heal), `users.list`.

**Channel IDs (`C…`/`G…`/`D…`) ≠ user IDs (`U…`).** To DM, resolve user → IM channel first (or use the shortcut above).

## Rate limits

- **`chat.postMessage` ≈ 1 message/sec per channel** (short bursts allowed). Most other methods sit in tiers (~20–100+/min). Rate-limited calls return **HTTP 429 + `Retry-After`** — honor it.
- ⚠️ **Watch (verify Alaska's app classification):** since **2025-05-29**, *newly-created* non-Marketplace apps have `conversations.history` / `conversations.replies` throttled to **1 req/min, max 15 objects**. Internal/customer-built apps appear **exempt**, but Alaska (custom, created 2026, non-Marketplace) should be confirmed — if it applies, it bites thread/history reads (pre-call-brief, intent-classifier). Volume is low (~1 call/day, small team) so likely tolerable regardless.

## Formatting — mrkdwn (not Markdown)

| Right (mrkdwn) | Wrong |
|---|---|
| `*bold*` (single `*`) | `**bold**` → literal asterisks |
| `_italic_` | `*italic*` → renders bold |
| `~strike~` | `~~strike~~` |
| `` `code` `` / ```` ```block``` ```` | (same) |

Links use angle brackets `<https://url|label>` (no `[text](url)`); mentions `<@U…>` / `<#C…>`. **Block Kit** = structured JSON in a `blocks` array (section / divider / context / header / actions), max 50 blocks/message. *(House style — first names only, no visible Slack IDs/emails, message-length caps per output type, no process narration — is workflow: see `workspace/SOUL.md` § Slack Message Discipline.)*

## Known failure modes / gotchas

- **Bot must be a member of a channel** before it can post or read history (`not_in_channel` otherwise). Can't see private channels it isn't invited to.
- **Don't post to a user ID expecting a channel** in the canonical flow — resolve via `conversations.open` (or rely on the documented shortcut).
- **Posting too fast** → throttled/dropped; keep ~1 msg/sec per channel, back off on 429.
- **`**double asterisks**`** render literally — use single.
- **Ephemeral messages** can't be updated/deleted and vanish on reload — don't use them for state.
- **`thread_ts` must be the parent's `ts`**, not a reply's; add `reply_broadcast:true` to also surface to the channel.
- **Past silent-failure modes (patched v2.3):** cron `delivery.channel: webchat` sent output to an unreachable surface (fixed → `{mode:none}` + explicit `channel=slack` in-prompt); Follow-Through 6 PM had 27 silent `Message failed` errors. (Detail → `docs/alaska-operating-model.md` / `memory/system-evolution.md`.)

## How Alaska uses this → pointers (not duplicated here)

- **Incoming DMs/@-mentions** are classified into ~9 intents (TASK_CREATE/UPDATE/BLOCKER, STATUS_QUERY, REMINDER_REQUEST, STANDUP_REPORT, META_COMMENT, SHARING, MULTI_INTENT; `WATCHER_REQUEST` coming with Watchers V1) → `skills/intent-classifier/`.
- **Identity resolution + self-heal** (Slack ID → roster; `users.info` fallback; Sandeep ≠ Samder discipline) → `workspace/SOUL.md` + `workspace/MEMORY.md`.
- **Message discipline + standup-thread reply rules** → `workspace/SOUL.md` / `workspace/AGENT_RULES.md`.
- **Post/DM helpers + queue-first send** → `skills/shared-toolkit/SKILL.md`.
- **Which agent posts where + cadence** → `docs/alaska-operating-model.md`.

## People / ownership

- **Owns the Slack workspace + Alaska bot:** Abhinav (admin).
- **SME for the intent-classifier + Slack action wiring:** Sandeep.

## Open questions

- **[NEEDS ABHINAV]** Should other team channels (e.g. `#agentic-ai`) be added to the canonical list, or stay off-limits for Alaska posts?
- **[NEEDS ABHINAV/SANDEEP]** Confirm Alaska's Slack app classification re: the 2025 non-Marketplace history/replies throttle (above).
