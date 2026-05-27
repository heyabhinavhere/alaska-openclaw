#!/bin/bash
set -e

# Make /opt/lib importable for Python helpers (rrule_helper, etc.)
export PYTHONPATH="/opt/lib:${PYTHONPATH}"

echo "[alaska] Starting Alaska AI Project Manager..."

mkdir -p /data/.openclaw

# DEFENSIVE: if the runtime config is corrupted (invalid JSON or suspiciously
# small), restore from OpenClaw's auto-backup .bak file. If no backup exists,
# fall through to fresh git copy. Prevents crash-loop after a bad dashboard
# config edit (the failure mode that took prod down on 2026-05-27).
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

# Sync workspace files from git (SOUL.md, USER.md, MEMORY.md, etc.)
# These define Alaska's personality, identity, and memory
# Only copy if workspace doesn't already have them (preserve runtime edits)
WORKSPACE_DIR="/root/.openclaw/workspace"
if [ -d /opt/default-workspace ]; then
  # Copy all files and directories from git, preserving structure
  # Only copy files that don't already exist (preserve runtime edits)
  cd /opt/default-workspace
  find . -type d | while read dir; do
    mkdir -p "$WORKSPACE_DIR/$dir"
  done
  find . -type f | while read file; do
    if [ ! -f "$WORKSPACE_DIR/$file" ]; then
      cp "$file" "$WORKSPACE_DIR/$file"
      echo "[alaska] Workspace: initialized $file from git"
    fi
  done
  cd /
  echo "[alaska] Workspace files ready at $WORKSPACE_DIR"
fi

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
