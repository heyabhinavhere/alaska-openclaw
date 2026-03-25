#!/bin/bash
set -e

echo "[alaska] Starting Alaska AI Project Manager..."

# First deploy: copy default config if none exists
# Subsequent deploys: preserve Alaska's live config (dashboard changes, runtime settings)
if [ ! -f /data/.openclaw/openclaw.json ]; then
  echo "[alaska] First deploy detected. Copying default config..."
  mkdir -p /data/.openclaw
  cp /opt/default-config/openclaw.json /data/.openclaw/openclaw.json
  echo "[alaska] Default config copied to /data/.openclaw/openclaw.json"
else
  echo "[alaska] Existing config found at /data/.openclaw/openclaw.json."
  # Ensure gateway.mode is set (required by OpenClaw, missing in older configs)
  if ! grep -q '"mode"' /data/.openclaw/openclaw.json 2>/dev/null; then
    echo "[alaska] Patching: adding gateway.mode=local to existing config..."
    cp /opt/default-config/openclaw.json /data/.openclaw/openclaw.json
  else
    echo "[alaska] Config looks good. Preserving it."
  fi
  # Always ensure bind is 0.0.0.0 (not loopback) so Railway proxy can reach the gateway
  if grep -q '"loopback"' /data/.openclaw/openclaw.json 2>/dev/null; then
    echo "[alaska] Patching: changing bind from loopback to 0.0.0.0..."
    sed -i 's/"loopback"/"0.0.0.0"/g' /data/.openclaw/openclaw.json
  fi
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
# bind 0.0.0.0 so Railway's reverse proxy can reach the gateway (loopback blocked external access)
exec openclaw gateway run --port 18789 --allow-unconfigured
