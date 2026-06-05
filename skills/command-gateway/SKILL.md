---
name: command-gateway
description: >-
  The single /alaska command namespace. When a team member sends "/alaska
  <subcommand> ..." to Alaska in Slack (DM or @-mention) — e.g. "/alaska user
  2762", "/alaska help" — this skill runs the deterministic executor and relays
  its reply. P0 LIVE subcommand: `user <id>` (posts a 360° user case-file DOCX to
  the channel the command was run in). `help`/`ping` are live; `audit`/`brief`/`pmf`
  are honest "coming soon" stubs. Routing + execution are deterministic Python in
  lib/alaska_command_gateway/execute.py; this skill is the thin Slack adapter.
version: 0.2.0
metadata:
  openclaw:
    always: false
    emoji: "🛰️"
    requires:
      bins: [python3]
      env: [SLACK_BOT_TOKEN, BON_API_BASE_URL, BON_ADMIN_API_KEY]
---

# Command Gateway (`/alaska`)

One command namespace — `/alaska <subcommand> …` — so every Alaska capability is
discoverable and consistent. This is a **mention-command** (parsed from the
message body), exactly like `/audit` and `/pmf` — NOT a native Slack slash command
(that is a later UX upgrade; see "Native slash command" below). alaska-core and the
intent-classifier recognize the `/alaska` prefix (after any leading @-mention) and
hand control here.

## When this runs

A team member sends, in a DM or an @-mention:

```
/alaska user 2762        → post a 360° user case file (DOCX) to THIS channel
/alaska help             → list the available subcommands
/alaska ping             → liveness check
/alaska audit 1414       → (coming in P1 — currently an honest stub)
/alaska brief today      → (coming in P1)
/alaska pmf status       → (coming in P2)
```

## How Alaska runs this (one command, then relay)

All parsing, routing, validation, document rendering and Slack delivery are done
**deterministically in Python**. Your job is only to (1) extract the Slack
context, (2) run ONE command, (3) relay its `text`. Do not interpret or
re-route — the executor's routing table is the source of truth.

**Run the executor** (`/opt/lib` is already on `PYTHONPATH`; it is repeated here
only for clarity):

```bash
PYTHONPATH=/opt/lib python3 -m alaska_command_gateway.execute \
  --text "<everything after '/alaska'>" \
  --invoker "<slack user id of the sender>" \
  --channel "<slack channel id the message was sent in>" \
  --channel-type "<dm if the channel id starts with 'D', else channel>" \
  --thread-ts "<message thread_ts, ONLY if the command was sent inside a thread>"
```

Fill the fields from the inbound Slack event:
- `--text` — the message body with the leading `/alaska` (and any `@alaska`
  mention) removed. E.g. message `@alaska /alaska user 2762` → `--text "user 2762"`.
- `--invoker` — the sender's Slack user id (e.g. `U07GKLVA9FE`).
- `--channel` — the channel/DM id the message arrived in (e.g. `C0ANKDD664A` or `D…`).
- `--channel-type` — `dm` if `--channel` starts with `D`, otherwise `channel`.
- `--thread-ts` — include ONLY if the message was in a thread; otherwise omit it.

**Then relay the result.** The command prints JSON `{"ok": …, "text": "…", …}`.
**Post the `text` field back to the same channel/thread, verbatim.** It is already
written for a human (success confirmations, usage hints, and errors alike). Do not
add commentary, do not re-run, do not "fix" a `ok:false` reply — just relay it.

For the `user` subcommand the executor has already validated and **uploaded the
case-file DOCX to `--channel`** before returning; the `text` you relay is the
short confirmation that goes with the file ("📇 User case file for #2762 posted
above."). You do not upload anything yourself.

## What gets delivered, and where

`/alaska user <id>` posts the case-file DOCX **into the channel the command was
run in** (team decision, 2026-06-05 — clear and unambiguous over a private DM).
The profile contains **no SSN, DOB, or full address** — user-profile-360's
redactor strips those upstream — so the document is safe for the team's shared
channels. It does carry financial figures (score, debt, spending), which the team
treats as shared internal data; the file's own header still says "internal — do
not share externally." If `--channel` is omitted the executor generates but does
not deliver (and says so).

## Routing table — the one place to tune

The live routing table is **`ROUTES` in `lib/alaska_command_gateway/execute.py`** —
one row per subcommand: `subcommand → executor → {ok, text}`. To **add** a command,
add a row + a small `_cmd_*` function. To **change** what a command does, edit its
row. This is purely additive: it does **not** touch `intent-classifier` or
`alaska-core` (those only learn the `/alaska` *prefix*, once). Current rows:

| subcommand | status | what it does |
|------------|--------|--------------|
| `user <id>` | **live** | build + post a 360° user case file (DOCX) |
| `help` | live | list subcommands |
| `ping` | live | liveness check |
| `audit <id>` | stub → P1 | will run the `bon-internal-audit` skill |
| `brief [today]` | stub → P1 | daily brief / standup sheet |
| `pmf <q>` | stub → P2 | routes to `pmf-cohort-os` |

## Guarantees / failure handling

- The executor **never crashes the command** — a bad handler or a failed lookup
  returns a friendly `ok:false` `text` (e.g. "No BON user matches `404`."). Relay it.
- Document generation goes through a **validate-before-deliver gate**: a malformed
  DOCX is never posted; you'd get an `ok:false` explaining why, with the file kept
  server-side for retry.
- It is **read-only** with respect to BON systems: it reads the user profile (via
  `user-profile-360`) and writes only a file to the artifact store + Slack. It never
  messages the end user and never triggers Customer.io / SMS / email.

## Native slash command (future, not P0)

OpenClaw natively supports Slack slash commands in Socket Mode on our pinned
`v2026.5.28`. Turning `/alaska` into a *native* command (autocomplete, an ephemeral
ack) is a later UX upgrade: it needs a `channels.slack.slashCommand` config block
(schema to be confirmed live) + a one-line Slack-app change, and it would call this
same executor. The HTTP receiver in `verify.py` + `receiver.py` is the *other*
deployment shape (own-the-endpoint, Architecture B) and is **not** used here.
