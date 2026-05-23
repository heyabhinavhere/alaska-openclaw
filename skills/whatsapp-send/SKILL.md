---
name: whatsapp-send
description: DEPRECATED (2026-05-23). Was the WhatsApp Meta Cloud API backup channel for urgent DMs. Slack has been rock-solid; this path hasn't fired in months. Kept for reference, not maintained. Token (90-day Meta test) is likely expired.
version: 1.0.0
metadata:
  openclaw:
    deprecated: true
    requires:
      env: [WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID]
      bins: [curl, sqlite3]
    primaryEnv: WHATSAPP_TOKEN
    emoji: "📱"
---

# WhatsApp Send (DEPRECATED — Backup Channel)

> **Status as of 2026-05-23:** Deprecated. Slack is the only path that matters now. This skill is retained for reference but not actively maintained. The 90-day Meta test-number token is likely expired. Do not invoke unless Abhinav explicitly asks you to.

Slack is the primary channel. Use WhatsApp only for urgent DMs that need immediate attention — but per the deprecation note above, this path isn't reliable. Prefer Slack DM.

## When to Use WhatsApp

- P0 Critical blockers that need founder attention NOW
- System-down alerts
- When specifically requested by a team member
- Never for routine updates (use Slack instead)

## How to Send

1. Queue the message to SQLite first:
```bash
sqlite3 /data/queue/alaska.db "INSERT INTO outbox (target, payload, status) VALUES ('whatsapp', '{\"to\": \"<phone_number>\", \"message\": \"<message_text>\"}', 'pending');"
```

2. Send via WhatsApp Cloud API:
```bash
curl -X POST "https://graph.facebook.com/v21.0/${WHATSAPP_PHONE_NUMBER_ID}/messages" \
  -H "Authorization: Bearer ${WHATSAPP_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "<recipient_phone_with_country_code>",
    "type": "text",
    "text": { "body": "<message>" }
  }'
```

3. Mark as sent in the queue after successful delivery (HTTP 200).

## Message Formatting

- Keep messages under 1000 characters
- Use line breaks for readability
- Start urgent messages with: "🚨 URGENT:"
- Include context: what, why, and what action is needed
- End with the source: "— Alaska, AI PM"

## Phone Number IDs

Test number: Phone Number ID 965087886698848
WhatsApp Business Account ID: 913020021356025

## Rate Limits

- Max 80 messages per hour on test number
- Track sends in SQLite to avoid hitting limits
