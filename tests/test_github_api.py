"""Тесты GitHub API и shell guard."""

from viu.integrations.github.api import branch_candidates, normalize_repo, push_file_via_api
from viu.shell_guard import shell_git_blocked


def test_normalize_repo():
    assert normalize_repo("Shadowsector/Viu") == "Shadowsector/Viu"
    assert normalize_repo("https://github.com/Shadowsector/Viu") == "Shadowsector/Viu"
    assert normalize_repo("https://github.com/Shadowsector/Viu.git") == "Shadowsector/Viu"


def test_shell_git_blocked():
    assert shell_git_blocked("git init")
    assert shell_git_blocked("cd foo && git push origin main")
    assert shell_git_blocked("git commit -m x")
    assert shell_git_blocked("git init") is not None
    assert shell_git_blocked("dir U:\\Viu") is None


def test_push_file_via_api_gist_fallback(monkeypatch):
    calls = {"gist": 0}

    def fake_user(token):
        return True, "@den"

    def fake_repo(repo, token):
        return False, "no repo access"

    def fake_gist(filename, content, *, token, description=""):
        calls["gist"] += 1
        return True, "https://gist.github.com/abc"

    monkeypatch.setattr("viu.integrations.github.api.github_token_valid", fake_user)
    monkeypatch.setattr("viu.integrations.github.api.get_repo_info", fake_repo)
    monkeypatch.setattr("viu.integrations.github.api.upload_gist", fake_gist)

    ok, msg = push_file_via_api(
        "docs/CURSOR_HANDOFF.md",
        "hello",
        message="test",
        token="ghp_x",
    )
    assert ok
    assert calls["gist"] == 1
    assert "gist.github.com" in msg


def test_branch_candidates_dedupe():
    branches = branch_candidates("main", {"default_branch": "main"})
    assert branches[0] == "main"
    assert branches.count("main") == 1
