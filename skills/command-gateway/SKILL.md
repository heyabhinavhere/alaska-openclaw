---
name: command-gateway
description: >-
  Platform layer for a single native Slack slash command, /alaska, with
  subcommands routed internally (help, ping, audit, and later pmf/user/brief).
  Provides Slack request-signature verification, a 3-second acknowledgement, and
  an async job pattern. P0 ships the tested core + a reference receiver but is
  NOT wired live in production. Library lives in lib/alaska_command_gateway/.
version: 0.1.0
metadata:
  openclaw:
    always: false
    emoji: "🛰️"
    requires:
      bins: [python3]
      env: [SLACK_SIGNING_SECRET, SLACK_BOT_TOKEN]
---

# Command Gateway (`/alaska`)

One native Slack command — `/alaska` — with subcommands routed internally. This
is the platform alternative to today's instruction-routed pseudo-commands (e.g.
`/pmf` is matched as message text inside the intent-classifier). A single command
namespace keeps every Alaska action discoverable and consistent.

```
/alaska help                 list available subcommands
/alaska ping                 liveness check
/alaska audit 1414           generate an internal audit report  (DRY-RUN in P0)
(later)  /alaska pmf status   /alaska user 1414   /alaska brief today
```

## Status: P0 — built, tested, NOT wired live

P0 delivers the runtime-agnostic brain and a reference HTTP receiver, fully
covered by tests. It does **not** turn `/alaska` on in production.

**Verified (2026-06-05):** OpenClaw *natively* supports Slack slash commands —
Socket Mode (no public URL, **no signing secret**) and HTTP mode. But native
support landed *after* our pinned **`v2026.3.13`** (GitHub #66194, resolved
~2026-04), so live Alaska can't receive a Socket-Mode slash command today — hence
the instruction-routed `/pmf` and `/audit` workaround. Going live needs the
**`v2026.3.13 → v2026.5.26` upgrade** (+ a `config/openclaw.json` `streaming` /
`nativeStreaming` fix + an `openclaw doctor --fix` preflight). Then the recommended
path is **Architecture A**: OpenClaw routes `/alaska` → a routing skill that calls
this lib's `parse_command` + handlers (`help`/`ping` answered deterministically,
`audit` enqueued). In that path `verify.py` + `receiver.py` are unused — they are
the HTTP-mode / own-the-endpoint alternative (Architecture B). All live wiring is a
separate, **approved** step. See
[docs/platform/command-gateway.md](../../docs/platform/command-gateway.md).

## Flow

```
Slack POST (command, text, user_id, channel_id, response_url, team_id, X-Slack-Signature)
  -> verify_slack_signature()   reject bad sig (401) / stale ts >300s (401) / wrong team (403)
  -> parse_command(text)        "audit 1414" -> {sub: audit, args: [1414]}
  -> dispatch_ack()             sync answer (help/ping) OR async "started" + job spec
  -> ack within 3s              immediate ephemeral response
  -> create_job() (if async)    filesystem JSON record (queued); NO inline long work
  -> run_job() worker           finalize off the request path -> POST result to response_url
```

## Add a new subcommand (no shared-routing edits)

```python
from alaska_command_gateway import register_handler, ephemeral, register_finalizer

def status_handler(parsed, context):
    # sync answer:
    return ephemeral("PMF status: ...")
    # or async: return ephemeral("Working…", **{"async": {"command": "pmf", "params": {...}}})

register_handler("pmf", status_handler)
# for async commands, also register the deferred worker:
register_finalizer("pmf", lambda job: {"text": "...result..."})
```

This is purely additive — it does **not** touch `skills/intent-classifier` or
`skills/alaska-core`. `/pmf` can migrate here later by registering a `pmf` handler
that calls the existing `pmf-cohort-os` skill.

## Security (fail closed)

- Verifies the Slack signing secret (`SLACK_SIGNING_SECRET`); HMAC-SHA256 over
  `v0:{timestamp}:{body}`, constant-time compare. Never the deprecated token.
- Rejects stale timestamps (>300s) and, when configured
  (`SLACK_ALLOWED_TEAM_ID`), disallowed workspaces.
- Without a signing secret the receiver refuses to process (500), unless a caller
  explicitly opts out for a local dry run.
- Rejections are logged with reason + safe fields only — never the raw body or
  the signature.

## audit is DRY-RUN in P0

`/alaska audit <user_id>` parses + enqueues a job, but the worker only posts a
"would run" message. Live audit is connected to the `bon-internal-audit` skill +
the Artifact Service in a later, approved PR (#4), after Audit Agent v1 is stable.
