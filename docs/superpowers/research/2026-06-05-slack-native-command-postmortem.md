# Slack command routing — why native slash is deferred, and how `!`-commands work

**Date:** 2026-06-05 · **Status:** decided · **Audience:** future engineers + agents working on Alaska's Slack command surface.

> **TL;DR.** Native Slack slash commands (`/alaska …`) are **deferred, not dead** — they hit two hard OpenClaw/Slack limits we couldn't clear before launch. The production command surface is **`!`-prefixed mention/DM commands** (`@alaska !audit 1453`, `!case 2762`, `!pmf …`) routed by the model. This memo records the constraints so nobody re-derives them the hard way.

## The core constraint: live Slack messages are model-routed, not code-routed

OpenClaw (2026.5.28) has **no deterministic interception of a live Slack DM or @-mention**. Every inbound message becomes an LLM agent turn; "routing" is instructions in `always:true` SKILL.md files that the model is *asked* to follow. There is no pre-model hook that can catch a message and dispatch it in code. The only deterministic routers OpenClaw exposes are:

- **Native slash commands** — see below (deferred).
- **Webhook `hooks`** (`config/openclaw.json` → `hooks.mappings[]`) — external HTTP only; cannot catch a Slack message.

So for the live message surface, reliability is a *prompt-engineering* problem (make the model obey), not a routing-code problem. That's what the `!`-command layer (OM-4) is.

## Why native `/alaska` slash commands are DEFERRED

We registered `/alaska` in the Slack app and wired `channels.slack.commands.{native,nativeSkills}`. It did **not** work, for two independent reasons confirmed from the live build + OpenClaw source:

1. **Slack's 3-second ack vs. an LLM turn.** A Slack slash command must get a response within **3 seconds**. Any Alaska command that does real work (a BON API lookup + document render + Slack upload is several seconds; an LLM turn adds more) blows that budget → Slack shows *"/alaska failed because the app did not respond."* OpenClaw 2026.5.28 has **no deferred-reply / async-ack mechanism** for slash commands (verified: no `defer`, `ackTimeoutMs`, or `response_url` knob in `channels.slack` schema — only cosmetic `ackReaction`/`typingReaction`).
2. **The dispatched command never receives the channel or sender.** OpenClaw's `command-dispatch: tool` path hands the tool only `{ command, commandName, skillName }` — the Slack `channel_id` and `user_id` are used for auth gating and then dropped before dispatch (traced in `dist/get-reply-*.js`). So a slash command **cannot** post a file "where you ran it" or know who ran it.

In our testing the native command also never reached the gateway at all (no log trace), consistent with a Request-URL/transport ambiguity on top of the above — i.e. the Socket-Mode slash transport is itself unproven on our deployment.

## What we do instead — `!`-mention/DM commands

`@alaska !audit 1453` (or `!audit 1453` in a DM). A normal message turn **has** the channel + sender and **no 3-second limit**, so the engine can take its time and post where you ran it. The trigger is a closed whitelist (`!audit !case !pmf !help !ping`); the model is instructed to route a whitelisted `!`-command deterministically and never improvise. See `docs/alaska-operating-model.md` §1.5 and `SOUL.md` → "STEP 0 — Command Router".

## What would unblock native slash (post-launch, not a reliability prerequisite)

- **Prove the Socket-Mode slash transport** on Railway (does Slack deliver the `/alaska` event to the connected gateway at all?), and set `channels.slack.commands.native: true` only after that.
- A **fast-ack-then-background** pattern: a `command-dispatch: tool` that spawns the real work as a detached job and returns an instant ack inside 3s, delivering the result to a **fixed** channel (the tool can't see the originating one). This trades "post where you ran it" for determinism — acceptable for some verbs, not others.
- Re-check the `channels.slack.nativeStreaming`/`streaming` config that crash-looped the gateway during the 5.28 upgrade (see `entrypoint.sh` strip logic) before touching `channels.slack` again.

**Bottom line for the next engineer:** don't wire `/alaska` as a native slash command expecting it to "just work." Use the `!`-command layer. Native slash is a post-launch UX upgrade gated on the transport proof above.
