#!/bin/bash
# Apply all SQL migrations in numerical order, idempotently.
# Tracks applied migrations in the `_migrations` table.
set -e

DB="${1:-/data/queue/alaska.db}"
MIGRATION_DIR="${2:-/opt/migrations}"

# Bootstrap the tracking table
sqlite3 "$DB" "CREATE TABLE IF NOT EXISTS _migrations (
  filename TEXT PRIMARY KEY,
  applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);"

# Apply each .sql file not yet recorded
for migration in $(ls "$MIGRATION_DIR"/*.sql | sort); do
  name=$(basename "$migration")
  applied=$(sqlite3 "$DB" "SELECT 1 FROM _migrations WHERE filename='$name';")
  if [ "$applied" = "1" ]; then
    echo "[migrations] $name already applied — skipping"
    continue
  fi
  echo "[migrations] Applying $name..."
  sqlite3 "$DB" < "$migration"
  sqlite3 "$DB" "INSERT INTO _migrations (filename) VALUES ('$name');"
  echo "[migrations] $name applied"
done
