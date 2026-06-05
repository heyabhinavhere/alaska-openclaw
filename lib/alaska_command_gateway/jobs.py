"""Async command jobs — filesystem-JSON records + a worker that finishes work
off the Slack request path.

Per the platform decision, job status lives entirely on the /data volume as JSON
(no alaska.db / alaska_pmf.db writes):

    <base>/<job_id>.json    where <base> = $ALASKA_COMMAND_JOBS_DIR
                            or /data/workspace/command_jobs

Lifecycle: a slash command that can't answer in <3s is enqueued (status
"queued") by the receiver, which acks immediately. A worker then calls run_job():
it marks the job "running", invokes the command's finalizer, marks it
"done"/"error", and posts the final message to the command's response_url.

Finalizers are registered per command. P0 ships only the `audit` finalizer, and
it is a DRY RUN — it returns a "would run" message and performs NO live audit.
Live audit is wired to the bon-internal-audit skill in a later, approved PR.

    create_job(command, actor, channel, params, response_url=...) -> dict
    run_job(job_id, http_request=...) -> dict
    get_job(job_id) -> dict | None
    register_finalizer(command, fn) / FINALIZERS
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("alaska_command_gateway.jobs")

DEFAULT_BASE = "/data/workspace/command_jobs"

# command -> finalizer(job_dict) -> {"text": str, "response_type": "ephemeral"|"in_channel"}
Finalizer = Callable[[Dict[str, Any]], Dict[str, Any]]
FINALIZERS: Dict[str, Finalizer] = {}

# (method, url, *, headers, body, timeout) -> (status, bytes)
HttpRequest = Callable[..., Tuple[int, bytes]]


def jobs_base() -> str:
    return os.environ.get("ALASKA_COMMAND_JOBS_DIR", DEFAULT_BASE)


def register_finalizer(command: str, fn: Finalizer) -> None:
    FINALIZERS[command.lower()] = fn


def _now(now: Optional[str]) -> str:
    return now or datetime.now(timezone.utc).isoformat()


def _path(base: str, job_id: str) -> str:
    return os.path.join(base, "%s.json" % job_id)


def _write(base: str, job: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(base, exist_ok=True)
    path = _path(base, job["job_id"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(job, fh, indent=2, sort_keys=True)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return job


def create_job(
    command: str,
    actor: str,
    channel: str,
    params: Dict[str, Any],
    *,
    response_url: Optional[str] = None,
    response_type: str = "ephemeral",
    job_id: Optional[str] = None,
    base_dir: Optional[str] = None,
    now: Optional[str] = None,
) -> Dict[str, Any]:
    """Create and persist a queued job record. Returns the job dict."""
    base = base_dir or jobs_base()
    job = {
        "job_id": job_id or uuid.uuid4().hex[:12],
        "command": command,
        "actor": actor,
        "channel": channel,
        "params": params or {},
        "response_url": response_url,
        "response_type": response_type,
        "status": "queued",
        "result": None,
        "error": None,
        "created_at": _now(now),
        "updated_at": _now(now),
    }
    logger.info("job %s queued: command=%s actor=%s channel=%s",
                job["job_id"], command, actor, channel)
    return _write(base, job)


def get_job(job_id: str, *, base_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    path = _path(base_dir or jobs_base(), job_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def update_job(job_id: str, *, status: Optional[str] = None, result: Any = None,
               error: Optional[str] = None, base_dir: Optional[str] = None,
               now: Optional[str] = None) -> Optional[Dict[str, Any]]:
    base = base_dir or jobs_base()
    job = get_job(job_id, base_dir=base)
    if job is None:
        return None
    if status is not None:
        job["status"] = status
    if result is not None:
        job["result"] = result
    if error is not None:
        job["error"] = error
    job["updated_at"] = _now(now)
    return _write(base, job)


def _live_http_request(method: str, url: str, *, headers: Optional[dict] = None,
                       body: Optional[bytes] = None, timeout: float = 15.0) -> Tuple[int, bytes]:
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, exc.read()
        except Exception:
            return exc.code, b""
    except Exception as exc:
        return 0, str(exc).encode("utf-8", "replace")


def post_to_response_url(response_url: str, payload: Dict[str, Any], *,
                         http_request: Optional[HttpRequest] = None) -> Dict[str, Any]:
    """Best-effort POST of a Slack message payload to a slash command's
    response_url. Never raises. Returns {ok, status}."""
    http_request = http_request or _live_http_request
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    status, _ = http_request("POST", response_url, headers=headers, body=body, timeout=15.0)
    return {"ok": 200 <= status < 300, "status": status}


def run_job(job_id: str, *, http_request: Optional[HttpRequest] = None,
            base_dir: Optional[str] = None, now: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Execute a queued job's finalizer and deliver the result to response_url.

    Marks the job running -> done/error. A finalizer that raises is captured as
    a clean error and a friendly failure message is posted (the user is never
    left hanging). Returns the final job dict, or None if the job is missing.
    """
    base = base_dir or jobs_base()
    job = get_job(job_id, base_dir=base)
    if job is None:
        return None

    update_job(job_id, status="running", base_dir=base, now=now)
    finalizer = FINALIZERS.get(str(job.get("command", "")).lower())
    if finalizer is None:
        job = update_job(job_id, status="error", error="no_finalizer_for_command",
                         base_dir=base, now=now)
        _deliver(job, {"response_type": "ephemeral",
                       "text": "Sorry — I couldn't complete `%s` (no handler)." % job.get("command")},
                 http_request)
        return job

    try:
        outcome = finalizer(job)
        text = outcome.get("text", "Done.")
        rtype = outcome.get("response_type", job.get("response_type", "ephemeral"))
        job = update_job(job_id, status="done", result={"text": text, "response_type": rtype},
                         base_dir=base, now=now)
        _deliver(job, {"response_type": rtype, "text": text}, http_request)
    except Exception as exc:  # finalizer bug / data error — fail cleanly, tell the user
        logger.exception("job %s finalizer failed", job_id)
        job = update_job(job_id, status="error", error=str(exc), base_dir=base, now=now)
        _deliver(job, {"response_type": "ephemeral",
                       "text": "Sorry — `%s` failed while running. The team has been notified."
                       % job.get("command")},
                 http_request)
    return job


def _deliver(job: Optional[Dict[str, Any]], payload: Dict[str, Any],
             http_request: Optional[HttpRequest]) -> None:
    if not job:
        return
    response_url = job.get("response_url")
    if response_url:
        post_to_response_url(response_url, payload, http_request=http_request)
