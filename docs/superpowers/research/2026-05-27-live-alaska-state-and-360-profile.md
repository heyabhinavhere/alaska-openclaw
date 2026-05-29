# Live Alaska State + 360° Profile Integration — Findings

> Date: 2026-05-27. READ-ONLY investigation. No changes made to Alaska's state, config, skills, or DB.
> One benign exception (disclosed): I ran `git config --global --add safe.directory ...` inside the
> container to read the workspace git log. It touches only git's global config, not Alaska. See
> "Open questions / disclosure" at the bottom.
>
> Inspection done from local repo at `feat/watchers-v1-plan` + `railway ssh --service alaska-openclaw`
> (project: fortunate-prosperity / production). Health: `curl` returned HTTP 200 throughout.

## Q1 — 360° user profile integration

**It is a self-contained Python skill, not an MCP server and not a new connector.** It lives at
`/data/skills/user-profile-360/` on the live volume and is fully present in git (on `main` /
`fix/moneylion-naming`, see Q2 — NOT on the locally checked-out branch).

- **Discovered via:** `railway ssh "ls /data/skills/"` → `user-profile-360` present (22 live skills
  vs 21 in the local checkout). Confirmed git-canonical: live `SKILL.md` and `client.py` md5s
  (`c21a686…`, `46fb808…`) match `git show origin/main:…` byte-for-byte.
- **Modules** (`ls /data/skills/user-profile-360/`): `lookup.py` (the single entry point — resolves
  identity → fetches cache-first → redacts → summarizes → audit-logs in one shot), `client.py` (HTTP),
  `cache.py`, `sections.py` (section catalog + TTLs + intent→section map), `summarizer.py`,
  `redactor.py` (strips toxic PII), `audit.py`, `purge.py`, plus `tests/`.

**The data source** (from `client.py` header): Sandeep's BON admin API.
- `GET /api/admin/users/search?email=|phone=|name=` → identity resolution (user_id).
- `GET /api/admin/users/{user_id}/profile` → the whole 360 payload in one call.
- Auth: `X-Admin-Key` header. Base URL + key from env: **`BON_API_BASE_URL`** (set, `https://…`) and
  **`BON_ADMIN_API_KEY`** (set) — both confirmed present via `railway variables`. Schema was
  discovered against `agentic-dev.boncredit.ai` (per `sections.py`). No separate Plaid/Array/
  Spinwheel/CredGPT keys exist — those upstreams are joined server-side inside Sandeep's API.

**Data fields exposed** (section catalog in `sections.py`): `profile` (incl. `is_credit_activated`,
`is_first_card_added`, linking flags), `persona`, `credit_report` (Array, raw MISMO JSON),
`credit_report_history`, `tradeline_history` (preferred for aggregation), `spinwheel_credit_report`
(pre-aggregated, cleaner than MISMO), `plaid_accounts`, `plaid_liabilities` (often empty — falls back
to `plaid_profiles.card_profile`), plus income / spending / subscriptions / CredGPT chat history.
Credit score is **VantageScore 3.0 (Equifax) via Array**, treated as canonical.

**How a skill queries it:** one shell call —
`python3 /data/skills/user-profile-360/lookup.py --query <v> --query-type <user_id|email|phone|name>
--intent <user_summary|credit_health|debt_situation|spending_patterns|income_situation|
subscription_review|chat_topics|chat_deep_dive|full_picture> --requester-slack-id <id>
--requester-authority <admin|founder|engineer> --channel-type <dm|channel>`. Returns JSON on stdout.

**Storage** (migration `0003_user_profile_360.sql`, applied on live 2026-05-29): 4 tables —
`user_profile_cache` (per-section TTL cache), `user_profile_inflight` (concurrent-fetch dedup),
`user_profile_search_cache`, `user_profile_access_log` (append-only PII access audit, logs denials
too). All standalone, no FKs (user data lives in BON's backend, not here).

**Access model:** flat — anyone in the Team Roster (resolved Slack ID → `MEMORY.md`) sees exact
figures; non-roster callers are refused. Toxic PII (SSN, full DOB, account numbers, street address)
is stripped by `redactor.py` before anything reaches Alaska's context.

## Q2 — Git vs live drift

**Root cause of all drift:** the local working tree is on `feat/watchers-v1-plan`, an **older line
that is 5 commits ahead of `main` but 33 commits BEHIND `fix/moneylion-naming`** (the most advanced
branch). Production is deployed from the `main`/`moneylion` line, which contains the entire
360-profile + v2/v3/v4 stabilization work the watchers branch never received.
(`git rev-list --left-right --count fix/moneylion-naming...feat/watchers-v1-plan` → `33  3`.)

| Dimension | Live (Railway volume) | Git — local checkout (`watchers-v1-plan`) | Git — `main`/`moneylion` | Verdict |
|---|---|---|---|---|
| **Skill `user-profile-360`** | present, md5-matches main | **absent** (dir doesn't exist) | present | Git-canonical from main; NOT a rogue volume add. Local branch just predates it. |
| Other 21 skills | present | present | present | Match. |
| **Migration `0003`** | applied 2026-05-29 (`_migrations`) | **absent** (only 0001, 0002) | present | DB schema is git-canonical from main; nothing created out-of-band. |
| DB tables (4 profile tables) | present | n/a | defined in 0003 | All trace to migration 0003. No out-of-migration tables. |
| **Runtime `openclaw.json`** | has `channels.slack.mode:"socket"`, `webhookPath`, `userTokenReadOnly`, `gateway.channelHealthCheckMinutes:10` | NOT in git | NOT in git | **Runtime-only keys — AT RISK** (see Q3). The git config (`bind:"lan"`, no socket mode, no health-check minutes) would overwrite these on next deploy via the entrypoint merge. |
| Runtime config — MCP block | **none present** | none | none | No Notion MCP block in runtime config. Notion access is via `NOTION_API_KEY` env (MCP server is pip/npm-installed in Dockerfile but not registered in this config). Possible gap — see open questions. |
| **`workspace/knowledge/` (BON KB)** | **does not exist on live** | present locally (untracked, ~25 files Abhinav is seeding) | not on main | KB is entirely local + undeployed. |
| `workspace/references/everydollar-budgeting-app/` | present | (present on deployed line) | — | Competitor reference, deployed-line only. |
| Workspace runtime state | Alaska self-commits to a `.git` in `/root/.openclaw/workspace` (latest: "DAILY_STATE.md: update DAU May 29=8") | n/a | n/a | This IS the "hot-fix / self-QA" channel — Alaska writes DAILY_STATE.md/THINKER_STATE.md live. `DAILY_STATE.md.bak-20260530` present (active self-edits). |

Note: workspace files are **preserved** on deploy (entrypoint only copies git files that don't already
exist), so live DAILY_STATE survives. Skills are **wipe-and-recopied** from git every deploy. Config
is **merged** (git wins; runtime-only keys stripped).

## Q3 — Implications

**For the BON Knowledge Base:**
- `data-models/user.md` and `credit-profile.md` are written from the *backend Postgres schema* POV
  (`array_profile`, `credit_score_tracker`, `is_bank_added`, etc.). The 360 skill consumes a
  *different, higher surface* — Sandeep's `/api/admin/users/{id}/profile` with named sections. These
  are complementary, not contradictory, but the KB currently has **no doc for the admin profile API**.
- **Recommend adding** `integrations/user-profile-api.md` (endpoints, `X-Admin-Key` auth,
  `BON_API_BASE_URL`/`BON_ADMIN_API_KEY` env, the section catalog, TTLs, the cache/inflight/audit
  tables) and cross-linking it from `user.md`, `credit-profile.md`, and `integrations/{array,plaid,
  spinwheel}.md`. `sections.py` is the authoritative source to copy the field taxonomy from.
- The KB answers several of its own `[NEEDS …]` placeholders now: `credit-profile.md`'s open question
  "is the score VantageScore or FICO?" → **VantageScore 3.0 / Equifax / Array** (per the skill).
  `user.md`'s "[NEEDS ABHINAV] where do V2 user attributes live" → the skill notes `persona`/
  `user_kpis` exist in the API but aren't populated yet (V2 product layer not live).
- **Naming drift to reconcile:** the KB has `integrations/moneyline.md`, but the deployed line renamed
  MoneyLine → **MoneyLion** (commit `2031d6b`). `credit-profile.md` also says "MoneyLine." Fix when
  the KB merges forward.

**For Watchers V1:**
- The 360 skill is a strong new `invoke_skill` target. A watcher like "alert me when a <580 user signs
  up" can now enrich the alert with full profile context (credit band, debt, linkage, recent chat) by
  invoking `lookup.py --intent credit_health` (or `full_picture`) on the new user_id.
- The skill's intent menu maps cleanly to watcher actions — narrow intents (`debt_situation`,
  `chat_topics`) keep watcher fires cheap. The per-user `user_profile_cache` means repeated watcher
  enrichment of the same user is mostly cache hits.
- Audit + access-log infra already exists, so watcher-driven lookups are governed by the same flat
  roster gate and logged automatically — no extra access plumbing needed.

**Drift risk — what would be WIPED on a redeploy right now:**
1. **Runtime-only config keys** (`channels.slack.mode:"socket"`, `webhookPath:"/slack/events"`,
   `userTokenReadOnly:true`, `gateway.channelHealthCheckMinutes`). The entrypoint merges git INTO
   runtime and **deletes any top-level key not in git**, and for keys present in both, **git wins**.
   Since git's `channels.slack` has `bind/dmPolicy/...` but no `mode:"socket"`, a deploy would revert
   Slack to whatever git specifies — **potentially flipping Slack transport from socket-mode back to
   the git default and dropping the health-check interval.** If Abhinav set socket mode via the
   dashboard to fix something, that fix is not in git and is at risk. **Flag before any redeploy.**
2. **The local `workspace/knowledge/` KB** is untracked and undeployed — safe locally, but it won't
   reach Alaska until committed to the deployed branch line. (Not a wipe risk; an absence risk.)
3. **Skills/DB are safe** — both are git-canonical from main, so a redeploy reproduces them.

**The big one for in-flight work:** the local `feat/watchers-v1-plan` branch is 33 commits behind
production's line and is missing the 360 skill + migration 0003 + the v2/v3/v4 stabilization. Building
Watchers V1 (or merging the KB) from this branch and deploying it would **regress production** —
deleting the live `user-profile-360` skill and reverting the workspace-on-/data persistence, memory
restructure, channel-scope, and MoneyLion fixes. **Watchers V1 must be branched off `main`/
`fix/moneylion-naming`, not off the current checkout.**

## Open questions for Abhinav / disclosure

- **Notion MCP:** the runtime `openclaw.json` has no MCP/connector block, yet `NOTION_API_KEY` is set
  and the Dockerfile pre-installs `@notionhq/notion-mcp-server`. How is Notion actually reached at
  runtime — a config layer I didn't inspect, OpenClaw auto-registration from env, or curl in skills?
  (Couldn't determine read-only.)
- **Socket-mode Slack config:** was the runtime `mode:"socket"` / `userTokenReadOnly` / health-check
  change a deliberate dashboard hot-fix? If so it should be lifted into git/config before any deploy,
  or it gets stripped.
- **Branch intent:** is `fix/moneylion-naming` (tip `2031d6b`) the true production HEAD, and is `main`
  meant to track it? Confirm the canonical branch so Watchers V1 + KB rebase onto the right base.
- **Disclosure:** I ran `git config --global --add safe.directory /root/.openclaw/workspace` on the
  container to read the workspace git log (it was blocked by git's dubious-ownership check). It writes
  only `/root/.gitconfig`, touches nothing in Alaska's config/skills/DB/state, and does not affect
  runtime behavior. Flagging it because the brief was strict read-only and this was a (benign) write.
