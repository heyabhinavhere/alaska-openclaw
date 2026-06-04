"""Customer.io execution adapter for PMF interventions (P6).

The store owns the safety state machine: an intervention is only ever sent after a
human approval AND a pass through `customerio_guard.validate_customerio_action`
(dry-run + audience + suppression present, SMS blocked). This module is just the
injectable *executor seam* the store calls once those gates pass, plus a thin,
best-effort live adapter against the Customer.io App transactional API.

Nothing here sends on its own: tests inject a fake executor, and the live adapter
is only wired when the operator explicitly asks for it (CLI `--execute-live`) with
`CUSTOMERIO_APP_API_KEY` present. Mirrors the slack_delivery / judge injectable
pattern — the live API surface is a deploy-time concern, not a build dependency.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Callable

# Customer.io App API transactional send (per-user email). Push/in-app use
# different surfaces and are intentionally not auto-sent by the live adapter yet.
CIO_TRANSACTIONAL_EMAIL_URL = "https://api.customer.io/v1/send/email"

# (guard action dict) -> result dict, e.g. {"customerio_ref": ..., "status": 200}
CioExecutor = Callable[[dict[str, Any]], dict[str, Any]]

# (method, url, body) -> (status_code, response_bytes)
HttpPost = Callable[..., "tuple[int, bytes]"]


class CustomerIoAuthError(RuntimeError):
    """Raised when the Customer.io app API key is missing for a live send."""


def _app_api_key() -> str:
    key = os.environ.get("CUSTOMERIO_APP_API_KEY")
    if not key:
        raise CustomerIoAuthError("CUSTOMERIO_APP_API_KEY must be set for live Customer.io execution")
    return key


def _live_http_post(url: str, body: bytes, *, token: str, timeout: float = 30.0) -> "tuple[int, bytes]":
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (trusted host)
        return response.status, response.read()


def make_live_executor(*, http_post: HttpPost | None = None, token: str | None = None) -> CioExecutor:
    """Build the live executor the CLI passes to the store on an explicit send.

    Sends an approved, guard-validated intervention via the CIO transactional email
    API. Raises on a non-2xx / transport error so the store records the intervention
    as 'failed' rather than a false 'executed'. Push/other channels raise until a
    live path for them is wired + validated.
    """
    http_post = http_post or _live_http_post

    def _execute(action: dict[str, Any]) -> dict[str, Any]:
        channel = action.get("channel")
        if channel != "email":
            raise NotImplementedError(f"live Customer.io executor supports email only; got channel={channel!r}")
        api_key = token or _app_api_key()
        draft = action.get("draft") or {}
        payload = {
            "to": draft.get("to") or draft.get("email"),
            "transactional_message_id": draft.get("transactional_message_id") or draft.get("template_id"),
            "message_data": draft.get("message_data") or {},
            "identifiers": draft.get("identifiers")
            or ({"id": draft.get("customer_id")} if draft.get("customer_id") else {}),
        }
        status, raw = http_post(CIO_TRANSACTIONAL_EMAIL_URL, json.dumps(payload).encode("utf-8"), token=api_key)
        try:
            data = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError, TypeError):
            data = {}
        if not 200 <= status < 300:
            raise RuntimeError(f"Customer.io send failed: status {status} {data.get('meta') or data}")
        return {"customerio_ref": data.get("delivery_id") or data.get("id"), "status": status}

    return _execute
