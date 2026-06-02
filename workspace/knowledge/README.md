# BON Knowledge Base

**Last updated:** 2026-05-27 by Abhinav
**Status:** Draft. Second pass. Solo-owned.

---

## BON in one paragraph

BON is an AI financial advisor for deep sub prime Americans. Two pillars: **Save Money** (stop users leaking cash to fees and interest) and **Manage Money** (track, organize, budget). It's an app named, "BON Credit". The AI chat/agent (CredGPT) is the primary surface. The AI agent finds things, tells users what to do, tracks results.

## What this KB is

Structured, machine-readable domain knowledge for Alaska. Every fact Alaska might need to act intelligently lives here in one place, in one format. Integration semantics, event taxonomies, metric definitions, persona segments. Without it, Alaska asks "what counts as a failed Plaid user?" every time. With it, she reads `integrations/plaid.md` and acts.

This is **executable knowledge for Alaska**, not narrative documentation for humans. Structure matters as much as content because Alaska's skills grep predictable sections to load only what they need.

## Killed features (do NOT surface as live)

Some files still reference legacy schemas. Treat all of these as historical.

- Unclaimed property lookup
- Class action claims matching
- "Get" pillar (only Save + Manage remain)
- Rewards, deals, shopping system
- BON Points, daily drops, spin wheel rewards
- Tremendous gift cards, Rye affiliate commerce, Stripe in-app purchases

Where a DB column or Amplitude event still exists for one of these, the relevant file marks it `LEGACY` or `DEAD`. Don't compute against them.

## Structure

```
workspace/knowledge/
├── README.md                          this file
├── architecture.md                    BON's stack: apps, services, data flows
│
├── integrations/                      one file per external system
│   ├── plaid.md                       bank + card linking
│   ├── spinwheel.md                   identity verification + debt payments
│   ├── array.md                       credit reports (Equifax via Array)
│   ├── amplitude.md                   product analytics
│   ├── customerio.md                  campaigns, push, email, SMS orchestration
│   ├── moneylionbyengine.md           offers rail (cash advance / loans / cards) (upcoming — integration in progress)
│   ├── twilio.md                      SMS + WhatsApp
│   ├── fireflies.md                   meeting transcription (Alaska ops)
│   ├── notion.md                      ops databases + write contracts (Alaska ops)
│   ├── slack.md                       team comms + bot conventions (Alaska ops)
│   └── github.md                      9 BON repos + branch conventions
│
├── definitions/                       shared vocabulary
│   ├── metrics.md                     6 success metrics, Activated Saver, diagnostic metrics
│   ├── lifecycle-events.md            onboarding funnel + activation + churn
│   ├── personas.md                    ICP segments + credit-score buckets
│   └── pmf-cohort-os.md               Alaska V5 PMF cohort operating contract
│
└── playbooks/                         operational recipes
    ├── common-queries.md              reusable Amplitude + Customer.io queries
    └── failure-modes.md               known failure patterns + detection signatures
```

Files marked **(Alaska ops)** are Alaska-internal, not BON product context.

## File format

Every file follows the same template. Skills grep these section names.

```markdown
# [System / Model / Concept Name]

**Last updated:** YYYY-MM-DD by Abhinav
**Status:** Draft | Skeleton | Final

## Purpose at BON
1-3 paragraphs: what this is, why BON uses it, where it fits.

## Architecture
how we integrate, data flows, key services.

## [Events | Schema | Capabilities | Definitions]
the structured payload, tables, lists, taxonomies.

## Definitions used across the team
canonical definitions, dated.

## Known failure modes / edge cases
real-world things to watch for.

## Common queries / patterns
reusable specs, usually links to `playbooks/common-queries.md`.

## People
SME + recent changes.
```

Definitions and playbooks adapt section names where appropriate. The **Purpose → Architecture/Schema → Definitions → Failure modes → Queries → People** flow is consistent.

## How Alaska consumes the KB

Alaska doesn't read the whole KB on every invocation. Skills keyword-match the user request, load only matching files, and always load `definitions/metrics.md` + `definitions/lifecycle-events.md` (small, common, useful for most queries).

Example. The watcher-creator skill on "watch failed Plaid users":

1. Tokenize. "Plaid" matches `integrations/plaid.md`. "users" matches `integrations/user-profile-api.md`.
2. Always load metrics + lifecycle-events.
3. Read the matched files.
4. Build the watcher draft from KB definitions.
5. Store the loaded file paths in `watcher.knowledge_sources` for re-validation.

Per the spec, skills declare which files they consume via `kb_files` metadata in their `SKILL.md` frontmatter.

## Team roster

For Slack/Notion IDs and authority tiers, see `workspace/MEMORY.md` § Team Roster.

| Person | Role |
|---|---|
| Abhinav Jain | Product & Design Lead. Sole owner of this KB. Creator of Alaska. |
| Darwin Tu | Co-founder. Ops, Strategic direction. |
| Samder Khangarot | Co-founder. Marketing, GTM, content, partnerships. |
| Sandeep Singh | AI / Agent architecture lead. Owns backend and agent system. |
| Pankaj Pal | Frontend lead. Flutter. Plaid integration. |
| Shailesh Kumar | AI engineer (joined April 2026). |
| Nilesh Kumar | Backend (Node.js) (joined May 05 2026). |
| Tarun Kumar | QA. |
| Alaska | An AI, smartest coworker for the team. |

## Ownership and maintenance

This KB is **owned solo by Abhinav**. No one else edits, reviews, or has access. Alaska reads it. Abhinav writes it. Alaska can write if Abhinav asks to do so. That's the entire access list.

No PR review. Abhinav edits directly. The `Last updated` header is the freshness signal. A planned KB-freshness Watcher (Watchers V1) will check weekly and DM Abhinav about files older than 60 days — not built yet. Skills using stale files **warn but don't refuse**. Better to use slightly-old knowledge than guess.

## Status legend

Each file's top line reads:

- **`Status: Final`** — reviewed and signed off. Treat as canonical.
- **`Status: Draft`** — initial pass. Use but flag inconsistencies.
- **`Status: Skeleton`** — structure only. Look for `[NEEDS DETAIL]` markers.

Most files in this second pass are `Draft`. None is `Final` until Abhinav signs off.

## Cross-references

- **Why KB exists:** `docs/superpowers/specs/2026-05-26-bon-knowledge-base.md`
- **First consumer:** `docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md`
- **Current operational state:** `workspace/MEMORY.md`
- **Personality + security:** `workspace/SOUL.md`, `skills/alaska-core/SKILL.md`
- **API access patterns:** `workspace/TOOLS.md`
- **Operational state of the team:** `workspace/DAILY_STATE.md`
