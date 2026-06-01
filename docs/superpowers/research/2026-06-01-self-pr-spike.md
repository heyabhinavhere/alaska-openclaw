# Self-PR-from-container spike — findings

**Date:** 2026-06-01
**Phase / task:** Self-improvement loop, Phase 0, Task 0.2
**Helper under test:** `lib/open_self_pr.py`
**Verdict:** ✅ PASS — Alaska can open a PR on its own repo from the container, using only the Python stdlib.

## Why this spike existed

The container Alaska runs in (OpenClaw on Railway) ships with only `curl`, `python3`,
and `sqlite3` — **no `git`, no `gh` CLI**. The entire self-improvement loop is moot if
the agent cannot open a pull request from that environment. This spike de-risks that
single unknown before any further work: prove a PR can be opened via the GitHub REST
API over HTTPS with `urllib` alone.

## What was run

A throwaway PR was opened by calling `lib.open_self_pr.open_pr(...)` directly, with the
token sourced from the local `gh` CLI (`gh auth token`, authed as `heyabhinavhere`) and
exported as `GITHUB_SELF_IMPROVE_TOKEN` for the single invocation. One new file was
created on a fresh branch:

- **Branch:** `self-improve-spike-20260601-114739`
- **File:** `docs/superpowers/research/_spike.md` (a new file — exercises the `sha=None` path)
- **PR:** [#44](https://github.com/heyabhinavhere/alaska-openclaw/pull/44)

## Result

| Check | Outcome |
|-------|---------|
| `open_pr` returned a PR URL | ✅ `https://github.com/heyabhinavhere/alaska-openclaw/pull/44` |
| PR existed on GitHub (independent `gh` verify) | ✅ state `OPEN`, base `main`, head `self-improve-spike-20260601-114739` |
| PR contained exactly the intended file | ✅ only `docs/superpowers/research/_spike.md` |
| New branch ref created on remote | ✅ `refs/heads/self-improve-spike-20260601-114739 @ 59a4d06` |
| PR was `MERGEABLE` (clean, no conflicts) | ✅ |
| Cleanup: PR closed | ✅ state `CLOSED` |
| Cleanup: branch deleted | ✅ ref now returns HTTP 404 |

No stray external state remains — the PR is closed and the branch is gone.

## What this confirms

1. **The REST mechanics work end-to-end** with stdlib `urllib` only: get base SHA →
   create branch ref → PUT file contents (base64) → open PR. No `git`, no `gh`, no
   third-party packages.
2. **The new-file path works** (the contents `GET` 404s, `sha` stays `None`, the `PUT`
   omits `sha`). This is the path real self-improvement PRs will most often hit, and it
   is now also covered by `test_open_pr_new_file_omits_sha`.
3. **`open_pr` never merges** — it only opens. Closing/merging is a separate, human step.

## Caveats / notes for production

- **Token used here ≠ production token.** This spike used the local `gh` user token,
  which *can* merge/push. The production credential must be the narrow, fine-grained PAT
  (`GITHUB_SELF_IMPROVE_TOKEN` on Railway): Contents r/w + PRs r/w, **no admin/merge**,
  scoped to `alaska-openclaw` only. That "the token truly cannot merge" property is
  validated in Phase 1's grant step, not here.
- **Graceful degradation confirmed by unit tests:** if `GITHUB_SELF_IMPROVE_TOKEN` is
  unset, `open_pr` raises `SelfPRError` rather than crashing — so the loop simply
  no-ops on environments without the token.
- **Network failures now surface cleanly:** `_req` wraps both `HTTPError` and `URLError`
  in `SelfPRError`, so a DNS/timeout/SSL failure in the container yields a diagnosable
  error instead of a raw traceback.
- **Non-atomic multi-file PRs:** files are PUT sequentially; a mid-sequence failure
  leaves a partial branch. Acceptable because a human reviews every PR before merge, and
  self-improvement PRs are expected to touch one skill file at a time.
