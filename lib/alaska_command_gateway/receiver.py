"""Slack slash-command receiver — the verify -> parse -> 3s-ack -> enqueue path.

`handle_slash_command()` is the runtime-agnostic core: it takes a raw HTTP body
+ headers and returns the status, the immediate Slack response body, and any
async job that was created. It NEVER runs long work inline, so the Slack 3-second
ack is always met. It is fully unit-testable with no socket.

A reference HTTP server (stdlib http.server) wraps that core so the flow can be
run locally and end-to-end tested. **It is NOT started by entrypoint.sh in P0** —
turning `/alaska` on in production is a separate, approved wiring step (the live
transport — Socket Mode bridge vs an OpenClaw /hooks mapping vs Events API — is
chosen with the owner after verifying OpenClaw's capabilities). See
docs/platform/command-gateway.md.

Security posture (fail closed):
  * a signing secret is required to process a request (unless the caller
    explicitly opts out for local dry-run via enforce_signature=False);
  * bad signature -> 401, stale timestamp -> 401, disallowed team -> 403;
  * rejects are logged with reason + safe fields only (never the raw body,
    never the signature).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, Optional, Sequence
from urllib.parse import parse_qs

from . import jobs
from .core import GATEWAY_VERSION, dispatch_ack, parse_command
from .verify import team_allowed, verify_slack_signature

logger = logging.getLogger("alaska_command_gateway.receiver")

SIG_HEADER = "x-slack-signature"
TS_HEADER = "x-slack-request-timestamp"


def parse_form(raw_body: str) -> Dict[str, str]:
    if isinstance(raw_body, bytes):
        raw_body = raw_body.decode("utf-8", "replace")
    return {k: v[0] for k, v in parse_qs(raw_body, keep_blank_values=True).items()}


def _header(headers: Dict[str, str], name: str) -> str:
    for k, v in (headers or {}).items():
        if k.lower() == name:
            return v
    return ""


def build_context(form: Dict[str, str]) -> Dict[str, Any]:
    return {
        "command": form.get("command", ""),
        "text": form.get("text", ""),
        "user_id": form.get("user_id", ""),
        "channel_id": form.get("channel_id", ""),
        "response_url": form.get("response_url", ""),
        "team_id": form.get("team_id", ""),
        "version": GATEWAY_VERSION,
    }


def _reject(status: int, reason: str, message: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    logger.warning("rejected slash command: reason=%s team=%s user=%s command=%s",
                   reason, ctx.get("team_id", ""), ctx.get("user_id", ""), ctx.get("command", ""))
    return {"status": status, "body": {"response_type": "ephemeral", "text": message},
            "job": None, "ok": False, "reject_reason": reason}


def handle_slash_command(
    raw_body: str,
    headers: Dict[str, str],
    *,
    signing_secret: Optional[str] = None,
    allowed_teams: Optional[Sequence[str]] = None,
    enforce_signature: bool = True,
    now: Optional[float] = None,
    base_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify + route a Slack slash command. Returns
    {status, body, job, ok, reject_reason}. Does NOT run long work inline."""
    form = parse_form(raw_body)
    ctx = build_context(form)

    if enforce_signature:
        secret = signing_secret if signing_secret is not None else os.environ.get("SLACK_SIGNING_SECRET")
        if not secret:
            return _reject(500, "no_signing_secret",
                           "Gateway is not configured to verify requests.", ctx)
        ok = verify_slack_signature(
            secret, _header(headers, TS_HEADER), raw_body, _header(headers, SIG_HEADER), now=now)
        if not ok:
            return _reject(401, "bad_signature", "Invalid request signature.", ctx)

    if not team_allowed(ctx.get("team_id"), allowed_teams):
        return _reject(403, "team_not_allowed", "This workspace is not allowed to use Alaska.", ctx)

    parsed = parse_command(ctx.get("text"))
    ack = dict(dispatch_ack(parsed, ctx))
    async_spec = ack.pop("async", None)   # strip internal key from the Slack-facing body

    job = None
    if async_spec:
        job = jobs.create_job(
            command=async_spec.get("command", parsed.subcommand),
            actor=ctx.get("user_id", ""),
            channel=ctx.get("channel_id", ""),
            params=async_spec.get("params", {}),
            response_url=ctx.get("response_url") or None,
            response_type=ack.get("response_type", "ephemeral"),
            base_dir=base_dir,
        )

    return {"status": 200, "body": ack, "job": job, "ok": True, "reject_reason": None}


# --------------------------------------------------------------------------
# reference HTTP server (NOT started by entrypoint in P0)
# --------------------------------------------------------------------------

def _make_handler_class(signing_secret: Optional[str], allowed_teams: Optional[Sequence[str]],
                        enforce_signature: bool, base_dir: Optional[str]):
    from http.server import BaseHTTPRequestHandler

    class SlackCommandHandler(BaseHTTPRequestHandler):
        server_version = "AlaskaCommandGateway/%s" % GATEWAY_VERSION

        def log_message(self, *args):  # quiet default logging
            return

        def _send(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802 (stdlib name)
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
            headers = {k: v for k, v in self.headers.items()}
            result = handle_slash_command(
                raw, headers, signing_secret=signing_secret, allowed_teams=allowed_teams,
                enforce_signature=enforce_signature, base_dir=base_dir)
            self._send(result["status"], result["body"])
            # Finish async work off the response path.
            job = result.get("job")
            if result["ok"] and job:
                threading.Thread(target=jobs.run_job, args=(job["job_id"],),
                                 kwargs={"base_dir": base_dir}, daemon=True).start()

    return SlackCommandHandler


def make_server(port: int = 18790, *, signing_secret: Optional[str] = None,
                allowed_teams: Optional[Sequence[str]] = None,
                enforce_signature: bool = True, base_dir: Optional[str] = None):
    """Build (but do not start) an http.server.HTTPServer for the gateway.
    Returns the server; caller invokes serve_forever()."""
    from http.server import HTTPServer
    handler = _make_handler_class(signing_secret, allowed_teams, enforce_signature, base_dir)
    return HTTPServer(("0.0.0.0", port), handler)


def _main() -> int:
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("ALASKA_GATEWAY_PORT", "18790"))
    secret = os.environ.get("SLACK_SIGNING_SECRET")
    if not secret:
        logger.error("SLACK_SIGNING_SECRET is required to run the reference receiver.")
        return 1
    logger.info("Alaska command gateway (reference receiver) listening on :%d", port)
    make_server(port, signing_secret=secret).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
