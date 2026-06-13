#!/bin/bash
# Test for lib/sync_workspace.sh (Issue H persistence fix).
#
# Proves the behavior that fixes the bug:
#   1. First boot (empty volume) seeds CONFIG + STATE and creates the symlink.
#   2. A redeploy REFRESHES config from git but PRESERVES runtime state
#      (DAILY_STATE.md and friends survive — the actual bug).
#   3. New runtime-only files (not in the image) are preserved.
#   4. The operation is idempotent.
#
# Run: bash tests/test_workspace_persistence.sh
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SYNC="$SCRIPT_DIR/lib/sync_workspace.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

IMG="$TMP/img"; DATA="$TMP/data"; LINK="$TMP/root/workspace"
mkdir -p "$IMG/memory" "$IMG/references" "$IMG/workbench/journal"

# Image (git) seed versions
printf 'SOUL v1\n'            > "$IMG/SOUL.md"            # CONFIG
printf 'MEMORY v1\n'          > "$IMG/MEMORY.md"          # CONFIG
printf 'DAILY git-seed\n'     > "$IMG/DAILY_STATE.md"     # STATE
printf 'THINKER git-seed\n'   > "$IMG/THINKER_STATE.md"   # STATE
printf 'note1\n'              > "$IMG/memory/2026-05-01.md"  # STATE (subdir)
printf 'ref1\n'               > "$IMG/references/api.md"      # CONFIG (dir)
printf 'workbench index v1\n' > "$IMG/workbench/INDEX.md"     # STATE (workbench/ NOT in CONFIG dirs)

run() { PERSIST_WS="$DATA" LINK_WS="$LINK" IMG_WS="$IMG" bash "$SYNC" >/dev/null 2>&1; }
fail() { echo "FAIL: $1 (got: '$(cat "$2" 2>/dev/null)')"; exit 1; }
eq()   { [ "$(cat "$1" 2>/dev/null)" = "$2" ] || fail "$3" "$1"; }

# 1) First boot: empty volume -> everything seeds, symlink created
run
[ -L "$LINK" ] || { echo "FAIL: LINK should be a symlink"; exit 1; }
[ "$(readlink "$LINK")" = "$DATA" ] || { echo "FAIL: symlink should point to the volume"; exit 1; }
eq "$DATA/SOUL.md" "SOUL v1" "first boot: SOUL seeded"
eq "$DATA/DAILY_STATE.md" "DAILY git-seed" "first boot: DAILY seeded"
eq "$DATA/memory/2026-05-01.md" "note1" "first boot: memory note seeded"
eq "$DATA/references/api.md" "ref1" "first boot: references seeded"
eq "$DATA/workbench/INDEX.md" "workbench index v1" "first boot: workbench seeded"
echo "PASS 1: first boot seeds config + state + symlink"

# 2) Runtime mutates state + config on the volume, then a new deploy ships new config
printf 'DAILY runtime-updated by MI\n' > "$DATA/DAILY_STATE.md"
printf 'THINKER runtime\n'             > "$DATA/THINKER_STATE.md"
printf 'runtime memory note\n'         > "$DATA/memory/2026-05-29.md"   # NEW runtime-only file
printf 'SOUL hand-edited on box\n'     > "$DATA/SOUL.md"                 # config edited on box (should be overwritten)
printf 'SOUL v2 (shipped via git)\n'   > "$IMG/SOUL.md"                  # git ships new config
printf 'DAILY git-seed CHANGED\n'      > "$IMG/DAILY_STATE.md"           # changed seed must NOT clobber runtime
printf '08:40 — audit — path\n'        > "$DATA/workbench/journal/2026-06-13.md"  # NEW runtime workshop journal line
printf 'INDEX edited on box\n'         > "$DATA/workbench/INDEX.md"      # workbench is STATE: box edit must survive
printf 'workbench index v2 (git)\n'    > "$IMG/workbench/INDEX.md"       # git ships new INDEX; must NOT clobber the box copy
run
eq "$DATA/SOUL.md" "SOUL v2 (shipped via git)" "redeploy: CONFIG (SOUL) refreshed from git"
eq "$DATA/DAILY_STATE.md" "DAILY runtime-updated by MI" "redeploy: STATE (DAILY) preserved"
eq "$DATA/THINKER_STATE.md" "THINKER runtime" "redeploy: STATE (THINKER) preserved"
eq "$DATA/memory/2026-05-29.md" "runtime memory note" "redeploy: NEW runtime file preserved"
eq "$DATA/workbench/journal/2026-06-13.md" "08:40 — audit — path" "redeploy: NEW workbench journal preserved"
eq "$DATA/workbench/INDEX.md" "INDEX edited on box" "redeploy: workbench is STATE — box edit preserved, NOT refreshed"
echo "PASS 2: redeploy refreshes config, preserves state (incl. workbench)"

# 3) Idempotency: run again -> no breakage, state still preserved
run
eq "$DATA/DAILY_STATE.md" "DAILY runtime-updated by MI" "idempotent: STATE still preserved"
[ -L "$LINK" ] || { echo "FAIL: idempotent: LINK still a symlink"; exit 1; }
echo "PASS 3: idempotent"

echo "ALL TESTS PASSED"
