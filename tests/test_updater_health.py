"""Тесты updater (zip/git) и health."""

from pathlib import Path
from unittest.mock import patch

from viu.health import ollama_available
from viu.updater import (
    cleanup_broken_git,
    check_for_update,
    current_commit,
    package_root,
    usable_git_root,
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


def test_check_for_update_broken_git_falls_back_to_github(tmp_path, monkeypatch):
    from viu import updater

    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(updater, "package_root", lambda: tmp_path)
    monkeypatch.setattr(
        updater,
        "remote_sha_github",
        lambda repo=updater.DEFAULT_REPO, branch=updater.DEFAULT_BRANCH: "abc123remote",
    )
    monkeypatch.setattr(updater, "read_local_sha", lambda root=None: "")

    def fake_run_git(args, cwd, timeout=120.0, retries=1):
        if args[:2] == ["remote", "get-url"]:
            return 2, "No such remote 'origin'"
        return 1, "no origin"

    import viu.updater as u

    monkeypatch.setattr(u, "_run_git", fake_run_git)
    assert cleanup_broken_git(tmp_path) is True
    assert not (tmp_path / ".git").exists()
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


def test_cleanup_obsolete(tmp_path):
    from viu.updater import cleanup_obsolete

    (tmp_path / "start_viu.bat").write_text("x", encoding="utf-8")
    (tmp_path / "check_unity.bat").write_text("x", encoding="utf-8")
    (tmp_path / "Viu.cmd").write_text("keep", encoding="utf-8")
    legacy = tmp_path / "legacy_scripts"
    legacy.mkdir()
    (legacy / "old.bat").write_text("x", encoding="utf-8")

    removed = cleanup_obsolete(tmp_path)
    assert "start_viu.bat" in removed
    assert "check_unity.bat" in removed
    assert "legacy_scripts/" in removed
    assert not (tmp_path / "start_viu.bat").exists()
    assert not legacy.exists()
    # Viu.cmd не трогаем.
    assert (tmp_path / "Viu.cmd").exists()


def test_single_instance_guard():
    from viu.gui import acquire_single_instance

    port = 47777
    first = acquire_single_instance(port)
    assert first is not None
    second = acquire_single_instance(port)
    assert second is None  # второй экземпляр не поднимется
    first.close()


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
