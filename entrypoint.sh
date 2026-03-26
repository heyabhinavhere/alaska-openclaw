#!/bin/bash
set -e

echo "[alaska] Starting Alaska AI Project Manager..."

mkdir -p /data/.openclaw

# First deploy: copy default config from git
# Subsequent deploys: preserve runtime config (Notion MCP, device approvals, etc.)
# To force a config reset, set FORCE_CONFIG_RESET=true in Railway env vars
if [ ! -f /data/.openclaw/openclaw.json ] || [ "$FORCE_CONFIG_RESET" = "true" ]; then
  cp /opt/default-config/openclaw.json /data/.openclaw/openclaw.json
  echo "[alaska] Config initialized from git (first deploy or forced reset)"
else
  echo "[alaska] Preserving runtime config (Notion MCP, device approvals intact)"
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

echo "[alaska] Starting OpenClaw gateway..."

# exec replaces this shell with the gateway process
# This ensures Railway's SIGTERM reaches the gateway directly for clean shutdown
exec openclaw gateway run --port 18789 --allow-unconfigured
