"""audit_slack — concise internal summary + Slack post + file upload.

Vendored and thin (no import of V5 lib/pmf_os/slack_delivery). Reuses only the
knowledge of Slack's APIs: chat.postMessage and the 3-step external upload
(files.getUploadURLExternal -> PUT bytes -> files.completeUploadExternal).

Delivery is internal-only: the audit posts back to whoever invoked /audit. It
NEVER messages the end user and NEVER touches Customer.io / SMS. The summary is
built from persona + the lead opportunity only, so no raw PII leaves the report.
"""
from __future__ import annotations

import json
import os
from typing import Callable, Optional
from urllib.parse import urlencode

POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
GET_UPLOAD_URL = "https://slack.com/api/files.getUploadURLExternal"
COMPLETE_UPLOAD_URL = "https://slack.com/api/files.completeUploadExternal"


class SlackAuthError(Exception):
    pass


def build_summary(audit: dict) -> str:
    """Concise, PII-free Slack line. Format mirrors the skill's example:
    'Audit complete for user 1414. Pattern: <persona>. Lead opportunity:
     <type>, ~$X/year, confidence <level>. Report attached.'"""
    meta = audit.get("audit_meta", {}) or {}
    user = audit.get("user", {}) or {}
    opps = audit.get("opportunities", []) or []
    uid = meta.get("user_id", "?")
    persona = user.get("persona_pattern", "unknown")
    if opps:
        lead = opps[0]
        cm = lead.get("confidence_multiplier", 0)
        level = "high" if cm >= 1.0 else ("medium" if cm >= 0.7 else "low")
        yearly = int(round(lead.get("yearly_savings", 0)))
        return ("Audit complete for user %s. Pattern: %s. Lead opportunity: %s, "
                "~$%s/year, confidence %s. Report attached."
                % (uid, persona, lead.get("type"), yearly, level))
    return ("Audit complete for user %s. Pattern: %s. No ranked opportunity found. "
            "Report attached." % (uid, persona))


def _bot_token(token: Optional[str]) -> str:
    token = token if token is not None else os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise SlackAuthError("SLACK_BOT_TOKEN is not set")
    return token


def _live_http(method, url, headers=None, body=None, timeout=30):
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b""
    except Exception as e:
        return 0, str(e).encode("utf-8", "replace")


def _json(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def post_message(channel: str, text: str, *, token: Optional[str] = None,
                 http_request: Optional[Callable] = None, thread_ts: Optional[str] = None,
                 timeout: int = 30) -> dict:
    token = _bot_token(token)
    http_request = http_request or _live_http
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    headers = {"Authorization": "Bearer " + token,
               "Content-Type": "application/json; charset=utf-8"}
    status, raw = http_request("POST", POST_MESSAGE_URL, headers, json.dumps(payload).encode(), timeout)
    data = _json(raw)
    return {"ok": bool(data.get("ok")), "status": status, "ts": data.get("ts"),
            "error": data.get("error")}


def upload_file(channel: str, path: str, title: str, *, initial_comment: Optional[str] = None,
                token: Optional[str] = None, http_request: Optional[Callable] = None,
                thread_ts: Optional[str] = None, timeout: int = 60) -> dict:
    token = _bot_token(token)
    http_request = http_request or _live_http
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError as e:
        return {"ok": False, "step": "read", "error": str(e)}

    auth = {"Authorization": "Bearer " + token}

    # Step 1: reserve an upload URL.
    form = {"Authorization": "Bearer " + token,
            "Content-Type": "application/x-www-form-urlencoded"}
    body1 = urlencode({"filename": os.path.basename(path), "length": len(blob)}).encode()
    s1, r1 = http_request("POST", GET_UPLOAD_URL, form, body1, timeout)
    d1 = _json(r1)
    if not d1.get("ok"):
        return {"ok": False, "step": "get_upload_url", "status": s1, "error": d1.get("error")}

    # Step 2: PUT the bytes to the issued URL.
    s2, _ = http_request("POST", d1["upload_url"], auth, blob, timeout)
    if not (200 <= s2 < 300):
        return {"ok": False, "step": "upload", "status": s2, "file_id": d1.get("file_id")}

    # Step 3: complete the upload (this is what shares it into the channel).
    files_payload = {"files": [{"id": d1["file_id"], "title": title}], "channel_id": channel}
    if initial_comment:
        files_payload["initial_comment"] = initial_comment
    if thread_ts:
        files_payload["thread_ts"] = thread_ts
    headers_json = {"Authorization": "Bearer " + token,
                    "Content-Type": "application/json; charset=utf-8"}
    s3, r3 = http_request("POST", COMPLETE_UPLOAD_URL, headers_json, json.dumps(files_payload).encode(), timeout)
    d3 = _json(r3)
    if not d3.get("ok"):
        return {"ok": False, "step": "complete", "status": s3,
                "error": d3.get("error"), "file_id": d1.get("file_id")}
    return {"ok": True, "step": "complete", "file_id": d1.get("file_id")}


def deliver(channel: str, summary_text: str, docx_path: str, *, token: Optional[str] = None,
            http_request: Optional[Callable] = None, thread_ts: Optional[str] = None) -> dict:
    """Post the summary, then upload the report. Best-effort: a failed upload is
    reported but never raises and never touches the on-disk artifact, so the
    report is preserved for a retry."""
    summary = post_message(channel, summary_text, token=token,
                           http_request=http_request, thread_ts=thread_ts)
    file_res = upload_file(channel, docx_path, "Internal Audit Report",
                           token=token, http_request=http_request, thread_ts=thread_ts)
    return {"ok": bool(summary.get("ok") and file_res.get("ok")),
            "summary": summary, "file": file_res}
