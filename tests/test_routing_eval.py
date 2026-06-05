"""Routing eval — the machine-checkable definition of "correct routing" (OM-4).

The corpus `tests/fixtures/routing_eval.jsonl` has two layers:
  - `offline`: text the EXECUTOR receives → assert the deterministic resolution
    (parse_command + the ROUTES whitelist) lands on the expected verb or 'unknown'.
    This is what CI guards.
  - `live`: full Slack messages whose routing depends on the MODEL's recognition
    decision (does Alaska dispatch a `!`-command vs. answer as chat?). That can't
    be unit-tested — the on-box agent runs these and scores them from `command_audit`
    against the 4-part bar. Here we only assert the corpus is well-formed.

Run: python3 -m pytest tests/test_routing_eval.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from alaska_command_gateway.core import parse_command  # noqa: E402
from alaska_command_gateway.execute import ROUTES  # noqa: E402

CORPUS = REPO_ROOT / "tests" / "fixtures" / "routing_eval.jsonl"
_VALID_EXPECT = set(ROUTES) | {"unknown", "conversation"}


def _rows():
    out = []
    for line in CORPUS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _resolve(text: str) -> str:
    """The deterministic resolution the executor performs: parse → whitelist."""
    verb = parse_command(text).subcommand
    return verb if verb in ROUTES else "unknown"


def test_corpus_is_well_formed():
    rows = _rows()
    assert len(rows) >= 20  # a real corpus, not a stub
    for r in rows:
        assert r.get("layer") in ("offline", "live"), r
        assert r.get("text"), r
        assert r.get("expect") in _VALID_EXPECT, r


def test_offline_rows_resolve_deterministically():
    """Every offline row resolves to exactly its expected verb (or 'unknown')."""
    failures = []
    offline = [r for r in _rows() if r["layer"] == "offline"]
    assert offline, "the offline corpus must not be empty"
    for r in offline:
        got = _resolve(r["text"])
        if got != r["expect"]:
            failures.append("%r → %s (expected %s)" % (r["text"], got, r["expect"]))
    assert not failures, "deterministic routing mismatches:\n" + "\n".join(failures)


def test_live_conversation_rows_have_no_whitelisted_bang_verb():
    """Defense: a 'conversation' row must not begin with `!<whitelisted-verb>` — if it
    did, the corpus itself would be contradictory (it would actually be a command)."""
    for r in _rows():
        if r["layer"] == "live" and r["expect"] == "conversation":
            # strip a leading @mention the way the model would, then check the first token
            body = r["text"].split(None, 1)
            body = body[1] if body and body[0].lower().lstrip("@").startswith("alaska") else r["text"]
            first = (body.split() or [""])[0]
            if first.startswith("!"):
                assert first.lstrip("!/").lower() not in ROUTES, r
