# TOOLS.md — Data Access & Channel Reference

## Available Data APIs — ALWAYS USE THESE

You have live API access to the four systems below. For THESE, **never say "I don't have access"** — if a call fails, the honest phrasing is "that data is unavailable right now," not "no access."

⚠️ This rule applies ONLY to the four APIs in this section. It does NOT mean you can reach everything. For systems you genuinely have no key to, see **"What you can and cannot reach"** below and say so plainly. (See alaska-core → Honesty & Restraint #2.)

### Customer.io (`$CUSTOMERIO_APP_API_KEY`)
- **What:** Push notification delivery, email delivery/opens/clicks, campaign management, user messaging history
- **When to use:** Any question about push delivery, emails, campaigns, "did user X receive messages?"
- **Skill:** `/data/skills/customerio-ops/SKILL.md`
- **Quick API:**
  - Campaigns: `curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" "https://api.customer.io/v1/campaigns"`
  - User messages: `curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" "https://beta-api.customer.io/v1/api/customers/<USER_ID>/messages"`
  - Campaign metrics: `curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" "https://api.customer.io/v1/campaigns/<ID>/metrics"`
  - User attributes: `curl -s -H "Authorization: Bearer $CUSTOMERIO_APP_API_KEY" "https://api.customer.io/v1/customers/<USER_ID>/attributes"`

### Amplitude (`$AMPLITUDE_API_KEY:$AMPLITUDE_SECRET_KEY`)
- **What:** DAU, user activity, sessions, event history, user profiles, funnels
- **When to use:** Any analytics question, user behavior, DAU charts
- **Skill:** `/data/skills/amplitude-analyst/SKILL.md`
- **ALWAYS use python3** for filtered queries (curl breaks with nested JSON)
- **ALWAYS apply Real Users filter** (credit_score > 0, exclude test IDs 2300/2503/2604/2601/2605/287/2062)

### GitHub (`$BON_GITHUB_TOKEN`) — READ ONLY
- **What:** Commits, PRs, branches, AND file contents across 9 repos (2 orgs: Bonhq, Bonlife)
- **Never push/merge/create** anything — **RED LINE: READ ONLY on every repo, including alaska-openclaw**
- **Full repo map** (default branches — `bon_webservices` = `dev_testing`! — owners, team GitHub handles): `workspace/knowledge/integrations/github.md`. Sandeep's stack: LangChain/LangGraph (Python), Langfuse, EKS + Terraform + Jenkins + ArgoCD + Docker.
- **Why `BON_GITHUB_TOKEN`, not `GITHUB_TOKEN`:** OpenClaw ≥2026.5.28 strips the well-known credential names `GITHUB_TOKEN`/`GH_TOKEN` from session env by design (bundled denylist — not configurable). Do NOT rename back; it silently breaks every GitHub read.

**Reading source files (for grounded code answers):** before making ANY claim about code, fetch the actual file — never describe code from memory or inference:

```bash
curl -s -H "Authorization: Bearer $BON_GITHUB_TOKEN" -H "User-Agent: alaska" \
  "https://api.github.com/repos/<org>/<repo>/contents/<path>?ref=<branch>" \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())"
```

Quote the lines you actually got back and name the repo + branch you read. If it returns 404/403, the file moved, or the logic lives outside these 9 repos (e.g., the hosted agentic service at `theagentic.ai`) — say you couldn't read it and name the owner. Do NOT invent file paths, line numbers, or function names. (See alaska-core → Honesty & Restraint #1.)

### Notion (`$NOTION_API_KEY`)
- **What:** Decision Log, Meeting Notes, Blockers, Changelog, Team Roster, Risk Register, Backlog, Daily Scrum.
- **Sprint Board (DB `4494fedd-faee-47d7-a475-595e3c18370a`) is RETIRED as of 2026-05-23 — do not write to it.** The new task DB is TBD (Phase 2.3 of the stabilization plan).
- **Read API:** `POST /v1/data_sources/{id}/query` with `Notion-Version: 2025-09-03`.
- **Write API:** `POST /v1/pages`, `PATCH /v1/pages/{id}` with `Notion-Version: 2022-06-28`.
- **Write contract (exact JSON shapes):** see `/data/skills/shared-toolkit/SKILL.md` → "Notion Write Contract" section.

### BON Backend — User Profile 360 (`$BON_ADMIN_API_KEY`)
- **What:** Everything BON holds on a single user — credit (Array + Spinwheel), Plaid accounts/liabilities/income/spending, detected subscriptions, and CredGPT chat history.
- **When to use:** Any question about a SPECIFIC user's financial situation, credit, debt, spending, or chat ("tell me about user 2762", "what's going on with jane@example.com", "show me their last chats", "why isn't this user engaging").
- **Skill:** `/data/skills/user-profile-360/SKILL.md` — read it; the flow is one command (`lookup.py`), not raw curl.
- **Lookup by:** user_id, email, phone, or name (search resolves to user_id).
- **Toxic PII (SSN/DOB/account#/address) is auto-stripped.** Per-user only — for aggregate metrics use Amplitude.

### Cross-referencing Rule
When someone asks about a specific user, **combine the three per-user sources:**
- BON Profile 360 → credit, debt, Plaid finances, subscriptions, chat content (the financial picture)
- Amplitude → sessions, events, activity days, user properties (the behaviour picture)
- Customer.io → messages sent (push/email), delivery status, opens/clicks (the messaging picture)
- Use the BON profile for "who is this user / their finances / their chats"; use Amplitude + Customer.io to enrich with behaviour and messaging. Present one combined answer.

### If an API fails
For the four APIs above, say "that data is unavailable right now" or "the API returned an error" — **never** "I don't have access" (you DO have access; the call just failed).

## What you can and cannot reach

Know this boundary cold. Bluffing about it is what erodes trust fastest.

**You CAN reach (directly):**
- Slack — read/post in your channels + DMs
- Notion — the project DBs (Decision Log, Meeting Notes, Blockers, Changelog, Team Roster, Risk Register, Backlog, Daily Scrum; Sprint Board is retired)
- Amplitude — product analytics, events, user properties, funnels
- Customer.io — campaigns, messaging history, delivery metrics, user attributes
- GitHub — READ across the 9 repos: commits, PRs, branches, and **file contents** (see "Reading source files")
- The local task store (SQLite) — tasks, blockers, reminders, classifier data

**You CANNOT reach (say so plainly, point to who can):**
- The **backend application database directly** — you cannot run ad-hoc queries or bulk extracts against it. BUT a *specific user's* profile (credit reports, tradelines, Plaid finances, subscriptions, chat) IS reachable via the **user-profile-360 skill**, which calls the admin API Sandeep built for exactly this (see "BON Backend — User Profile 360" above). So: per-user profile lookups by id/email/phone/name = **yes, through that skill**; arbitrary backend DB queries or bulk pulls = **no** (Owner: Sandeep / Nilesh).
- The **hosted AI / agentic service** runtime (`theagentic.ai`, `convo_agent_v3`) — its LIVE runtime and internals you cannot inspect. You CAN read CredGPT source to explain its logic, and you CAN see a user's *stored* chat history (their questions + the agent's recorded answers) via the user-profile-360 skill — but you cannot trace *why* it produced a specific response at runtime; that's Sandeep's to debug.
- Any third-party system you have no key to.

If a request needs a "cannot" item, say: "I can't reach that directly — <owner> would need to pull it." Never imply you fetched data you couldn't. (See alaska-core → Honesty & Restraint #2.)

---

## Slack Channels (all 12 — moved from MEMORY.md 2026-06-12)

Membership = access (no allowlist). Agents proactively POST to the first 4; the other 8 are team channels Alaska observes and responds in when mentioned/relevant.

**Posts to:**
| Channel | ID | Purpose |
|---|---|---|
| #project-management | C0ANKDD664A | Main work channel; MI summaries |
| #alaska-daily-pulse | C0APP7V6H8C | Daily Pulse, Weekly Digest |
| #alaska-alerts | C0APP7X4TMJ | Risk Radar, critical alerts (+ #pmf-cohort for PMF delivery once live) |
| #daily-standup | C0ASLANJ0RL | Pre-call sheets |

**Member of / observes (responds when mentioned):** #agentic-ai C0AQFPMR4TA · #backend C0B5YDMMSTU · #front-end C07GH72L6JW · #bugs C0AUCCQQB5F · #design C07GKMML6HJ · #user-audit C0B1W3LUZ4G · #competitor-audit C0AS0KMV398 · #whatsapp C0AUSQT37R6

## Notion Data Sources (moved from MEMORY.md 2026-06-12) — query via POST /v1/data_sources/{id}/query

- Sprint Board: b2219ef8-025c-437b-8780-58cb398ffb0f (write DB: 4494fedd-faee-47d7-a475-595e3c18370a) — **RETIRED, read-only history**
- Proposals: a99d3610-875a-4a08-ac2b-dae1df125523
- Blockers: 33b45697-aa28-42a5-9bc1-78226ab624ff (write DB: 5c7ae380-97c9-42e9-855a-c1d69ee2c51d)
- Meeting Notes: 43987da1-b2d8-4fa5-a2b8-a38ef3a27625 (write DB: ec053f5c-c92a-4997-a8f1-c223b25b3549)
- Decision Log: b8e61ebb-330d-4b5d-b745-1e4b1333c30f (write DB: 4ef87f2b-08d4-47ae-bcd4-e95d80a91017)
- Agent Signals: ead7f865-4bd4-4e19-af96-bff5c73d0758 (write DB: 0fb278fa-8f38-465c-b0ce-de587227b491)
- Team Roster: 3a8f17ff-c30c-4750-9e6e-77a1e135ec9e (write DB: a2ba23a2-85f7-487e-91d9-f6045e9df343)
- Risk Register: c05a0ba1-2543-4cb7-b156-8f57f26a6ff4
- Changelog: 8c2719be-efb1-45d7-a86d-6500e4de6fde (write DB: 97bcd149-1262-4894-94f2-04ed2f5ab077)
- Backlog: dcf4fd4e-f1d2-46b3-84d0-e5466f5025a2
- Daily Scrum: 0565274b-b967-46b3-b9c9-77d00e1ecfeb (write DB: bc0f92c4-8893-40e2-a5c8-f785fec780be)

---

## Team Roster

**Canonical source:** `/root/.openclaw/workspace/MEMORY.md` → Team Roster section. Includes Slack IDs, Notion User IDs (when populated), roles, locations, and authority tiers. Do not duplicate the roster here.

---

## Internal Test User IDs (exclude from DAU)

2300, 2503, 2604, 2601, 2605, 287, 2062
