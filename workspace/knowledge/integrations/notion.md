# Notion — BON's Operations Datastore

**Last updated:** 2026-05-30 · **Status:** Draft. API facts verified against developers.notion.com (May 2026) + our live `shared-toolkit` write contract.

> **What this file is:** what Notion is at BON, how Alaska authenticates, and **what she can DO with it** — the API surface (data sources, version routing, write shapes), the database IDs, the rate limits. The capability + reference layer.
> **What it is NOT:** how Alaska decides *what* to write or *which agent* writes where — that's workflow. The exact write JSON lives in `skills/shared-toolkit/SKILL.md` (§ Notion Write Contract); which agent writes which DB lives in `docs/alaska-operating-model.md`; the roster + Notion user IDs live in `workspace/MEMORY.md`.

---

## What it is

Notion is BON's structured **store of operational records** — the Decision Log, Meeting Notes, Blockers, Risk Register, Changelog, Backlog, Proposals, and Daily Scrum DBs. Agents write durable, queryable records here (queue-first) and read them back for context.

**It is *not* the single source of truth** — a common misconception (BON's original 2026 design *did* call Notion "the only source of truth," but the system outgrew that). Today the operating truth is split:
- **Live working state** — per-person status, current focus, recent decisions/blockers/metrics → `DAILY_STATE.md` (which titles itself "Single Source of Truth" and is read by every agent before acting; in V4 it becomes a view of the SQLite task graph).
- **Tasks** → the SQLite task graph (V4) / `DAILY_STATE.md` today. The Notion **Sprint Board is retired** — Notion holds no live task board.
- **Team roster + Slack/Notion identity** → `MEMORY.md` (the Notion Team Roster DB is a secondary copy, not canonical).

So Notion is the durable **record/archive** layer for operational documents; the live truth lives in `DAILY_STATE.md` / the task graph / `MEMORY.md`.

## Auth + the API model

| | |
|---|---|
| Auth | `Authorization: Bearer $NOTION_API_KEY` (internal integration, scoped to the BON Credit workspace) |
| Token prefix | newer tokens are `ntn_…`; older `secret_…` tokens still work |
| Connection gotcha | a new integration has **zero page access by default** — each page/DB must be explicitly shared with the integration (cascades to children), or every call errors |

**The data-sources model (Notion API ≥ `2025-09-03`):** a *database* is now a container holding one or more **data sources**, each with its own `data_source_id` and schema. That's why BON keeps two IDs per object — a **data source ID** (reads) and a **write DB ID** (page-create parent).

⚠️ **Version routing — this is BON's proven setup; mixing the two → cryptic 400s:**
- **Reads:** `POST /v1/data_sources/{data_source_id}/query` with `Notion-Version: 2025-09-03`
- **Writes:** `POST /v1/pages` and `PATCH /v1/pages/{page_id}` with `Notion-Version: 2022-06-28`

(Notion's modern guidance is to standardize on `2025-09-03`+ everywhere, but our `shared-toolkit` explicitly warns that some page-write shapes are rejected on `2025-09-03` — so the **split above is what works today**. Revisit only deliberately.)

## The databases (what each holds)

**The canonical name → (data source ID, write DB ID) map lives in `workspace/MEMORY.md` § Notion Data Sources** — that's the single source; don't embed the IDs here (they're already mirrored across ~9 files and drift). Mechanics: reads use the *data source ID*, writes use the *write DB ID* (some objects share one).

| Database | What lives there |
|---|---|
| Decision Log | every team decision with context, date, who |
| Meeting Notes | Fireflies-derived notes |
| Blockers | active blockers + resolution tracking |
| Risk Register | risks by category, severity, mitigation |
| Changelog | what shipped, when, by whom |
| Backlog | prioritized items not yet active |
| Proposals | items awaiting team confirmation |
| Team Roster | people, roles, skills, availability |
| Agent Signals | agent-to-agent coordination |
| Daily Scrum | pre-call sheets (currently posted to Slack instead) |
| **Sprint Board** | **RETIRED 2026-05-23 — read-only history, never write** |

*(Which agent writes which DB → `docs/alaska-operating-model.md`; canonical IDs → `workspace/MEMORY.md` § Notion Data Sources.)*

## Writing — what Alaska can set

`POST /v1/pages` with `{"parent":{"database_id":"<WRITE_DB_ID>"}, "properties":{…}}`; `PATCH /v1/pages/{id}` to update. **Property keys must match the DB's schema exactly.** The exact value-shape per property type is the **canonical contract in `skills/shared-toolkit/SKILL.md` → Notion Write Contract** — don't reinvent it here. The two that bite:

- **`Status` is a `select`, not a `status` type.** Write `{"select":{"name":"…"}}`, never `{"status":{…}}` — wrong key fails silently (Notion does no coercion). `select` auto-creates a new option by name; `status` cannot via API.
- **`Owner` is a `people` field, now ENABLED.** Write `{"people":[{"id":"<notion_user_id>"}]}` using the roster's Notion ID (`MEMORY.md`). The assignee must be a workspace member/guest and a `person` (not a bot). Fall back to first-name-in-Notes only if a person has no ID. *(This was paused until 2026-05-29 when team Notion IDs were captured — now lifted.)*

**Always write queue-first** (`shared-toolkit` § notionWrite): the write lands in local SQLite first, then syncs to Notion — survives outages, never loses a record.

## Rate limits / pagination / limits

*(Per Notion's published API limits — developers.notion.com; standard platform limits, not separately measured against our workspace.)*

- **~3 requests/sec** average per integration. Over → HTTP **429** + `Retry-After` (seconds) — honor it. (The queue-first path is also the backpressure valve — don't hammer.)
- Pagination: `page_size` default/max **100**; response carries `has_more` + `next_cursor` (pass back as `start_cursor`).
- Payload caps: ≤**1000** block elements and ≤**500 KB** body per request; arrays (rich_text, multi_select, relations, people) cap at **100**; rich-text/URL strings cap at **2000** chars.

## Known failure modes / gotchas

- **Integration not shared** with the page/DB → every call errors. The most common silent setup failure.
- **Wrong API version for the endpoint** → 400 (`2025-09-03` on `/pages`, or `2022-06-28` on `/data_sources/query`).
- **`Status` written as `status` instead of `select`** → silent miswrite (see above).
- **People assignment** needs a real workspace member + `person` type; non-members/bots rejected.
- **3 req/s is low** — batch/queue and back off on 429.
- **Gateway restart wipes uncommitted workspace files** — commit workspace changes immediately (a past data-loss lesson; not Notion-specific but bites the roster/state that feeds Notion writes).

## How Alaska uses this → pointers (not duplicated here)

- Exact write JSON per property type → `skills/shared-toolkit/SKILL.md` § Notion Write Contract.
- Queue-first write mechanics → `skills/shared-toolkit/SKILL.md` § notionWrite.
- Which agent writes which DB, and the source-of-truth model → `docs/alaska-operating-model.md`.
- Roster + Notion user IDs (for the Owner field) → `workspace/MEMORY.md` → Team Roster.

## People / ownership

- **Owns the Notion workspace + data model/schemas:** Abhinav (admin).

## Open questions

- **[NEEDS ABHINAV]** Revive the `Daily Scrum` DB (now that pre-call sheets post to Slack), or formally deprecate it?
- **[NEEDS ABHINAV]** Design of the clean new "Active Work" DB if/when the v2 task graph projects to Notion (currently SQLite-only).
