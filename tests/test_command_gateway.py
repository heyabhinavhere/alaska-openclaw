"""Alaska Command Gateway — test suite (stdlib only, no live network/socket).

Covers: Slack signature verification (valid / invalid / stale / missing), team
allowlist, command parsing, subcommand dispatch (help/ping/audit + unknown +
missing/invalid args), the verify->parse->ack->enqueue receiver path (fast ack,
no inline long work), filesystem-JSON job records, and the async worker
(run_job) posting to response_url with a fake transport (success + failure).

Run: python3 -m pytest tests/test_command_gateway.py -q
"""
from __future__ import annotations

import hashlib
import hmac
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

import alaska_command_gateway as G  # noqa: E402
from alaska_command_gateway import core, jobs, verify  # noqa: E402

SECRET = "8f742231b10e4f8c9b2e1a0d3c5e7f90"
FIXED_TS = 1_700_000_000


def _tmp() -> str:
    return tempfile.mkdtemp(prefix="alaska_gateway_test_")


def _sign(raw_body: str, ts: int = FIXED_TS, secret: str = SECRET):
    base = ("v0:%d:%s" % (ts, raw_body)).encode("utf-8")
    sig = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return {"X-Slack-Signature": sig, "X-Slack-Request-Timestamp": str(ts)}


def _form(text: str, **over) -> str:
    fields = {"command": "/alaska", "text": text, "user_id": "U1",
              "channel_id": "C1", "team_id": "T1",
              "response_url": "https://hooks.slack.test/r/abc"}
    fields.update(over)
    return urlencode(fields)


class _FakeHttp:
    def __init__(self, status=200):
        self.calls = []
        self.status = status

    def __call__(self, method, url, *, headers=None, body=None, timeout=None):
        import json
        self.calls.append({"method": method, "url": url,
                           "payload": json.loads(body.decode()) if body else None})
        return self.status, b"ok"


# --------------------------------------------------------------------------
# signature verification
# --------------------------------------------------------------------------

def test_valid_signature_passes():
    body = _form("ping")
    h = _sign(body)
    assert verify.verify_slack_signature(
        SECRET, h["X-Slack-Request-Timestamp"], body, h["X-Slack-Signature"], now=FIXED_TS) is True


def test_invalid_signature_fails():
    body = _form("ping")
    assert verify.verify_slack_signature(
        SECRET, str(FIXED_TS), body, "v0=deadbeef", now=FIXED_TS) is False


def test_tampered_body_fails():
    h = _sign(_form("ping"))
    assert verify.verify_slack_signature(
        SECRET, h["X-Slack-Request-Timestamp"], _form("audit 1414"),
        h["X-Slack-Signature"], now=FIXED_TS) is False


def test_stale_timestamp_fails():
    body = _form("ping")
    h = _sign(body)
    # now is 10 minutes after the signed timestamp -> outside the 300s window.
    assert verify.verify_slack_signature(
        SECRET, h["X-Slack-Request-Timestamp"], body, h["X-Slack-Signature"],
        now=FIXED_TS + 600) is False


def test_missing_fields_fail_closed():
    assert verify.verify_slack_signature("", "1", "b", "v0=x") is False
    assert verify.verify_slack_signature(SECRET, "", "b", "v0=x") is False
    assert verify.verify_slack_signature(SECRET, "notanumber", "b", "v0=x", now=FIXED_TS) is False


def test_team_allowlist():
    assert verify.team_allowed("Tanything", None) is True          # open by default
    assert verify.team_allowed("T1", ["T1", "T2"]) is True
    assert verify.team_allowed("T9", ["T1", "T2"]) is False
    assert verify.team_allowed("", ["T1"]) is False


# --------------------------------------------------------------------------
# command parsing + dispatch
# --------------------------------------------------------------------------

def test_parse_command():
    p = core.parse_command("audit 1414")
    assert p.subcommand == "audit" and p.args == ["1414"]
    assert core.parse_command("").subcommand == "help"
    assert core.parse_command("  ping ").subcommand == "ping"
    assert core.parse_command("/alaska audit 1414").args == ["1414"]   # tolerate full text


def test_help_and_ping_dispatch():
    ctx = {"version": G.GATEWAY_VERSION}
    help_resp = core.dispatch_ack(core.parse_command("help"), ctx)
    assert "/alaska" in help_resp["text"] and help_resp["response_type"] == "ephemeral"
    ping_resp = core.dispatch_ack(core.parse_command("ping"), ctx)
    assert "pong" in ping_resp["text"] and G.GATEWAY_VERSION in ping_resp["text"]


def test_audit_dispatch_returns_async_spec():
    resp = core.dispatch_ack(core.parse_command("audit 1414"), {})
    assert resp["async"] == {"command": "audit", "params": {"user_id": "1414"}}
    assert "started" in resp["text"]


def test_audit_missing_and_invalid_args():
    assert "Usage" in core.dispatch_ack(core.parse_command("audit"), {})["text"]
    assert "doesn't look like" in core.dispatch_ack(core.parse_command("audit abc"), {})["text"]


def test_unknown_subcommand_is_helpful():
    resp = core.dispatch_ack(core.parse_command("frobnicate"), {})
    assert "Unknown subcommand" in resp["text"]
    assert "audit" in resp["text"]  # lists known subcommands


# --------------------------------------------------------------------------
# receiver — verify -> parse -> ack -> enqueue
# --------------------------------------------------------------------------

def test_receiver_help_fast_ack_no_job():
    res = G.handle_slash_command(_form("help"), {}, enforce_signature=False, base_dir=_tmp())
    assert res["status"] == 200 and res["ok"] is True
    assert "/alaska" in res["body"]["text"]
    assert res["job"] is None
    assert "async" not in res["body"]   # internal key never leaks to Slack


def test_receiver_ping():
    res = G.handle_slash_command(_form("ping"), {}, enforce_signature=False, base_dir=_tmp())
    assert res["status"] == 200 and "pong" in res["body"]["text"]


def test_receiver_audit_enqueues_without_running_inline():
    base = _tmp()
    res = G.handle_slash_command(_form("audit 1414"), {}, enforce_signature=False, base_dir=base)
    assert res["status"] == 200 and "started" in res["body"]["text"]
    job = res["job"]
    assert job is not None
    assert job["command"] == "audit" and job["params"] == {"user_id": "1414"}
    # The long work must NOT have run inline — the job is still queued.
    persisted = jobs.get_job(job["job_id"], base_dir=base)
    assert persisted["status"] == "queued"
    assert persisted["actor"] == "U1" and persisted["channel"] == "C1"
    assert persisted["response_url"] == "https://hooks.slack.test/r/abc"


def test_receiver_missing_args_is_helpful_not_an_error():
    res = G.handle_slash_command(_form("audit"), {}, enforce_signature=False, base_dir=_tmp())
    assert res["status"] == 200 and res["job"] is None
    assert "Usage" in res["body"]["text"]


def test_receiver_signed_request_passes_and_tamper_fails():
    body = _form("ping")
    headers = _sign(body)
    ok = G.handle_slash_command(body, headers, signing_secret=SECRET, now=FIXED_TS, base_dir=_tmp())
    assert ok["status"] == 200 and "pong" in ok["body"]["text"]

    bad = G.handle_slash_command(_form("audit 1414"), headers, signing_secret=SECRET,
                                 now=FIXED_TS, base_dir=_tmp())  # body != signed body
    assert bad["status"] == 401 and bad["reject_reason"] == "bad_signature"


def test_receiver_stale_timestamp_rejected():
    body = _form("ping")
    headers = _sign(body)
    res = G.handle_slash_command(body, headers, signing_secret=SECRET,
                                 now=FIXED_TS + 600, base_dir=_tmp())
    assert res["status"] == 401 and res["reject_reason"] == "bad_signature"


def test_receiver_requires_secret_when_enforcing():
    res = G.handle_slash_command(_form("ping"), {}, signing_secret=None,
                                 enforce_signature=True, base_dir=_tmp())
    assert res["status"] == 500 and res["reject_reason"] == "no_signing_secret"


def test_receiver_disallowed_team_rejected():
    res = G.handle_slash_command(_form("ping", team_id="T9"), {}, enforce_signature=False,
                                 allowed_teams=["T1"], base_dir=_tmp())
    assert res["status"] == 403 and res["reject_reason"] == "team_not_allowed"


# --------------------------------------------------------------------------
# async worker — run_job posts to response_url
# --------------------------------------------------------------------------

def test_run_job_delivers_dry_run_result_to_response_url():
    base = _tmp()
    res = G.handle_slash_command(_form("audit 1414"), {}, enforce_signature=False, base_dir=base)
    job_id = res["job"]["job_id"]
    fake = _FakeHttp()
    done = jobs.run_job(job_id, http_request=fake, base_dir=base)
    assert done["status"] == "done"
    assert "Dry run" in done["result"]["text"]
    assert len(fake.calls) == 1
    assert fake.calls[0]["url"] == "https://hooks.slack.test/r/abc"
    assert "Dry run" in fake.calls[0]["payload"]["text"]


def test_run_job_unknown_command_fails_cleanly():
    base = _tmp()
    job = jobs.create_job("bogus", "U1", "C1", {}, response_url="https://hooks.slack.test/r/z",
                          base_dir=base)
    fake = _FakeHttp()
    done = jobs.run_job(job["job_id"], http_request=fake, base_dir=base)
    assert done["status"] == "error" and done["error"] == "no_finalizer_for_command"
    assert len(fake.calls) == 1  # user still gets a clean failure message


def test_run_job_finalizer_exception_is_captured():
    base = _tmp()
    jobs.register_finalizer("boom", lambda job: (_ for _ in ()).throw(RuntimeError("kaboom")))
    job = jobs.create_job("boom", "U1", "C1", {}, response_url="https://hooks.slack.test/r/z",
                          base_dir=base)
    fake = _FakeHttp()
    done = jobs.run_job(job["job_id"], http_request=fake, base_dir=base)
    assert done["status"] == "error" and "kaboom" in done["error"]
    assert "failed" in fake.calls[0]["payload"]["text"].lower()


# --------------------------------------------------------------------------
# isolation guard — never import V5 pmf_os or the audit skill at runtime
# --------------------------------------------------------------------------

def test_gateway_modules_do_not_import_workstream_code():
    import re
    pkg = REPO_ROOT / "lib" / "alaska_command_gateway"
    forbidden = re.compile(r"^(import|from)\s+(lib\.)?(pmf_os|audit_[a-z]+|bon_internal)")
    for pyfile in pkg.glob("*.py"):
        for line in pyfile.read_text(encoding="utf-8").splitlines():
            assert not forbidden.match(line.strip()), "%s imports workstream code: %s" % (pyfile.name, line)
