# Phase 1 Self-Improvement Grant: Token + Branch Protection Checklist

**Date:** 2026-06-01

## Purpose

These are the human-gate steps that switch ON Alaska's ability to open pull requests against its own repo. They must be completed before the Phase 3 self-improver can open real PRs. Until then, the system degrades gracefully: the Phase 2 feedback collector continues logging feedback, and the Phase 3 self-improver logs `"PR disabled — token unset"` and skips without crashing. Do these steps once when you're ready to activate the loop.

---

## Section 1 — Create the Fine-Grained Personal Access Token (PAT)

**Why:** A fine-grained PAT scoped to one repo, with only the minimum permissions needed, means a compromised or runaway token cannot touch anything outside `alaska-openclaw`. It also cannot merge a PR that branch protection blocks — so even if Alaska opens a PR it cannot auto-approve or merge it.

- [ ] Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
- [ ] Set **Resource owner** to `heyabhinavhere`
- [ ] Set **Repository access** to **Only select repositories**, then select **`alaska-openclaw` ONLY** — not "All repositories"
- [ ] Under **Repository permissions**, set:
  - **Contents** = **Read and write**
  - **Pull requests** = **Read and write**
  - Everything else = **No access** (explicitly: no Administration, no Deployments, no Environments, no Secrets, no Workflows)
- [ ] Set expiry to **90 days** (or your preference — just set one)
- [ ] Add a calendar reminder to rotate the token before it expires
- [ ] Copy the token immediately (it won't be shown again)
- [ ] Go to **Railway → Alaska service → Variables** and add:
  ```
  GITHUB_SELF_IMPROVE_TOKEN=<paste token here>
  ```
  Never commit this value to the repo.

---

## Section 2 — Enable Branch Protection on `main`

**Why:** Branch protection with required Code Owner review gives `.github/CODEOWNERS` its teeth. Without it, CODEOWNERS is advisory only. The no-self-approval requirement stops Alaska from merging its own PRs even if the token somehow had admin rights.

- [ ] Go to **GitHub → `alaska-openclaw` → Settings → Branches**
- [ ] Create a rule targeting the branch name `main`. GitHub has two UIs — either works:
  - **Branch protection rules** (classic): click **Add branch protection rule**, branch name pattern `main`.
  - **Rulesets** (newer): click **Add branch ruleset**, target `main`, and set **Enforcement status** to **Active**.
- [ ] Enable **Require a pull request before merging** (this alone blocks direct pushes to `main` — every change must go through a PR)
- [ ] Set **Required approving reviews** to **≥ 1**
- [ ] Enable **Require review from Code Owners** (this is what ties `.github/CODEOWNERS` to enforcement — without it, CODEOWNERS is advisory only)
- [ ] Enable **Block force pushes** (defense in depth — the PR requirement above already blocks direct pushes, but this removes any ambiguity that history could be rewritten on `main` to sidestep review)
- [ ] Ensure **no bypass is granted to the token's identity** — this is what stops the bot from self-approving or force-merging:
  - Classic UI: tick **Do not allow bypassing the above settings**.
  - Ruleset UI: leave the **Bypass list** empty — do **not** add any actor (including `heyabhinavhere`, any app, or any PAT identity) to it.

---

## Section 3 — Verify CODEOWNERS Is Active

**Why:** Branch protection + CODEOWNERS working together is the actual control. Worth confirming before the self-improver goes live.

- [ ] Open a **throwaway test PR** (branch off `main`, touch any file under `migrations/`, e.g. add a comment line)
- [ ] Confirm GitHub **automatically requests review from `@heyabhinavhere`**
- [ ] Confirm the PR shows a **"Review required"** merge block (not mergeable until a Code Owner approves)
- [ ] **Close the PR and delete the test branch — do not merge it.** (If you do accidentally merge, it's harmless — just revert; but closing is cleaner.)

---

## Section 4 — Graceful Degradation (Context, Not an Action)

No action needed here. This section explains what happens before you do the steps above.

Until `GITHUB_SELF_IMPROVE_TOKEN` is set in Railway:
- The **Phase 2 feedback collector** runs normally and logs all improvement feedback to the database — no data is lost
- The **Phase 3 self-improver** checks for the token at startup; if absent, it logs `"PR disabled — token unset"` and exits cleanly without crashing or retrying in a loop
- No PRs are opened, no GitHub API calls are made

This means the system is safe to deploy before these steps are done. The grant is the switch that turns on PR-opening, not a prerequisite for anything else to work.
