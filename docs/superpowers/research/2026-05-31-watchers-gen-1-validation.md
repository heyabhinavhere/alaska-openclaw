# Watcher Gen 1 — Validation Report

**Date:** 2026-05-31
**Branch:** `feat/watcher-gen-1`
**Scope:** Static + structural + cross-skill-contract validation of the Watcher Gen 1 build (W0–W4.1). The full end-to-end *runtime* replay (inject DM → classifier → watcher-creator → dispatcher firing) is a live exercise and is deferred to the post-merge activation brief (W4.3 Step 2) — it needs Alaska's runtime, real Amplitude/GitHub/Notion APIs, and prod data. This report covers everything verifiable in the repo without that runtime, which is the deterministic data + contract layer.

---

## 1. What shipped (Gen 1)

| Task | Artifact | Commit |
|---|---|---|
| W0.1 | `migrations/0004_watchers_v1.sql` (watchers + watcher_fires + event_pollers) | 70acbeb (+ a2a02ad, 6fbb21c enum fixes) |
| W0.2 | `WATCHER_REQUEST` intent in intent-classifier (v1.2.0) | fc4562f |
| W1.1 | `skills/watcher-creator/SKILL.md` (+ write-ahead/id-reserve review fixes) | a151ac6 + a2a02ad |
| W1.2 | 5 templates under `skills/watcher-creator/templates/` | cce0050 |
| W1.3 | `WATCHER_REQUEST` routing in slack-commands | 69b00eb |
| W2.1 | `skills/watcher-dispatcher/SKILL.md` | 6fbb21c |
| W2.2 | Watcher approval routing (per-fire + creation gate) in slack-commands | 9ba45b6 |
| W3.1 | Watcher management commands in slack-commands | 642eb9b |
| W3.2 | `skills/event-poller/SKILL.md` + 4 event-type crons | a02761f |
| W4.1 | `skills/watcher-janitor/SKILL.md` + janitor cron | 7a3e404 |

**Deferred (by decision, tracked):** W2.3 Phase C→watchers migration + reminder-dispatcher retirement (#50 — sequenced after prod validation, since both dispatchers coexist conflict-free). Gated template invoke-actions (#49 — follow-through.escalate_unacked_assignments, task-handler.query_stale, amplitude/thinker query interfaces) light up when Phase B task data flows + the dispatcher's invoke layer is exercised.

---

## 2. Static checks — PASS

- Migration is `0004` (no collision with `0003_user_profile_360.sql`).
- All 4 new skills present: watcher-creator, watcher-dispatcher, event-poller, watcher-janitor.
- 5 templates present and valid JSON.
- `WATCHER_REQUEST` wired in intent-classifier (3 refs); watcher-creator referenced in slack-commands (14 refs).
- `user-profile-360` wired in both creator + dispatcher; **no phantom `identity-resolver` usage** — the only match is the dispatcher's explicit prohibition ("NEVER use a phantom identity-resolver").
- KB Tier-1 (`workspace/knowledge/integrations/user-profile-api.md`) is git-tracked (gates W.1).
- W2.3 deferral confirmed: `lib/migrate_phase_c_to_watchers.py` and the `phase_c_migrated` entrypoint hook are absent (intentional, #50).

---

## 3. Synthetic-DB lifecycle exercise — PASS

Applied `0001`→`0004` to a throwaway DB and ran the exact SQL contracts each skill depends on:

| # | Contract | Result |
|---|---|---|
| 1 | creator Step 6a — reserve id at `pending_approval`, `openclaw_cron_id` NULL | ✓ reserved |
| 2 | creator Step 8 — write-ahead `pending_approval → pending_cron_create → active` + cron_id | ✓ active, cron set |
| 3 | dispatcher Step 8 — `acted` fire row + `memory_state.last_fact_key` + `fire_count++` | ✓ count=1, fact stored |
| 4 | dispatcher Step 6 — memory gate (`fact_key == last_fact_key`) | ✓ → `skipped_memory` |
| 5 | dispatcher Step 7 — rung-0 `awaiting_approval` fire row | ✓ exists |
| 6 | dispatcher Step 4 — double-prompt guard | ✓ → `skipped_pending_approval` |
| 7 | event-poller Step 2 — subscriber match `json_extract(trigger_config,'$.event_name')` | ✓ returns the event watcher |
| 8 | janitor Step 6 — orphan-watcher detection (active cron-type, NULL cron) | ✓ correctly flagged a deliberately-incomplete test row |
| 9 | janitor Step 5 — stale `pending_approval` sweep query | ✓ runs (0 candidates for a fresh row) |
| 10 | `watcher_fires` audit trail | ✓ intact (acted, skipped_memory) |

The `0004` CHECK constraints were independently confirmed: `status` accepts `pending_cron_create` + rejects garbage; `watcher_fires.outcome` accepts `skipped_pending_approval` + rejects garbage; `autonomy_rung` rejects 3; FK to watchers enforced; `event_pollers` seeded with the 4 types.

---

## 4. Cross-skill contract consistency — PASS

- **Cron payload string** watcher-creator writes (`Run /data/skills/watcher-dispatcher/SKILL.md procedure for watcher_id=W-N`) is byte-identical to what the dispatcher parses.
- **Event dispatch:** event-poller invokes watcher-dispatcher (4 refs); dispatcher documents the `{{event}}` payload it receives.
- **Per-fire grammar:** `approve W-N fire` is emitted by the dispatcher and parsed by slack-commands.
- **Gated templates:** 3 templates carry a `gated` field; watcher-creator reads it (data-driven readiness, no hardcoded list).
- **Enums:** every status/outcome/rung value used across the skills exists in the `0004` CHECK constraints.
- **Autonomy discipline:** watcher-creator rejects `autonomy_rung=2` (Gen 2 only); dispatcher treats a misconfigured rung-1 external send as a failure.

---

## 5. Deferred to live post-merge activation (W4.3 Step 2)

These require Alaska's runtime + real APIs + prod data and will be exercised live after merge + redeploy, then observed for the plan's "3 clean days":

1. **Self-approvable creation** — DM "every Monday show me DAU" → draft → confirm → cron.add → active.
2. **Cost-gated creation** — a >$3/day watcher routes to Abhinav → approve → activate.
3. **Per-fire approval** — a rung-0 external-send watcher drafts → creator approves → sends.
4. **Event watcher** — "alert me when <580 signs up" → event-poller picks it up within its window → DMs creator.
5. **Memory dedup live** — run a watcher twice with the same data → 2nd fire `skipped_memory`.
6. **Management** — pause / resume / delete (+ cron.remove) / show.
7. **Janitor** — create an orphan cron → nightly run removes it.

**Prod prerequisite (Ops-4 / Pre-flight P.0):** Phase B task graph is wired but dormant (0 rows). The task-graph templates (`stale-task`, `cross-person-task-assign`) and the `task_status_changed` poller stay inert until a real task flows end-to-end — confirm this before relying on them. `deploy-impact` + a `deploy_succeeded` poller wait on Sandeep wiring the deploy event source.

---

## 6. Verdict

The Gen 1 data layer and all cross-skill contracts are internally consistent and exercise correctly against the real schema. The build is ready to open as a PR and validate live in prod. No blocking issues found.
