import os

from viu.env_file import bootstrap_env, ensure_env_file, github_token, load_env_file


def test_load_env_file_sets_missing_only(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_TEST_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("VIU_TEST_KEY=from_file\nVIU_OTHER=1\n", encoding="utf-8")
    load_env_file(tmp_path)
    assert os.environ["VIU_TEST_KEY"] == "from_file"
    monkeypatch.setenv("VIU_TEST_KEY", "already")
    load_env_file(tmp_path)
    assert os.environ["VIU_TEST_KEY"] == "already"


def test_reload_secret_overwrites_empty_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_GITHUB_TOKEN", "")
    env = tmp_path / ".env"
    env.write_text("VIU_GITHUB_TOKEN=ghp_from_file\n", encoding="utf-8")
    load_env_file(tmp_path)
    assert os.environ["VIU_GITHUB_TOKEN"] == "ghp_from_file"


def test_ensure_env_file_copies_example(tmp_path):
    example = tmp_path / ".env.example"
    example.write_text("VIU_GITHUB_TOKEN=\n", encoding="utf-8")
    path = ensure_env_file(tmp_path)
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == example.read_text(encoding="utf-8")


def test_bootstrap_env_and_github_token(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_GITHUB_TOKEN", raising=False)
    (tmp_path / ".env.example").write_text(
        "VIU_GITHUB_TOKEN=ghp_test_token\n", encoding="utf-8"
    )
    bootstrap_env(tmp_path)
    assert github_token() == "ghp_test_token"
