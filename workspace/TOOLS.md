# TOOLS.md - Local Notes & Data Access

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
- **What:** Sprint Board, blockers, meeting notes, team roster, decisions
- **Skill patterns:** `/data/skills/shared-toolkit/SKILL.md`

### Cross-referencing Rule
When someone asks about a specific user, **combine Amplitude + Customer.io:**
- Amplitude → sessions, events, activity days, user properties
- Customer.io → messages sent (push/email), delivery status, opens/clicks
- Present both in one answer

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

## Team Slack IDs

- Abhinav: U07GKLVA9FE (Admin)
- Samder: U0APEUXD9DH (CEO)
- Darwin: U0APK8VTT62 (COO)
- Pankaj: U0AQ0817FJM (Frontend)
- Sandeep: U0AQFJV9B32 (AI Eng)
- Shailesh: U0AQ1UZHZ8D (AI Eng)
- Alaska bot: U0ANY9YTNUR / B0ANHAVSS78

## Internal Test User IDs (exclude from DAU)

2300, 2503, 2604, 2601, 2605, 287, 2062
