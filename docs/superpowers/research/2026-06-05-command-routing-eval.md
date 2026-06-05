# Command-routing eval — corpus + run history (living doc)

**Purpose:** because `!`-command routing is model-mediated (see the [native-command post-mortem](2026-06-05-slack-native-command-postmortem.md)), reliability can't be proven by unit tests alone. This doc is the **living record** of how routing actually performs deploy-over-deploy, so we can answer *"did this deploy regress routing?"* and tune the SKILL prompt against real failures.

## The corpus

The machine-checkable corpus lives at `tests/fixtures/routing_eval.jsonl` (asserted offline by `tests/test_routing_eval.py`). Each row is `{text, expect_target, note}`. It must cover four classes:

1. **Known commands** → expect their verb's target (`!case 2762` → `case`, `!pmf likely lovers` → `pmf`, …).
2. **Look-alikes that must NOT route** → `! this is broken`, `!important`, `!?`, `!nope` → `unknown` (helpful error), and bare-word collisions (`audit 1453` with no `!`) → `conversation`.
3. **Plain chat** → `good morning`, `lunch?` → `conversation`.
4. **Capture intents (regression guard)** → `T-42 done` → task-handler, `remind me Friday` → reminder, `we decided to use Twilio` → decision. These must keep working unchanged.

## The 4-part promotion bar (a verb goes live only when ALL hold)

1. Known commands: **≥95%** correctly routed.
2. Plain chat: **0** false command-routes.
3. Task / reminder / decision: **0** regressions.
4. Unknown `!thing`: a **helpful "unknown command — try `!help`"**, never random chat.

Below bar → fix the SKILL prompt + redeploy + re-measure (never a code change). Source of live numbers: the `command_audit` table (`GROUP BY matched`); see `docs/platform/command-gateway.md`.

## Run history

| Date | Deploy / PR | Verbs live | Known-cmd routed | Plain-chat false-routes | Capture regressions | Unknown→error | Notes / SKILL tweak that followed |
|---|---|---|---|---|---|---|---|
| _(PR-2 baseline — to be recorded)_ | | `!case !help !ping` | | | | | first live measurement |

_(append one row per deploy; never delete rows — the history is the value.)_
