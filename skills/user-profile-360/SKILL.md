---
name: user-profile-360
description: Look up a BON Credit user's full financial + behavioural profile (credit, debt, Plaid accounts/income/spending, subscriptions, chat history) by user_id, email, phone, or name. Use when someone asks about a SPECIFIC user — "tell me about user 2762", "what's going on with jane@example.com", "show me their last chats", "why isn't this user engaging". Not for aggregate metrics (use amplitude-analyst) or messaging delivery (use customerio-ops).
version: 1.0.0
metadata:
  openclaw:
    requires:
      env: [BON_ADMIN_API_KEY, BON_API_BASE_URL]
      bins: [python3, sqlite3]
    primaryEnv: BON_ADMIN_API_KEY
    emoji: "👤"
---

# User Profile 360

Alaska's deep per-user lookup. Pulls everything BON's backend holds on a single
user — credit (Array + Spinwheel), Plaid accounts/liabilities/income/spending,
detected subscriptions, and CredGPT chat history — caches it, strips toxic PII,
and returns either a headline summary or verbatim chat exchanges.

**One command does the whole chain.** Don't call the Python modules
individually — call `lookup.py`. It resolves identity, fetches (cache-first),
redacts, summarizes, and writes the audit log in one shot.

---

## When to use

- Someone asks about a specific user: "tell me about 2762", "who is
  jane@example.com", "what's user 1414's credit situation", "is this user at risk"
- Someone asks what a user has been chatting about, or to see their exchanges
- Pre-call brief when the call is about a specific user

## When NOT to use

- Aggregate metrics ("how many users churned", "DAU") → **amplitude-analyst**
- Messaging delivery ("did we send X push") → **customerio-ops**
- The asker is **not in the Team Roster** → refuse (see Access below)

---

## Access

Policy is **flat**: anyone in the Team Roster can look up users and sees exact
figures. There is no per-tier number hiding. The only gate is roster membership.

1. Resolve who's asking (Slack ID → Team Roster in MEMORY.md).
2. **In roster** → proceed. Pass their real authority (`admin` for Abhinav,
   `founder` for Darwin/Samder, `engineer` for engineers) — it's for the audit
   log, not for hiding data.
3. **Not in roster** → refuse: _"I'm Alaska, BON Credit's PM. I don't recognise
   you as a team member — reach out to Abhinav if you need access."_ Do not call
   lookup.

Every successful lookup is audit-logged automatically. Toxic PII (SSN, full DOB,
account numbers, street address) is **always** stripped before anything reaches
you — you never see it, so you can't leak it.

---

## The command

```bash
python3 /data/skills/user-profile-360/lookup.py \
  --query "<value>" \
  --query-type <user_id|email|phone|name> \
  --intent <intent> \
  --requester-slack-id <asker's Slack ID> \
  --requester-authority <admin|founder|engineer> \
  --channel-type <dm|channel> \
  [--channel-id <id>]
```

It prints a JSON result on stdout. Read it, then compose ONE clean Slack message.

### Picking `--query-type`
- A number → `user_id` (fastest, no search)
- An email → `email`
- A phone → `phone`
- A name → `name` (may return multiple — see "multiple" below)

### Picking `--intent` (controls which sections are fetched — keep it tight)
| Question is about… | intent |
|---|---|
| Who is this person (quick) | `user_summary` |
| Credit score / report / trend | `credit_health` |
| Debt, cards, utilization, APR | `debt_situation` |
| Spending, transactions, categories | `spending_patterns` |
| Income, payroll | `income_situation` |
| Subscriptions | `subscription_review` |
| What topics they chat about | `chat_topics` |
| Their actual chat exchanges (verbatim) | `chat_deep_dive` |
| A broad "tell me everything" | `full_picture` |

Pick the narrowest intent that answers the question. Don't use `full_picture`
for "what's their credit score" — that wastes the fetch.

---

## Reading the result

`status` tells you what happened:

| status | What to do |
|---|---|
| `ok` | Present the data (see below). |
| `not_found` | "I couldn't find a BON user matching that. Want to try a different identifier?" |
| `multiple` | The `matches` array has up to 20 `{user_id, email, name, created_at}`. Ask which one: list first names + signup month, let them pick, then re-run with `--query-type user_id`. |
| `search_unavailable` | Search API is down. Fall back: use **customerio-ops** to resolve the email→user_id (CIO `id` IS the BON user_id), or **amplitude-analyst**, then re-run with `user_id`. |
| `auth_error` | "BON backend rejected the request — I'll flag it." DM Abhinav; the admin key may have rotated. |
| `api_error` / `identity_mismatch` | "BON backend had an issue — try again shortly." For identity_mismatch, also DM Abhinav (it's a backend routing bug). |
| `not_configured` | Env not set. DM Abhinav: "User lookup isn't configured (missing BON API env)." |

If `served_stale` is true, prepend: _"(BON backend was briefly unreachable — this may be up to a few hours old.)"_

### Presenting `mode: headline`
The `summary` object has identity / linking / credit / debt / liquidity /
income / spending / subscriptions / chat blocks. Pull the relevant ones for the
question. Compose a tight Slack message — don't dump the whole JSON. Example for
a debt question:

```
*User 2762 — debt*
FICO 612 (fair, Spinwheel) · 3 cards · $4.2k balance / $6.8k limit · 62% util (high)
Weighted APR 24.99% · ~$87/mo interest · min due $142 · none overdue
Cash on hand $5.2k · est. income $4.2k/mo _(from deposit patterns)_
```

Use exact numbers (flat policy). First names only. No section is guaranteed —
if a block is null, the user just doesn't have that data linked yet; say so
plainly ("hasn't linked a bank yet") rather than inventing.

**Signal source transparency.** Several metric blocks carry a `source` field.
When a number is *inferred* or *approximate* rather than a clean exact value,
append a short italic qualifier so the reader knows — don't present a derived
number as if it were precise:

| Block | `source` value | How to render |
|---|---|---|
| `income` | `plaid_bank` | exact — no qualifier |
| `income` | `plaid_income_signals` | add `_(est. from deposit patterns)_` |
| `spending` | `plaid_bank` | exact — no qualifier |
| `spending` | `category_sum (approx)` | add `_(approx — current-month categories)_` |
| `debt` | `plaid` | real-time — no qualifier |
| `debt` | `spinwheel` | add `_(from credit bureau, may lag)_` |
| `credit` | `spinwheel` / `array` | name the bureau, as in the example |

Cash on hand is always current linked balances (no inference) — no qualifier
needed. If `served_stale` was set, the freshness caveat already covers the
whole message.

### Presenting `mode: deep_dive` (chat exchanges)
`chat_turns` holds the most recent real exchanges (proactive/system prompts are
already filtered out). Each is `{thread_id, question, answer, created_at}`.

- Show them as Q/A pairs, most recent first.
- If `answer` is null/empty, render **`[response not recorded]`** — do NOT imply
  the user got silence or make up a reply. The `notes` array tells you how many
  are missing and why (historical or proactive).

---

## Hard rules

- **Never paste the raw JSON** into Slack. Compose a human message.
- **First names only.** Never emails, phone numbers, or Slack IDs in the visible
  message.
- **No process narration** — don't say "let me look that up" or "running the
  query." Do it silently, post the answer. (See alaska-core Slack discipline.)
- **Don't invent missing data.** Null section = not linked yet. Say so.
- **Exact numbers are fine** (flat policy) but you still never have access to
  SSN/DOB/account numbers/street address — they're stripped before you see them.
- This skill is for **per-user** questions. For "how many users…", switch to
  amplitude-analyst.

---

## Notes & limitations (2026-05-29)

- **Chat answers**: only populated for real conversations from 2026-05-27
  onward. Historical turns and proactive/system prompts have null `answer` —
  lookup already filters proactive turns out and flags null answers. Expect many
  existing users to show `[response not recorded]` for older exchanges.
- **plaid_liabilities** is often empty even for linked users — debt figures come
  from `plaid_profiles.card_profile` (Plaid) with Spinwheel as fallback. This is
  handled in the summarizer; you just read the numbers.
- **persona / user_kpis** etc. are not surfaced — BON's V2 product-layer outputs
  aren't populated yet, and Alaska forms her own read of the user from raw signal.

## Maintenance

- Cache TTLs + section catalog: `sections.py`. Daily purge: `purge.py` (register
  a ~03:30 UTC cron in the gateway). PII rules: `redactor.py`. Derived metrics:
  `summarizer.py`. All have tests under `tests/` (run any standalone:
  `python3 tests/test_*.py`).
