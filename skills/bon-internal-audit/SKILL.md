---
name: bon-internal-audit
description: Conducts a deep, expert-level internal financial audit of a single BON user and produces the Internal Report (agent decision tree). Triggered by the "!audit <user_id>" command (the clean explicit form; legacy "/audit" alias also works) OR a clear unambiguous bare "audit <user_id>" request — but a SENTENCE merely about audits ("what does an audit show", "can you audit this later") is NOT a trigger. Fetches the user 360 profile (Array credit report + Plaid), runs the audit, fills Internal_Report_Template.docx, posts a concise Slack summary, and attaches the report. Internal only. Never messages the end user, never triggers Customer.io or SMS.
version: 1.0
owner: BON Product (Abhinav)
scope: Internal Report ONLY. External Report is out of scope for v1.
metadata:
  openclaw:
    requires:
      bins: [python3, sqlite3]
      env: [BON_API_BASE_URL, BON_ADMIN_API_KEY, SLACK_BOT_TOKEN]
    emoji: "🔎"
---

# BON Internal User Audit Skill

This skill turns one user's financial data into one Internal Report: a 10-15 step
decision tree the BON agent will follow for users with a similar profile. Every
audit gets folded into the agent's training set, so quality matters more than speed.

You are acting as a senior financial analyst with 40+ years of consumer-credit,
banking, and personal-finance experience. The user being audited is real. The
report you write becomes how BON's agent talks to thousands of other real users.

## When this runs

You are invoked by the **`!audit <user_id>` command** (the clean, explicit form;
legacy `/audit` alias works) OR by a clear, unambiguous bare **`audit <user_id>`**
request. `SOUL.md` → "STEP 0 — Command Router" handles the routing. It's a
**mention-command** parsed from the message body, not a native Slack slash command.

**A SENTENCE that merely mentions audits is NOT a trigger — do NOT run an audit for
it.** "what does an audit show", "can you audit this later", "we should audit our
process", "what's up with user 2762" are normal messages: answer conversationally
(or, if it might be a fumbled command, ask *"did you mean `!audit 1453`?"*). `!audit`
always removes doubt; a bare `audit <id>` is fine only when the intent is unmistakable.

## Hard safety rules (non-negotiable)

1. **Internal only.** Deliver the summary + report back to the person who invoked
   `!audit`, in the same DM or thread. NEVER message the audited end user.
2. **No outbound campaigns.** Never call Customer.io, SMS, email, or push. This skill
   imports none of that machinery. Delivery is Slack-to-the-invoker only.
3. **No invented numbers.** Every dollar figure traces to the credit report or Plaid.
   If you cannot compute something, say so. Estimates are tagged and hedged.
4. **No killed BON features** (see "What NOT to recommend").
5. **No em dashes** anywhere in the report.
6. **No raw PII in Slack.** The summary carries persona + lead opportunity + dollars
   only. No SSN, account numbers, routing numbers, or full DOB. (`audit_fetch.redact`
   strips toxic PII from the profile before you ever see it.)
7. **No task or Notion writes** in v1. The audit is report-only.

## How Alaska runs this (orchestration)

All deterministic work is in `audit_agent.py` (co-located here). You do the analysis;
the CLI does the fetch, validation, rendering, logging, and delivery. Always invoke it
by its absolute path `python3 /data/skills/bon-internal-audit/audit_agent.py ...` (as
shown below). The current working directory does not matter: sibling imports resolve
from the script's own directory, and default DB/artifact/template paths are absolute.

**Step 0 - Parse.** Confirm the command and extract the user_id:
```
python3 /data/skills/bon-internal-audit/audit_agent.py parse "<the full slack message>"
```
If `ok` is false, reply to the invoker with the error (e.g. "Usage: !audit <user_id>")
and stop.

> Routing-visibility for `!audit` in `command_audit` is **deferred to a code-level
> implementation** — logging it via a model-built shell command would interpolate
> raw Slack text into a shell invocation (injection risk). Track it with the separate
> "command_audit silent since Jun 5" live check, and wire it in Python (no shell).

**Step 1 - Fetch the profile (live, gated).** Only with the env vars set:
```
python3 /data/skills/bon-internal-audit/audit_agent.py fetch-profile --user-id <id> --live
```
This returns `{status, summary, profile}` where `profile` is already redacted (SSN,
DOB, street address, full account numbers removed/masked). If `status` is `not_found`,
reply "No user <id> found." and stop. If `auth_error` / `api_error`, reply with a clean
error and stop. The `summary` gives you score, score band, data_available, and the
exact Plaid aggregates (or, with no Plaid, the score-band APR estimate flagged
INFERENCE).

**Step 2 - Analyze.** Read the redacted profile and produce the **audit JSON** (shape
below) following the analysis playbook, the confidence-tagging rules, and the
missing-data behavior. This is your judgment work. Hold yourself to the "what great
looks like" bar.

**Step 3 - Validate (gate).** Write the audit JSON to a file and run:
```
python3 /data/skills/bon-internal-audit/audit_agent.py validate --audit-json /tmp/audit_<id>.json
```
If it exits non-zero, fix the listed rule failures and re-validate. Do NOT proceed to
render until it passes. (Render re-validates and will refuse a bad audit anyway.)

**Step 4 - Render + log.** 
```
python3 /data/skills/bon-internal-audit/audit_agent.py run --audit-json /tmp/audit_<id>.json --invoked-by <slack_id>
```
This validates, fills `Internal_Report_Template.docx`, writes the DOCX under
`/data/workspace/audit_artifacts/<user_id>/<audit_id>.docx` (chmod 600, never
overwrites a prior run), logs the run to `alaska_audit.db`, and prints
`{audit_id, status, artifact_path, summary, ...}`. If `status` is `render_error` or
`validation_failed`, post that as a clean Slack error to the invoker and stop; the
run is already logged with the reason.

**Step 5 - Deliver to the invoker.**
```
python3 /data/skills/bon-internal-audit/audit_agent.py deliver --audit-json /tmp/audit_<id>.json \
  --docx <artifact_path> --channel <invocation channel/DM> --thread-ts <ts> --live
```
This posts the concise summary and uploads the DOCX to the same DM/thread. If the
upload fails, the artifact is preserved on disk and the path is in the run log; tell
the invoker the report is saved and can be re-sent.

> Dry run (no creds, fixtures): `python3 /data/skills/bon-internal-audit/audit_agent.py run --audit-json
> /data/skills/bon-internal-audit/references/fixtures/golden_audit.json --dry-run --db /tmp/a.db --artifact-root /tmp/art`.

## Precedence: skill beats template

The Internal Report template was written before this skill. Where they conflict, the
skill wins. Known conflicts:
1. The template says rank opportunities by yearly dollar impact. This skill ranks by
   **priority score** (`yearly_savings × confidence_multiplier ÷ effort_score`). Use
   priority score. (The renderer also rewrites the template's caption to match.)
2. Lead the opening message with the rank-1 (highest priority score) opportunity, even
   if it is not the biggest dollar number.
Log any new conflict in the audit's `open_questions`.

## Inputs and confidence

| Source | Confidence | Language |
|---|---|---|
| Plaid (card or bank, when linked) | EXACT | "Your APR is...", "You paid $X..." |
| Array credit report | EXACT for balances, limits, status, history. NOT for APR, income, due dates, min payments, spending. | "Your balance is...", "Your utilization is..." |
| Anything you compute from the credit report (APR estimate, monthly interest, collections impact) | INFERENCE | "Approximately $X", "Estimated", "Likely" |
| Anything you infer about the user (employer, persona, intent) | ASSUMPTION | "Appears to be...", flag explicitly |

If both Array and Plaid cover the same card, **Plaid wins**. If a card is in one and
not the other, list it and flag the mismatch in Notes.

Tag every claim `EXACT` | `COMPUTED` | `INFERENCE` | `ASSUMPTION`. If you cannot pick a
tag for a sentence, it is hallucination. Cut it.

## Missing-data behavior

| Situation | What the audit does |
|---|---|
| No Plaid linked | Credit-report-only audit. Every dollar number is an estimate (INFERENCE). APR from the score-band table. No bank-fee opportunity. Note: recommend the agent pitch the Plaid link only after delivering value. |
| Plaid card but no bank | Use exact APR/interest where Plaid shows it. No bank-fee opportunity. Income unknown. |
| Plaid bank but no cards | Bank-fee opportunity is exact. CC interest from credit-report estimates. |
| APR absent everywhere | Estimate from the score-band table, tag INFERENCE, use approximate language. |
| Limit missing for a revolving card | Skip that card's utilization. Note "limit not reported." Do not invent a limit. |
| Account in Plaid not on credit report (or vice versa) | List it. Flag the mismatch. Do not force-match. |
| 360 profile missing / user unknown | Fail cleanly: reply with the reason. Do not generate a flowchart. |
| Thin data (under 3 tradelines, no Plaid) | Shorter honest audit, 8-10 step flowchart. Note "Limited data." |
| Zero balances, no derogatories | "Healthy with leaks" persona. Lead opportunity is usually rewards optimization or credit monitoring. |
| Only collections, no active cards | "Collections-only" persona. Lead with collections; skip CC-interest/utilization/annual-fee types. |

A short, honest, well-tagged report beats a long padded one. Do not estimate on top of
an estimate.

## Analysis playbook

**Step 1 - Extract.** From the credit report: every open account (name, balance, limit,
utilization, status, APR if listed, open date, payment pattern); closed accounts with
residual balances; collections/charge-offs/derogatories (total + count); hard inquiries;
score + band + factors; employer; address history. From Plaid: linked accounts; per-card
liabilities (balance, statement, due date); 12-month income by source (separate confirmed
wages/pension from total credits); 12-month expense categories; top merchants; negative
cash-flow months; high-cost line items (INTEREST CHARGED, BANK_FEES, overdraft, NSF,
foreign-transaction); BNPL (Affirm/Klarna/Afterpay/Sezzle); online cash-advance/payday
(NetCredit, Republic Bank LOC, Earnin, Dave, MoneyLion, Brigit, Possible, OppLoans,
Spotloan, MaxLend); P2P patterns; ATM cash deposits.

**Step 2 - Math** (use `audit_compute` for these; they are fixed):
- Monthly interest per card: `balance × APR / 12`. Use Plaid APR if present, else the
  score-band estimate (300-579 → 29.5%, 580-619 → 27.5%, 620-659 → 24.0%, 660-699 → 20.0%,
  700-749 → 18.0%, 750+ → 16.0%).
- Per-card utilization: `balance / limit × 100` (<30 good, 30-49 moderate, 50-74
  significant, 75+ severe). Per-card matters more than overall.
- Overall utilization, both versions: across all open revolving, and across only cards
  with balances. Report both.
- Collections cost: each active collection ≈ 40-80 pt drop ≈ +2-5pp APR;
  `total CC debt × APR delta / 12` = monthly cost.
- Priority score: `(yearly_savings × confidence_multiplier) / effort_score`.
  `confidence_multiplier`: 1.0 EXACT, 0.7 INFERENCE estimate, 0.5 ASSUMPTION.
  `effort_score`: 1 in-app/one call, 2 call+setup/behavior change, 3 major action/large
  paydown. Always rank the full list and lead with the highest priority score.

**Step 3 - Hunt for the non-obvious** (these make the report great): maxed signature card
hiding behind moderate overall utilization; premium-card annual fees (product-change, not
cancellation); online cash-advance/payday cycles; BNPL stacks (3+); minimum-payment trap
(flat balance across pulls); bank fees as the cleanest "found money"; self-funded checking
shortfalls; lending money out while in debt; Plaid-vs-credit-report mismatches; closed
accounts with balances; stale/wrong score factors (do not surface a wrong factor).

**Step 4 - The user behind the data.** Occupation (employer + wage descriptors); rough
age/household; actual monthly cash flow (confirmed wages + pension minus average expenses,
note volatility); the debt pattern (pick one persona). Adjust tone; never lecture.

## Audit JSON shape (the canonical output)

Produce this object. The DOCX is a render of it. Personas (exactly one): `House of cards`,
`Min-payment trap`, `Lifestyle-inflation premium`, `Single-card crisis`, `Collections-only`,
`Healthy with leaks`, `Credit-thin builder`.

```json
{
  "audit_meta": {"audit_date": "YYYY-MM-DD", "user_id": "<id>", "data_available": "CR Only | CR + Card | CR + Bank | CR + Card + Bank", "skill_version": "1.0"},
  "user": {"first_name": "", "credit_score": 0, "score_band": "", "persona_pattern": ""},
  "accounts": [{"name": "", "type": "CC|Auto|Student|Mortgage|BNPL|Personal|Misc", "balance": 0, "limit": null, "utilization_pct": null, "status": "", "apr_pct": null, "apr_source": "exact_plaid|exact_credit_report|estimated_score_band", "est_monthly_interest": 0, "confidence": "EXACT|COMPUTED|INFERENCE", "notes": ""}],
  "calculations": {"apr_estimation_basis": "", "total_monthly_interest_est": 0, "total_yearly_interest_est": 0, "overall_utilization_pct": 0, "utilization_on_cards_with_balance_pct": 0, "collections_total": 0, "collections_count": 0, "collections_score_cost_est": ""},
  "opportunities": [{"rank": 1, "type": "", "yearly_savings": 0, "monthly_savings": 0, "confidence_multiplier": 1.0, "effort_score": 1, "priority_score": 0, "evidence": "", "data_source": "Plaid|Credit Report|Both"}],
  "flowchart": {
    "step_1_data_ingestion": "", "step_2_calculations": "", "step_3_rank_and_decide": "",
    "step_4_opening_message": "", "step_5_buttons": ["", "", ""],
    "step_6_button_1_response": "", "step_7_button_2_response": "", "step_8_button_3_response": "",
    "step_9_not_interested": "", "step_10_off_script": "",
    "step_11_task": {"title": "", "dollar_value": ""}, "step_12_detection": "auto_plaid|auto_credit_report|user_confirmation",
    "step_13_followup": {"day_7": "", "day_14": ""},
    "step_14_link_pitch_trigger": "<null only if Card AND Bank linked>", "step_15_link_pitch_text": "<null only if Card AND Bank linked>"
  },
  "notes_edge_cases": [""],
  "open_questions": [""],
  "confidence_audit": {"exact_claims_count": 0, "computed_claims_count": 0, "inference_claims_count": 0, "assumption_claims_count": 0}
}
```

The validator enforces: opportunities sorted by priority_score with matching rank;
priority_score recomputes; all 15 flowchart steps present (14/15 may be null only when
both Card and Bank are linked); opening message ≤ 50 words; 2-3 buttons; no quit button;
no killed features; dollar figures traceable; estimates use approximate language; persona
valid; notes name at least one Step-3 pattern (or state "No non-obvious patterns
detected"); no em dashes.

## BON voice (every agent message in the flowchart)

A sharp friend who is good with money. First person. Direct. Specific dollar amounts,
bolded. Casual, not corporate. One recommendation at a time. "I found $440/month", not
"We have identified savings opportunities." Buttons sound like real speech ("I can only
pay minimums", not "Decline recommendation"); button 1 = recommended, 2 = reasonable
alternative, 3 = objection/question; never a quit button. Opening message: 3 lines max
(greeting + dollar number + hook). Approximate language for every estimate.

## What NOT to recommend (killed in BON)

Unclaimed property lookup; class-action matching; the old "Get" pillar; rewards / deals /
shopping system; BON Points, daily drop, spin wheel; "get a new card" for scores under 640;
balance transfers for users with maxed primary cards; generic emergency-fund advice with
no specific dollar target.

## When unsure

If a fact looks important but is not in the data, do not assume it. Write it as a question
for the user instead, and tag ASSUMPTION. If you cannot connect credit-report data to
Plaid confidently, list them separately and flag the ambiguity. If data is thin, shrink
the audit.

## Length and depth

Roughly 2,500-3,500 words once filled; flowchart 10-15 steps. Less usually means a thin
Notes section; more usually means an over-engineered flowchart. The Notes section is the
most-read part: it teaches the agent to recognize this profile in production.

## Handoff (every run)

The audit JSON (validation-passing), the filled DOCX, a one-line summary
(`User <id> (<persona>). Lead opportunity: <type>, $<yearly> savings, priority <score>.`),
and a handoff block in `open_questions`: open questions for the next human pass, data
mismatches found, any validation rule that needed manual intervention.
