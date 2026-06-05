---
name: alaska
description: >-
  The native /alaska Slack slash command. When a team member runs "/alaska
  <subcommand> <args>" (e.g. "/alaska user 2762", "/alaska help"), OpenClaw invokes
  THIS skill directly by name. It runs the deterministic command executor and
  relays the result. P0: "user <id>" builds a 360° user case-file DOCX and posts
  it to the #user-audit channel. Slack slash dispatch does not expose the
  originating channel to a command, so delivery is the fixed #user-audit channel
  by design.
version: 1.0.0
user-invocable: true
metadata:
  openclaw:
    emoji: "🛰️"
    requires:
      bins: [python3]
      env: [SLACK_BOT_TOKEN, BON_API_BASE_URL, BON_ADMIN_API_KEY]
---

# `/alaska` — native Slack command

You were invoked **as the `/alaska` slash command** (OpenClaw handed you this skill
by name — this is NOT a free-form chat message). The user's input is the
subcommand + args that follow `/alaska`, e.g. `user 2762`, `help`, `ping`.

## Do EXACTLY this — run one command, relay its reply, nothing else

This is a command, not a question. Do **not** answer it yourself, do **not**
summarise the user, do **not** look anything up on your own. The executor does
100% of the work. Run this single bash command:

```bash
PYTHONPATH=/opt/lib python3 -m alaska_command_gateway.execute \
  --text "<the user's input — everything after /alaska, e.g. user 2762>" \
  --invoker "<the sender's Slack id if the turn exposes it, otherwise: slash>" \
  --channel "C0B1W3LUZ4G" \
  --channel-type "channel" \
  --channel-label "#user-audit"
```

Then **post the executor's printed `text` field back to the user, verbatim.** It is
already written for a human — a confirmation, a usage hint (`/alaska user <id>`),
or a friendly error. Add nothing.

### Why `--channel` is hardcoded

OpenClaw's slash-command dispatch does **not** give a command the channel it was
run in. So by team decision (2026-06-05) every case file is delivered to the
dedicated **#user-audit** channel (`C0B1W3LUZ4G`). Do not change this id, and do
not try to post the file somewhere else — the executor uploads the DOCX to
#user-audit itself. You only relay the text confirmation.

## What each subcommand does (source of truth: `ROUTES` in `lib/alaska_command_gateway/execute.py`)

| input | result |
|-------|--------|
| `user <id>` | builds a 360° user case-file DOCX, posts it to #user-audit |
| `help` | lists the subcommands |
| `ping` | liveness check |
| `audit` / `brief` / `pmf` | honest "coming soon" stubs (P1/P2) |

## Guardrails

- Internal only. Reads the user profile and posts a file to #user-audit. It NEVER
  messages the audited end user and NEVER triggers Customer.io / SMS / email.
- The case file carries no SSN/DOB/full address (user-profile-360 strips them
  upstream); it does carry financial figures, which #user-audit is the home for.
- The executor never crashes the command — on any failure it returns a friendly
  `ok:false` text. Relay it; do not retry or improvise.
```
