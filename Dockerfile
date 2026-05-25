# Alaska — AI Project Manager
# Custom OpenClaw setup: Slack + Notion MCP pre-installed
# Pinned version — no surprise auto-updates

# 1panel/openclaw mirrors the official OpenClaw with confirmed version tags on Docker Hub
FROM 1panel/openclaw:2026.3.13

USER root

# Install system dependencies: SQLite for local queue, curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pre-install the Slack plugin (baked into the image, survives restarts)
RUN cd /usr/local/lib/node_modules/openclaw && \
    npx openclaw plugins install @openclaw/slack 2>/dev/null || true

# Pre-install the Notion MCP server (no runtime npx download on cold start)
RUN npm install -g @notionhq/notion-mcp-server 2>/dev/null || true

# Create directories for persistent data and default config
RUN mkdir -p /data/.openclaw /data/workspace /data/skills /data/queue \
    /opt/default-config && \
    chown -R node:node /data

# Copy default config to a staging location (entrypoint decides when to use it)
COPY --chown=node:node config/openclaw.json /opt/default-config/openclaw.json

# Copy entrypoint script
COPY --chown=node:node entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

# Copy custom skills to staging (volume mount hides /data/skills/)
COPY --chown=node:node skills/ /opt/default-skills/

# Copy SQL migrations to staging
COPY --chown=node:node migrations/ /opt/migrations/

# Copy workspace files to staging (SOUL.md, USER.md, MEMORY.md, etc.)
COPY --chown=node:node workspace/ /opt/default-workspace/

USER node

# Environment variables
ENV OPENCLAW_STATE_DIR=/data/.openclaw
ENV OPENCLAW_WORKSPACE_DIR=/data/workspace
ENV PORT=8080

# Health check: verify gateway is responding every 30 seconds
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:18789/healthz || exit 1

# Use our entrypoint script (handles first-deploy config, then starts gateway)
ENTRYPOINT ["/opt/entrypoint.sh"]
