"""Slack delivery for PMF Cohort OS daily runs.

Posts the daily cohort summary to a Slack channel and (best-effort) uploads the
HTML cockpit as a file. HTTP is injectable (`http_request`) so the orchestrator
is fixture-tested with no live Slack calls; the live default uses urllib + a bot
token from `SLACK_BOT_TOKEN`. Mirrors the collectors' injectable-fetcher pattern.

The cockpit upload uses Slack's external-upload flow (getUploadURLExternal -> PUT
bytes -> completeUploadExternal). Delivery is best-effort: a failed upload never
blocks the summary, and the orchestrator captures any failure rather than raising.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
SLACK_GET_UPLOAD_URL = "https://slack.com/api/files.getUploadURLExternal"
SLACK_COMPLETE_UPLOAD_URL = "https://slack.com/api/files.completeUploadExternal"

# (method, url, *, headers, body) -> (status_code, response_bytes)
HttpRequest = Callable[..., "tuple[int, bytes]"]
# (channel, summary_text, html_path|None) -> delivery result dict
SlackSender = Callable[[str, str, "str | None"], "dict[str, Any]"]


class SlackAuthError(RuntimeError):
    """Raised when the Slack bot token is missing for a live send."""


def _bot_token() -> str:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise SlackAuthError("SLACK_BOT_TOKEN must be set for live Slack delivery")
    return token


def _live_http_request(method: str, url: str, *, headers: dict | None = None, body: bytes | None = None, timeout: float = 30.0) -> "tuple[int, bytes]":
    request = urllib.request.Request(url, method=method, data=body, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (trusted host)
        return response.status, response.read()


def _parse(raw: bytes) -> dict[str, Any]:
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def _api_json(url: str, payload: dict[str, Any], *, token: str, http_request: HttpRequest) -> "tuple[int, dict[str, Any]]":
    body = json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    status, raw = http_request("POST", url, headers=headers, body=body)
    return status, _parse(raw)


def _api_form(url: str, fields: dict[str, str], *, token: str, http_request: HttpRequest) -> "tuple[int, dict[str, Any]]":
    body = urllib.parse.urlencode(fields).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"}
    status, raw = http_request("POST", url, headers=headers, body=body)
    return status, _parse(raw)


def post_summary(channel: str, text: str, *, token: str | None = None, http_request: HttpRequest | None = None, thread_ts: str | None = None) -> dict[str, Any]:
    """Post a text summary via chat.postMessage. Returns {ok, ts, status, error}."""
    http_request = http_request or _live_http_request
    token = token or _bot_token()
    payload: dict[str, Any] = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    status, data = _api_json(SLACK_POST_MESSAGE_URL, payload, token=token, http_request=http_request)
    return {"ok": bool(data.get("ok")), "ts": data.get("ts"), "status": status, "error": data.get("error")}


def upload_file(channel: str, path: str, title: str, *, initial_comment: str | None = None, token: str | None = None, http_request: HttpRequest | None = None) -> dict[str, Any]:
    """Upload the cockpit file via Slack's external-upload flow. Best-effort."""
    http_request = http_request or _live_http_request
    token = token or _bot_token()
    file_path = Path(path)
    if not file_path.exists():
        return {"ok": False, "step": "read", "error": "file_missing", "path": str(file_path)}
    content = file_path.read_bytes()
    status1, info = _api_form(SLACK_GET_UPLOAD_URL, {"filename": file_path.name, "length": str(len(content))}, token=token, http_request=http_request)
    if not info.get("ok"):
        return {"ok": False, "step": "get_upload_url", "status": status1, "error": info.get("error")}
    upload_url, file_id = info.get("upload_url"), info.get("file_id")
    status2, _ = http_request("POST", upload_url, headers={"Content-Type": "application/octet-stream"}, body=content)
    if not 200 <= status2 < 300:
        return {"ok": False, "step": "upload", "status": status2, "file_id": file_id}
    payload: dict[str, Any] = {"files": [{"id": file_id, "title": title}], "channel_id": channel}
    if initial_comment:
        payload["initial_comment"] = initial_comment
    status3, done = _api_json(SLACK_COMPLETE_UPLOAD_URL, payload, token=token, http_request=http_request)
    return {"ok": bool(done.get("ok")), "step": "complete", "status": status3, "file_id": file_id, "error": done.get("error")}


def deliver(channel: str, summary_text: str, html_path: str | None = None, *, token: str | None = None, http_request: HttpRequest | None = None) -> dict[str, Any]:
    """High-level delivery: post the summary, then best-effort upload the cockpit.

    Never raises — returns a structured result the orchestrator records. The
    cockpit upload is threaded under the summary message when both succeed.
    """
    token = token or _bot_token()
    result: dict[str, Any] = {"summary": None, "file": None, "ok": False}
    summary = post_summary(channel, summary_text, token=token, http_request=http_request)
    result["summary"] = summary
    result["ok"] = bool(summary.get("ok"))
    if html_path:
        result["file"] = upload_file(
            channel, html_path, "PMF cohort cockpit",
            initial_comment="📎 PMF daily cockpit (full detail) — download this HTML and open it in a browser to view it; Slack won't render it inline.",
            token=token, http_request=http_request,
        )
    return result


def make_live_sender(*, token: str | None = None) -> SlackSender:
    """Build the live (channel, summary, html_path) sender the CLI passes to the
    orchestrator. Token resolves from SLACK_BOT_TOKEN at call time if not given."""
    def _send(channel: str, summary_text: str, html_path: str | None) -> dict[str, Any]:
        return deliver(channel, summary_text, html_path, token=token)
    return _send
