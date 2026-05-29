# TOOLS.md — Data Access & Channel Reference

## Available Data APIs — ALWAYS USE THESE

You have live API access. **Never say "I don't have access" to any of these.**

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

### GitHub (`$GITHUB_TOKEN`) — READ ONLY
- **What:** Commits, PRs, branches across 9 repos (2 orgs: Bonhq, Bonlife)
- **Never push/merge/create** anything

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
Say "API returned an error" or "unavailable" — **never** "I don't have access."

---

## Slack Channels

| Channel | ID | Purpose |
|---|---|---|
| #project-management | C0ANKDD664A | Main work channel |
| #alaska-daily-pulse | C0APP7V6H8C | Daily Pulse, Weekly Digest |
| #alaska-alerts | C0APP7X4TMJ | Risk Radar, critical alerts |
| #daily-standup | C0ASLANJ0RL | Pre-call sheets |

---

## Team Roster

**Canonical source:** `/root/.openclaw/workspace/MEMORY.md` → Team Roster section. Includes Slack IDs, Notion User IDs (when populated), roles, locations, and authority tiers. Do not duplicate the roster here.

---

## Internal Test User IDs (exclude from DAU)

2300, 2503, 2604, 2601, 2605, 287, 2062
