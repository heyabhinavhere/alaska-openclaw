"""open_self_pr.py — open a PR on alaska-openclaw via the GitHub REST API.

The container has no git and no gh CLI, so self-improvement PRs are opened by
talking to the GitHub REST API directly over HTTPS with urllib. This helper
creates a branch off main, commits file changes to it, and opens a PR. It never
merges — a human reviews and merges every PR.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request

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
    except urllib.error.URLError as e:
        raise SelfPRError(f"{method} {path} -> network error: {e.reason}")


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
