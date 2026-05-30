# Post-Incident Integrity Audit — Alaska Production Volume

**Date:** 2026-05-30
**Auditor:** forensic research subagent (read-only)
**Trigger:** Three stale `railway up` deploys on 2026-05-27 22:42–23:07 IST from a branch 32 commits behind main (now `REMOVED`). Active deploy `fe858583` (GitHub-main-sourced, 2026-05-30 01:36 IST).
**Method:** READ-ONLY only. `railway ssh "<read cmd>"`, `sqlite3 SELECT/.schema/.tables`, `git log/show/ls-tree`, `curl` GET. No writes, no config/DB mutation, no restart/redeploy, no `openclaw doctor`.
**Live version confirmed:** `OpenClaw 2026.3.13` (`railway ssh "openclaw --version"`).
**Health at audit time:** `HTTP 200 in 0.96s` — service UP, SSH never dropped.

> **Method note on byte-for-byte comparisons:** "match" = identical MD5. Live MD5s via `md5sum` (Linux container); git-side MD5s via macOS `md5` of `git show origin/main:<path>`. MD5 is content-addressed and platform-independent, so identical hashes prove identical bytes.

---

## Section 0 — Deployment layer — **HEALTHY**

**Active = `fe858583`; the 3 stale deploys are REMOVED.**

```
$ railway deployment list
  fe858583-da3c-4264-a63e-516b87c202b9 | SUCCESS  | 2026-05-30 01:36:22 +05:30   <-- ACTIVE
  ...
  ab4bf4a0-4dac-4140-b1e5-5205e180beec | REMOVED  | 2026-05-27 23:07:40 +05:30   <-- stale #3
  c4ac190c-db87-4602-a4d1-eccd80286b02 | REMOVED  | 2026-05-27 23:04:18 +05:30   <-- stale #2
  5e8052fc-81c9-4373-95e7-e79692f1e727 | REMOVED  | 2026-05-27 22:42:11 +05:30   <-- stale #1
```

All three named stale deploys (`5e8052fc`, `c4ac190c`, `ab4bf4a0`, timestamps 22:42–23:07 on 2026-05-27) are `REMOVED`. Active is `fe858583`, `SUCCESS`.

**Active deploy booted CLEAN on v2026.3.13 — no repair warnings:**

```
$ railway logs   (active deployment, boot sequence)
[sync_workspace] workspace ready on persistent volume /data/workspace (config refreshed, state preserved)
[alaska] SQLite queue already exists.
[alaska] Checking for pending migrations...
[alaska] Merging git config into runtime config...
[alaska] Config merged successfully
[migrations] 0001_v2_task_model.sql already applied — skipping
[alaska] Skills mirror-synced from git to /data/skills/ (22 skills present)
[migrations] 0002_classifier_secondary_intents.sql already applied — skipping
[migrations] 0003_user_profile_360.sql already applied — skipping
[alaska] Migrations complete.
[alaska] Hooks token injected into config
[alaska] Starting OpenClaw gateway...
2026-05-29T20:07:39 [health-monitor] started (interval: 600s, ...)
2026-05-29T20:07:39 [gateway] agent model: anthropic/claude-opus-4-6
2026-05-29T20:07:40 [slack] socket mode connected
```

Key absences (all GOOD): no `⚠️ Runtime config is CORRUPTED`, no `Removing stale key:`, no `Restored runtime config from .bak`. The config guard's repair path and the merge's strip path were BOTH untriggered on last boot → the volume's config was already valid going in. `SQLite queue already exists` → DB was not re-initialized. `socket mode connected` → Slack came up clean.

> Note (not damage): `agent model: anthropic/claude-opus-4-6`. The git config pins no model, so this is OpenClaw's runtime default, unrelated to the stale deploys.

---

## Section 1 — Skills integrity — **HEALTHY**

**Live skill list == main skill list (whitespace-normalized diff is empty):**

```
$ railway ssh "ls -1 /data/skills/"  → 22 dirs:
alaska-core amplitude-analyst customerio-ops daily-pulse doc-keeper follow-through
intent-classifier log-usage meeting-intelligence onboarding pre-call-brief proposal-loop
reminder-dispatcher report-health risk-radar shared-toolkit slack-commands sprint-operator
task-handler thinker user-profile-360 whatsapp-send

$ git ls-tree origin/main skills/  → 22 skill dirs + skills/.gitkeep

$ diff <(live, sorted) <(main dirs minus .gitkeep, sorted)
NO_DIFF — lists identical (whitespace-normalized)
```

`.gitkeep` is also present live (`ls -1a` shows it). No orphan skill live-but-not-on-main; no skill on-main-but-not-live. `user-profile-360` (the skill added in the missing-32-commits window) is present.

**4 critical SKILL.md files — MD5 match byte-for-byte:**

```
live md5sum                              git md5
c21a6869774d1da3f72f10dd9d0c951c  user-profile-360/SKILL.md      == c21a6869774d1da3f72f10dd9d0c951c
34236ac84ee3dd55766b7d2a19cbba50  task-handler/SKILL.md          == 34236ac84ee3dd55766b7d2a19cbba50
6fff3944f1071a68b7803ffb27d432ba  intent-classifier/SKILL.md     == 6fff3944f1071a68b7803ffb27d432ba
1571392c345afa46050b9f2db7386b06  meeting-intelligence/SKILL.md  == 1571392c345afa46050b9f2db7386b06
```

**`user-profile-360` — ALL 14 files MD5-match main (SKILL.md + 8 .py + 5 test .py):**

```
live (find ... | md5sum)                 git (git show ... | md5)   MATCH?
c21a6869...  SKILL.md                                  c21a6869...   ✓
a750e987...  audit.py                                  a750e987...   ✓
f86a528e...  cache.py                                  f86a528e...   ✓
46fb8080...  client.py                                 46fb8080...   ✓
e3cd3e01...  lookup.py                                 e3cd3e01...   ✓
6a1554ed...  purge.py                                  6a1554ed...   ✓
352c16af...  redactor.py                               352c16af...   ✓
88f0425e...  sections.py                               88f0425e...   ✓
eeb14595...  summarizer.py                             eeb14595...   ✓
7493281c...  tests/test_cache_audit.py                 7493281c...   ✓
c995f609...  tests/test_client.py                      c995f609...   ✓
688ae442...  tests/test_lookup.py                      688ae442...   ✓
6f80940f...  tests/test_redactor.py                    6f80940f...   ✓
17d977a2...  tests/test_summarizer.py                  17d977a2...   ✓
```

Zero mismatches, zero missing files. The GitHub-main auto-deploy fully re-synced skills after the stale deploys. **No residual skill damage.**

---

## Section 2 — Config integrity — **HEALTHY**

**Live runtime config dump (`railway ssh "cat /data/.openclaw/openclaw.json"`, secret values redacted):**

```json
{
  "tools": { "agentToAgent": { "enabled": true } },
  "hooks": {
    "enabled": true, "path": "/hooks", "token": "<REDACTED 64-hex>",
    "mappings": [ { "id": "fireflies-transcript", ... "deliver": true, "channel": "slack" } ]
  },
  "channels": {
    "slack": {
      "mode": "socket",                  <-- runtime-only, PRESENT
      "webhookPath": "/slack/events",    <-- runtime-only, PRESENT
      "enabled": true,
      "userTokenReadOnly": true,         <-- runtime-only, PRESENT
      "groupPolicy": "open", "streaming": false, "nativeStreaming": false,
      "dmPolicy": "open", "allowFrom": ["*"]
    }
  },
  "gateway": {
    "port": 18789, "mode": "local", "bind": "lan",
    "controlUi": { "allowedOrigins": ["https://alaska-openclaw-production.up.railway.app"],
                   "dangerouslyDisableDeviceAuth": true },
    "auth": { "mode": "token" },
    "trustedProxies": ["0.0.0.0/0"],
    "channelHealthCheckMinutes": 10      <-- runtime-only health interval, PRESENT
  }
}
```

**Structural key-diff (live vs `git show origin/main:config/openclaw.json`, via Python flatten):**

```
=== KEYS IN GIT-MAIN but ABSENT in LIVE (would mean merge failed) ===
  (none — every git-main key is present live)

=== KEYS IN LIVE but NOT in GIT-MAIN (runtime-only — must be preserved) ===
  channels.slack.mode = 'socket'
  channels.slack.userTokenReadOnly = true
  channels.slack.webhookPath = '/slack/events'
  gateway.channelHealthCheckMinutes = 10

=== VALUE MISMATCHES on shared keys ===
  hooks.token: git='__HOOKS_TOKEN__' live=<injected at boot>   (EXPECTED — templated)
  (no other mismatches)
```

All three runtime-only keys the prior research flagged (`slack.mode:"socket"`, `slack.userTokenReadOnly`, the `channelHealthCheckMinutes` health interval) are **PRESENT NOW**. They were NOT stripped. Every git-main key applied. Only "mismatch" is the templated hooks token (`__HOOKS_TOKEN__` in git → injected at boot via `sed`), which is correct.

**No corruption-archive files exist:**

```
$ railway ssh "ls -la /data/.openclaw/openclaw.json*"
-rw------- 1642  May 29 20:07  openclaw.json          <-- current, valid
-rw------- 1605  May 27 16:46  openclaw.json.bak       <-- OpenClaw rolling auto-backup
-rw------- 1605  Apr  1 08:45  openclaw.json.bak.1     <-- "
-rw------- 2026  Mar 31 20:07  openclaw.json.bak.2     <-- "
-rw------- 2249  Mar 31 20:00  openclaw.json.bak.3     <-- "
-rw------- 2026  Mar 31 20:00  openclaw.json.bak.4     <-- "
```

NO `openclaw.json.broken-*` files. The entrypoint guard creates `openclaw.json.broken-<timestamp>` only when it detects corruption — none exist, so the guard's corruption path was never hit on this volume. The `.bak*` files are OpenClaw's own rolling backups (note the Mar/Apr dates, predating the incident), not guard archives. **Config fully intact; no hidden damage.**

---

## Section 3 — Database integrity — **HEALTHY** (with one explained nuance)

**Tables (`sqlite3 .tables`) — all expected present, incl. all 4 `user_profile_*`:**

```
_migrations  agent_runs  agent_signals_local  blockers  briefed_meetings
classifier_audit  daily_pulse  doc_keeper_log  fireflies_dedup  intent_inbox
last_check_timestamp  new_done_tasks  nudges  outbox  phase_a3_replay_audit
processed_meetings  proposals  risk_scores  routine_proposals  scheduled_actions
snoozes  sprints  standup_prompts  system_health  task_categories  task_events
task_mentions  tasks  temp_done_tasks  thinker_observations  token_usage
user_profile_access_log  user_profile_cache  user_profile_inflight  user_profile_search_cache
```

**Migration tracking (`_migrations` — the run_migrations.sh table; NOT "schema_migrations") — all 3 recorded:**

```
$ sqlite3 -header -column /data/queue/alaska.db 'SELECT * FROM _migrations ORDER BY filename;'
filename                               applied_at
-------------------------------------  -------------------
0001_v2_task_model.sql                 2026-05-25 04:58:13   (pre-incident)
0002_classifier_secondary_intents.sql  2026-05-26 05:55:01   (pre-incident)
0003_user_profile_360.sql              2026-05-29 10:17:53   (re-applied by GitHub-main deploy)
```

**Row counts:**

```
$ sqlite3 ... "SELECT name, COUNT(*) ..."
tasks                      | 0
task_events                | 0
task_mentions              | 0
blockers                   | 0
scheduled_actions          | 0
intent_inbox               | 584
classifier_audit           | 584
user_profile_cache         | 26
user_profile_inflight      | 0
user_profile_access_log    | 5
user_profile_search_cache  | 0
```

**Interpretation (per the "be skeptical" rule):** The v2 task-model tables (`tasks`, `task_events`, `task_mentions`, `blockers`, `scheduled_actions`) show **0 rows**. This is **NOT stale-deploy damage**, for three independent reasons:
1. The stale deploys ran the OLD entrypoint, which only touches SQLite via `if [ ! -f alaska.db ]` (create-if-absent) and idempotent migrations. No code path DROPs or DELETEs these tables. The DB file persisted (`SQLite queue already exists` in the boot log).
2. The schema is fully present and correct (see below) and `_migrations` shows 0001 applied 2026-05-25 — *before* the incident — and never rolled back.
3. These tables back the **v2 task model**, which per project state is "V1 coding done, validating" — i.e. the v2 writer is not yet live-populating them. Meanwhile `intent_inbox`/`classifier_audit` (584 each) and `user_profile_cache`/`access_log` (26/5) carry real, current data → the live data path is healthy.

The 0-row tables would only be a red flag if a baseline showed them previously populated. No such baseline exists (stated in the brief), and the mechanism for loss is absent. Classified HEALTHY; flagged transparently under "COULD NOT VERIFY" for the missing baseline.

**Schema match (live `.schema` vs migration files) — v2 task tables + user_profile tables:**
- `tasks`, `task_events`, `task_mentions`, `blockers`, `scheduled_actions`, `intent_inbox`, `classifier_audit`: live schema matches `0001` exactly — all columns, all CHECK constraints, the `trg_tasks_updated_at` trigger, and all indexes (`idx_tasks_owner_status`, `idx_task_events_task`, etc.) present.
- `classifier_audit.secondary_intents TEXT DEFAULT '[]'` (added by `0002`) is **present** in the live schema (last column) → 0002 fully applied, not half-applied.
- `user_profile_cache / _inflight / _access_log / _search_cache`: live schema matches `0003` exactly — all columns, all CHECK constraints (`requester_authority`, `outcome`, `channel_type`, `redaction_tier`, `query_type`), all indexes (`idx_upc_*`, `idx_upal_*`, `idx_upsc_*`).

No half-applied migration. **DB schema intact.**

---

## Section 4 — Workspace integrity — **HEALTHY**

**`/root/.openclaw/workspace` IS a symlink → `/data/workspace` (persistence model intact):**

```
$ railway ssh "ls -la /root/.openclaw/workspace"
lrwxrwxrwx 1 root root 15 May 29 20:07 /root/.openclaw/workspace -> /data/workspace
$ railway ssh "readlink -f /root/.openclaw/workspace"
/data/workspace
```

It is a symlink, not a real directory. No competing/duplicate real workspace at `/root/.openclaw/workspace`. The stale deploy's old (pre-symlink) logic did NOT leave a broken model — `sync_workspace.sh` re-affirmed the symlink on the recovery boot.

**Persist target contents — all required state files present:**

```
$ railway ssh "ls -la /data/workspace/"
AGENTS.md  AGENT_RULES.md  BON_CREDIT_DESIGN_DOC.md  DAILY_STATE.md  HEARTBEAT.md
IDENTITY.md  MEETING_INTELLIGENCE_V2.md  MEMORY.md  SOUL.md  THINKER_STATE.md  TOOLS.md
USER.md  Weekly_Digest_April_14-17_2026.md  sprint-planning-status.md
memory/  references/  scripts/  .git/  .openclaw/
DAILY_STATE.md.bak-20260530    <-- a manual/runtime backup (harmless)
```

Required files DAILY_STATE.md, THINKER_STATE.md, MEMORY.md, SOUL.md, TOOLS.md, AGENT_RULES.md, AGENTS.md — all present. `memory/` and `references/` directories present (with content).

**`knowledge/` dir absent — but this is EXPECTED, not damage:** `sync_workspace.sh` lists `knowledge` in `WS_CONFIG_DIRS`, but it only seeds dirs that exist in the image (`/opt/default-workspace`). `git ls-tree -r origin/main workspace/` confirms **no `workspace/knowledge/` in the git image** → nothing to seed → absence is correct.

**Freshness — state files are RECENT (May 29), not clobbered to a stale date:**

```
$ railway ssh "head /data/workspace/DAILY_STATE.md"
# Last compiled: 2026-05-29 16:30 UTC (from May 29 team call)

$ ... THINKER_STATE.md
# Last updated: 2026-05-29 15:31 UTC

$ ... MEMORY.md
Last updated: 2026-05-29
```

mtimes corroborate the preserve-vs-refresh design: git-canonical CONFIG files (SOUL/TOOLS/AGENTS/MEMORY/etc.) all `May 29 20:07` (refreshed at the recovery boot), while STATE files DAILY_STATE.md (`19:37`) and THINKER_STATE.md (`15:34`) retain earlier preserved mtimes. No file regressed to a stale (e.g. May-21) date → no seed-from-git clobber of runtime state. **Workspace fully intact.**

---

## Section 5 — Cron integrity — **HEALTHY**

```
$ railway ssh "ls -la /data/.openclaw/cron/"
-rw------- 62487  May 29 20:15  jobs.json
-rw------- 62525  May 29 20:15  jobs.json.bak
-rw------- 61524  May 27 17:33  jobs.json.pre-v5.26    <-- known harmless backup, as expected
drwx------        May 25 14:40  runs/
```

- **`jobs-state.json` is ABSENT** (`test -f ... && echo EXISTS || echo ABSENT` → `ABSENT — good`). The crashed v5.26 upgrade did NOT leave a partial-migration artifact. This directly clears stated-risk #4.
- `jobs.json.pre-v5.26` present (the known backup) — noted, harmless.

**Job count = 13, all enabled, and a strict SUPERSET of the pre-v5.26 backup (12) → nothing dropped:**

```
$ cat jobs.json | python3 (len + enabled)
COUNT: 13   (all 13 enabled=True)

$ compare current vs jobs.json.pre-v5.26 (sorted IDs)
CURRENT (13): [...c73b2390, d68db521, 6f47d5f3, cc5aa06b, 78bed8c7, 4c66b47c,
               90d41d53, f1fe3123, efd2e521, 95fa890c, 2a93b1f6, 07cb97da, 22446cc3]
PRE-v5.26 (12): same set MINUS 22446cc3
```

Current is pre-v5.26 + 1 new job (`22446cc3`, added after May 27). All 12 pre-incident jobs survived; one was legitimately added since. CLAUDE.md's "~14" is an approximation; actual is 13, all enabled. **Cron state intact and growing.**

---

## Section 6 — Stray artifacts — **HEALTHY**

```
$ railway ssh "find /data/.openclaw -maxdepth 2 \( -name '*.broken-*' -o -name '*.bak' \) -exec ls -la {} \;"
-rw------- 62525  May 29 20:15  /data/.openclaw/cron/jobs.json.bak
-rw------- 1605   May 27 16:46  /data/.openclaw/openclaw.json.bak
```

Only two `.bak` files, both normal rolling auto-backups (cron + config). **NO `*.broken-*` corruption archives anywhere** under `/data/.openclaw` → the entrypoint guard never had to archive a corrupt config on this volume. No leftover artifacts attributable to a failed/stale deploy.

---

## Section 7 — Git + PR hygiene — **SUSPECT** (volume is clean; the *remediation* is not yet in production)

**`origin/main` current:**

```
$ git log origin/main --oneline -5
59324e2 Merge pull request #25 from heyabhinavhere/docs/restore-final-wrap
7c81e2e docs: accuracy — cron dashboard sync is delegated/pending, not done
5d645f8 docs(stabilization): log Wave 5 (MoneyLion naming / Issue I) ...
e9afdea docs(stabilization): final wrap — coord doc + Alaska memory ...
5155a67 Merge pull request #23 from heyabhinavhere/fix/moneylion-naming
```

**FINDING 7a — PR #24 is 6 commits BEHIND main (brief expected 0):**

```
$ git rev-list --count origin/fix/entrypoint-config-guard..origin/main
6
$ git log origin/fix/entrypoint-config-guard..origin/main --oneline
59324e2, 7c81e2e, 5d645f8, e9afdea  (PR #25 + stabilization docs)
5155a67, 2031d6b                    (PR #23 MoneyLion naming)
```

The brief asserted this should be `0`. It is `6`. The 6 missing commits are **all docs/naming** (PR #23 MoneyLion rename, PR #25 stabilization wrap) — no code or skill changes — so rebasing PR #24 onto main is low-risk. But the brief's "based on current main" premise is **factually wrong**; report it rather than rubber-stamp it.

**FINDING 7b (MOST IMPORTANT) — the config-corruption guard is NOT in main and NOT in production:**

```
$ git show origin/main:entrypoint.sh | grep -c 'openclaw.json.broken-|Restored runtime config from .bak'
0                              <-- main has NO guard
$ git show origin/fix/entrypoint-config-guard:entrypoint.sh | grep -c ...
4                              <-- the guard lives ONLY on PR #24's branch
$ railway ssh "grep -c '...' /opt/entrypoint.sh"   (the DEPLOYED image entrypoint)
0                              <-- PRODUCTION is running WITHOUT the guard
```

PR #24 (`fix/entrypoint-config-guard`, state **OPEN**, MERGEABLE) is the home of the +33-line config-corruption guard built in response to *this very P0*. It has **not been merged to main**, and `origin/main` == the live `/opt/entrypoint.sh` (both guard-free). **Production currently has no automatic recovery from a corrupt `openclaw.json` write.** This is not volume *damage* — the volume is clean — but it is a live exposure: if another interrupted write corrupts the config, the boot has no `.bak`-restore safety net and could crash-loop. *(Note: the auditor's local working tree is checked out on `fix/entrypoint-config-guard`, which is why a guard-bearing 6953-byte entrypoint.sh is on disk locally; that is NOT what's deployed.)*

**Stale branch `feat/watchers-v1-plan` — its 3 unique commits are accounted for; nothing valuable stranded:**

```
$ git log origin/main..origin/feat/watchers-v1-plan --oneline
3e8599c docs(research): commit OpenClaw upgrade research + post-upgrade correction
9a9ffee revert(docker): rollback OpenClaw upgrade attempt — config schema break
11cdfbb hotfix(entrypoint): auto-restore openclaw.json from .bak on corrupt config
```

1. **`11cdfbb` entrypoint hotfix** → same guard now in PR #24 (verified: PR #24 branch entrypoint `grep -c` = 4). Accounted for.
2. **`9a9ffee` Docker bump+revert** → net no-op. `origin/main` Dockerfile = `FROM 1panel/openclaw:2026.3.13`; `watchers-v1` Dockerfile = also `FROM 1panel/openclaw:2026.3.13` (with a rollback comment). Same pin. Accounted for.
3. **`3e8599c` upgrade research doc** → preserved in PR #24 branch as `docs/superpowers/research/2026-05-27-openclaw-upgrade-v2026.3-to-v2026.5.md` (present on PR #24 branch + local tree; not yet in main). Accounted for (rides into main with PR #24).

`git diff --stat origin/main..watchers-v1` further confirms watchers-v1 is the stale culprit (38 files, +748/−4190 — it is *missing* the entire user-profile-360 skill, the workspace-persistence test, and MEMORY.md updates that are on main). No unique+valuable work is stranded there beyond the three commits above.

Verdict **SUSPECT** (not DAMAGED): the persistent volume shows no git-related damage, but production is missing the guard remediation and PR #24 is stale relative to main — both should be resolved.

---

## SUMMARY TABLE

| Section | Verdict | Evidence-backed? |
|---|---|---|
| 0 — Deployment layer | HEALTHY | Yes — `deployment list` + clean boot log |
| 1 — Skills integrity | HEALTHY | Yes — list diff + 14-file MD5 match |
| 2 — Config integrity | HEALTHY | Yes — full key-diff + no `.broken-*` |
| 3 — Database integrity | HEALTHY | Yes — `_migrations` + counts + `.schema` |
| 4 — Workspace integrity | HEALTHY | Yes — `readlink` + file list + headers |
| 5 — Cron integrity | HEALTHY | Yes — no `jobs-state.json`; 13⊇12 IDs |
| 6 — Stray artifacts | HEALTHY | Yes — `find` shows only normal `.bak` |
| 7 — Git + PR hygiene | SUSPECT | Yes — guard not in main/prod; PR#24 -6 |

---

## DAMAGE FOUND

**No residual damage to the persistent volume from the 2026-05-27 stale deploys.** Skills, config (incl. all runtime-only keys), DB schema + migration tracking, workspace symlink + state freshness, and cron state are all intact. The GitHub-main auto-deploy fully recovered the volume; the active boot needed zero repairs (no `Removing stale key`, no `CORRUPTED`, no `.broken-*` archive).

**One non-volume exposure (Section 7b), worth fixing:**
- **Production is running without the config-corruption guard.** `/opt/entrypoint.sh` (deployed) and `origin/main:entrypoint.sh` both lack the `.bak`-restore logic (`grep -c` = 0). The guard exists only in unmerged, OPEN, MERGEABLE PR #24.
- **Evidence:** see Section 7b command block.
- **Recommended remediation:** rebase PR #24 onto current `origin/main` (the 6 commits behind are docs-only, low-risk), merge it, and let the GitHub-main auto-deploy ship the guard to production. This closes the exact failure mode this audit was triggered by. (Read-only audit — not performed here.)

---

## COULD NOT VERIFY

1. **Whether the 0-row v2 task tables (`tasks`, `task_events`, `task_mentions`, `blockers`, `scheduled_actions`) ever held data.** No known-good baseline exists (stated in brief). I verified the *mechanism* for loss is absent (no DROP/DELETE path; DB persisted; 0001 applied pre-incident and never rolled back; schema intact) and that the live data path is healthy elsewhere (`intent_inbox`/`classifier_audit` = 584; `user_profile_cache` = 26). To verify positively: check whether the v2 task-handler writer is expected to be live yet (project state says v2 is "validating"), or compare against any prior `railway logs`/DB snapshot from before 2026-05-27.
2. **Application-level correctness of the data in populated tables.** I confirmed counts and schema, not semantic validity of the 584 classifier rows or 26 cached profiles (out of read-only scope and not requested).
3. **In-memory gateway state** (loaded cron schedule vs on-disk `jobs.json`, live Slack session). I verified on-disk artifacts and that the process is UP (`HTTP 200`, `socket mode connected` in logs); I did not introspect the running process beyond logs (would risk a mutating command).

---

## NET VERDICT

**CLEAN — no residual damage from the stale deploys.**

The persistent volume (`/data/skills`, `/data/.openclaw/openclaw.json`, `/data/.openclaw/cron`, `/data/queue/alaska.db`, `/data/workspace`) fully recovered: byte-identical skills, complete config with all runtime-only keys preserved, intact DB schema with all three migrations recorded, a correct workspace symlink with fresh (May 29) state, and a cron set that lost nothing (superset of the pre-v5.26 backup). No `*.broken-*` archives, no `jobs-state.json` artifact, no orphans.

**Caveat (separate from volume integrity):** the config-corruption guard remediation is sitting in unmerged PR #24 and is NOT in production (Section 7b). The volume is safe today, but the safety net for the next corrupt-write is not deployed. Recommend rebasing + merging PR #24.
