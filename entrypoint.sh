#!/bin/bash
set -e

echo "[alaska] Starting Alaska AI Project Manager..."

# Always use config from git (source of truth)
mkdir -p /data/.openclaw
cp /opt/default-config/openclaw.json /data/.openclaw/openclaw.json
echo "[alaska] Config synced from git to /data/.openclaw/openclaw.json"
echo "[alaska] Active config:"
cat /data/.openclaw/openclaw.json

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

# Start gateway in background so we can extract the token after startup
openclaw gateway run --port 18789 --allow-unconfigured &
GATEWAY_PID=$!

# Wait for gateway to initialize and create token files
sleep 5

# Debug: show all files in state directory to find where token lives
echo "[alaska] === DEBUG: Files in /data/.openclaw/ ==="
ls -la /data/.openclaw/
echo "[alaska] === DEBUG: All files recursively ==="
find /data/.openclaw/ -type f 2>/dev/null

# Try to find and display the gateway token
echo "[alaska] === DEBUG: Looking for gateway token ==="
for f in /data/.openclaw/gateway-token /data/.openclaw/token /data/.openclaw/.gateway-token /data/.openclaw/credentials.json /data/.openclaw/auth.json; do
  if [ -f "$f" ]; then
    echo "[alaska] Found token file: $f"
    cat "$f"
    echo ""
  fi
done

# Try to get tokenized dashboard URL
echo "[alaska] === DEBUG: Attempting openclaw dashboard --no-open ==="
openclaw dashboard --no-open 2>&1 || echo "[alaska] dashboard command failed"

# Check all env vars related to gateway/token
echo "[alaska] === DEBUG: Gateway-related env vars ==="
env | grep -i -E "gateway|token|openclaw|auth|password" 2>/dev/null || echo "[alaska] No matching env vars"

echo "[alaska] === DEBUG DONE ==="

# Wait on the gateway process (forward signals)
wait $GATEWAY_PID
