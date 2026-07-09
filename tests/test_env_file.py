from viu.env_file import load_env_file


def test_load_env_file_sets_missing_only(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_TEST_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("VIU_TEST_KEY=from_file\nVIU_OTHER=1\n", encoding="utf-8")
    load_env_file(tmp_path)
    import os

    assert os.environ["VIU_TEST_KEY"] == "from_file"
    monkeypatch.setenv("VIU_TEST_KEY", "already")
    load_env_file(tmp_path)
    assert os.environ["VIU_TEST_KEY"] == "already"
