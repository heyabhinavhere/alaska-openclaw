import lib.open_self_pr as m  # PYTHONPATH=/opt/lib in prod; in dev run from repo root


def test_no_changes_raises(monkeypatch):
    monkeypatch.setenv("GITHUB_SELF_IMPROVE_TOKEN", "x")
    try:
        m.open_pr({}, "t", "b")
        assert False
    except m.SelfPRError as e:
        assert "no changes" in str(e)


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("GITHUB_SELF_IMPROVE_TOKEN", raising=False)
    try:
        m.open_pr({"skills/x/SKILL.md": "hi"}, "t", "b")
        assert False
    except m.SelfPRError as e:
        assert "GITHUB_SELF_IMPROVE_TOKEN" in str(e)


def test_open_pr_sequence(monkeypatch):
    monkeypatch.setenv("GITHUB_SELF_IMPROVE_TOKEN", "x")
    calls = []

    def fake_req(method, path, body=None):
        calls.append((method, path))
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": "BASESHA"}}
        if "/contents/" in path and method == "GET":
            return {"sha": "OLDSHA"}
        if path.endswith("/pulls"):
            return {"html_url": "https://github.com/o/r/pull/1"}
        return {}

    monkeypatch.setattr(m, "_req", fake_req)
    url = m.open_pr({"skills/x/SKILL.md": "new content"}, "title", "body", branch="b1")
    assert url == "https://github.com/o/r/pull/1"
    methods = [c[0] for c in calls]
    assert methods == ["GET", "POST", "GET", "PUT", "POST"]  # base→branch→getsha→put→pr
