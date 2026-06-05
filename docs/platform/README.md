# Alaska Platform Layer — Command Gateway + Artifact Service

Two reusable platform primitives that future Alaska capabilities depend on:

1. **Command Gateway** — one native Slack command, `/alaska`, with subcommands
   routed internally. → [command-gateway.md](command-gateway.md)
2. **Artifact Service** — on-demand beautiful DOCX/PDF generation + validation +
   storage + Slack delivery, stdlib-only. → [artifact-service.md](artifact-service.md)

Both are built as the **smallest safe v1**: isolated new modules, fully tested,
touching **zero** shared/runtime files, and turning on **no** live production
behavior. They are the long-term foundation for `/alaska audit 1414`,
`/alaska pmf status`, `/alaska user 1414`, `/alaska brief today`, PMF memos,
audit reports, user case files, weekly digests, and internal docs.

## Where the code lives

```
lib/alaska_artifacts/         reusable artifact service (DOCX/PDF/store/upload + CLI)
lib/alaska_command_gateway/   reusable /alaska gateway (verify/parse/dispatch/jobs/receiver)
skills/artifact-service/      discoverability SKILL.md (how to use the service)
skills/command-gateway/       discoverability SKILL.md (how /alaska works + add subcommands)
tests/test_alaska_artifacts.py        46 platform tests total, stdlib-only, green
tests/test_command_gateway.py
docs/platform/                this folder
```

## Research memo (verified findings)

**Runtime.** OpenClaw `1panel/openclaw:2026.3.13`, a single process
(`exec openclaw gateway run --port 18789`). Railway routes public traffic to that
one port. Python 3.9.6. The image is deliberately **slim** — `sqlite3, curl,
python3-dateutil` only; **no** LibreOffice/poppler/python-docx/reportlab/
weasyprint (a test, `tests/test_pmf_artifact_runtime.py`, guards this). So the
whole platform is **stdlib-only**.

**Slack today.** Socket Mode (`SLACK_BOT_TOKEN` xoxb + `SLACK_APP_TOKEN` xapp);
no public Slack request URL. Inbound DMs/@mentions are classified by
`skills/intent-classifier` and `skills/alaska-core`. `/pmf` is **not** a native
slash command — it is a text prefix matched inside the classifier. There are **no**
native Slack slash commands.

**The `/hooks` system.** `config/openclaw.json` enables a built-in `/hooks`
receiver, but it authenticates with a **static Bearer token** and its only
mapping uses `action: "agent"` (a slow LLM turn). Slack slash commands send
`X-Slack-Signature` (not a Bearer token) and need a <3s ack — so `/hooks` is
**not** usable for native slash commands as-is.

**Artifact prior art (studied, never imported).** Two independent stdlib OOXML
implementations exist: `lib/pmf_os/{docflow,artifacts}.py` (V5; DocFlow model →
hand-built DOCX) and `skills/bon-internal-audit/audit_render.py` (template-fill:
token map + table-row cloning + fail-if-placeholder-survives). The Slack 3-step
external-upload with an injectable transport appears in `lib/pmf_os/slack_delivery.py`
and `skills/bon-internal-audit/audit_slack.py`. The platform **re-implements**
these generically — it does not import workstream code (a test asserts this).

## P0 / P1 / P2

| | Command Gateway | Artifact Service |
|---|---|---|
| **P0 (done)** | verify + parse + 3s-ack + async jobs + `help`/`ping`/`audit`(dry-run) + reference receiver | DOCX from model, DOCX template-fill, validate, filesystem-JSON store, Slack upload, **text PDF** |
| **P1** | live wiring (after OpenClaw-capability check + approval); `pmf`/`user`/`brief` subcommands | appendix DOCX; markdown/HTML fallback; richer DocFlow |
| **P2** | richer interactive responses (blocks, modals) | DOCX→PDF (LibreOffice → needs package approval); images/charts; registry UI; retention |

## What is intentionally NOT done

- `/alaska` is **not** wired into the live runtime. No edits to `entrypoint.sh`,
  `Dockerfile`, `config/openclaw.json`, or any migration.
- `audit` is **dry-run** — no live audit runs until a later, approved PR connects
  the `bon-internal-audit` skill.
- No DB writes (no `alaska.db` / `alaska_pmf.db`). No Customer.io / SMS / email.

## Do-not-touch (respected)

V4: `entrypoint.sh`, `Dockerfile`, `config/openclaw.json`, `migrations/*`,
`skills/{alaska-core,intent-classifier,task-handler,slack-commands}`,
`workspace/{SOUL,AGENT_RULES,MEMORY,DAILY_STATE,THINKER_STATE}.md`.
V5: `lib/pmf_os/**`, `skills/pmf-cohort-os/`, `alaska_pmf.db`, `/pmf`.
Audit v1: `skills/bon-internal-audit/**`, `tests/test_audit.py`.

## Run the tests

```bash
python3 -m pytest tests/test_alaska_artifacts.py tests/test_command_gateway.py -q
# or the whole suite:
python3 -m pytest tests/ -q
```
