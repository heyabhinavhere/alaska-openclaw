# Command Gateway — `/alaska`

One native Slack command with subcommands routed internally. This document is the
integration reference: architecture, the (deferred) live wiring options, required
Slack app settings, env vars, security, and how to extend it.

Code: `lib/alaska_command_gateway/` · Skill: `skills/command-gateway/SKILL.md`
Tests: `tests/test_command_gateway.py`

## Architecture

```
Slack /alaska audit 1414
  │  command=/alaska  text="audit 1414"  user_id  channel_id  response_url  team_id
  │  headers: X-Slack-Signature, X-Slack-Request-Timestamp
  ▼
handle_slash_command(raw_body, headers)                      # receiver.py — testable core
  ├─ verify_slack_signature()   bad sig → 401 · stale ts >300s → 401
  ├─ team_allowed()             disallowed workspace → 403
  ├─ parse_command("audit 1414") → ParsedCommand(sub="audit", args=["1414"])
  ├─ dispatch_ack()             help/ping → sync answer ; audit → "started" + async spec
  ├─ create_job() if async      filesystem JSON record (status=queued)   ← no DB
  └─ return {status, body, job}  immediate ephemeral ack  (always < 3s; no long work inline)
        │
        ▼ (off the request path)
run_job(job_id)  → finalizer → status done/error → POST result to response_url
```

`handle_slash_command()` is runtime-agnostic and fully unit-tested with no
socket. `receiver.make_server()` wraps it in a stdlib `http.server` for local /
dry-run use and end-to-end tests. **The reference server is NOT started by
`entrypoint.sh` in P0.**

## Subcommands

| Subcommand | P0 behavior |
|---|---|
| `/alaska help` | lists subcommands (ephemeral) |
| `/alaska ping` | "pong" + gateway version |
| `/alaska audit <user_id>` | parse + enqueue async job; **dry-run** (posts "would run"); no live audit |
| `/alaska pmf|user|brief` | documented as coming later (registered when wired) |

## The live-wiring decision (deferred, needs approval)

A *true* native `/alaska` needs a way for Slack to reach the gateway. The repo's
single public port belongs to the OpenClaw process, Slack runs in Socket Mode,
and the built-in `/hooks` receiver uses a static Bearer token + a slow
`action:agent` turn (see [README research memo](README.md)). So the transport
must be chosen with the owner **after verifying OpenClaw's capabilities** — never
guessed. Three candidates:

1. **Socket Mode `slash_commands`** *(cleanest if supported)* — when Socket Mode
   is on, Slack delivers slash commands over the existing websocket. No public
   URL, no signing secret. **Verify:** does OpenClaw's Slack plugin surface
   `slash_commands` envelopes to a handler? If yes, bridge them into
   `handle_slash_command()` (with `enforce_signature=False`, since the app token
   already authenticates the socket).
2. **OpenClaw `/hooks` mapping** — point a Slack slash command request URL at the
   gateway's public `/hooks/alaska`. **Verify:** do hooks support a fast,
   non-`agent` action that returns a handler's output within 3s, and per-mapping
   verification compatible with `X-Slack-Signature`? If yes, add a `hooks`
   mapping in `config/openclaw.json` (a shared-file change → separate approved PR).
3. **HTTP Events API receiver** — switch Slack to Events API and expose
   `handle_slash_command()` on a public route. On Railway this means either an
   OpenClaw-native Events receiver or a second service (the single-port
   constraint makes a sidecar non-trivial). Largest change.

Whichever is chosen, the gateway **core does not change** — only a thin adapter
that feeds it `(raw_body, headers)` and returns `body`.

### Required Slack app settings (when wiring live)

- **Slash Commands → Create New Command:** Command `/alaska`, Request URL =
  the chosen public endpoint (Events/hooks options only; Socket Mode needs no
  URL), short description, usage hint `help | ping | audit <user_id>`.
- **Basic Information → Signing Secret** → set as `SLACK_SIGNING_SECRET`.
- Socket Mode option additionally needs **App-Level Token** (`SLACK_APP_TOKEN`,
  already present) and Socket Mode enabled.
- Bot scopes already in use: `chat:write`, `files:write` (for result delivery /
  artifact upload).

## Environment variables

| Var | Needed for | Notes |
|---|---|---|
| `SLACK_SIGNING_SECRET` | Events/hooks wiring + signature verification | **new**; required to process requests when enforcing |
| `SLACK_BOT_TOKEN` | posting results / uploading artifacts | already configured |
| `SLACK_APP_TOKEN` | Socket Mode option | already configured |
| `SLACK_ALLOWED_TEAM_ID` | optional team allowlist (comma-separated) | if unset, all workspaces allowed (repo's current posture) |
| `ALASKA_COMMAND_JOBS_DIR` | job record location | defaults to `/data/workspace/command_jobs` |
| `ALASKA_GATEWAY_PORT` | reference receiver port | defaults to `18790` (local/dry-run only) |

## Security (fail closed)

- HMAC-SHA256 over `v0:{timestamp}:{raw_body}`, constant-time compare against
  `X-Slack-Signature`. The deprecated verification token is never used.
- Stale timestamps (>300s) are rejected; replay window matches Slack's guidance.
- Without a signing secret, the receiver refuses to process (HTTP 500) unless a
  caller explicitly opts out for a local dry run (`enforce_signature=False`).
- Optional workspace allowlist via `SLACK_ALLOWED_TEAM_ID`.
- Rejections are logged with **reason + safe fields only** (team/user/command) —
  never the raw body, never the signature.

## Job records (filesystem JSON, no DB)

`<ALASKA_COMMAND_JOBS_DIR>/<job_id>.json`:

```json
{"job_id":"a1b2c3d4e5f6","command":"audit","actor":"U123","channel":"C123",
 "params":{"user_id":"1414"},"response_url":"https://hooks.slack.com/...",
 "response_type":"ephemeral","status":"queued","result":null,"error":null,
 "created_at":"2026-06-05T...","updated_at":"2026-06-05T..."}
```

Status flows `queued → running → done|error`. Failures (finalizer raises, or no
finalizer) are captured and a clean message is posted to `response_url`.

## Add a new subcommand

```python
from alaska_command_gateway import register_handler, ephemeral, register_finalizer

def brief_handler(parsed, context):
    return ephemeral("Working on today's brief…",
                     **{"async": {"command": "brief", "params": {"day": parsed.args[0:1]}}})

register_handler("brief", brief_handler)
register_finalizer("brief", lambda job: {"text": build_brief(job["params"]),
                                         "response_type": "in_channel"})
```

Purely additive — no edits to `skills/intent-classifier` or `skills/alaska-core`.

## How `/pmf` migrates later

Today `/pmf` is a text prefix matched inside `skills/intent-classifier`. To move
it under the gateway without disrupting current behavior:

1. Register a `pmf` handler that calls the existing `pmf-cohort-os` skill
   (sync for quick status, or async for heavier queries).
2. Wire the live transport (above) so `/alaska pmf status` reaches the gateway.
3. Only then, retire the classifier's `/pmf` prefix rule. Until step 3 the two
   coexist; nothing is removed without approval.

## How `audit` goes live (platform PR #4)

Replace the dry-run finalizer with one that calls the `bon-internal-audit` skill
to produce the audit JSON, renders the report via the **Artifact Service**
(`render_docx_from_template` against the audit template), validates it
(`validate_docx`), stores it (`store_artifact`), and uploads it
(`upload_artifact_to_slack`) to the channel/thread. Only after Audit Agent v1 is
merged and stable, and with explicit approval.
