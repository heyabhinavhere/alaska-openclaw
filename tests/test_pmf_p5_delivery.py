"""P5 tests: Slack delivery (injectable, fixture-only) + the team-tier privacy
verification — name/email/phone are KEPT by the data-minimization policy;
SSN / routing / address are dropped and account numbers reduced to last-4."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os import slack_delivery  # noqa: E402
from pmf_os.artifacts import build_report_snapshot, render_html  # noqa: E402


def _recorder():
    """A fake http_request that records calls and returns canned Slack responses."""
    calls: list[dict] = []

    def http_request(method, url, *, headers=None, body=None):
        calls.append({"method": method, "url": url, "headers": headers or {}, "body": body})
        if "chat.postMessage" in url:
            return 200, b'{"ok": true, "ts": "1700000000.000100"}'
        if "getUploadURLExternal" in url:
            return 200, b'{"ok": true, "upload_url": "https://files.slack.com/upload/x", "file_id": "F123"}'
        if "completeUploadExternal" in url:
            return 200, b'{"ok": true, "files": [{"id": "F123"}]}'
        return 200, b"OK"  # the raw-bytes POST to the returned upload_url

    return calls, http_request


def test_post_summary_builds_chat_postmessage():
    calls, http = _recorder()
    res = slack_delivery.post_summary("C123", "daily summary line", token="xoxb-test", http_request=http)
    assert res["ok"] is True and res["ts"]
    call = calls[0]
    assert call["method"] == "POST" and call["url"].endswith("chat.postMessage")
    assert call["headers"]["Authorization"] == "Bearer xoxb-test"
    assert json.loads(call["body"]) == {"channel": "C123", "text": "daily summary line"}


def test_post_summary_surfaces_slack_error():
    def http(method, url, *, headers=None, body=None):
        return 200, b'{"ok": false, "error": "channel_not_found"}'

    res = slack_delivery.post_summary("CBAD", "x", token="t", http_request=http)
    assert res["ok"] is False and res["error"] == "channel_not_found"


def test_upload_file_runs_three_step_flow():
    calls, http = _recorder()
    path = Path(tempfile.mkdtemp(prefix="p5_")) / "cockpit.html"
    path.write_text("<html></html>", encoding="utf-8")
    res = slack_delivery.upload_file("C123", str(path), "Cockpit", token="t", http_request=http)
    assert res["ok"] is True and res["file_id"] == "F123"
    urls = [c["url"] for c in calls]
    assert any("getUploadURLExternal" in u for u in urls)
    assert "https://files.slack.com/upload/x" in urls  # raw bytes POST to the issued url
    assert any("completeUploadExternal" in u for u in urls)


def test_upload_file_missing_file_is_handled():
    _, http = _recorder()
    res = slack_delivery.upload_file("C123", "/no/such/file.html", "x", token="t", http_request=http)
    assert res["ok"] is False and res["error"] == "file_missing"


def test_deliver_posts_summary_then_uploads():
    _, http = _recorder()
    path = Path(tempfile.mkdtemp(prefix="p5_")) / "c.html"
    path.write_text("<html></html>", encoding="utf-8")
    res = slack_delivery.deliver("C1", "summary", str(path), token="t", http_request=http)
    assert res["ok"] is True
    assert res["summary"]["ok"] is True and res["file"]["ok"] is True


def test_deliver_without_html_skips_upload():
    calls, http = _recorder()
    res = slack_delivery.deliver("C1", "summary", None, token="t", http_request=http)
    assert res["ok"] is True and res["file"] is None
    assert all("upload" not in c["url"].lower() for c in calls)


def test_team_cockpit_keeps_name_drops_secrets():
    users = [{
        "user_key": "user:1001", "name": "Jordan Rivera", "email": "jordan@example.com",
        "phone_number": "+14155550123", "current_stage": "activated_user",
        "current_health": "healthy", "is_real_user": True,
        "ssn": "123-45-6789", "routing_number": "021000021",
        "address": "742 Evergreen Terrace", "account_number": "1234567890",
        "financial_context": {"note": "balance owed; SSN 123-45-6789 on file"},
    }]
    snap = build_report_snapshot(cohort={"name": "C"}, users=users, queues=[], privacy_tier="team")
    user = snap["users"][0]
    # kept by policy — the whole team needs these to troubleshoot
    assert user["name"] == "Jordan Rivera" and user["email"] == "jordan@example.com"
    assert user["phone_number"] == "+14155550123"
    # dropped at source
    assert "ssn" not in user and "routing_number" not in user and "address" not in user
    # account number reduced to last-4
    assert user["account_number"].startswith("•") and user["account_number"].endswith("7890")
    # SSN pattern scrubbed even inside free text
    assert "123-45-6789" not in user["financial_context"]["note"]
    # The cockpit is now AGGREGATE-ONLY (the per-user table was removed) — so it carries
    # no per-user name AND, critically, no secrets in a channel-posted artifact. The
    # team-visible per-user detail (name kept, secrets dropped — asserted above) lives in
    # the /pmf case file instead.
    out = Path(tempfile.mkdtemp(prefix="p5_")) / "cockpit.html"
    render_html(snap, out)
    text = out.read_text(encoding="utf-8")
    assert "Jordan Rivera" not in text  # aggregate cockpit → no per-user PII in the channel
    assert "123-45-6789" not in text and "742 Evergreen Terrace" not in text


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
