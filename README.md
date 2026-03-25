# Alaska — AI Project Manager

Custom OpenClaw deployment for Alaska, an autonomous AI Project Manager for early-stage startups.

## What's included

- **OpenClaw v2026.3.13** (pinned, no auto-updates)
- **Slack plugin** pre-installed
- **Notion MCP server** pre-installed (native protocol, no third-party CLI)
- **SQLite queue** initialized with WAL mode (local "drafts folder" for data durability)
- **Smart entrypoint** that preserves config across redeployments
- **Railway-ready** with persistent storage, health checks, and auto-restart

## Setup

1. Create a private GitHub repo, push this code
2. In Railway: "New Service" → "Deploy from GitHub repo" → select this repo
3. Attach a persistent volume at `/data` (Railway dashboard → service → Volumes)
4. Add environment variables (see below)
5. Deploy

## Environment Variables (set in Railway Variables tab)

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key (console.anthropic.com) |
| `OPENCLAW_GATEWAY_TOKEN` | Yes | Dashboard password |
| `SETUP_PASSWORD` | Yes | Admin/setup page password |
| `NOTION_API_KEY` | Yes | Notion integration key (ntn_...) |
| `SLACK_BOT_TOKEN` | Yes | Slack bot token (xoxb-...) |
| `SLACK_APP_TOKEN` | Yes | Slack app token (xapp-...) |

See `.env.example` for the full list including system variables.

## How it works

- **First deploy:** Entrypoint copies default config → starts gateway → Alaska comes online
- **Subsequent deploys:** Entrypoint preserves existing config → starts gateway → Alaska keeps all settings
- **Rollback:** Railway dashboard → Deployments → click previous deployment → "Rollback"

## Custom Skills (Agents)

Place custom OpenClaw skills in the `skills/` directory. Push to GitHub → Railway auto-deploys.

The 8 Alaska PM agents:
1. Meeting Intelligence
2. Proposal Loop
3. Sprint Operator
4. Daily Pulse
5. Follow-Through Engine
6. Doc Keeper
7. Risk Radar
8. Thinker Agent

## Updating OpenClaw version

Edit the `FROM` tag in `Dockerfile` line 5:
```dockerfile
FROM ghcr.io/openclaw/openclaw:2026.3.13
```
Change the version, push to GitHub, Railway auto-deploys. If it breaks, rollback.

## Architecture

```
GitHub repo (this) → Railway builds Docker image → Container runs on Railway
                                                         ↓
                                                    OpenClaw Gateway
                                                    ├── Slack (Socket Mode)
                                                    ├── Notion (MCP protocol)
                                                    ├── SQLite queue (/data/queue/)
                                                    └── Config (/data/.openclaw/)
```
