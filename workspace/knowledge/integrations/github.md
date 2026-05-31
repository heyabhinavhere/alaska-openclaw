# GitHub — Repos, Read Access, and the READ-ONLY Rule

**Last updated:** 2026-05-30 by Abhinav
**Status:** Draft

---

## Why Alaska has GitHub access (the point)

GitHub is how Alaska answers code and repo questions **from the real source instead of from memory.** When someone asks "where is X handled?" or "did that fix land?", Alaska fetches the actual file or commit and answers from the bytes she just read. She does NOT reconstruct code from recollection.

This capability exists because the opposite failed badly. In a past investigation, Alaska produced confident but fabricated, self-contradicting findings about the code, answering from memory instead of from the source, then stating things that weren't true. The fix is grounded reading, and its discipline (below) matters MORE now that the capability is real, not less. Reading-to-answer is NOT a license to autonomously crawl multiple repos and broadcast conclusions.

---

## What Alaska CAN do

### 1. Read actual file contents (the headline capability)

Alaska can fetch and read the real contents of any file in the 9 private repos via the GitHub Contents API, then decode it:

```bash
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" -H "User-Agent: alaska" \
  "https://api.github.com/repos/<org>/<repo>/contents/<path>?ref=<branch>" \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())"
```

- **Always pass `?ref=<branch>`** and use the repo's real default branch (see the table. `bon_webservices` is **`dev_testing`**, everything else is `main`).
- Verified working: returns HTTP 200 with base64 `content` for private-repo files.
- This is the mechanism behind every grounded code answer.
- **Don't know the exact path?** List the repo's file tree first, then read the file you find:
  ```bash
  curl -s -H "Authorization: Bearer $GITHUB_TOKEN" -H "User-Agent: alaska" \
    "https://api.github.com/repos/<org>/<repo>/git/trees/<branch>?recursive=1"
  ```
  Find the path in the tree, then fetch its contents with the call above. Never guess a path. List, then read.

### 2. Track engineering activity (read)

- Recent **commits** (per repo, or filtered by author + date).
- **Pull requests** (open + closed/merged).
- **Branches**, file trees, tags/releases (none of the repos tag releases today).

### 3. Cross-repo activity rollups

"What shipped today across all repos" requires querying **both** orgs (`Bonhq/*` and `Bonlife/*`). GitHub has no org-level rollup endpoint.

---

## How to answer a code question (the grounded-reading discipline)

This is the rule that keeps the capability honest:

1. **Quote the real bytes.** Fetch the file this turn and quote the actual lines. Name the repo, branch, and path you read.
2. **If you can't read it, say so plainly.** 404, file moved, logic lives outside the 9 repos. Name who owns it. Don't paper over a gap.
3. **Never state a path, line number, function name, or "there's another copy in…"** that you did not pull this turn. No reconstruction from memory.
4. **Answering is not investigating.** A code question = read + quote + answer. It is NOT a cue to autonomously walk multiple repos and post conclusions to a channel. If broader investigation seems warranted, propose it to the asker first.

---

## READ-ONLY: the hard rule (and the honest caveat)

**Alaska never writes to GitHub.** No push, merge, branch create/delete, PR open/close, issue close, or commenting. Ever. This applies to all 9 repos AND to `alaska-openclaw/` (Alaska's own config repo), where the temptation to "just fix this one thing" is highest.

**Honest caveat, don't paper over this:** the rule is currently enforced by THIS INSTRUCTION, not by the token's scope. The `$GITHUB_TOKEN` in use actually carries full `repo` read + write access to all repos. Broader than read-only. A swap to a fine-grained, read-only token (Contents:read + commit/PR read) is planned. Abhinav owns that change. Until then, treat READ-ONLY as absolute discipline. The key will not stop a mistaken write. Only the rule will.

---

## Auth + access

- **Env var:** `$GITHUB_TOKEN` (40-char token; never log it, never put it in Slack output)
- **Current scope:** full `repo` read+write (see caveat above). To be narrowed to read-only.
- **API base:** `https://api.github.com`
- **Rate limit:** 5,000 req/hr authenticated. Walking commit history across 9 repos hourly can add up. Cache where possible. If you hit it (HTTP 403 + `X-RateLimit-Remaining: 0`), back off and say "GitHub rate-limited, I'll retry shortly." Never fail silently or invent an answer.

### Common read patterns

```bash
# File contents on the right branch (see default-branch table!)
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" -H "User-Agent: alaska" \
  "https://api.github.com/repos/Bonhq/bon_webservices/contents/src/app.js?ref=dev_testing" \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())"

# Recent commits in a repo
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/Bonlife/BON-CredGPT/commits?per_page=20"

# Commits by a specific engineer in the last 7 days (use the handle table below)
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/Bonlife/BON-CredGPT/commits?author=Sandy-39&since=2026-05-23T00:00:00Z"

# PRs (open + closed)
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/Bonhq/bon_webservices/pulls?state=all&per_page=20"
```

---

## Repository map (9 repos, 2 orgs)

Default branch + primary internal owner verified against live data 2026-05-30.

### Bonhq org (product code)

| Repo | Default branch | Internal owner | Purpose |
|---|---|---|---|
| `bon_app` | `main` | Pankaj | Flutter mobile app (iOS + Android). Much of the history is MobileFirst (Leo, Pritam); Pankaj is the internal owner. |
| `bon_webservices` | **`dev_testing`** | Nilesh (← Sai) | Node.js backend API (Express + Sequelize + PostgreSQL). **Default branch is `dev_testing`, not `main`.** Top committers are all MobileFirst/external (`kush922`/Kush Sharma, Amit, Sai); Nilesh (`nileshkr6607`) is the internal owner taking it over. |
| `Landingpage` | `main` | External (no current dev) | Marketing site. Built by MobileFirst (Sai, Jaydeep); dormant since ~Apr 10, 2026. No web dev on the team now. Abhinav owns design/direction/edits. |

### Bonlife org (AI + infra, Sandeep)

| Repo | Default branch | Internal owner | Purpose |
|---|---|---|---|
| `BON-CredGPT` | `main` | Sandeep | AI credit-analysis agent core. LangChain + LangGraph (Python). Most active AI repo; Shailesh also commits. |
| `Agentic-Dashboard` | `main` | Sandeep | Internal AI dashboard. Low commit volume. |
| `Agentic-Chat-UI` | `main` | Sandeep | Internal chat UI for testing the agent. Low commit volume. |
| `BON-Terraform` | `main` | Sandeep | AWS infrastructure as code. |
| `BON-EKS` | `main` | Sandeep | Kubernetes manifests + Helm charts. Dockerfile for `bon_webservices` lives here. |
| `BON-langfuse` | `main` | Sandeep | Langfuse observability deployment. Only repo with a `CODEOWNERS` file. |

Plus `alaska-openclaw/` (Alaska's config), which the READ-ONLY rule covers explicitly.

---

## What Alaska CANNOT reach (capability vs boundary)

Be precise about the edge, and never bluff past it.

**Reachable via GitHub:** file contents, commits, PRs, branches, tags across the 9 repos plus `alaska-openclaw/`.

**NOT reachable via GitHub, even though you might wish it were:**

- The **running** hosted agent's live behavior or runtime state. The repo has the code that defines the agent. It does not have the live agent. Route to Sandeep.
- The **live backend database, including the User 360 profile API.** Querying actual user data is the app's API/DB, not the repo. Route to Nilesh.
- **CI/build logs in Jenkins/ECR.** The repo has the code that gets built. The build pipeline state lives in Jenkins. See `architecture.md` for the pipeline map.
- **Notion DB definitions and content.** No code, no repo. Route to Notion.
- **Customer.io campaigns and segments.** Configured in CIO dashboard, not in code. See `customerio.md`.
- **Amplitude dashboards.** Event names live in app code, dashboard configs live in Amplitude. See `amplitude.md`.
- **Fireflies transcripts.** Configured outside any repo.

**When a tool Alaska HAS fails** (e.g., GitHub API error/timeout): say "unavailable," not "no access."

**When something is a genuine boundary** (e.g., live agent runtime, prod DB): say "I can't reach that directly," and point to who can (Sandeep for AI/infra + the live agent; Nilesh for the backend/DB).

---

## Team GitHub handles (for author-filtered queries)

Verified from commit authorship 2026-05-30:

| Person | GitHub handle | Notes |
|---|---|---|
| Sandeep | `Sandy-39` | All Bonlife repos; dominant CredGPT author. High confidence. |
| Pankaj | `pankaj468` | `bon_app`. |
| Shailesh | `shailesh-bon` | git name "shailesh kumar"; commits to CredGPT. |
| Abhinav | `heyabhinavhere` | Org/repo owner; occasional Landingpage + alaska-openclaw. |
| Nilesh | `nileshkr6607` | Backend (`bon_webservices`); joined ~May, so his commits are recent/sparse vs the MobileFirst history. Author-filtering by his handle will show less than his real involvement. |

**MobileFirst (external agency, offboarding):** `kush922` (Kush Sharma, backend engineer, top `bon_webservices` committer), `leonardChongtham` ("Leo"), `PritamMobileFirst`, `amitmobilefirstapplications` (Amit Majumder), `hemanthmobilefirst`, `jaydeep-mobilefirst`, `sairamsara` (Sai). Much of `bon_app` + `bon_webservices` history is theirs.

**Author-filtering caveat:** filtering activity by the *internal* team's handles will undercount real repo activity, because MobileFirst authored (and still authors) a large share of `bon_app` and `bon_webservices`. When reporting "who did what," account for this. Don't imply the internal team is the only source of commits.

---

## Definitions used across the team

- **"BON repos"** = the 9 repos in the map above. When the team says "all our repos," they mean these 9.
- **"App"** = `bon_app` (Flutter). When someone says "the app," they mean this.
- **"Backend"** = `bon_webservices`. The Express API.
- **"AI layer" / "agent"** = `BON-CredGPT` and supporting `Agentic-*` repos.
- **"Infra"** = `BON-Terraform` + `BON-EKS`. Sandeep's domain.
- **"READ-ONLY"** = the absolute rule for Alaska. No push, merge, branch, issue-close, or comment operations on any repo, including `alaska-openclaw/`.
- **"Grounded reading"** = the discipline of quoting bytes Alaska fetched this turn, not facts she remembers from before.
- **"MobileFirst"** = the external agency that built much of `bon_app` and `bon_webservices`. Offboarding. Their commits dominate the history of those two repos.

---

## Known failure modes / edge cases

- **Wrong default branch.** `bon_webservices` defaults to `dev_testing`. Reading it with `?ref=main` returns stale code or 404. Always confirm the branch from the table.
- **MobileFirst vs internal authorship** (see caveat above). Don't misattribute or undercount.
- **Don't push.** The single most important constraint. Token write-access does not relax it.
- **Don't expose the token.** Never log `$GITHUB_TOKEN` or include it in any message.
- **Two orgs.** "All BON commits today" must query both `Bonhq/*` and `Bonlife/*`.
- **Author email vs handle drift.** Same person may commit under multiple git names/emails. The handle table is the reliable join key.
- **No CODEOWNERS / no release tags** (except `BON-langfuse`'s CODEOWNERS). Don't assume formal review-ownership or tag-based releases exist.
- **These 9 repos are the complete set of BON repos.** If asked about a repo not listed here, say it isn't among BON's known repos. Don't assume it exists or fabricate its contents.
- **Memory-vs-bytes drift on code answers.** Even when Alaska just fetched a file, the temptation to extrapolate ("and there's probably a matching handler in…") is high. The grounded-reading discipline is the only defense.

---

## Common queries / patterns

| Query | How |
|---|---|
| Read a specific file on the right branch | Contents API with `?ref=<branch>` from the repo map |
| List a repo's file tree | `git/trees/<branch>?recursive=1` |
| Recent commits in one repo | `GET /repos/<org>/<repo>/commits?per_page=20` |
| Recent commits across all 9 repos | Loop both orgs (`Bonhq/*` + `Bonlife/*`); no rollup endpoint exists |
| PRs (open + closed/merged) | `GET /repos/<org>/<repo>/pulls?state=all&per_page=20` |
| PRs merged today by author | Filter `pulls` for `state=closed` + `merged_at` today + author handle |
| Commits by a specific engineer (last N days) | `commits?author=<handle>&since=<ISO date>` using the handle table |
| Cross-repo activity by team member | Loop the 9 repos; filter commits by handle; deduplicate |
| Build / deploy status | Not in GitHub. Route to Jenkins/ECR. See `architecture.md`. |

---

## People / ownership

- **Repo strategy / org settings:** Sandeep + Abhinav.
- **`Bonhq/bon_app`:** Pankaj (internal) + MobileFirst history.
- **`Bonhq/bon_webservices`:** Nilesh (`nileshkr6607`, ← Sai) internal owner; history is heavy MobileFirst (Kush Sharma, Amit, Sai).
- **`Bonhq/Landingpage`:** External/dormant (was MobileFirst). Abhinav owns design/direction/edits. No internal web dev.
- **All `Bonlife/*`:** Sandeep.
- **`alaska-openclaw/`:** Abhinav.
