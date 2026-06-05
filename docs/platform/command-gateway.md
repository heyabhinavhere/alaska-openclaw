# Command Gateway — `/alaska`

> **Status (2026-06-05):** the **live command surface is `!`-mention/DM commands** (`@alaska !case 2762`, `!help`, …), not native `/alaska` slash commands. Native slash is **deferred** — see [the post-mortem](../superpowers/research/2026-06-05-slack-native-command-postmortem.md) and the command-layer spec in [`alaska-operating-model.md` §1.5](../alaska-operating-model.md). The deterministic dispatch engine below (`lib/alaska_command_gateway/`) is unchanged and powers both paths; the sections on native slash / the HTTP receiver describe the deferred architecture.

One command namespace with subcommands routed internally. This document is the
integration reference: the dispatch engine, reliability & observability, the
(deferred) native-slash wiring options, env vars, security, and how to extend it.

Code: `lib/alaska_command_gateway/` · Skill: `skills/command-gateway/SKILL.md`
Tests: `tests/test_command_gateway.py` · `tests/test_command_execute.py`

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

## The live-wiring decision — VERIFIED 2026-06-05

Verified against `docs.openclaw.ai` + the OpenClaw GitHub tracker:

**OpenClaw natively supports Slack slash commands** in both transports, with feature
parity (messaging, slash commands, App Home, interactivity):
- **Socket Mode** (Alaska's mode): the slash command is delivered *over the existing
  websocket*; `slash_commands[].url` is ignored → **no public URL, no signing secret**
  (the app-level token authenticates the socket). Config: `channels.slack.commands.native: true`
  (off by default), `slashCommand.enabled`/`name`, map the command → a skill/agent.
- **HTTP mode**: `channels.slack.mode: http` + `webhookPath` + `signingSecret`; Slack POSTs
  to the request URL.

**Version caveat (decisive):** GitHub issue **#66194** ("OpenClaw does not currently
handle incoming slash command payloads from Slack Socket Mode … command fails silently")
was a feature request **closed 2026-04-13** — *after* our pinned **`v2026.3.13`
(2026-03-14)**. So the **live gateway almost certainly cannot receive a native Socket-Mode
slash command today** (it would time out) — which is exactly why `/pmf` and `/audit` use
the instruction-routed workaround. Native `/alaska` therefore requires the OpenClaw upgrade
**`v2026.3.13 → v2026.5.26`** (in-repo research: SAFE — but it crashes on boot unless
`config/openclaw.json` drops `nativeStreaming` and makes `streaming` an object, and adds an
`openclaw doctor --fix` preflight in `entrypoint.sh`).

### Two live architectures

- **A — OpenClaw-native routing (recommended).** Slack `/alaska` → OpenClaw (Socket Mode,
  post-upgrade) → a `command-gateway` **skill** that calls this lib's `parse_command` +
  handler registry: `help`/`ping` answered deterministically, `audit` enqueued. OpenClaw owns
  the 3s ack + async. **No signing secret. Uses parse/dispatch/handlers/jobs; `verify.py` +
  `receiver.py` are not used.** New shared changes: enable native commands in
  `config/openclaw.json` + create the Slack `/alaska` command + the routing skill (+ the
  separate image upgrade).
- **B — gateway-owns-the-endpoint.** Slack `/alaska` → HTTP-mode `webhookPath` (or a custom
  `/hooks` route) → `handle_slash_command()` (this lib's `verify.py` + `receiver.py`). Avoids
  the upgrade but re-architects all Slack connectivity (mode is channel-wide) and still needs
  one capability check (a fast non-`agent` hook action). Riskier.

Either way the gateway **core (parse/dispatch/handlers/jobs) does not change** — only the
adapter differs (a skill for A, the HTTP receiver for B).

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

## Reliability & observability (the `!`-command layer)

`!`-command routing is **model-mediated** at the recognition step (the model decides
to dispatch), then **deterministic** in `execute.route()`. We can't unit-test the
model's decision, so reliability is **measured**.

**`command_audit` table** (`alaska.db`, migration `0007`; append-only; inert on
`alaska_pmf.db`). One row per routing decision:

| column | meaning |
|---|---|
| `created_at` | UTC timestamp |
| `raw_text` | the command text only (e.g. `case 2762`) — no PII, no whole DMs |
| `verb` | the matched/attempted verb |
| `matched` | `route` (dispatched) · `unknown` (`!`+non-whitelisted) · `fallthrough` (looked command-like, answered as chat) |
| `routed_target` | the skill/executor that ran |
| `ok` / `status` | the executor result |
| `invoker` / `channel` / `channel_type` | Slack context (best-effort) |
| `gateway_version` | for cross-deploy comparison |

Write-points: a **deterministic** insert inside `execute.route()` (swallow-on-error — it
can never crash a command); a **best-effort** SKILL-emitted row for `unknown`/`fallthrough`
(the dangerous direction — a false route — is captured deterministically regardless).

**Measuring (read `command_audit`):** hit-rate = `route` / commands-sent; false-route =
`route` rows whose `raw_text` is obvious prose; per-verb health = `WHERE verb=… GROUP BY status`.
Surface a weekly one-liner on the nightly cost-report DM; alert `#alaska-alerts` only on
`status='handler_error'` spikes.

**The 4-part promotion bar — a verb goes live only when ALL hold** (false positives are
worse than misses): known commands **≥95%** routed · plain chat **0** false-routes ·
task/reminder/decision **0** regressions · unknown `!thing` → **helpful error**, not random chat.
Below bar → fix the SKILL prompt + redeploy + re-measure (never a code change). Recorded in
[`command-routing-eval.md`](../superpowers/research/2026-06-05-command-routing-eval.md).

**Definition of done, per verb:** (1) a `ROUTES`/router row; (2) a per-verb row in
`tests/test_command_execute.py` (happy path with injected generator, bad-arg, not-found,
handler-exception → friendly `ok:false`); (3) eval-corpus rows in `tests/fixtures/routing_eval.jsonl`
(the command + a look-alike that must NOT route); (4) read-only or a confirm-before-write
handshake; (5) the measured numbers recorded in the eval doc.

**Rollout discipline:** every PR branches from `origin/main` and is rebased on `origin/main`
immediately before merge — **never stacked** on another open PR's branch (a stacked merge once
stranded a change off `main`). And **ADD before REMOVE**: add the new authoritative router and
prove it against the bar *before* deleting any of the old scattered prefix rules.
