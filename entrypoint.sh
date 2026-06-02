#!/bin/bash
set -e

# Make /opt/lib importable for Python helpers (rrule_helper, etc.)
export PYTHONPATH="/opt/lib:${PYTHONPATH}"

echo "[alaska] Starting Alaska AI Project Manager..."

mkdir -p /data/.openclaw

# DEFENSIVE: if the runtime config is corrupted (invalid JSON or suspiciously
# small), restore from OpenClaw's auto-backup .bak file. If no backup exists,
# fall through to fresh git copy. This guards the config-merge node script below
# from crashing on JSON.parse (set -e would kill the boot → crash loop).
# Note: the merge logic below already strips keys-not-in-git, which handles the
# "extra unknown keys" failure mode (the 2026-05-27 P0). This block handles the
# WORSE case: actual JSON corruption from an interrupted write.
if [ -f /data/.openclaw/openclaw.json ]; then
  CONFIG_SIZE=$(stat -c%s /data/.openclaw/openclaw.json 2>/dev/null || stat -f%z /data/.openclaw/openclaw.json 2>/dev/null || echo 0)
  CONFIG_VALID=$(node -e "try { JSON.parse(require('fs').readFileSync('/data/.openclaw/openclaw.json','utf8')); console.log('ok'); } catch(e) { console.log('bad'); }" 2>/dev/null || echo bad)

  if [ "$CONFIG_VALID" != "ok" ] || [ "$CONFIG_SIZE" -lt 200 ]; then
    echo "[alaska] ⚠️  Runtime config is CORRUPTED (size=$CONFIG_SIZE, parse=$CONFIG_VALID)"
    if [ -f /data/.openclaw/openclaw.json.bak ]; then
      BAK_SIZE=$(stat -c%s /data/.openclaw/openclaw.json.bak 2>/dev/null || stat -f%z /data/.openclaw/openclaw.json.bak 2>/dev/null || echo 0)
      BAK_VALID=$(node -e "try { JSON.parse(require('fs').readFileSync('/data/.openclaw/openclaw.json.bak','utf8')); console.log('ok'); } catch(e) { console.log('bad'); }" 2>/dev/null || echo bad)
      if [ "$BAK_VALID" = "ok" ] && [ "$BAK_SIZE" -ge 200 ]; then
        cp /data/.openclaw/openclaw.json /data/.openclaw/openclaw.json.broken-$(date +%s)
        cp /data/.openclaw/openclaw.json.bak /data/.openclaw/openclaw.json
        echo "[alaska] ✅ Restored runtime config from .bak (size=$BAK_SIZE). Broken version archived."
      else
        echo "[alaska] ⚠️  .bak is also corrupted (size=$BAK_SIZE, parse=$BAK_VALID). Falling through to fresh git copy."
        cp /data/.openclaw/openclaw.json /data/.openclaw/openclaw.json.broken-$(date +%s)
        rm /data/.openclaw/openclaw.json
      fi
    else
      echo "[alaska] ⚠️  No .bak file present. Falling through to fresh git copy."
      cp /data/.openclaw/openclaw.json /data/.openclaw/openclaw.json.broken-$(date +%s)
      rm /data/.openclaw/openclaw.json
    fi
  fi
fi

if [ ! -f /data/.openclaw/openclaw.json ]; then
  # First deploy: copy git config directly
  cp /opt/default-config/openclaw.json /data/.openclaw/openclaw.json
  echo "[alaska] First deploy — config initialized from git"
else
  # Subsequent deploys: merge git config INTO runtime config
  # Git config updates (new keys, changed values) apply
  # Runtime-only keys (Notion MCP, device approvals) are preserved
  echo "[alaska] Merging git config into runtime config..."
  node -e "
    const fs = require('fs');
    const git = JSON.parse(fs.readFileSync('/opt/default-config/openclaw.json', 'utf8'));
    const runtime = JSON.parse(fs.readFileSync('/data/.openclaw/openclaw.json', 'utf8'));

    // Deep merge: git values win, but runtime-only keys are kept
    function merge(target, source) {
      const result = { ...target };
      for (const key of Object.keys(source)) {
        if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])
            && target[key] && typeof target[key] === 'object' && !Array.isArray(target[key])) {
          result[key] = merge(target[key], source[key]);
        } else {
          result[key] = source[key];
        }
      }
      return result;
    }

    const merged = merge(runtime, git);
    // Remove keys that exist in runtime but NOT in git (stale/broken keys)
    for (const key of Object.keys(merged)) {
      if (!(key in git)) {
        console.log('[alaska] Removing stale key: ' + key);
        delete merged[key];
      }
    }
    fs.writeFileSync('/data/.openclaw/openclaw.json', JSON.stringify(merged, null, 2));
    console.log('[alaska] Config merged successfully');
  "
fi

# Mirror-sync skills from git to volume on every deploy.
# Skills are git-canonical (no runtime edits), so the volume should EXACTLY match
# /opt/default-skills/. Previous behavior used `cp -r` which added new files but
# never removed deleted ones — that left orphan skills on the volume after the
# v2.2 stabilization (system-health/, daily-standup/). Wipe-and-recopy fixes that.
mkdir -p /data/skills
find /data/skills -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -r /opt/default-skills/. /data/skills/
echo "[alaska] Skills mirror-synced from git to /data/skills/ ($(ls /data/skills | wc -l | tr -d ' ') skills present)"

# Workspace persistence (Issue H fix).
# The workspace now lives on the PERSISTENT /data volume so runtime STATE
# (DAILY_STATE.md, THINKER_STATE.md, memory/, digests) survives deploys.
# /root/.openclaw/workspace is symlinked to it, so the many hardcoded
# /root/.openclaw/workspace references in skills + cron prompts keep working.
# CONFIG files (SOUL.md, TOOLS.md, MEMORY.md, ...) are refreshed from git each
# deploy; STATE is seeded once then preserved. See lib/sync_workspace.sh
# (unit-tested by tests/test_workspace_persistence.sh). Non-fatal on error so a
# workspace hiccup can never crash-loop the boot.
bash /opt/lib/sync_workspace.sh || echo "[alaska] WARN: workspace sync reported an issue (non-fatal, continuing boot)"

# Ensure queue directory exists for SQLite local queue
mkdir -p /data/queue

# Initialize SQLite queue database with WAL mode if it doesn't exist
if [ ! -f /data/queue/alaska.db ]; then
  echo "[alaska] Initializing SQLite queue database with WAL mode + FK enforcement..."
  sqlite3 /data/queue/alaska.db "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT NOT NULL, payload TEXT NOT NULL, status TEXT DEFAULT 'pending', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, sent_at DATETIME, retry_count INTEGER DEFAULT 0);"
  echo "[alaska] SQLite queue ready at /data/queue/alaska.db"
else
  echo "[alaska] SQLite queue already exists."
fi

# Apply any pending SQL migrations (idempotent — safe to run every boot)
if [ -d /opt/migrations ]; then
  echo "[alaska] Checking for pending migrations..."
  bash /opt/migrations/run_migrations.sh /data/queue/alaska.db /opt/migrations
  echo "[alaska] Migrations complete."
fi

# PMF Cohort OS uses a separate SQLite file by default so V5's heavier cohort
# writes cannot contend with the V4 task/watchers graph. Operators may override
# the path with PMF_DB_PATH. If they intentionally point it at alaska.db, skip
# the second migration pass.
PMF_DB_PATH="${PMF_DB_PATH:-/data/queue/alaska_pmf.db}"
if [ -d /opt/migrations ] && [ "$PMF_DB_PATH" != "/data/queue/alaska.db" ]; then
  if [ ! -f "$PMF_DB_PATH" ]; then
    echo "[alaska] Initializing PMF SQLite database with WAL mode + FK enforcement at $PMF_DB_PATH..."
    sqlite3 "$PMF_DB_PATH" "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;"
  else
    echo "[alaska] PMF SQLite database already exists at $PMF_DB_PATH."
  fi
  echo "[alaska] Checking PMF database for pending migrations..."
  bash /opt/migrations/run_migrations.sh "$PMF_DB_PATH" /opt/migrations
  echo "[alaska] PMF database migrations complete."
fi

# Substitute env vars into config (OpenClaw doesn't do this natively)
if [ -n "$HOOKS_TOKEN" ]; then
  sed -i "s/__HOOKS_TOKEN__/$HOOKS_TOKEN/g" /data/.openclaw/openclaw.json
  echo "[alaska] Hooks token injected into config"
fi

echo "[alaska] Starting OpenClaw gateway..."

# exec replaces this shell with the gateway process
exec openclaw gateway run --port 18789 --allow-unconfigured
