"""Socket-Mode executor for /alaska — test suite (deterministic, no network).

Covers the live routing table: help/ping text, unknown + arg validation, the
`user` happy path with an injected generator (asserting channel + authority are
threaded through), lookup-error surfaces, generated-but-not-delivered, the
coming-soon stubs, authority mapping, and handler crash-proofing.

Run: python3 -m pytest tests/test_command_execute.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

from alaska_command_gateway import execute as E  # noqa: E402


def _ctx(**over):
    base = dict(invoker="U07GKLVA9FE", channel="C0ANKDD664A", channel_type="channel")
    base.update(over)
    return E.build_context(**base)


# --------------------------------------------------------------------------
# authority mapping (log-only; never gates)
# --------------------------------------------------------------------------

def test_authority_for_known_and_unknown():
    assert E.authority_for("U07GKLVA9FE") == "admin"
    assert E.authority_for("U0APEUXD9DH") == "founder"
    assert E.authority_for("U0AQFJV9B32") == "engineer"
    assert E.authority_for("Uxxxxx") == "unknown"
    assert E.authority_for(None) == "unknown"


def test_build_context_derives_authority():
    ctx = E.build_context(invoker="U07GKLVA9FE", channel="C1")
    assert ctx["authority"] == "admin" and ctx["channel"] == "C1"
    # explicit override wins
    assert E.build_context(invoker="U07GKLVA9FE", authority="system")["authority"] == "system"


# --------------------------------------------------------------------------
# help / ping / unknown
# --------------------------------------------------------------------------

def test_help_lists_every_route():
    res = E.route("help", _ctx())
    assert res["ok"] is True
    for name in ("help", "ping", "user", "audit", "brief", "pmf"):
        assert ("/alaska %s" % name) in res["text"]


def test_empty_text_defaults_to_help():
    assert E.route("", _ctx())["ok"] is True
    assert "/alaska user" in E.route(None, _ctx())["text"]


def test_ping():
    assert "pong" in E.route("ping", _ctx())["text"]


def test_unknown_subcommand_is_friendly_not_crash():
    res = E.route("frobnicate now", _ctx())
    assert res["ok"] is False and res["status"] == "unknown_subcommand"
    assert "Unknown command" in res["text"] and "`user`" in res["text"]


# --------------------------------------------------------------------------
# user — arg validation
# --------------------------------------------------------------------------

def test_user_missing_arg_shows_usage():
    res = E.route("user", _ctx())
    assert res["ok"] is False and "Usage" in res["text"]


def test_user_nondigit_id_rejected():
    res = E.route("user maria", _ctx())
    assert res["ok"] is False and "doesn't look like" in res["text"]


# --------------------------------------------------------------------------
# user — happy path with an injected generator
# --------------------------------------------------------------------------

def test_user_happy_path_threads_channel_and_authority():
    captured = {}

    def fake_generate(user_id, invoker, **kw):
        captured["user_id"] = user_id
        captured["invoker"] = invoker
        captured["kw"] = kw
        return {"ok": True, "status": "ok", "user_id": int(user_id),
                "artifact_id": "user-casefile/2762/x.docx", "delivered": True,
                "served_stale": False}

    res = E.route("user 2762", _ctx(generate_fn=fake_generate))
    assert res["ok"] is True and res["delivered"] is True
    assert "posted above" in res["text"] and "#2762" in res["text"]
    # The generator was called with THIS channel + the invoker's mapped authority.
    assert captured["user_id"] == "2762" and captured["invoker"] == "U07GKLVA9FE"
    assert captured["kw"]["channel_id"] == "C0ANKDD664A"
    assert captured["kw"]["channel_type"] == "channel"
    assert captured["kw"]["requester_authority"] == "admin"
    assert captured["kw"]["deliver"] is True


def test_user_threads_thread_ts_when_present():
    captured = {}

    def fake(user_id, invoker, **kw):
        captured.update(kw)
        return {"ok": True, "status": "ok", "user_id": 2762, "delivered": True}
    E.route("user 2762", _ctx(thread_ts="1779042600.001200", generate_fn=fake))
    assert captured["thread_ts"] == "1779042600.001200"


def test_user_stale_cache_is_flagged_in_reply():
    def fake(user_id, invoker, **kw):
        return {"ok": True, "status": "ok", "user_id": 2762, "delivered": True, "served_stale": True}
    res = E.route("user 2762", _ctx(generate_fn=fake))
    assert res["ok"] is True and "stale cache" in res["text"]


def test_user_not_found_is_friendly():
    def fake(user_id, invoker, **kw):
        return {"ok": False, "status": "not_found", "user_id": 404, "message": "No user matches 404."}
    res = E.route("user 404", _ctx(generate_fn=fake))
    assert res["ok"] is False and "No BON user matches" in res["text"]


def test_user_multiple_matches_is_friendly():
    def fake(user_id, invoker, **kw):
        return {"ok": False, "status": "multiple", "message": "3 users match.", "matches": [1, 2, 3]}
    res = E.route("user 12", _ctx(generate_fn=fake))
    assert res["ok"] is False and "More than one user" in res["text"]


def test_user_generated_but_delivery_failed_warns():
    def fake(user_id, invoker, **kw):
        return {"ok": True, "status": "ok", "user_id": 2762, "delivered": False,
                "artifact_id": "user-casefile/2762/x.docx",
                "slack": {"ok": False, "error": "channel_not_found"}}
    res = E.route("user 2762", _ctx(generate_fn=fake))
    assert res["ok"] is False and "couldn't post" in res["text"] and "channel_not_found" in res["text"]


def test_user_no_channel_skips_delivery():
    seen = {}

    def fake(user_id, invoker, **kw):
        seen["deliver"] = kw["deliver"]  # no channel -> generator told not to deliver
        return {"ok": True, "status": "ok", "user_id": 2762, "delivered": False}
    res = E.route("user 2762", E.build_context(invoker="U07GKLVA9FE", channel=None, generate_fn=fake))
    assert seen["deliver"] is False
    assert res["ok"] is True and "generated" in res["text"]


# --------------------------------------------------------------------------
# coming-soon stubs never execute, never 500
# --------------------------------------------------------------------------

def test_future_commands_are_honest_stubs():
    for cmd in ("audit 1414", "brief today", "pmf status"):
        res = E.route(cmd, _ctx())
        assert res["ok"] is True and "coming" in res["text"].lower()


# --------------------------------------------------------------------------
# a handler bug is caught, not propagated
# --------------------------------------------------------------------------

def test_handler_exception_becomes_friendly_error():
    def boom(user_id, invoker, **kw):
        raise RuntimeError("kaboom")
    res = E.route("user 2762", _ctx(generate_fn=boom))
    assert res["ok"] is False and res["status"] == "handler_error"
    assert "internal error" in res["text"]
