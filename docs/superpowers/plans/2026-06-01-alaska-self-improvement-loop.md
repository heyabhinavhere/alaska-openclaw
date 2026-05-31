# Alaska Self-Improvement Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alaska learns from team feedback and opens human-reviewed PRs that sharpen the *Principles* in its own skill files — closing the loop so it improves on its own.

**Architecture:** A `skill_feedback` SQLite table; a `feedback-collector` skill+cron that scans existing audit trails + Slack reactions and logs feedback signals (purely additive — edits no handler skill); a `self-improver` skill+daily cron that clusters feedback, runs a 7-step "teach how to learn" process, and opens ONE PR/day editing only the Principles zone of a target skill (via the GitHub REST API + a scoped write token, since the container has no git/gh). Humans review every PR; nothing auto-merges.

**Tech Stack:** OpenClaw on Railway; prompt-driven `SKILL.md` skills; SQLite (`/data/queue/alaska.db`); Python 3 stdlib (`urllib`) for the GitHub REST API; GitHub branch protection + CODEOWNERS for mechanical safety.

---

## READ FIRST — you (the implementer) have zero context

You are a separate agent in your own git worktree. You did not see the design conversation. Internalize this before any task:

**Repo & deploy model.** Repo: `heyabhinavhere/alaska-openclaw` → Railway auto-redeploys on merge to `main`. `entrypoint.sh` on deploy: runs `migrations/*.sql` via `run_migrations.sh`; mirror-syncs `/opt/default-skills/` → `/data/skills/` (skills are git-canonical — runtime edits wiped); exports `PYTHONPATH=/opt/lib`. **`docs/` is NOT deployed.** **`config/cron-jobs-backup.json` is a documentation SNAPSHOT — NOT loaded on deploy.** Live crons are registered with the in-session `cron.add` OpenClaw tool (an activation step a human/Alaska runs; it is NOT automatic from the snapshot file). The container has **`curl` + `python3` + `sqlite3` only — NO `git`, NO `gh`, NO `pytest`**. (Run unit tests in your dev worktree, not the container; use `python3 -m pytest` or `python3 -m unittest`.)

**The full design is in** `docs/superpowers/specs/2026-06-01-alaska-self-improvement-loop-design.md`. Read it.

**Hard constraints (do not violate):**
- **Never touch `workspace/knowledge/`** (Alaska's KB — Abhinav-authored-only), `migrations/`, `config/`, `entrypoint.sh`, or `Dockerfile` from the self-improvement loop. CODEOWNERS will enforce this; the skills must also state it.
- **The loop sharpens Principles only; it must NEVER weaken a 🔒 Guardrail** (PII/money/deploy/safety). If a lesson is actually a new guardrail, it FLAGS it for a human, never self-writes it.
- **Never auto-merge.** Branch protection requires human review (Abhinav + Claude).
- **The write token is scoped to `alaska-openclaw` ONLY** — never BON product repos.

**Parallel-agent file boundaries (CRITICAL — another agent is editing these concurrently).** You may create all new files freely and edit `skills/pre-call-brief/SKILL.md`. You must **NOT** edit `skills/watcher-creator/`, `skills/watcher-dispatcher/`, `skills/watcher-janitor/`, `skills/slack-commands/`, `skills/intent-classifier/`, or `workspace/SOUL.md` — those are in active flight. Their zone-restructure is **Phase 4, gated on those PRs merging first** (a human will tell you when). Each phase is its own PR to `main`; rebase on latest `main`.

---

## File Structure

| File | New/Modify | Responsibility | Phase |
|---|---|---|---|
| `lib/open_self_pr.py` | Create | Open a PR on alaska-openclaw via GitHub REST API (no git/gh) | 0 |
| `lib/test_open_self_pr.py` | Create | Unit tests (mocked API) for the helper | 0 |
| `.github/CODEOWNERS` | Create | Mechanically protect KB/migrations/config/entrypoint/Dockerfile | 1 |
| `migrations/0005_skill_feedback.sql` | Create | `skill_feedback` audit table | 2 |
| `skills/feedback-collector/SKILL.md` | Create | Scan audit trails + Slack → log feedback signals | 2 |
| `skills/self-improver/SKILL.md` | Create | Cluster feedback → 7 steps → open one PR/day | 3 |
| `config/cron-jobs-backup.json` | Modify | Snapshot entries for the 2 new crons (live reg is separate) | 2,3 |
| `skills/pre-call-brief/SKILL.md` | Modify | Restructure into Principles / Guardrails 🔒 zones | 3 |
| `workspace/MEMORY.md` | Modify | One-line note recording the loop + its constraints | 3 |
| watcher/slack/SOUL skills | Modify | Zone-restructure — **Phase 4, sequenced** | 4 |

---

## Phase 0 — Prove PR-from-container works (de-risk FIRST)

If Alaska can't open a PR from the container, the whole loop is moot. Build + prove the helper before anything else.

### Task 0.1: `lib/open_self_pr.py` — GitHub REST API PR helper

**Files:**
- Create: `lib/open_self_pr.py`
- Test: `lib/test_open_self_pr.py`

- [ ] **Step 1: Write failing tests** (`lib/test_open_self_pr.py`) — mock the API layer; assert the call sequence + guards:

```python
import importlib, sys, types
import lib.open_self_pr as m  # PYTHONPATH=/opt/lib in prod; in dev run from repo root

def test_no_changes_raises(monkeypatch):
    monkeypatch.setenv("GITHUB_SELF_IMPROVE_TOKEN", "x")
    try:
        m.open_pr({}, "t", "b"); assert False
    except m.SelfPRError as e:
        assert "no changes" in str(e)

def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("GITHUB_SELF_IMPROVE_TOKEN", raising=False)
    try:
        m.open_pr({"skills/x/SKILL.md": "hi"}, "t", "b"); assert False
    except m.SelfPRError as e:
        assert "GITHUB_SELF_IMPROVE_TOKEN" in str(e)

def test_open_pr_sequence(monkeypatch):
    monkeypatch.setenv("GITHUB_SELF_IMPROVE_TOKEN", "x")
    calls = []
    def fake_req(method, path, body=None):
        calls.append((method, path))
        if path.endswith("/git/ref/heads/main"): return {"object": {"sha": "BASESHA"}}
        if "/contents/" in path and method == "GET": return {"sha": "OLDSHA"}
        if path.endswith("/pulls"): return {"html_url": "https://github.com/o/r/pull/1"}
        return {}
    monkeypatch.setattr(m, "_req", fake_req)
    url = m.open_pr({"skills/x/SKILL.md": "new content"}, "title", "body", branch="b1")
    assert url == "https://github.com/o/r/pull/1"
    methods = [c[0] for c in calls]
    assert methods == ["GET", "POST", "GET", "PUT", "POST"]  # base→branch→getsha→put→pr
```

- [ ] **Step 2: Run, verify fail** — `python3 -m pytest lib/test_open_self_pr.py -v` → FAIL (module/func missing). (If pytest absent, port to `unittest`.)

- [ ] **Step 3: Implement** (`lib/open_self_pr.py`):

```python
"""open_self_pr.py — open a PR on alaska-openclaw via the GitHub REST API.

The container has no git/gh (curl+python3 only), so self-improvement PRs go
through the REST API using GITHUB_SELF_IMPROVE_TOKEN — a fine-grained, PR-only
write token scoped to alaska-openclaw ONLY (never BON product repos). It never
merges; branch protection requires human review.
"""
from __future__ import annotations
import base64, json, os, time, urllib.request, urllib.error

OWNER, REPO, BASE, API = "heyabhinavhere", "alaska-openclaw", "main", "https://api.github.com"

class SelfPRError(RuntimeError):
    pass

def _token() -> str:
    t = os.environ.get("GITHUB_SELF_IMPROVE_TOKEN")
    if not t:
        raise SelfPRError("GITHUB_SELF_IMPROVE_TOKEN not set — self-improvement PRs disabled")
    return t

def _req(method: str, path: str, body=None):
    url = path if path.startswith("http") else f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {_token()}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "alaska-self-improver")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        raise SelfPRError(f"{method} {path} -> {e.code}: {e.read().decode()[:300]}")

def open_pr(changes: dict, title: str, body: str, branch: str | None = None) -> str:
    """changes: {repo_path: new_full_content}. Returns the PR html_url. Never merges."""
    if not changes:
        raise SelfPRError("no changes to open a PR for")
    branch = branch or f"self-improve/{time.strftime('%Y%m%d-%H%M%S')}"
    base_sha = _req("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{BASE}")["object"]["sha"]
    _req("POST", f"/repos/{OWNER}/{REPO}/git/refs", {"ref": f"refs/heads/{branch}", "sha": base_sha})
    for path, content in changes.items():
        sha = None
        try:
            sha = _req("GET", f"/repos/{OWNER}/{REPO}/contents/{path}?ref={BASE}").get("sha")
        except SelfPRError:
            sha = None  # new file
        payload = {"message": f"self-improve: update {path}", "branch": branch,
                   "content": base64.b64encode(content.encode()).decode()}
        if sha:
            payload["sha"] = sha
        _req("PUT", f"/repos/{OWNER}/{REPO}/contents/{path}", payload)
    return _req("POST", f"/repos/{OWNER}/{REPO}/pulls",
                {"title": title, "body": body, "head": branch, "base": BASE})["html_url"]
```

- [ ] **Step 4: Run, verify pass** — `python3 -m pytest lib/test_open_self_pr.py -v` → PASS.

- [ ] **Step 5: Commit** — `git add lib/open_self_pr.py lib/test_open_self_pr.py && git commit -m "feat(self-improve): GitHub REST API PR helper (no git/gh in container)"`

### Task 0.2: Live spike — open a real throwaway PR from a container-like env

- [ ] **Step 1:** With a temporary fine-grained PAT (create-branch/PR on alaska-openclaw, no merge) exported as `GITHUB_SELF_IMPROVE_TOKEN`, run a one-off:
```bash
PYTHONPATH=. python3 -c "import lib.open_self_pr as m; print(m.open_pr({'docs/superpowers/research/_spike.md':'# spike\n'}, 'spike: prove PR-from-container', 'throwaway — close me'))"
```
- [ ] **Step 2:** Confirm the PR URL prints and the PR exists on GitHub. Confirm the token **cannot merge** it. Close the PR + delete the branch.
- [ ] **Step 3:** If it fails (fine-grained token scope/permission quirks), STOP and report — resolve before Phase 1+. Record findings in `docs/superpowers/research/2026-06-0X-self-pr-spike.md` and commit.

---

## Phase 1 — Safety rails (before any self-edit capability)

### Task 1.1: `.github/CODEOWNERS`

**Files:** Create: `.github/CODEOWNERS`

- [ ] **Step 1: Write the file** (replace `@abhinav-handle` with the real GitHub handle/team):
```
# Self-improvement loop may only touch skills/. Everything below requires a human owner.
/workspace/knowledge/   @abhinav-handle
/migrations/            @abhinav-handle
/config/                @abhinav-handle
/entrypoint.sh          @abhinav-handle
/Dockerfile             @abhinav-handle
/lib/                   @abhinav-handle
/.github/               @abhinav-handle
```
- [ ] **Step 2: Commit** — `git add .github/CODEOWNERS && git commit -m "chore(ci): CODEOWNERS — protect KB/migrations/config from self-edit"`

### Task 1.2: Grant + branch protection (manual — document, don't automate)

- [ ] **Step 1:** In a `docs/superpowers/research/2026-06-0X-self-improve-grant.md` checklist (commit it), document for Abhinav to perform on GitHub + Railway:
  - Create a **fine-grained PAT** scoped to **only `alaska-openclaw`**: Contents=read/write, Pull requests=read/write, **no admin/merge**. Store as Railway env var `GITHUB_SELF_IMPROVE_TOKEN`.
  - Enable **branch protection** on `main`: require ≥1 approving review; require review from Code Owners; do not allow the token's identity to self-approve.
  - Verify CODEOWNERS is active (a PR touching `migrations/` requests the human owner).
- [ ] **Step 2:** This is a human gate. The loop's skills (Phase 2/3) must degrade gracefully if `GITHUB_SELF_IMPROVE_TOKEN` is unset (collector still logs; self-improver logs "PR disabled — token unset" and skips, never crashes).

---

## Phase 2 — Capture only (`skill_feedback` + collector)

### Task 2.1: Migration `0005_skill_feedback.sql`

**Files:** Create: `migrations/0005_skill_feedback.sql`

- [ ] **Step 1: Write** (idempotent):
```sql
-- Migration 0005: skill_feedback — audit of feedback signals + what they changed.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS skill_feedback (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  source_surface TEXT NOT NULL
                 CHECK (source_surface IN ('standup','dm_qa','watcher','daily_pulse','meeting_intelligence','other')),
  signal_type    TEXT NOT NULL
                 CHECK (signal_type IN ('correction','pushback','parse_failure','explicit_flag','brief_gap','outcome_failure')),
  target_skill   TEXT NOT NULL,            -- e.g. 'pre-call-brief'
  excerpt        TEXT,                     -- the relevant message/context (escaped)
  actor_slack_id TEXT,
  source_ref     TEXT,                     -- Slack permalink/thread for traceability
  processed      BOOLEAN NOT NULL DEFAULT 0,
  processed_at   DATETIME,
  resulting_pr   TEXT                      -- PR URL once a change is proposed (nullable)
);
CREATE INDEX IF NOT EXISTS idx_skill_feedback_unprocessed ON skill_feedback(processed, created_at);
CREATE INDEX IF NOT EXISTS idx_skill_feedback_skill ON skill_feedback(target_skill, created_at);
```
- [ ] **Step 2: Test the chain** locally:
```bash
TMP=$(mktemp -d); for f in migrations/000*.sql; do sqlite3 "$TMP/t.db" < "$f"; done
sqlite3 "$TMP/t.db" "INSERT INTO skill_feedback (source_surface,signal_type,target_skill,excerpt) VALUES ('standup','correction','pre-call-brief','test');"
sqlite3 "$TMP/t.db" "SELECT count(*) FROM skill_feedback;"   # expect 1
sqlite3 "$TMP/t.db" "INSERT INTO skill_feedback (source_surface,signal_type,target_skill) VALUES ('bogus','x','y');" 2>&1 | head -1  # expect CHECK error
rm -rf "$TMP"
```
- [ ] **Step 3: Commit** — `git add migrations/0005_skill_feedback.sql && git commit -m "feat(self-improve): migration 0005 skill_feedback table"`

### Task 2.2: `skills/feedback-collector/SKILL.md`

**Files:** Create: `skills/feedback-collector/SKILL.md`

- [ ] **Step 1: Write the skill.** It MUST contain (read the spec §"feedback-collector" + the existing `skills/watcher-janitor/SKILL.md` for the scan-cron style and `skills/shared-toolkit/SKILL.md` §1.5 escape rules):
  - **Frontmatter:** `name: feedback-collector`, `version: 1.0.0`, `metadata.openclaw.requires.bins: [sqlite3, python3]`, `emoji: "👂"`.
  - **When invoked:** a cron fires `Run /data/skills/feedback-collector/SKILL.md procedure.`
  - **Procedure (scan, derive, log — additive, NEVER edit a handler skill):**
    1. Read a watermark (reuse a row in `event_pollers` named `feedback_collector`, or a dedicated marker) so you only scan since last run.
    2. Scan existing audit trails for signals, mapping each to a `skill_feedback` row (escape free text per §1.5):
       - `task_events` (event_type in `dedup_decision` low_confidence, `unknown_t_id_referenced`) → `signal_type='correction'/'parse_failure'`, `target_skill='task-handler'`/the originating skill.
       - `watcher_fires` (outcome `failed`) → `outcome_failure`, `target_skill='watcher-dispatcher'`.
       - `classifier_audit` (low confidence / mismatch vs human action) → `correction`, `target_skill='intent-classifier'`.
       - **standup threads** (pre-call-brief replies): a reply that corrects a brief, pushes back on a follow-up, or a logged "Couldn't parse that" → `correction`/`pushback`/`parse_failure`, `target_skill='pre-call-brief'`, `source_surface='standup'`.
       - **Slack reactions/notes** on Alaska's own messages (the explicit-flag vocabulary: 👎 / ✏️ / 🚫, or an `@alaska` note) → `explicit_flag`.
    3. Write `skill_feedback` rows with `source_ref` (Slack permalink/thread) for traceability. Advance the watermark only AFTER writing (crash-safe).
  - **Anti-patterns:** never act on anything (capture only); never edit any handler skill; never log a row without `source_ref`; implicit signals are best-effort — when unsure, log nothing (the PR gate + explicit flags carry the high-confidence load); never read or write `workspace/knowledge/`.
- [ ] **Step 2: Verify** — `grep -c "capture only\|NEVER edit\|skill_feedback" skills/feedback-collector/SKILL.md` (≥3); confirm it references no `watcher-creator`/`slack-commands` *edits*.
- [ ] **Step 3: Synthetic test** — seed a temp DB with 0001–0005 + synthetic `task_events`/`watcher_fires`/`classifier_audit` rows; run the documented SQL the skill specifies; assert it would produce the right `skill_feedback` rows (right surface/signal_type/target_skill) and ignores normal chatter.
- [ ] **Step 4: Commit** — `git add skills/feedback-collector/SKILL.md && git commit -m "feat(self-improve): feedback-collector skill (capture-only)"`

### Task 2.3: Collector cron snapshot + activation note

**Files:** Modify: `config/cron-jobs-backup.json`

- [ ] **Step 1:** Append (using `python3 -m json.tool` round-trip with `ensure_ascii=True` to keep the diff minimal — see the existing entries) a cron entry mirroring the live shape (canonical `delivery:{"mode":"none"}`):
```json
{"name":"Feedback Collector","enabled":true,"agentId":"main","sessionKey":"agent:main:main","sessionTarget":"isolated","wakeMode":"now","schedule":{"kind":"cron","expr":"0 */4 * * *","tz":"UTC"},"payload":{"kind":"agentTurn","message":"Run /data/skills/feedback-collector/SKILL.md procedure.","timeoutSeconds":300},"delivery":{"mode":"none"},"state":{}}
```
- [ ] **Step 2:** Record in the activation checklist (`docs/.../activation.md`): this cron is a SNAPSHOT — register it live via `cron.add` post-merge.
- [ ] **Step 3: Commit** — `git add config/cron-jobs-backup.json && git commit -m "feat(self-improve): feedback-collector cron snapshot (live reg via cron.add)"`

---

## Phase 3 — Propose-only (`self-improver`, scoped to pre-call-brief)

### Task 3.1: Restructure `skills/pre-call-brief/SKILL.md` into zones

**Files:** Modify: `skills/pre-call-brief/SKILL.md`

- [ ] **Step 1:** Add two clearly delimited sections WITHOUT changing behavior: `## Principles (the self-improvement loop may sharpen these)` — move the judgment guidance here (what to surface, source-hint taste, follow-up tone, opinionated suggestions); and `## Guardrails — FROZEN 🔒 (never auto-edited)` — mark the hard rules with a leading 🔒 (PRIVATE-to-Abhinav for the actual pre-call brief, the parser anti-patterns "never silently match / never re-process / never call task-handler with another person's owner_slack_id"). Also fix the pre-existing header drift (it says "private to Abhinav only" but Steps 3–4 do per-person team standup — clarify the two modes).
- [ ] **Step 2: Verify** — `grep -c "Principles (the self-improvement\|Guardrails — FROZEN 🔒" skills/pre-call-brief/SKILL.md` (=2); confirm every former anti-pattern survived (no guardrail lost).
- [ ] **Step 3: Commit** — `git add skills/pre-call-brief/SKILL.md && git commit -m "refactor(pre-call-brief): split Principles vs Guardrails 🔒 zones"`

### Task 3.2: `skills/self-improver/SKILL.md`

**Files:** Create: `skills/self-improver/SKILL.md`

- [ ] **Step 1: Write the skill.** It MUST contain (read the spec §"self-improver" + the 7 steps):
  - **Frontmatter:** `name: self-improver`, `version: 1.0.0`, `requires.bins: [sqlite3, python3]`, `requires.env: [GITHUB_SELF_IMPROVE_TOKEN, ANTHROPIC_API_KEY]`, `emoji: "📈"`.
  - **When invoked:** daily cron `Run /data/skills/self-improver/SKILL.md procedure.`
  - **Procedure:**
    1. `SELECT * FROM skill_feedback WHERE processed=0`. If none → exit silently.
    2. **SCOPE GUARD (Phase 3):** only act on rows where `target_skill='pre-call-brief'`. Leave others unprocessed (later phases widen this).
    3. Cluster related rows. For each cluster run the **7 steps**: identify → why → zoom to pattern → check existing principles → write as a *principle* (how to think, not if-X-then-Y) → place in the target skill's **`## Principles`** zone → edit by sharpening/merging (keep the file tight; never append a brittle Nth rule).
    4. Read the current target skill content from `/data/skills/<skill>/SKILL.md`. Compute the edited full content. **Edits go ONLY inside the `## Principles` zone. NEVER modify a 🔒 Guardrail line, NEVER any other skill, NEVER `workspace/knowledge/`/`migrations/`/`config/`.** If a lesson is actually a new guardrail (safety/irreversible), do NOT write it — note it in the PR body under "⚠️ Proposed new GUARDRAIL — needs human codification".
    5. Open ONE PR via the helper:
       ```bash
       PYTHONPATH=/opt/lib python3 -c "import open_self_pr as m; print(m.open_pr(<changes dict>, '<title>', '<body>'))"
       ```
       (If `GITHUB_SELF_IMPROVE_TOKEN` is unset → log `self-improver: PR disabled (token unset)` and exit; never crash.)
    6. PR body = plain-English summary: which feedback drove which principle change, per the 7 steps, + any ⚠️ guardrail flags. DM Abhinav + Claude the PR URL.
    7. `UPDATE skill_feedback SET processed=1, processed_at=CURRENT_TIMESTAMP, resulting_pr='<url>' WHERE id IN (...)`.
  - **Anti-patterns:** never auto-merge (you can't — branch protection); never edit outside the Principles zone; never touch protected paths; never self-write a guardrail (flag it); one PR/day max; if feedback is thin/low-confidence, propose nothing rather than invent a change.
- [ ] **Step 2: Verify** — `grep -c "Principles\|never\|GUARDRAIL\|open_self_pr" skills/self-improver/SKILL.md` (multiple); confirm the SCOPE GUARD to `pre-call-brief` is present.
- [ ] **Step 3: Dry-run** — seed `skill_feedback` with synthetic `pre-call-brief` rows; walk the procedure by hand; assert the proposed edit lands only in the Principles zone, touches no 🔒 line/protected path, and flags a safety-type lesson instead of writing it.
- [ ] **Step 4: Commit** — `git add skills/self-improver/SKILL.md && git commit -m "feat(self-improve): self-improver skill (propose-only, pre-call-brief scope)"`

### Task 3.3: Self-improver daily cron snapshot + MEMORY note

**Files:** Modify: `config/cron-jobs-backup.json`, `workspace/MEMORY.md`

- [ ] **Step 1:** Append the daily cron snapshot:
```json
{"name":"Self-Improver","enabled":true,"agentId":"main","sessionKey":"agent:main:main","sessionTarget":"isolated","wakeMode":"now","schedule":{"kind":"cron","expr":"0 2 * * *","tz":"UTC"},"payload":{"kind":"agentTurn","message":"Run /data/skills/self-improver/SKILL.md procedure.","timeoutSeconds":600},"delivery":{"mode":"none"},"state":{}}
```
- [ ] **Step 2:** Add a one-line MEMORY.md note under system evolution: "Self-improvement loop (feedback-collector + self-improver) live — learns from team feedback, opens human-reviewed PRs to the Principles zone of skills (never KB/guardrails). Crons registered via cron.add."
- [ ] **Step 3: Commit** — `git add config/cron-jobs-backup.json workspace/MEMORY.md && git commit -m "feat(self-improve): self-improver cron snapshot + MEMORY note"`

---

## Phase 4 — Expand targets (SEQUENCED — only after the in-flight watcher/DM-routing PRs merge)

**Do NOT start Phase 4 until a human confirms the watcher + DM-routing PRs are merged to `main`.** Then, one PR per skill:

### Task 4.1–4.N: Zone-restructure each new target skill

**Files:** Modify (one per task): `skills/watcher-creator/SKILL.md`, `skills/watcher-dispatcher/SKILL.md`, `skills/slack-commands/SKILL.md`, `skills/intent-classifier/SKILL.md` (and confirm `workspace/SOUL.md`'s gate rules are correctly classified as 🔒 Guardrails, not loop-editable).

- [ ] For each: add `## Principles (loop may sharpen)` + `## Guardrails — FROZEN 🔒` sections; move judgment guidance to Principles; 🔒-mark every safety rule (PII guard, $3 gate, write-ahead, "never cron.add a user request", recipient/date discipline); verify no guardrail lost (`grep` the former anti-patterns); commit per skill.
- [ ] Update the self-improver SCOPE GUARD (Task 3.2 step 2) to include the newly-restructured skills, one at a time, observing PR quality before widening further.

---

## Verification Plan

**Static / unit (dev worktree):**
```bash
python3 -m pytest lib/test_open_self_pr.py -v            # helper unit tests pass
ls migrations/0005_skill_feedback.sql                    # migration present
for s in feedback-collector self-improver; do ls skills/$s/SKILL.md; done
ls .github/CODEOWNERS
grep -c "Guardrails — FROZEN 🔒" skills/pre-call-brief/SKILL.md   # =1 (zones in place)
# migration chain applies + CHECK constraints hold (Task 2.1 Step 2)
```

**Live (post-merge + redeploy + activation):**
1. Phase-0 spike PR opened + closed (proves PR-from-container).
2. Branch protection blocks an unreviewed merge; a PR touching `migrations/` requests the human code-owner.
3. Register the 2 crons via `cron.add`; confirm in `cron.list`.
4. Capture soak (Phase 2): after a few standup days, `SELECT source_surface, signal_type, target_skill, count(*) FROM skill_feedback GROUP BY 1,2,3;` shows sensible signals, no garbage.
5. Propose soak (Phase 3): the self-improver opens a real PR editing only `pre-call-brief`'s Principles zone; Abhinav+Claude review quality; confirm no 🔒/protected-path touch.

**What "done" looks like:** a daily ~60-second PR from Alaska proposing a principle improvement to `pre-call-brief`, backed by `skill_feedback` rows, reviewed + merged by humans, with zero guardrail/KB/protected-path edits ever.

---

## Out of scope (deferred)

- Daily Pulse / Follow-Through / Meeting Intelligence as targets (after Phase 4 settles).
- Automating the grant/branch-protection (manual human gate by design).
- Any change to BON product repos (never).
