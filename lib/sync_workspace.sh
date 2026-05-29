#!/bin/bash
# sync_workspace.sh — establish Alaska's workspace on the PERSISTENT volume.
#
# Issue H fix. Previously the workspace lived at /root/.openclaw/workspace, which
# is on the ephemeral overlay filesystem — so every deploy re-seeded it from the
# git image and wiped all runtime state (DAILY_STATE.md, THINKER_STATE.md, etc.).
#
# Now the workspace lives on the persistent /data volume, and
# /root/.openclaw/workspace is a SYMLINK to it. The ~20+ hardcoded
# /root/.openclaw/workspace references in skills + cron prompts keep working
# unchanged because the symlink resolves to the persistent location.
#
# Seeding rule — preserve-by-default:
#   CONFIG files (git-canonical: SOUL.md, TOOLS.md, MEMORY.md, ...) are
#     ALWAYS refreshed from the image on every deploy (so git stays the source
#     of truth for instructions — this is how guardrail updates ship).
#   Everything else (STATE: DAILY_STATE.md, THINKER_STATE.md, memory/, digests,
#     and any future runtime-written file) is seeded ONLY IF ABSENT, then
#     preserved across deploys.
#
# This mirrors the openclaw.json merge philosophy already in entrypoint.sh
# (git wins for config; runtime values are preserved).
#
# Paths + lists are env-overridable so the logic is unit-testable
# (see tests/test_workspace_persistence.sh).
set -u

PERSIST_WS="${PERSIST_WS:-/data/workspace}"
LINK_WS="${LINK_WS:-/root/.openclaw/workspace}"
IMG_WS="${IMG_WS:-/opt/default-workspace}"

# CONFIG allowlist (git-canonical → always refreshed). Anything NOT listed here
# is treated as STATE (seed-if-absent, preserved). Preserving by default means a
# mis-classification can only cause slightly-stale config, never runtime DATA LOSS.
WS_CONFIG_FILES="${WS_CONFIG_FILES:-SOUL.md USER.md IDENTITY.md AGENTS.md AGENT_RULES.md TOOLS.md MEETING_INTELLIGENCE_V2.md BON_CREDIT_DESIGN_DOC.md HEARTBEAT.md MEMORY.md}"
WS_CONFIG_DIRS="${WS_CONFIG_DIRS:-references scripts knowledge}"

mkdir -p "$PERSIST_WS"
mkdir -p "$(dirname "$LINK_WS")"

# If a REAL directory exists at the link path (old image layout / first cutover),
# replace it with a symlink. Its contents are git-derived and disposable — the
# persistent volume is the new home. Idempotent: on later boots it's already a
# symlink, so we just re-affirm it.
if [ -e "$LINK_WS" ] && [ ! -L "$LINK_WS" ]; then
  rm -rf "$LINK_WS" 2>/dev/null || true
fi
ln -sfn "$PERSIST_WS" "$LINK_WS" 2>/dev/null || true

if [ ! -d "$IMG_WS" ]; then
  echo "[sync_workspace] no image workspace at $IMG_WS — symlink ensured, nothing to seed"
  exit 0
fi

is_config() {
  # $1 = path relative to the workspace root (e.g. "SOUL.md" or "references/x.md")
  local rel="$1" top="${1%%/*}" c
  for c in $WS_CONFIG_FILES; do [ "$rel" = "$c" ] && return 0; done
  for c in $WS_CONFIG_DIRS;  do [ "$top" = "$c" ] && return 0; done
  return 1
}

(
  cd "$IMG_WS" || exit 0
  find . -type d | while read -r d; do mkdir -p "$PERSIST_WS/${d#./}"; done
  find . -type f | while read -r f; do
    rel="${f#./}"
    if is_config "$rel"; then
      cp "$f" "$PERSIST_WS/$rel" 2>/dev/null || true          # CONFIG: always refresh from git
    elif [ ! -f "$PERSIST_WS/$rel" ]; then
      cp "$f" "$PERSIST_WS/$rel" 2>/dev/null || true          # STATE: seed once, then preserved
    fi
  done
)

echo "[sync_workspace] workspace ready on persistent volume $PERSIST_WS (config refreshed, state preserved)"
