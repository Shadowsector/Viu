"""Тесты GitHub diagnose и сообщений об ошибках handoff."""

from viu.integrations.github.api import (
    _explain_contents_failure,
    _scope_hints,
    diagnose_github,
)


def test_scope_hints_public_repo_without_repo_scope():
    hints = _scope_hints(["read:user"])
    assert any("Public repo" in h for h in hints)
    assert any("gist" in h for h in hints)


def test_explain_contents_404_mentions_public():
    msg = _explain_contents_failure(
        404,
        repo="Shadowsector/Viu",
        branch="main",
        repo_private=False,
        scopes=["read:user"],
    )
    assert "public" in msg.lower() or "Public" in msg
    assert "repo" in msg


def test_diagnose_empty_token():
    report = diagnose_github("")
    assert "пуст" in report.lower() or "Токен пуст" in report


def test_diagnose_ok_classic_pat(monkeypatch):
    calls = []

    def fake_request(method, url, token, payload=None, *, timeout=60.0, auth_style="bearer"):
        calls.append((method, url))
        if url.endswith("/user"):
            return 200, {"login": "den"}, {"x-oauth-scopes": "repo, gist"}
        if "/repos/Shadowsector/Viu/branches" in url:
            return 200, [{"name": "main"}, {"name": "cursor/viu-agent-core-65c2"}], {}
        if "/repos/Shadowsector/Viu" in url and "contents" not in url:
            return 200, {"private": False, "default_branch": "main"}, {}
        if "contents/docs/CURSOR_HANDOFF.md" in url:
            return 404, {}, {}
        return 0, {}, {}

    monkeypatch.setattr("viu.integrations.github.api._api_request", fake_request)
    report = diagnose_github("ghp_testtoken1234", repo="Shadowsector/Viu")
    assert "Classic PAT" in report
    assert "@den" in report
    assert "public" in report.lower()
    assert "repo/public_repo — OK" in report
    assert "gist — OK" in report
