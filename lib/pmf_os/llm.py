"""Single LLM integration point for PMF Cohort OS.

A thin Anthropic Messages API call over urllib (there is no LLM SDK in the image),
key-gated on ANTHROPIC_API_KEY. Shared by the CredGPT quality/safety judge (P4.1)
and the end-cohort narrator (P7). Both wrap it behind an injectable seam, so this
live path is only exercised on a real run — never in CI.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-4-6"


class LLMUnavailable(RuntimeError):
    """Raised when no ANTHROPIC_API_KEY is available for a live LLM call."""


def anthropic_complete(prompt: str, *, model: str | None = None, max_tokens: int = 1024, timeout: float = 60.0) -> str:
    """Single-turn completion → concatenated text content.

    Raises LLMUnavailable without a key, or the underlying error on transport/HTTP
    failure (callers record 'failed'/'skipped' rather than fabricating output).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMUnavailable("ANTHROPIC_API_KEY not set")
    body = json.dumps(
        {
            "model": model or os.environ.get("PMF_LLM_MODEL") or DEFAULT_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=body,
        method="POST",
        headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (trusted host)
        payload = json.loads(response.read())
    return "".join(
        block.get("text", "")
        for block in (payload.get("content") or [])
        if isinstance(block, dict) and block.get("type") == "text"
    )


def extract_json(text: str) -> dict[str, Any]:
    """Best-effort: parse a JSON object from an LLM text response."""
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}
