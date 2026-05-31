# Fireflies — Meeting Transcription

**Last updated:** 2026-05-30 — trimmed to capabilities (the operating-model / pipeline content was relocated; see the pointer below).
**Status:** Draft. API + Fireflies quirks verified against live data.

> **What this file is:** what Fireflies *is* and what Alaska can *do* with it — the API, what's queryable, the quirks, the failure modes.
> **What it is NOT:** how Alaska's standup pipeline works. That's workflow, and it lives in two places:
> - `skills/meeting-intelligence/SKILL.md` — the extraction logic + anti-hallucination/normalization rules.
> - `docs/alaska-operating-model.md` — the write path (Fireflies → MI → task graph), the daily cadence, and the source-of-truth model **with the honest current-vs-V4 framing** (today MI writes `DAILY_STATE.md` directly; the SQLite graph is the V4 target after the Phase E cutover).
>
> This file stays **cutover-independent**: Fireflies' API doesn't change when the source of truth flips.

---

## Why Fireflies matters at BON

Fireflies is Alaska's **ears on the calls.** It records and transcribes the team's nightly calls; the **Meeting Intelligence (MI)** skill consumes each transcript and turns it into structured truth — tasks, blockers, decisions.

The standup pipeline **lives or dies by Fireflies → MI accuracy.** A wrong extraction (a fabricated commitment, a mis-transcribed name, the wrong speaker) propagates downstream and can surface as a **public standup item the next morning.** That's why the failure modes below are documented loudly — and why MI carries strict anti-hallucination + normalization rules (in the MI skill).

→ **How Alaska uses this (pointer, not duplicated here):** Fireflies transcript → Meeting Intelligence → the task graph → rendered views. The pipeline, cadence, and what's authoritative today vs. post-cutover are in `docs/alaska-operating-model.md`; the extraction + anti-hallucination logic is in `skills/meeting-intelligence/SKILL.md`. Channel/DM activity reaches the same task graph through *other* feeders (see the write-path map in the operating-model doc) — so don't expect a *transcript* to contain something said only in Slack.

---

## How Alaska gets Fireflies data (API + auth)

Fireflies is **GraphQL-only** — no REST surface, no webhooks. All queries POST to `https://api.fireflies.ai/graphql`.

| Field | Value |
|---|---|
| Endpoint | `https://api.fireflies.ai/graphql` |
| Auth | Bearer `$FIREFLIES_API_KEY` |
| Content type | `application/json` |
| Protocol | GraphQL POST only |
| Plan / owner | Fireflies Pro (~$19/mo); workspace admin = Abhinav |

```bash
# List recent transcripts (lightweight metadata)
curl -s -X POST "https://api.fireflies.ai/graphql" \
  -H "Authorization: Bearer $FIREFLIES_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"{ transcripts(limit: 5) { id title date duration organizer_email participants } }"}'

# Fetch ONE full transcript (sentences are the source of truth)
curl -s -X POST "https://api.fireflies.ai/graphql" \
  -H "Authorization: Bearer $FIREFLIES_API_KEY" -H "Content-Type: application/json" \
  -d '{"query":"{ transcript(id: \"<ID>\") { id title date duration organizer_email participants speakers { name } summary { overview shorthand_bullet action_items keywords } sentences { text speaker_name start_time } } }"}'
```

**READ-ONLY by discipline (honest caveat):** the Fireflies key technically has **write/mutation** access (`uploadAudio`, `deleteTranscript`, `setUserRole`, `addToLiveMeeting`). Alaska **never** calls a mutation — treat any write as a violation. The restriction is enforced by *this rule*, not by the key's scope. **Don't expose the key** in logs or Slack.

---

## Capabilities via API

| Query | Returns / notes |
|---|---|
| `transcripts(limit, skip, fromDate, toDate, host_email, organizer_email, participant_email, mine, keyword)` | List matching filters: `id, title, date, duration, organizer_email, participants`. `limit` max 50; `fromDate/toDate` are ISO date strings. |
| `transcript(id: "...")` | Full object: `sentences { text speaker_name start_time }`, `summary { ... }` (an **object**, not a scalar), `participants`, `speakers`, `meeting_link`. |
| `summary { overview shorthand_bullet action_items keywords }` | Fireflies' own auto-summary. A useful *starting* signal, but **the sentences are ground truth** — Fireflies' own action_items can miss or mis-attribute. |
| keyword search | `transcripts(keyword: "...")`, optional `scope: title \| sentences \| all`. |
| `user(id)` / `users` | Workspace member lookup. |
| Currently-recording / upcoming meetings | **Not reliably exposed. Skip.** Fireflies returns *past* transcripts only. |
| Mutations | Exist, but **Alaska never uses them.** |

---

## Fireflies-specific failure modes / quirks

- **Transcription drift is real and has bitten us.** Calls are often **Hinglish**, and proper nouns get mangled — most notably the partner **MoneyLion**, frequently transcribed as **"Moneyline"**, which propagated into state before it was caught. (MI normalizes known drift now — see the MI skill; stay alert for *new* drift.)
- **Duplicate notetaker bots.** More than one Fireflies "Fred" can occasionally join and record the **same** call, producing duplicate transcripts of one meeting. (MI does content-level dedup on top of transcript-ID dedup — see the MI skill.)
- **Speaker attribution can be wrong.** Fireflies guesses speakers from voice; similar voices or a shared mic cause drift. Cross-check against who actually owns the work.
- **Past transcripts only.** No upcoming/scheduled meetings, no reliable "currently recording" state.
- **Polling only — no webhooks.** Near-real-time = the MI poll cadence (in the operating-model doc). There's no push when a new transcript lands.
- **Mixed platforms.** Calls run on **Zoom and Google Meet**; the "Fred" notetaker joins both. Organizer is usually `abhinav@boncredit.ai`; `alaska@boncredit.ai` is on the invite.
- **Weekend calls happen.** MI runs daily so it catches them; the weekday-only Pre-Call Brief won't post sheets for them.
- **Calls can yield no transcript** (Fred didn't join, or a poll failed). This must be *noticed*, not silently skipped — a zero-transcript-on-a-call-day needs a health flag. A transcript that lands after the last evening poll waits for the next day's window. (How MI retries/flags this is in the MI skill; volume is low — ~one call/day — so `limit: 50` is never a concern.)

---

## Definitions (Fireflies terms)

- **Transcript** = Fireflies text record of a meeting with speaker attribution + timestamps + an auto-summary.
- **Commitment** = something a person *explicitly said they'd do*, with attribution. Distinct from a "mention." (MI only extracts commitments, not mentions — see the MI skill.)
- **"Fred"** = the Fireflies notetaker bot that joins calls to record.

*(The "source of truth" and "standup pipeline" definitions moved to `docs/alaska-operating-model.md` — they describe how Alaska works, not Fireflies.)*

---

## People / ownership

- **Owns the Fireflies account:** Abhinav (workspace admin).
- **SME for Meeting Intelligence (the consumer skill):** Sandeep + Abhinav.

---

## Open questions

- **[NEEDS ABHINAV]** Final fate of `DAILY_STATE.md` post-cutover — kept as the generated narrative view (current plan), or fully superseded by the Notion "Active Work" projection + Slack? *(Decision belongs in the operating-model doc / Phase E, not here.)*
- **[NEEDS ABHINAV]** Off-record / 1:1 founder calls — excluded from MI processing (privacy), or simply not recorded by Fireflies?
