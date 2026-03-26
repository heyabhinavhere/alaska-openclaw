---
name: log-usage
description: Track LLM token usage per agent with daily budget caps
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: [sqlite3]
    emoji: "📊"
---

# Log Token Usage

Track LLM token costs per agent to stay within the $300-450/month budget.

## Setup

On first use, create the usage tracking table if it doesn't exist:
```bash
sqlite3 /data/queue/alaska.db "CREATE TABLE IF NOT EXISTS token_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT NOT NULL, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, estimated_cost REAL DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);"
```

## How to Log Usage

After every LLM call, log the token count:
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO token_usage (agent, input_tokens, output_tokens, estimated_cost) VALUES ('<agent_name>', <input>, <output>, <cost>);"
```

## Cost Estimation

Using Claude Opus 4.6 pricing:
- Input: $15 per 1M tokens
- Output: $75 per 1M tokens

Daily budget cap: $15/day (~$450/month)

## Checking Usage

Get today's usage:
```bash
sqlite3 /data/queue/alaska.db "SELECT agent, SUM(input_tokens) as input, SUM(output_tokens) as output, ROUND(SUM(estimated_cost), 2) as cost FROM token_usage WHERE date(created_at) = date('now') GROUP BY agent;"
```

Get monthly total:
```bash
sqlite3 /data/queue/alaska.db "SELECT agent, SUM(input_tokens) as input, SUM(output_tokens) as output, ROUND(SUM(estimated_cost), 2) as cost FROM token_usage WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now') GROUP BY agent;"
```

## Budget Alerts

- If daily spend exceeds $12 (80% of cap), post a warning to Slack
- If daily spend exceeds $15, reduce non-critical agent activity (pause Thinker batches, reduce Follow-Through frequency)
- Include usage summary in Daily Pulse report
