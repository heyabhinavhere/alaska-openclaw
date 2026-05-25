#!/bin/bash
# Apply all SQL migrations in numerical order, idempotently.
# Tracks applied migrations in the `_migrations` table.
# Each migration is applied as a single transaction with its tracking insert,
# so partial application can't leave the DB in an inconsistent state.
set -e
shopt -s nullglob  # empty *.sql glob → empty loop, not error

DB="${1:-/data/queue/alaska.db}"
MIGRATION_DIR="${2:-/opt/migrations}"

# Bootstrap the tracking table
sqlite3 "$DB" "CREATE TABLE IF NOT EXISTS _migrations (
  filename TEXT PRIMARY KEY,
  applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);"

# Apply each .sql file not yet recorded. Iteration order is glob expansion order
# (lexical), which is what we want for numerically-prefixed migration files.
for migration in "$MIGRATION_DIR"/*.sql; do
  name=$(basename "$migration")
  # Escape single quotes in filename for safe SQL interpolation.
  # Variable-based form is portable across bash 3.2 (macOS) and bash 4+ (Linux container).
  q="'"; qq="''"
  name_escaped="${name//$q/$qq}"
  applied=$(sqlite3 "$DB" "SELECT 1 FROM _migrations WHERE filename='$name_escaped';")
  if [ "$applied" = "1" ]; then
    echo "[migrations] $name already applied — skipping"
    continue
  fi
  echo "[migrations] Applying $name..."
  # Atomic: wrap migration + tracking insert in a single transaction.
  # -bail stops sqlite3 on the first error so the COMMIT is never reached;
  # closing the connection mid-transaction triggers an automatic rollback.
  {
    echo "BEGIN;"
    cat "$migration"
    echo "INSERT INTO _migrations (filename) VALUES ('$name_escaped');"
    echo "COMMIT;"
  } | sqlite3 -bail "$DB" || {
    echo "[migrations] FAILED applying $name — DB rolled back, fix the migration and redeploy"
    exit 1
  }
  echo "[migrations] $name applied"
done
