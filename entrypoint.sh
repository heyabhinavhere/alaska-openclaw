#!/bin/bash
set -e

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
    fs.writeFileSync('/data/.openclaw/openclaw.json', JSON.stringify(merged, null, 2));
    console.log('[alaska] Config merged successfully');
  "
fi

# Ensure queue directory exists for SQLite local queue
mkdir -p /data/queue

# Initialize SQLite queue database with WAL mode if it doesn't exist
if [ ! -f /data/queue/alaska.db ]; then
  echo "[alaska] Initializing SQLite queue database with WAL mode..."
  sqlite3 /data/queue/alaska.db "PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT NOT NULL, payload TEXT NOT NULL, status TEXT DEFAULT 'pending', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, sent_at DATETIME, retry_count INTEGER DEFAULT 0);"
  echo "[alaska] SQLite queue ready at /data/queue/alaska.db"
else
  echo "[alaska] SQLite queue already exists."
fi

# Substitute env vars into config (OpenClaw doesn't do this natively)
if [ -n "$HOOKS_TOKEN" ]; then
  sed -i "s/__HOOKS_TOKEN__/$HOOKS_TOKEN/g" /data/.openclaw/openclaw.json
  echo "[alaska] Hooks token injected into config"
fi

echo "[alaska] Starting OpenClaw gateway..."

# exec replaces this shell with the gateway process
exec openclaw gateway run --port 18789 --allow-unconfigured
