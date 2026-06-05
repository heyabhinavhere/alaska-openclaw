---
name: command-gateway
description: >-
  Runs the DETERMINISTIC `!`-commands — `!case <id>` (post a 360° user case-file
  DOCX to the channel), `!help`, `!ping`. SOUL.md → "STEP 0 — Command Router" hands
  these here; this skill runs ONE Python command (lib/alaska_command_gateway/execute.py)
  and relays its `text`. The model-routed verbs `!audit` and `!pmf` are NOT this skill —
  they go to bon-internal-audit / pmf-cohort-os. Legacy `/alaska <sub>` is an alias.
version: 0.3.0
metadata:
  openclaw:
    always: false
    emoji: "🛰️"
    requires:
      bins: [python3]
      env: [SLACK_BOT_TOKEN, BON_API_BASE_URL, BON_ADMIN_API_KEY]
---

# Command Gateway — the `!case` / `!help` / `!ping` executor

This skill runs the **deterministic** `!`-commands. You only reach it from
`SOUL.md` → **STEP 0 — Command Router**, which already decided this is a command.
Your whole job: (1) take the Slack context, (2) run ONE command, (3) relay its
`text`. Do not interpret, classify, or re-route — the executor's `ROUTES` table is
the source of truth.

> `!audit` and `!pmf` are **not** handled here — STEP 0 sends those to
> `bon-internal-audit` and `pmf-cohort-os` respectively. This skill is `!case`,
> `!help`, `!ping` only.

## Run the executor (one command, then relay)

`/opt/lib` is already on `PYTHONPATH` (repeated below only for clarity):

```bash
PYTHONPATH=/opt/lib python3 -m alaska_command_gateway.execute \
  --text "<verb + args, e.g. case 2762>" \
  --invoker "<sender's Slack user id>" \
  --channel "<channel id the message was sent in>" \
  --channel-type "<dm if the channel id starts with 'D', else channel>" \
  --thread-ts "<message thread_ts, ONLY if it was sent inside a thread>"
```

Fill from the inbound Slack event:
- `--text` — the command without the `@alaska` mention. The leading `!` is optional
  (the executor strips it): `@alaska !case 2762` → `--text "case 2762"`. Legacy
  `@alaska /alaska user 2762` → `--text "user 2762"` also works.
- `--invoker` — the sender's Slack user id (e.g. `U07GKLVA9FE`).
- `--channel` / `--channel-type` — the channel/DM id and `dm`/`channel`.
- `--thread-ts` — include ONLY if the message was inside a thread.

**Then relay.** The command prints `{"ok": …, "text": "…", …}`. **Post `text` back
to the same channel/thread, verbatim** — it's already written for a human (success,
usage hint, or error). Do not add commentary, do not re-run, do not "fix" an
`ok:false`. For `!case`, the executor has already validated + **uploaded the DOCX to
`--channel`**; the `text` is just the confirmation that rides with the file.

## What `!case` delivers, and where

`!case <id>` posts the case-file DOCX **into the channel the command was run in**
(team decision, 2026-06-05). The profile carries **no SSN / DOB / full address**
(user-profile-360's redactor strips them upstream), so it's safe for the team's
shared channels; it does carry financial figures, and the file header says
"internal — do not share externally." If `--channel` is omitted the executor
generates but doesn't deliver (and says so).

## Routing table — the one place to tune

The live table is **`ROUTES` in `lib/alaska_command_gateway/execute.py`** — one row
per verb. Add a command = add a row + a small `_cmd_*`; change one = edit its row.
Current deterministic verbs:

| verb | status | what it does |
|------|--------|--------------|
| `case <id>` | **live** | build + post a 360° user case file (DOCX) |
| `user <id>` | live | back-compat alias of `case` |
| `help` / `ping` | live | list commands / liveness |
| `audit` / `pmf` / `brief` | not here | `audit`→bon-internal-audit, `pmf`→pmf-cohort-os (STEP 0 routes them); stubs only fire if mis-called |

## Guarantees

- The executor **never crashes the command** — a bad/failed call returns a friendly
  `ok:false` `text` (e.g. "No BON user matches `404`."). Relay it.
- **Validate-before-deliver:** a malformed DOCX is never posted (`ok:false`, file kept
  server-side for retry).
- **Read-only** wrt BON systems (reads the profile; writes only a file + Slack). Never
  messages the end user, never triggers Customer.io / SMS / email.
- Every invocation is logged to `command_audit` (migration 0007) for reliability
  measurement — automatic, best-effort, never affects the result.

## Native slash command — deferred

Turning `!`-commands into native `/alaska` Slack slash commands is a deferred,
post-launch UX upgrade — see
`docs/superpowers/research/2026-06-05-slack-native-command-postmortem.md` for why
(Slack's 3s ack + the dispatched command not receiving the channel/sender).
