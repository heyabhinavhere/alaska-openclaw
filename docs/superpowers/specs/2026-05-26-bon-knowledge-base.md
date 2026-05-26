# BON Knowledge Base — Design Spec

> **Status:** Design — foundational dependency for Alaska Watchers V1 and broader skill intelligence.
> **Date:** 2026-05-26
> **Author:** Abhinav (insight) + Claude (architecture)
> **Related docs:**
> - `docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md` — Watchers V1 (the primary consumer)
> - `workspace/MEMORY.md` — current operational state

---

## The insight

Right now Alaska asks too many "what does X mean?" questions because her domain knowledge is scattered:

- Slack IDs and team roster in `MEMORY.md`
- Notion DB schemas in `TOOLS.md`
- Amplitude API patterns in `references/amplitude-api-reference.md`
- Customer.io patterns embedded in the `customerio-ops` skill
- BON's domain (credit profiles, card linkage, financial coaching) — **nowhere structured**

When a user says "track failed Plaid users," Alaska has to ask what "failed" means. A great human PM doesn't ask — they know, because they've internalized how the company's systems work.

The fix is a **structured Knowledge Base** that codifies BON's operational knowledge in one place, with conventions skills can rely on. Every skill that needs domain knowledge reads the relevant KB files before acting.

This isn't documentation for humans. It's **executable knowledge for Alaska** — definitions, event taxonomies, common queries, integration architectures — all in a form she can reason over.

---

## Strategic value

Three reasons this is foundational, not optional:

1. **Watcher creation precision.** Without KB, every watcher creation is an interrogation. With KB, only HUMAN INTENT ambiguities remain ("how many to list", "what timezone"). Technical questions ("what counts as failed", "which filter is Real Users") get answered from the file.

2. **All skills get smarter.** Not just watcher-creator. Meeting Intelligence reading `personas.md` understands "single mom user" mentions. amplitude-analyst reading `metrics.md` uses the canonical DAU formula. customerio-ops reading `customerio.md` knows the segment definitions.

3. **Onboarding new team members + new engineers picking up Alaska.** The KB becomes a living architecture doc. New engineer joins → reads `workspace/knowledge/` → understands BON's stack and operational conventions.

---

## Structure

```
workspace/knowledge/
├── README.md                          Index + how-to + maintenance norms
├── architecture.md                    BON's overall stack: apps, services, data flows
│
├── integrations/                      One file per external system
│   ├── plaid.md                       Card linkage flow, events, "failed" definition
│   ├── spinwheel.md                   Tradeline data, capabilities
│   ├── array.md                       Credit data, partnership scope
│   ├── amplitude.md                   Event taxonomy, user properties, Real Users filter
│   ├── customerio.md                  Campaigns, segments, transactional API
│   ├── moneyline.md                   Cash advance / loans / cards integration
│   ├── twilio.md                      SMS/WhatsApp, A2P status
│   ├── fireflies.md                   Transcripts, webhook setup, conventions
│   ├── notion.md                      DBs, data sources (subsumes TOOLS.md Notion content)
│   ├── slack.md                       Channels, conventions, bot capabilities
│   └── github.md                      9 BON repos, event taxonomy, branch conventions
│
├── data-models/                       Internal domain models
│   ├── user.md                        BON user object: ID, email, score, attributes
│   ├── credit-profile.md              credit_score buckets, what they mean
│   ├── card-linkage.md                Card linking domain: attempt → link → match → tradeline
│   ├── financial-coaching.md          AI coaching model, conversation states
│   └── budgeting.md                   Minimum obligations, EveryDollar approach
│
├── definitions/                       Shared vocabulary
│   ├── metrics.md                     "DAU", "Real DAU", "card linkage rate", "churn" definitions
│   ├── lifecycle-events.md            signup, activation, first_card_link, churn
│   └── personas.md                    Single mom, credit-rebuilder, etc. — the ICP segments
│
└── playbooks/                         Operational recipes
    ├── common-queries.md              Reusable query specs (Amplitude funnels, CIO segments)
    ├── failure-modes.md               Known failure patterns + detection signatures
    └── escalation-tree.md             Who owns what — who to escalate to for X
```

### Why this structure

- **`integrations/`** is per-external-system. One owner per file (the engineer who works with it).
- **`data-models/`** is internal domain — how BON thinks about its own world.
- **`definitions/`** is shared vocabulary — words the team uses that mean specific things.
- **`playbooks/`** is operational — reusable patterns Alaska references in actions.

Files stay focused — each ~200-1000 lines. If a file grows past 1500, split.

---

## File format template

Every KB file follows this structure for grep-able predictability:

```markdown
# [System / Model / Concept Name]

**Last updated:** YYYY-MM-DD by [Name]
**Owner:** [Name] ([role]) | Backup: [Name]

## Purpose at BON
[1-3 paragraphs: what this is, why BON uses it, how it fits in our stack]

## Architecture
[How we integrate, data flows, key services]

## [Events / Schema / Capabilities — section appropriate to content type]
[Tables, lists, structured details]

## Definitions used across the team
[Canonical definitions the team has agreed on]
- **"X"** = [definition] (defined [when], [decision context])
- **"Y"** = [definition]

## Known failure modes / edge cases
[Real-world things to watch for]

## Common queries / patterns
[Reusable specs — usually links to playbooks/common-queries.md sections]

## People
- Owns integration: [Name]
- Backup: [Name]
- Subject matter expert: [Name]
- Recent changes: [Name] — [what + when]
```

### Example: `integrations/plaid.md`

```markdown
# Plaid — Card Linkage Integration

**Last updated:** 2026-05-26 by Sandeep
**Owner:** Sandeep (AI Eng) | Backup: Shailesh

## Purpose at BON
Plaid handles bank account + card linking for our users.
Used during onboarding (link a checking account) and ongoing card matching
(map linked cards to credit-bureau tradeline data via Array).

## Architecture
- User initiates link from the mobile app
- App calls our backend → backend calls Plaid Link API → returns Link Token
- App opens Plaid's modal with the token
- On success, Plaid returns public_token → we exchange for access_token
- We pull accounts via /accounts/get, store in our DB
- Card matching engine joins these against Array tradeline data
- Card matching uses last-4-digit priority + name normalization (May 21 decision)

## Events fired to Amplitude
| Event name | Fires when |
|---|---|
| `plaid_link_initiated` | User taps "Link account" in the app |
| `plaid_link_opened` | Plaid modal opens |
| `plaid_link_success` | User completes link successfully |
| `plaid_link_abandoned` | User closes modal without linking |
| `plaid_link_errored` | Plaid returns an error mid-flow |
| `plaid_card_matched` | Card matching engine matches Plaid account to tradeline |
| `plaid_card_match_failed` | Match attempted but no tradeline matched |

## Definitions used across the team

- **"Failed Plaid user"** = user with `plaid_link_initiated` event but NO `plaid_link_success`
  event in the same session window (default: 24h). Includes both abandoned and errored cases.
  (Defined Apr 18, team call)

- **"Card linkage rate"** = `count(unique users with plaid_link_success in window) /
  count(unique users with plaid_link_initiated in window)` — real users only.
  (Defined in `definitions/metrics.md`)

- **"Linked but unmatched"** = `plaid_link_success` event but no `plaid_card_matched`
  within 7 days. Indicates the matching engine couldn't tie linked accounts to tradelines.

## Known failure modes
- Bank not supported (Plaid catalog gap) → `plaid_link_errored` with code BANK_NOT_SUPPORTED
- MFA timeout → `plaid_link_errored` with code MFA_TIMEOUT
- Name mismatch causing card_match_failed (root cause: bank name vs brand name —
  see Decision Log May 21)

## Common queries
- Card linkage funnel: see `playbooks/common-queries.md#plaid-funnel`
- Failed user list with emails: see `playbooks/common-queries.md#plaid-failed-with-emails`
- Linked-but-unmatched users: see `playbooks/common-queries.md#linked-but-unmatched`

## People
- Owns integration: Sandeep (AI Eng)
- Backup: Shailesh (AI Eng)
- Recent RCA on matching engine: Shailesh (May 21)
```

---

## How skills consume the KB

### Pattern: keyword-driven file loading

Skills don't read ALL of KB on every invocation (that would explode context). They keyword-match the user request against the KB index, load only relevant files.

The watcher-creator skill (the primary KB consumer in V1) does:

```
1. Receive user request: "@alaska watch failed Plaid users"
2. Tokenize and match against KB index:
   - "Plaid" → integrations/plaid.md
   - "failed" → (no direct match — implicit from Plaid context)
   - "users" → data-models/user.md (low priority — only load if needed)
3. Always load: definitions/metrics.md + definitions/lifecycle-events.md
   (small, common, useful for most queries)
4. Read the matched files
5. Build watcher draft using KB definitions
6. Store the file paths in watcher.knowledge_sources for re-validation
```

### Other skills that should consume the KB

| Skill | KB files to load | Why |
|---|---|---|
| `watcher-creator` | Keyword-matched + metrics/lifecycle-events | Primary consumer |
| `amplitude-analyst` | `amplitude.md` + `metrics.md` always; data-models on request | Real Users filter, metric definitions |
| `customerio-ops` | `customerio.md` + `personas.md` | Segment definitions, ICP context |
| `meeting-intelligence` | `personas.md` + `definitions/lifecycle-events.md` | Understanding user-segment mentions in transcripts |
| `intent-classifier` | `personas.md` + `definitions/lifecycle-events.md` | Same — understand domain terms in messages |
| `task-handler` | None (purely operational) | Doesn't need domain knowledge |
| `pre-call-brief` | Owner + recipient KB on the fly (rarely needed) | Lightweight |
| `risk-radar` | All `failure-modes.md` + `metrics.md` | Critical for pattern detection |
| `thinker` | All of `definitions/` + most of `integrations/` | The autonomous-pattern-finder needs broad context |

Skills declare which KB files they need via metadata in their SKILL.md frontmatter:

```yaml
metadata:
  openclaw:
    requires:
      bins: [sqlite3]
    kb_files:
      always: ["definitions/metrics.md"]
      on_match: ["integrations/*", "data-models/*"]
```

---

## Maintenance norms

### Who edits what — Abhinav-only

**Confirmed 2026-05-27.** The Knowledge Base is Abhinav's responsibility alone. No domain-distributed authoring. Engineers do NOT submit PRs to KB files. They do NOT directly edit `workspace/knowledge/`.

Reasoning: KB content drives Alaska's behavior across many skills. Inconsistencies, drift, or honest mistakes by individual engineers would cascade into watcher misbehavior. Abhinav-as-sole-author ensures the KB stays a coherent single voice and reflects his canonical understanding of how BON works.

**What engineers CAN do:**
- Ask Alaska "what does plaid.md say about X?" — she'll quote
- Notify Abhinav of a definition that's drifted ("hey, our Plaid failure handling changed — KB needs an update")
- Flag stale KB content during their own work

**What engineers CANNOT do:**
- Submit PRs touching `workspace/knowledge/`
- Ask Alaska to update KB files on their behalf

**Alaska's enforcement:** Any apparent "edit KB" request from anyone other than Abhinav (Slack ID `U07GKLVA9FE`) gets the reply: *"Knowledge base changes go through Abhinav directly."* No further engagement.

**Tooling implication:** A CI check (GitHub Actions or pre-commit hook) should reject any commit to `workspace/knowledge/**` not authored by Abhinav. Easier to enforce mechanically than by code review.

- **No silent edits.** Update the "Last updated" header on every change.

### Freshness signal

- Each KB file's `Last updated` header is the ground truth.
- A Watcher (built in V1) checks weekly: "Are any KB files older than 60 days?" → DMs Abhinav with a list.
- Skills using a KB file note its age in their internal reasoning ("plaid.md last touched 75 days ago — definitions may be drift-prone"). They do NOT refuse to use stale files (warn, don't refuse — better to use slightly-old knowledge than guess).

### Watcher → KB linkage

Each Watcher stores `knowledge_sources` = JSON list of KB file paths used at creation. When a KB file is materially updated (signaled by a commit message tag or just a header change), Alaska runs a re-validation pass:

```
@alaska (to Abhinav): "I updated plaid.md. 3 active watchers reference it
(W-12, W-23, W-31). Want me to re-validate their definitions against
the new version?"
```

This catches the failure mode where a definition changes ("we now define failed differently") but old watchers keep using the old logic silently.

---

## Initial seed plan

Don't try to write everything at once. Seed in priority order:

### Tier 1 (must-have before Watchers V1 ships)

These directly unblock the 5 worked-example watchers:

1. `architecture.md` — high-level BON stack overview (1 page)
2. `integrations/plaid.md` — failed-user definitions, event taxonomy
3. `integrations/amplitude.md` — Real Users filter, event taxonomy, user properties
4. `integrations/customerio.md` — campaign types, segments, transactional API
5. `integrations/github.md` — 9 repos, event types, branch conventions
6. `integrations/notion.md` — DBs + data source IDs (extracted from TOOLS.md)
7. `data-models/user.md` — user schema
8. `data-models/credit-profile.md` — score buckets, "thin-file" / "subprime" definitions
9. `data-models/card-linkage.md` — domain model for linking + matching
10. `definitions/metrics.md` — DAU/MAU/card linkage rate/churn definitions
11. `definitions/lifecycle-events.md` — signup, activation, churn taxonomy
12. `definitions/personas.md` — single mom, credit-rebuilder, etc.
13. `playbooks/common-queries.md` — initial Amplitude queries that watchers reference

That's 13 files. Each ~200-500 lines. Roughly 1-2 days of focused authoring with team input.

### Tier 2 (can lag Watchers V1 by ~2 weeks)

14. `integrations/spinwheel.md`
15. `integrations/array.md`
16. `integrations/moneyline.md`
17. `integrations/twilio.md`
18. `integrations/fireflies.md`
19. `integrations/slack.md`
20. `data-models/financial-coaching.md`
21. `data-models/budgeting.md`
22. `playbooks/failure-modes.md`
23. `playbooks/escalation-tree.md`

### Tier 3 (grows organically)

24+. Anything else as use cases reveal needs.

---

## Authoring approach

Two ways to fill in KB files:

### Manual (engineering team writes them)

- Each engineer writes their domain's files
- Abhinav reviews and signs off
- ~1 hour per file with team input
- Pros: highest accuracy, team owns their stuff
- Cons: slow, requires coordination

### LLM-assisted (Alaska drafts, humans refine)

- Alaska scans the existing repo (skills, MEMORY.md, TOOLS.md, AGENT_RULES.md, code if any)
- Drafts the KB file from observed conventions
- Engineer reviews + corrects in a PR
- ~15 min per file (review only)
- Pros: fast
- Cons: needs human review or risks codifying mistakes

**Recommended:** LLM-assisted Tier 1 in a single batch (one work session), human-review-only PR. Tier 2+ as manual incremental work over weeks.

---

## Migration from existing scattered knowledge

| Currently in | Move to KB |
|---|---|
| `workspace/MEMORY.md` → Team roster | Stay in MEMORY.md (identity is special — it's the SOURCE OF TRUTH for who's who) |
| `workspace/MEMORY.md` → Architecture | Move to `knowledge/architecture.md` (MEMORY.md keeps a pointer) |
| `workspace/TOOLS.md` → Notion data source IDs | Move to `knowledge/integrations/notion.md` (TOOLS.md keeps a pointer) |
| `skills/amplitude-analyst/SKILL.md` → API patterns | Stay in skill (procedural). KB has the EVENT TAXONOMY + Real Users filter as canonical reference. |
| `references/amplitude-api-reference.md` | Consolidate into `knowledge/integrations/amplitude.md` |
| `skills/customerio-ops/SKILL.md` → API patterns | Stay in skill. KB has the CAMPAIGN TAXONOMY + SEGMENT DEFINITIONS. |

Pointers from MEMORY.md and TOOLS.md to KB files keep backward compatibility — skills currently reading those files don't break.

---

## Open questions — answered 2026-05-27

1. ✅ **KB authoring authority** — **Abhinav-only.** Not domain-distributed. See "Who edits what" section above.

2. ✅ **Freshness threshold** — **60 days, warn-only.** Alaska continues to use KB files past 60 days untouched, but flags the staleness in her drafts to give the user a chance to ask Abhinav for a refresh.

3. (Defaults stand — not raised in conversation, recommend going with: structured template format, git-history versioning, split at ~1500 lines.)

**Format strictness** — Structured template (the one above) for grep-parseability. Skills depend on predictable section names.

**Versioning** — Git history only. Don't manually track versions in file headers (one less thing to keep in sync).

**Granularity** — Split when a file exceeds ~1500 lines. Until then, one file per system / model / concept.

---

## Implementation steps (when ready)

1. Create `workspace/knowledge/` directory with `README.md` (index + how-to).
2. LLM-drafted Tier 1 files (13 files, one work session).
3. PR to main with Abhinav review.
4. Update `MEMORY.md` and `TOOLS.md` to add pointers to KB files (don't delete content yet — backward compat).
5. Update the 5-7 skills that should consume KB (add `kb_files` metadata + load logic).
6. Build the KB-freshness watcher template.
7. Tier 2 files seeded over the following 2 weeks.
8. After 2 weeks of usage: review which KB files were referenced by which watchers; tighten gaps.

---

## Cross-references

- **Watchers V1 spec:** `docs/superpowers/specs/2026-05-26-alaska-watchers-v1.md` (primary KB consumer)
- **Current operational state:** `workspace/MEMORY.md`
- **Existing tool docs being subsumed:** `workspace/TOOLS.md`, `references/amplitude-api-reference.md`
