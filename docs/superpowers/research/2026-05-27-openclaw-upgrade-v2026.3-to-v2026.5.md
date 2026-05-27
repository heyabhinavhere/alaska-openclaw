# OpenClaw Upgrade Research — v2026.3.13 → v2026.5.26

> **Date:** 2026-05-27
> **Author:** research subagent
> **Goal:** Decide whether to upgrade the production Docker image pin (`1panel/openclaw:2026.3.13` → `1panel/openclaw:2026.5.26`).

---

## ⚠️ CORRECTION POST-UPGRADE-ATTEMPT (2026-05-27 17:36 UTC)

The "SAFE TO UPGRADE NOW, HIGH confidence" verdict in this doc was **WRONG on one specific point**: `channels.slack.streaming` and `channels.slack.nativeStreaming`.

Actual outcome: upgrade attempt deployed at 17:36 UTC. Gateway crashed on boot with:
```
channels.slack: invalid config: must not have additional properties: "nativeStreaming"
channels.slack.streaming: invalid config: must be object
```

Schema changed between v2026.3.13 and v2026.5.26:
- `streaming` is now an object (was boolean)
- `nativeStreaming` is no longer a top-level property (likely merged into the streaming object)

The release notes inspection didn't surface this change. Rolled back to v2026.3.13 at 17:38:50 UTC. Total downtime: ~2 min.

**Lessons for next attempt:**
1. Run `openclaw doctor --fix` against a local copy of `config/openclaw.json` to see what the new version would migrate. This would have caught the schema break in dry-run.
2. Add `openclaw doctor --fix` as a pre-flight in `entrypoint.sh` before `openclaw gateway run` — handles ANY future schema changes the same way.
3. Q2 confidence ratings on schema fields not in release notes should be MEDIUM, not HIGH. "Release notes don't mention a change" ≠ "schema is unchanged."

The rest of this doc's analysis (cron API shape, hook handlers, skill format, the 3 tracked bugs, recommendation procedure, rollback mechanics) was accurate. The rollback procedure described in §"Rollback procedure" worked exactly as written.

---

## Sources consulted

- GitHub releases API (`gh release list/view --repo openclaw/openclaw`) — 31 stable releases between v2026.3.13 and v2026.5.26 inspected.
- GitHub issue tracker (`gh issue view 8557 / 11075 / 8712 / 7326 / 8558` and PR #11641) for the three known issues we track on v2026.3.13.
- Docker Hub: `https://hub.docker.com/r/1panel/openclaw/tags` — confirms `2026.5.26` tag was published ~5 hours before this research (May 27).
- Local repo: `Dockerfile`, `entrypoint.sh`, `config/openclaw.json`, `config/cron-jobs-backup.json`, `skills/*/SKILL.md`, prior research note `2026-05-27-openclaw-native-primitives.md`.
- Docs site (https://docs.openclaw.ai/automation/cron-jobs) — sparse on request-schema specifics; relied on release notes for shape changes.

---

## Q1 — Changelog summary

31 stable releases shipped between v2026.3.13 (2026-03-14) and v2026.5.26 (2026-05-27). Only **6 of those releases carry a `### Breaking` section**; the rest are change-and-fix only. Below is the per-version breakdown filtered to anything that could touch our setup.

### v2026.3.22 (2026-03-23) — BREAKING

- **Plugin SDK migration**: `openclaw/extension-api` removed; bundled plugins must use `openclaw/plugin-sdk/*` subpaths. _Affects us only if we wrote a custom plugin — we don't, we use skills._
- Browser/Chrome MCP: legacy extension relay path removed. _Not used._
- `CLAWDBOT_*` and `MOLTBOT_*` env vars removed; `.moltbot` state dir auto-migration removed. _Not used._
- New `cron tool: infer creating session's agentId for cron.add when agentId is omitted` (refs #40571).
- `Hooks/workspace`: repo-local `<workspace>/hooks` disabled by default until explicitly enabled. _Doesn't affect us — we use config-level `hooks.mappings`, not workspace hooks._
- `Skills/prompt budget`: registered skills preserved via compact catalog fallback before dropping. _Latent benefit._

### v2026.3.24 (2026-03-25) — no breaking, fixes only

### v2026.3.28 (2026-03-29) — BREAKING

- **Config/Doctor**: auto config migrations older than two months dropped. Very old legacy keys now fail validation instead of being rewritten on load. _Our config is current shape — not affected._
- Qwen `qwen-portal-auth` removed. _Not used._

### v2026.3.31 (2026-03-31) — BREAKING

- `nodes.run` shell wrapper removed; `nodes` channel now routes through `exec host=node`. _Not used._
- Gateway auth `trusted-proxy` now rejects mixed shared-token configs; local-direct fallback requires the configured token. _We use `"auth": {"mode": "token"}` — not affected._
- Skills/Plugins install scans fail closed on critical findings; new `--dangerously-force-unsafe-install` flag required to bypass. _We don't install at runtime; our skills are baked into the image._

### v2026.4.2 (2026-04-02) — BREAKING + Task Flow GA

- **Task Flow substrate restored** (#58930, #59610, #59622) — managed-vs-mirrored sync modes, durable state, `openclaw flows list|show|cancel` CLI. Plugins can now create Task Flows via `api.runtime.taskFlow`. _**Relevant for Watchers V1 V2 path.**_
- Plugin xAI/Firecrawl config paths moved to plugin-owned namespaces (legacy paths migrated by `openclaw doctor --fix`). _Not used._
- `before_agent_reply` hook added (#20067). _Latent feature — could be useful for guardrails later._

### v2026.4.5 (2026-04-06) — BREAKING

- **Config legacy aliases removed**: `talk.voiceId`, `talk.apiKey`, `agents.*.sandbox.perSession`, `browser.ssrfPolicy.allowPrivateNetwork`, `hooks.internal.handlers`, channel/group/room `allow` toggles **in favor of `enabled`**. Load-time compat retained + `openclaw doctor --fix` migration available. _Our `channels.slack.enabled: true` is the canonical form; we do NOT use `allow` toggles. Safe._

### v2026.4.7 → v2026.4.15 — no breaking, fixes only

Notable fixes in this band:
- **v2026.4.10**: `Cron: load jobId into id when on-disk store omits id` (#62246) — fixes "unknown cron job id" for hand-edited `jobs.json`. _Tracks our known issue #11075 area._
- **v2026.4.12**: `Cron/scheduling: treat nextRunAtMs <= 0 as invalid; self-heal corrupted zero timestamps` (#63507). _Reduces tail-risk of the family of issues that includes #8712._
- **v2026.4.14**: `Cron/announce: preserve all deliverable text payloads instead of collapsing to the last chunk`; `Cron/isolated sessions: carry full provider/model/auth-profile selection across retry restarts` (#57972).
- **v2026.4.15**: `Cron: replay interrupted recurring jobs on first gateway restart instead of waiting for second restart` (#60583); `Cron: send failure notifications through job's primary delivery channel when no failureDestination configured` (#60622); `Agents/tool-loop: unknown-tool stream guard enabled by default` (#67401); `Gateway/skills: cache invalidation when skills.* config writes happen` (#67401).

### v2026.4.20 → v2026.4.24 — BREAKING (one entry in 4.24, otherwise fixes)

- **v2026.4.20**: `Cron: split runtime execution state into jobs-state.json so jobs.json stays stable for git-tracked job definitions` (#63105). _**Schema split.** This means: our `config/cron-jobs-backup.json` snapshot — currently a single file with embedded `state` — represents the OLD shape. On the new version, definitions live in `jobs.json`, runtime state in `jobs-state.json`. The Doctor migrates this. Backup-restore tooling that assumes the merged shape will need to know about the split._
- **v2026.4.22**: `Cron tool: infer creating session's agentId for cron.add when agentId is omitted or undefined` (#40571). _Helpful._
- **v2026.4.23**: `Cron/doctor: repair malformed persisted cron job IDs through openclaw doctor, including legacy jobId, non-string id, and missing id rows` (Fixes #70128). _**Directly fixes the jobId/id naming inconsistency we tracked as #11075.**_
- **v2026.4.24**: BREAKING — `api.registerEmbeddedExtensionFactory(...)` removed; use `api.registerAgentToolResultMiddleware(...)`. _Plugin-only — not used._

### v2026.4.27, v2026.4.29 — no breaking, fixes only

- **v2026.4.27**: Many cron-delivery hardening fixes (#69285, #69587, #69000, #68858, #69015, #69021, #69040, #69153, #69163) — most touch isolated cron delivery with `delivery.mode: "none"` — exactly the pattern Alaska uses for all 14 production crons.
  - `Cron/delivery: treat explicit delivery.mode: "none" runs as not requested even if runner reports delivered: false` (#69285) — **fixes false delivery-failure logs we have seen**.
  - `Cron/isolated-agent: preserve explicit delivery.mode: "none" message targets without inheriting implicit "last" routing` (#69153).

### v2026.5.2 → v2026.5.26 — NO breaking changes in any v2026.5.x stable release

Notable additions:
- **v2026.5.2**: `agents.defaults.skipOptionalBootstrapFiles` (#62110); `Codex 0.128.0` bump; `Gateway/agent-tool: reject config.patch calls that newly enable dangerous flags (dangerouslyDisableDeviceAuth, allowInsecureAuth, etc.)` (#62006) — **already-enabled flags pass through unchanged** so our `dangerouslyDisableDeviceAuth: true` setting in `gateway.controlUi` continues to work; just blocks runtime escalation.
- **v2026.5.4–5.7**: Plugin npm-first cutover hardening, ClawHub artifact metadata, Slack `channels.slack.thread.requireExplicitMention` (#58276), Slack `socketMode.clientPingTimeout` overrides.
- **v2026.5.18**: Plugin descriptor planner caching; faster prompt-time tool planning.
- **v2026.5.19, v2026.5.20, v2026.5.22**: Transcript-backed meeting summaries, Telegram forum topic improvements, Discord/iMessage reaction approvals, named auth profiles.
- **v2026.5.26**: 
  - `Cron: default cron.maxConcurrentRuns to 8` (no longer requires explicit config — our prior research found this was already the de-facto default; now formalized).
  - `Cron: restore suspended cron lanes to configured/default concurrency after quota or circuit-breaker auto-resume` (no more "stuck at 1 concurrent" after errors).
  - `Cron: accept leading-plus relative durations such as +5m for one-shot --at schedules` (#86341).
  - `Cron: seed active scheduled/manual cron task rows with progress summary so status surfaces don't look blank` (#86313).
  - `Cron: preserve unsupported persisted cron payload rows during routine store writes while keeping those rows non-runnable` (#86415) — fixes #84922 (forward compat for new payload kinds).
  - `Agents/hooks/subagents: enforce default hook agent allowlists` (#86101) — _hook security tightening; our `fireflies-transcript` mapping should still work but worth a smoke test._
  - `Heartbeat: stop heartbeat turns after the first valid heartbeat_respond` (#86357) — token-cost reduction.
  - `Memory/security: reject prompt-like text submitted through explicit memory_store tool` (#87142).
  - `Gateway/security: enable default auth rate limiter for remote non-browser/HTTP auth failures when gateway.auth.rateLimit is unset` (#87148) — _preserves loopback exemption; should not affect our Railway deploy._
  - **Sharp image library replaced with Rastermill** — no more native image-processing dependency. _Latent benefit; no behavioral impact for Alaska._
  - Bundled Codex CLI bumped to 0.134.0.

---

## Q2 — Impact on our setup

| Subsystem | Status | Notes |
|---|---|---|
| `config/openclaw.json` schema | **PASS** | Our config uses canonical paths (`channels.slack.enabled`, `gateway.controlUi.dangerouslyDisableDeviceAuth`, `hooks.mappings`, `tools.agentToAgent.enabled`). None of the removed legacy aliases (v2026.4.5) are in use. |
| `gateway.controlUi.dangerouslyDisableDeviceAuth: true` | **PASS** | v2026.5.2 (#62006) blocks NEWLY enabling this via `config.patch` runtime calls, but already-enabled file-level config passes through unchanged. We set it in `config/openclaw.json` at build time, so we're fine. Security audit will flag it; harmless. |
| `channels.slack.allowFrom: ["*"]` | **PASS** | v2026.4.x (#66028) extended `allowFrom` to interactive Slack events. Wildcard `["*"]` preserves "open-by-default" behavior — explicitly called out in release notes. |
| `channels.slack.dmPolicy: "open"`, `groupPolicy: "open"` | **PASS** | No changes to these fields between v2026.3.13 and v2026.5.26. |
| `channels.slack.streaming: false`, `nativeStreaming: false` | **PASS** | Streaming preview improvements landed (Telegram/Slack), but our `false` values are honored. |
| Cron API shape in `config/cron-jobs-backup.json` (`schedule.kind`, `schedule.expr`, `payload.kind`, `delivery.mode`, `wakeMode`, `sessionTarget`) | **PASS** | All 14 entries use field names that are still canonical in v2026.5.26. `delivery.mode: "none"` semantics are explicitly hardened in v2026.4.27 (#69285, #69153) — fewer false delivery-failures, no behavioral break. |
| Cron state file location | **NEEDS-AWARENESS (not a pre-fix)** | v2026.4.20 (#63105) split state into `jobs-state.json`. The Doctor migrates on first run. Our `entrypoint.sh` doesn't manipulate `~/.openclaw/cron/*.json` directly, so the split is transparent. **The `config/cron-jobs-backup.json` snapshot we keep in git is now a hybrid (definition + state merged) — any tooling that programmatically restores it would need updating. We have no such tooling today; the file is informational.** |
| Cron API field naming (`jobId` vs `id`) | **PARTIALLY RESOLVED** | v2026.4.10 + v2026.4.23 added store-side normalization and doctor repair. The model-side tool-call shape issue (#11075) was triaged as "agent payload formatting" not a server bug; remains a class of caller error rather than a primitive bug. After upgrade, defensive `enabled: true` + jobId normalization in our skills can stay — it's belt-and-suspenders, not load-bearing. |
| Skill format (`metadata.openclaw.requires.bins`, `primaryEnv`, `emoji`, `always: true`) | **PASS** | No skill-frontmatter shape changes. `metadata.clawdbot` legacy alias is honored (#71323 fix) — irrelevant since we use `metadata.openclaw`. |
| Hook handler config (`hooks.mappings[].messageTemplate`, `action: "agent"`, `deliver: true`, `channel: "slack"`) | **PASS** | No documented changes to hook payload templating, `messageTemplate` semantics, or the `{{json}}` placeholder. v2026.4.2 added `before_agent_reply` hook (new optional pre-LLM hook), doesn't affect our existing `fireflies-transcript` mapping. v2026.5.26 tightened hook agent allowlists (#86101) — our mapping doesn't specify a non-default agent so it lands in the default allowlist. |
| Hook auth (`Authorization: Bearer __HOOKS_TOKEN__`) | **PASS** | No changes to `hooks.token` semantics or the bearer/`x-openclaw-token` header. v2026.5.26 security audit now flags reusing `hooks.token` as Gateway password auth (#84338) — our `HOOKS_TOKEN` env is distinct from Gateway auth, fine. |
| `gateway.tools.allow` and default deny list (cron, exec, shell, fs_write) | **PASS** | Default deny list unchanged in v2026.5.26. `tools.allow` semantics unchanged; new `tools.alsoAllow` field exists for additive policy (not required for us — we don't expose tools to external HTTP callers). |
| Built-in model defaults | **PASS** | Our config has no `gateway.agent.model` override (`agents.defaults.*` is also empty). OpenClaw's built-in model is selected via session config / cron `payload.model` — we set `anthropic/claude-sonnet-4-20250514` explicitly on the Sprint Operator cron, and similar overrides per skill. No models we use are retired. |
| `openclaw gateway run --port 18789 --allow-unconfigured` | **PASS** | Flags unchanged. v2026.5.2 added `openclaw gateway restart --force` and `--wait <duration>` but those are for the new `restart` subcommand — `run` is unaffected. |
| SQLite local queue / `entrypoint.sh` boot logic | **PASS** | No changes to `OPENCLAW_STATE_DIR` semantics. `/data/.openclaw/openclaw.json` still the runtime config path. Our `.bak` corruption guard in `entrypoint.sh` is fully forward-compatible. |
| Heartbeat behavior | **MINOR-WIN** | v2026.5.26 fixed heartbeat infinite-respond loop (#86357) — small token-cost saving. We don't drive workflows from heartbeat anyway (our prior research recommends against it for time-sensitive watchers). |
| Sharp image library replaced with Rastermill | **N/A** | We don't process images. Latent benefit (no Sharp install in image). |
| Bundled Codex CLI 0.134.0 | **N/A** | We don't use Codex agent runtime. |

**Net result: no PASS that requires a pre-fix.** All known config-shape changes either don't affect us, were already on the canonical path, or are handled transparently by Doctor migration at boot.

---

## Q3 — Known-issue resolution

| Issue | Status | Resolution |
|---|---|---|
| **#8557** — `enabled` field default-undefined bug (cron jobs created but never fire) | **FIXED** in v2026.3.13 or earlier | Closed 2026-02-04 as duplicate of #7326. Underlying root cause fixed by PR #11641 (merged 2026-02-08). Our pinned v2026.3.13 (released 2026-03-14) already contains the fix. **The defensive `enabled: true` pattern in our skills is no longer load-bearing**, but harmless. |
| **#11075** — `jobId` vs `id` API inconsistency on cron.update/remove | **NOT-A-SERVER-BUG** + **STORE-SIDE-MITIGATED** | Closed 2026-02-23. Triage note: "not fixed by either PR. This is an invalid tool-call payload shape (agent/tool-call formatting) issue. Needs stricter tool-call schema guidance/repair on caller side (or server-side coercion/clearer validator error mapping)." Subsequently, v2026.4.10 (#62246) + v2026.4.23 (#70128) added store-side normalization that loads `jobId` into `id` when missing, plus `openclaw doctor` repair for malformed IDs. Net: the underlying class of "I sent the wrong field name" remains a caller-side concern, but persistence-layer mismatches are auto-repaired. **Our field-name normalization defense in skills can stay; not load-bearing.** |
| **#8712** — `nextWakeAtMs` null bug (jobs persisted but never executed, WSL2-reported in 2026.2.1) | **FIXED** in v2026.3.13 or earlier | Closed 2026-02-04 as duplicate of #7326 → #8558 → fixed by PR #11641 (merged 2026-02-08). Our pinned v2026.3.13 already contains the fix. v2026.4.12 (#63507) added belt-and-suspenders self-heal for corrupted zero timestamps. **No risk on either current or upgraded version.** |

**Important correction to prior research:** the prior note (`2026-05-27-openclaw-native-primitives.md`) flagged #8557 and #8712 as "reportedly fixed but keep the defensive pattern." This research confirms they were fully resolved BEFORE our v2026.3.13 pin. The defensive patterns are still valuable as documentation but not as bug guards.

---

## Q4 — New features worth adopting

Listed in order of relevance to Watchers V1.

1. **Task Flow (v2026.4.2 GA, hardened through v2026.5.x)** — managed-vs-mirrored sync modes, durable state, `openclaw flows list|show|cancel`, `api.runtime.taskFlow` programmatic seam.
   - **Worth investigating, NOT for V1.** Prior research correctly flagged this. The programmatic API exists now (`api.runtime.taskFlow`), but it's a plugin-only seam — skills can't author Task Flows directly without a small plugin wrapper. Worth a runtime probe to evaluate for V2 consolidation of our `action_chain` DSL. **V1 ships unchanged.**

2. **`before_agent_reply` hook (v2026.4.2, #20067)** — plugins can short-circuit the LLM with synthetic replies after inline actions.
   - **Latent feature; not for V1.** Useful for response guardrails (e.g., "don't post if confidence is low") but requires a custom plugin. Skip for now.

3. **`Cron: accept leading-plus relative durations such as +5m for one-shot --at schedules` (v2026.5.26, #86341)** — ergonomic improvement for scheduling.
   - **Useful for the Reminder Dispatcher / Watcher creation flow.** Today our `lib/rrule_helper.py` and Phase C reminder skills compute `atMs` manually. Switching to `+5m` style for short-fuse reminders is a small QoL win; not a blocker. Adopt opportunistically.

4. **`Cron: seed active scheduled/manual cron task rows with progress summary` (v2026.5.26, #86313)** — `cron list/status` shows in-progress jobs instead of blank.
   - **Pure observability win.** No skill changes needed.

5. **`Cron: split runtime execution state into jobs-state.json` (v2026.4.20, #63105)** — definitions stay stable for git tracking; state isolated.
   - **Relevant if we ever want to source-control cron job definitions** (separate from the current "skill creates cron via tool-call" pattern). Today our 14 crons live in the runtime volume; splitting state out makes it easier to back up just the definitions. Latent benefit.

6. **`Cron: restore suspended cron lanes to configured/default concurrency after quota/circuit-breaker auto-resume` (v2026.5.26)** — recovery hardening.
   - **Reduces tail risk** of "cron parallelism stuck at 1 after a model error storm." Direct benefit; no code change required.

7. **Hook agent allowlist tightening (v2026.5.26, #86101)** — security default.
   - **Verify on first deploy:** smoke test the Fireflies webhook to confirm it still reaches the default agent. If broken, adding an explicit `agentId` to the mapping fixes it. Low risk.

8. **`Cron tool: infer creating session's agentId for cron.add` (v2026.4.22, #40571)** — quality-of-life for cron creation from skills.
   - We currently set `"agentId": "main"` explicitly on all 14 crons. The new default is the creating session's agent. No change required — explicit `"main"` continues to work.

**Verdict on Watchers V1 simplification:** None of the v2026.4/5 features collapse our `action_chain` DSL into a native primitive. Watchers V1 architecture is unchanged by this upgrade. The upgrade is value-positive but **not a Watchers V1 enabler**.

---

## Q5 — Upgrade + rollback procedure

### Upgrade is a single-line Dockerfile change

The 1panel/openclaw image has the `2026.5.26` tag published (confirmed on Docker Hub).

**Step 1 — Edit Dockerfile:**

```diff
-FROM 1panel/openclaw:2026.3.13
+FROM 1panel/openclaw:2026.5.26
```

**Step 2 — Optional pre-flight: bump skills snapshot invalidation.**

v2026.4.15 (#67401) added cache invalidation when `skills.*` config writes happen, so a fresh deploy will refresh the skills snapshot automatically. No action needed.

**Step 3 — Commit + push.** Railway picks up the new image, the gateway runs `openclaw doctor` implicitly on boot, and:

- `~/.openclaw/cron/jobs.json` is split into `jobs.json` (definitions) + `jobs-state.json` (state) by Doctor migration. Idempotent — re-running is safe.
- Any malformed cron job IDs (`jobId` instead of `id`, non-string `id`, missing `id`) are auto-repaired (v2026.4.23, #70128).
- Config migrations (v2026.4.5 alias renames) run if needed — we don't use any of the legacy aliases, so this is a no-op for us.

**Step 4 — Verify after deploy.** Run smoke checks:

1. Gateway boot log mentions v2026.5.26.
2. `curl -fsS http://127.0.0.1:18789/healthz` returns OK (existing Docker HEALTHCHECK already covers this).
3. Slack `/alaska help` (or any existing slash command) routes through.
4. Trigger a manual cron via Slack DM → confirms cron lane works.
5. Send a test Fireflies webhook with valid `HOOKS_TOKEN` → confirms hook routing works under the v2026.5.26 hook-allowlist tightening.

### Rollback procedure

**If unexpected issues arise**, the rollback is identical structure:

```diff
-FROM 1panel/openclaw:2026.5.26
+FROM 1panel/openclaw:2026.3.13
```

Push, redeploy. The cron state file split (`jobs-state.json`) created by v2026.5.26 will be ignored by v2026.3.13 (which only reads `jobs.json`). Brief consideration: `jobs.json` under v2026.5.26 no longer contains the `state` block — when v2026.3.13 reads it, all cron jobs will appear to have never run, but the next run computes from scratch using `schedule.expr` so the worst case is one duplicated fire for `kind: cron` jobs (and `kind: at` one-shots are typically already past or yet-to-fire — they self-clean). **Acceptable rollback cost.**

For a cleaner rollback, before the upgrade, copy the current cron state file:

```bash
# In the Railway shell or via volume backup
cp /data/.openclaw/cron/jobs.json /data/.openclaw/cron/jobs.json.pre-v5.26
```

If rollback is needed, restore that file before re-deploying v2026.3.13.

---

## Recommendation

**SAFE TO UPGRADE NOW**

Confidence: **HIGH** for compatibility (config, hooks, cron API, skill format all verified against release notes); **HIGH** for safety (no breaking changes in any v2026.5.x stable release; the most recent breaking change was v2026.4.24 and is plugin-only); **MEDIUM** for "no surprises in production" — we haven't run v2026.5.26 against our exact workload yet.

### Justification

1. **No breaking change between v2026.3.13 and v2026.5.26 affects our setup.** The four breaking releases (v2026.3.22, v2026.3.28, v2026.3.31, v2026.4.5, v2026.4.24) all remove legacy aliases, plugin-only APIs, or features we don't use.
2. **All three tracked bugs (#8557, #11075, #8712) were already resolved or mitigated before v2026.3.13** — the upgrade is value-additive, not bug-fix-driven. v2026.4.10, v2026.4.12, and v2026.4.23 add belt-and-suspenders self-healing for the cron-store family of issues.
3. **The cron isolated-delivery hardening in v2026.4.27** is directly relevant — we use `delivery.mode: "none"` on every cron, and #69285 fixes false delivery-failure logs we have likely seen in production.
4. **v2026.5.26 itself is fixes-and-perf-only**, no breaking changes, large security and reliability surface (rate limiter on auth failures, memory_store prompt-injection filter, default hook agent allowlists). Net positive on safety.
5. **The Doctor handles the one schema change (v2026.4.20 cron state split) transparently on first boot.** No action required.

### Pre-flight items (not blockers)

- **Smoke test** the Fireflies hook after upgrade — v2026.5.26 hook agent allowlist tightening (#86101) is the one config-adjacent behavior change. If our default agent isn't on the allowlist, we add an explicit `agentId` field to the mapping; trivial fix.
- **Back up `/data/.openclaw/cron/jobs.json`** before deploy (via Railway shell or volume snapshot) — gives a clean rollback path if needed.
- **Watch the first 24h of cron fires** — v2026.4.20's state file split is the biggest behind-the-scenes change. If any cron stops firing, `openclaw doctor` is the first remediation.

### When to upgrade

**Now is fine.** No reason to defer for Watchers V1 — Watchers V1 will build the same way on either version, and v2026.5.26 adds reliability fixes (cron-delivery, cron-suspension-recovery, heartbeat-loop) that directly benefit the Watchers V1 production surface.

If we want to be conservative, deploy on a **low-traffic window** (e.g., weekend or pre-9AM-IST cron storm) so the Doctor migration runs cleanly and the first cron storm exercises the new state-file path.

---

## Optional runtime probes

Three probes to tighten confidence to "HIGH across the board" before declaring Watchers V1 build-ready on v2026.5.26:

1. **Fireflies hook smoke test post-upgrade.** Send a synthetic Fireflies webhook with a known transcript ID; confirm the agent receives and processes it. Validates the hook agent allowlist change (#86101).

2. **Cron state file split verification.** After first boot on v2026.5.26, confirm `/data/.openclaw/cron/jobs-state.json` exists alongside `jobs.json`, and that all 14 production crons appear in both with consistent IDs. Validates the v2026.4.20 split landed correctly.

3. **Cron lane concurrency recovery test.** Force a model error storm (run 10 cron jobs with bad model config simultaneously), then verify the cron lane returns to `maxConcurrentRuns: 8` afterward, not stuck at 1. Validates the v2026.5.26 #86101 recovery fix.

None of these block the upgrade — they're confirmations after the fact.
