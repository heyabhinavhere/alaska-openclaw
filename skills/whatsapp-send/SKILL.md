---
name: whatsapp-send
description: Send WhatsApp messages via Meta Cloud API — backup channel for urgent DMs
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID]
      bins: [curl, sqlite3]
    primaryEnv: WHATSAPP_TOKEN
    emoji: "📱"
---

# WhatsApp Send (Backup Channel)

Slack is the primary channel. Use WhatsApp only for urgent DMs that need immediate attention.

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
