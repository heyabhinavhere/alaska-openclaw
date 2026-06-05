"""Slack file delivery for artifacts — stdlib only, injectable transport.

A generic, reusable re-implementation of Slack's external-upload flow
(files.getUploadURLExternal -> PUT bytes -> files.completeUploadExternal). It is
Alaska-owned: it does NOT import lib/pmf_os/slack_delivery (V5) or the audit
skill's audit_slack — it just reuses knowledge of the public Slack API, exactly
as those modules independently do.

`http_request` is injectable so tests run with a fake transport and never touch
the network. Signature:  (method, url, *, headers, body, timeout) -> (status, bytes)

Delivery is best-effort: a failure is reported in the return dict but NEVER
raises and NEVER deletes the on-disk artifact, so a retry can re-send the same
file.

    upload_artifact_to_slack(path, channel_id, thread_ts=None, ...) -> dict
    post_message(channel_id, text, ...) -> dict
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlencode

POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
GET_UPLOAD_URL = "https://slack.com/api/files.getUploadURLExternal"
COMPLETE_UPLOAD_URL = "https://slack.com/api/files.completeUploadExternal"

# (method, url, *, headers, body, timeout) -> (status_code, response_bytes)
HttpRequest = Callable[..., Tuple[int, bytes]]


class SlackAuthError(RuntimeError):
    """Raised only on the live path when SLACK_BOT_TOKEN is absent."""


def _bot_token(token: Optional[str]) -> str:
    token = token if token is not None else os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise SlackAuthError("SLACK_BOT_TOKEN must be set for live Slack delivery")
    return token


def _live_http_request(method: str, url: str, *, headers: Optional[dict] = None,
                       body: Optional[bytes] = None, timeout: float = 60.0) -> Tuple[int, bytes]:
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted host)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, exc.read()
        except Exception:
            return exc.code, b""
    except Exception as exc:  # network down, DNS, timeout — surface, don't crash
        return 0, str(exc).encode("utf-8", "replace")


def _parse(raw: bytes) -> Dict[str, Any]:
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def post_message(channel_id: str, text: str, *, token: Optional[str] = None,
                 thread_ts: Optional[str] = None, http_request: Optional[HttpRequest] = None,
                 timeout: float = 30.0) -> Dict[str, Any]:
    """Post a text message via chat.postMessage. Returns {ok, ts, status, error}."""
    http_request = http_request or _live_http_request
    token = _bot_token(token)
    payload: Dict[str, Any] = {"channel": channel_id, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    headers = {"Authorization": "Bearer " + token,
               "Content-Type": "application/json; charset=utf-8"}
    status, raw = http_request("POST", POST_MESSAGE_URL, headers=headers,
                               body=json.dumps(payload).encode("utf-8"), timeout=timeout)
    data = _parse(raw)
    return {"ok": bool(data.get("ok")), "ts": data.get("ts"), "status": status, "error": data.get("error")}


def upload_artifact_to_slack(
    path: str,
    channel_id: str,
    *,
    thread_ts: Optional[str] = None,
    title: Optional[str] = None,
    initial_comment: Optional[str] = None,
    token: Optional[str] = None,
    http_request: Optional[HttpRequest] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Upload `path` to a Slack channel via the 3-step external-upload flow.

    Best-effort: returns a structured result and never raises / never deletes
    the file. Result keys: {ok, step, file_id?, status?, error?}.
    """
    http_request = http_request or _live_http_request
    try:
        token = _bot_token(token)
    except SlackAuthError as exc:
        return {"ok": False, "step": "auth", "error": str(exc)}

    if not os.path.exists(path):
        return {"ok": False, "step": "read", "error": "file_missing", "path": path}
    with open(path, "rb") as fh:
        blob = fh.read()
    if not blob:
        return {"ok": False, "step": "read", "error": "file_empty", "path": path}

    title = title or os.path.basename(path)

    # Step 1 — reserve an upload URL.
    form_headers = {"Authorization": "Bearer " + token,
                    "Content-Type": "application/x-www-form-urlencoded"}
    body1 = urlencode({"filename": os.path.basename(path), "length": len(blob)}).encode("utf-8")
    s1, r1 = http_request("POST", GET_UPLOAD_URL, headers=form_headers, body=body1, timeout=timeout)
    d1 = _parse(r1)
    if not d1.get("ok"):
        return {"ok": False, "step": "get_upload_url", "status": s1, "error": d1.get("error")}
    upload_url, file_id = d1.get("upload_url"), d1.get("file_id")

    # Step 2 — PUT the bytes to the issued URL.
    s2, _ = http_request("POST", upload_url,
                         headers={"Authorization": "Bearer " + token,
                                  "Content-Type": "application/octet-stream"},
                         body=blob, timeout=timeout)
    if not 200 <= s2 < 300:
        return {"ok": False, "step": "upload", "status": s2, "file_id": file_id}

    # Step 3 — complete the upload (this shares it into the channel/thread).
    payload: Dict[str, Any] = {"files": [{"id": file_id, "title": title}], "channel_id": channel_id}
    if initial_comment:
        payload["initial_comment"] = initial_comment
    if thread_ts:
        payload["thread_ts"] = thread_ts
    json_headers = {"Authorization": "Bearer " + token,
                    "Content-Type": "application/json; charset=utf-8"}
    s3, r3 = http_request("POST", COMPLETE_UPLOAD_URL, headers=json_headers,
                          body=json.dumps(payload).encode("utf-8"), timeout=timeout)
    d3 = _parse(r3)
    return {"ok": bool(d3.get("ok")), "step": "complete", "status": s3,
            "file_id": file_id, "error": d3.get("error")}
