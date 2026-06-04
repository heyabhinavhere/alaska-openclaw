# BON Internal Audit Agent (`/audit <user_id>`)

The Audit Agent turns one user's financial data into one **Internal Report**: a
10-15 step agent decision tree (filled `Internal_Report_Template.docx`) that becomes
BON-agent training data. It is triggered from Slack and is **internal only**.

Status: **v1 (P0)**. Internal Report only. PDF, the findings appendix, and a native
Slack slash command are deferred (see Backlog).

## What happens on `hey @alaska /audit 1414`

```
Slack DM / @-mention "/audit 1414"
  -> router recognizes /audit (alaska-core DM handling + intent-classifier bypass)   [Phase 2]
  -> Alaska runs skills/bon-internal-audit/SKILL.md:
       parse user_id  -> audit_agent.py parse
       fetch profile  -> audit_agent.py fetch-profile --live   (redacted 360: Array CR + Plaid)
       ANALYZE        -> Alaska (the LLM) writes the audit JSON per the skill
       validate       -> audit_agent.py validate   (hard gate; refuses bad audits)
       render + log   -> audit_agent.py run         (fills DOCX, logs to alaska_audit.db)
       deliver        -> audit_agent.py deliver --live  (summary + DOCX to the invoker)
```

Alaska does the financial judgment; the Python CLI does the deterministic, testable
work (fetch, math, validation, DOCX fill, logging, Slack delivery).

## Files (all new, all in `skills/bon-internal-audit/`)

| File | Role |
|---|---|
| `SKILL.md` | The runbook + full reasoning spec Alaska executes |
| `audit_agent.py` | CLI + `run_audit` orchestration + run-log DB helpers |
| `audit_fetch.py` | Vendored BON Admin client + PII redaction + reliable aggregates |
| `audit_compute.py` | Fixed formulas (APR bands, interest, utilization, priority score) |
| `audit_validate.py` | The skill's programmatic gate (12 rules) |
| `audit_render.py` | Stdlib DOCX template fill (zipfile + xml.etree) |
| `audit_slack.py` | Summary builder + post + 3-step file upload |
| `schema.sql` | `audit_runs` table (idempotent) |
| `references/Internal_Report_Template.docx` | The vendored template |
| `references/fixtures/*.json` | Profile + golden-audit fixtures for tests/dry-run |
| `tests/test_audit.py` | 75 tests |

## Data sources

- **360 profile:** `GET {BON_API_BASE_URL}/api/admin/users/{id}/profile` with header
  `X-Admin-Key: {BON_ADMIN_API_KEY}`. One call returns Array credit report (MISMO) +
  Plaid card/bank/liabilities/transactions/income + subscriptions + identity.
- **Precedence:** Plaid wins over the credit report for the same card. Credit report is
  exact for balances/limits/status/history; NOT for APR/income/due dates/min
  payments/spending (those are estimated and tagged, or come from Plaid).
- **Redaction:** `audit_fetch.redact` drops SSN + full DOB + street address and masks
  phone + account numbers to last-4 before the data reaches the report or Slack.
- **Amplitude:** out of scope for v1.

## Storage

- Run log: **`/data/queue/alaska_audit.db`** (its OWN file; `ALASKA_AUDIT_DB_PATH` to
  override). Never the V4 `alaska.db` or V5 `alaska_pmf.db`.
- Artifacts: **`/data/workspace/audit_artifacts/<user_id>/<audit_id>.docx`**, chmod 600.
  `audit_id = audit-<UTC timestamp>-<user_id>`, so re-runs never overwrite a prior report.

## Isolation (why this is safe to build in parallel with V4/V5)

- Imports **nothing** from `lib/pmf_os` (V5) or any V4 skill. Vendors its own thin
  client/redactor/slack/render. A static test enforces "no pmf_os import".
- Writes **only** to `alaska_audit.db` and the artifact dir. Touches no V4/V5 table.
- Never calls Customer.io / SMS / email / push. Never messages the end user.
- The only shared-file edits are the two additive `/audit` router lines (Phase 2),
  mirroring the existing `/pmf` route. `SOUL.md`, `MEMORY.md`, `DAILY_STATE.md` are
  untouched.

## Safety invariants

Internal-only delivery (back to the invoker); no end-user message; no Customer.io/SMS;
no task/Notion writes; no invented dollar figures (everything traces to CR or Plaid);
estimates hedged ("approximately/estimated/likely"); no killed BON features; no em
dashes; no raw PII in the Slack summary (persona + lead opportunity + dollars only).
The validator and the renderer both enforce these and **refuse to emit a bad report**.

## Live verification (gated; run only after local tests pass)

1. `python3 -m pytest tests/test_audit.py -q` (unit) and `python3 -m pytest tests/ -q` (full).
2. Dry run: `python3 audit_agent.py run --audit-json references/fixtures/golden_audit.json --dry-run --db /tmp/a.db --artifact-root /tmp/art`.
3. With approval + env set, one internal test user: `fetch-profile --live` then `run` then `deliver --live`.
4. Verify: summary correct, DOCX opens with no placeholders, **no user-facing message
   sent**, no Customer.io/SMS, run row has audit_id/user_id/status/artifact_path/(error).

## Backlog

- **P1:** PDF (stdlib homegrown-writer pattern); the "notable findings" appendix DOCX.
- **P2:** native Slack slash command (request URL + signing secret); batch audits; an
  audit review queue; training-corpus ingestion automation.
