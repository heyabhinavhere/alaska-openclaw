# Personas — ICP Segments

**Last updated:** 2026-05-29 by Abhinav
**Status:** Draft

---

## Purpose at BON

The named user segments BON targets and the working definitions Alaska uses. Use this file when:

- A skill needs to interpret "single mom user" or "deep subprime user" in a request.
- A watcher needs to filter for a named segment.
- A campaign targets a persona and Alaska needs the audience definition.

Personas at BON are still being shaped. We're pre-PMF. **Deep sub prime** is the closest framing today and even that is rough. **Single mom** is the candidate first segment we're considering. Treat everything below as working hypothesis, not locked truth. Edit freely as the picture sharpens.

---

## Core ICP

BON's core user is a **deep sub prime American**. Credit score typically under 580. Phone-first. Cash-strapped. Recovering from past credit damage or building credit for the first time. Motivated by immediate financial relief, not long-term wealth planning.

Common day-to-day signals:
- Lives paycheck to paycheck.
- Has at least one credit card with a high balance and high interest.
- Pays late fees, overdraft fees, or both.
- Wants a single clear answer ("what should I pay this month?") not a financial dashboard.

This is the implicit baseline. Named segments below are sub-segments or adjacent variants.

---

## Named segments

### Single Mom

- **Status:** Primary marketing target.
- **Why:** Identified by Samder as the highest-leverage cohort. Large addressable market within deep subprime.
- **Operational filter:** **No reliable filter exists today.** BON doesn't collect gender or family-status data in the app or in Amplitude/CIO. If asked for "single mom user counts," tell the requester this and offer either a proxy (e.g., users acquired through single-mom-targeted creatives) or note the data gap.
- **Reference material:** strategy and creative playbook live in `Single moms research/` folder in the project workspace. That's a marketing reference, not an Alaska data source.

### Veterans

- **Status:** Planned next marketing focus after Single Mom.
- **Operational filter:** None today.

### Credit Rebuilder

- **Status:** Always relevant. Not a specific campaign target.
- **Working definition:** real user with credit score in the 500-650 range, actively engaged in the app (checking score, linking cards, asking the agent about how to improve).
- **Operational filter:** filter `gp:credit_score` between 500 and 650, real user filter applied. See `definitions/metrics.md` § Real Users filter.

---

## Credit-score buckets

The score is VantageScore 3.0 (via Array, from Equifax), not FICO. Boundaries below use standard score-range conventions as working defaults. Update here when BON locks its own thresholds.

| Bucket | Score range |
|---|---|
| Deep Subprime | < 580 |
| Subprime | 580 - 619 |
| Near Prime | 620 - 659 |
| Prime | 660 - 719 |
| Super Prime | 720+ |

To query a bucket in Amplitude, filter `gp:credit_score` with the appropriate range. Use `"greater"` / `"less"` operators (not "greater than" / "less than"). Score values pass as strings. See `definitions/metrics.md` § Known failure modes for the operator gotchas.

---

## Plaid-linking segments

Four operational segments defined by `gp:is_card_linked` and `gp:is_bank_linked`. Used for engagement analysis, not for marketing targeting.

| Segment | Filter | ~% of real users (May 2026) | Behavioral pattern |
|---|---|---|---|
| **Card Only** | `is_card_linked = "true"` AND `is_bank_linked ≠ "true"` | ~9% | Deepest chat sessions (95-113s per visit). Chat-focused. |
| **Bank Only** | `is_card_linked ≠ "true"` AND `is_bank_linked = "true"` | ~14% | Highest non-chat screen time (34s). Data reader. |
| **Both Linked** | both `"true"` | ~10% | Returns 3.5× more than Neither (6.86 sessions/user) but chats the LEAST (30s/visit). Power data checker. |
| **Neither Linked** | both `≠ "true"` | ~68% | Majority. Stable chat engagement (~80-87s). Credit-report-only users. |

Stored as strings, not booleans. Filter with `"true"`, not `true`. See `definitions/metrics.md` § Linked-user counts.

---

## Definitions used across the team

- **"Deep sub prime American"** = core ICP. Credit score typically under 580. Cash-strapped. Phone-first.
- **"Single mom"** = primary marketing target. No operational filter exists today.
- **"Veterans"** = planned next marketing focus.
- **"Credit Rebuilder"** = real user with score 500-650, actively engaged.
- **"Deep Subprime / Subprime / Near Prime / Prime / Super Prime"** = score buckets using standard score-range conventions (score is VantageScore 3.0 via Array, not FICO).
- **"Failed Plaid user"** = event-based segment, defined in `integrations/plaid.md`. Not a persona.

## Known failure modes / edge cases

- **Persona-to-filter mapping is mostly missing.** A skill asked to send a "single mom" message has no operational way to identify those users in Amplitude or CIO. Acknowledge the gap when asked. Don't invent a proxy without flagging it.
- **No demographic data in Amplitude.** Gender, family status, occupation are not collected. Persona segmentation today depends entirely on credit score, linking state, or platform/geo.
- **Score buckets aren't enforced in product code.** They live here as working defaults. Product code may treat ranges differently.

## Common queries / patterns

| Query | Where |
|---|---|
| Real users by linking segment | `playbooks/common-queries.md` § Linking segments |
| Users with credit score in range X-Y | `playbooks/common-queries.md` § Score range filter |
| Top chatters by message count | `playbooks/common-queries.md` § Top chatters |
| Per-user lookup across systems | Use the User 360 profile API (Sandeep) |

## People

- **Owns persona strategy:** Samder (marketing) + Darwin (user audits).
- **Owns operational filters:** Pankaj (app-side instrumentation) + Sandeep (CredGPT-side).
- **Owns ICP definition:** Abhinav.
