#!/bin/bash
set -e

# Make /opt/lib importable for Python helpers (rrule_helper, etc.)
export PYTHONPATH="/opt/lib:${PYTHONPATH}"

echo "[alaska] Starting Alaska AI Project Manager..."

mkdir -p /data/.openclaw

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

# Substitute env vars into config (OpenClaw doesn't do this natively)
if [ -n "$HOOKS_TOKEN" ]; then
  sed -i "s/__HOOKS_TOKEN__/$HOOKS_TOKEN/g" /data/.openclaw/openclaw.json
  echo "[alaska] Hooks token injected into config"
fi

echo "[alaska] Starting OpenClaw gateway..."

# exec replaces this shell with the gateway process
exec openclaw gateway run --port 18789 --allow-unconfigured
