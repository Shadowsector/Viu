"""Тесты updater (zip/git) и health."""

from pathlib import Path
from unittest.mock import patch

from viu.health import ollama_available
from viu.updater import (
    check_for_update,
    current_commit,
    package_root,
    write_install_stamp,
)


def test_check_for_update_no_git(tmp_path, monkeypatch):
    from viu import updater

    monkeypatch.setattr(updater, "find_git_root", lambda start=None: None)
    monkeypatch.setattr(
        updater,
        "remote_sha_github",
        lambda repo=updater.DEFAULT_REPO, branch=updater.DEFAULT_BRANCH: "abc123remote",
    )
    monkeypatch.setattr(updater, "read_local_sha", lambda root=None: "")
    result = check_for_update()
    assert result.checked
    assert result.has_updates


def test_install_stamp(tmp_path):
    write_install_stamp(tmp_path, "cursor/test-branch", note="zip")
    stamp = tmp_path / ".viu" / "installed_version.txt"
    assert stamp.is_file()
    assert "test-branch" in stamp.read_text(encoding="utf-8")


def test_version_label_zip(tmp_path, monkeypatch):
    from viu import updater

    write_install_stamp(tmp_path, "cursor/viu-agent-core-65c2")
    monkeypatch.setattr(updater, "find_git_root", lambda start=None: None)

    def fake_root():
        return tmp_path

    monkeypatch.setattr(updater, "package_root", fake_root)
    ref = updater.current_commit()
    assert "zip" in ref or "viu-agent" in ref


@patch("urllib.request.urlopen")
def test_ollama_available_mock(mock_urlopen):
    class Resp:
        def read(self):
            return b'{"models":[]}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    mock_urlopen.return_value = Resp()
    assert ollama_available()
