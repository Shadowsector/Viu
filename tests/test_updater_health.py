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
    write_package_sha,
    _version_message,
)


def test_check_for_update_no_git(tmp_path, monkeypatch):
    from viu import updater

    monkeypatch.setattr(updater, "find_git_root", lambda start=None: None)
    monkeypatch.setattr(
        updater,
        "remote_sha_github",
        lambda repo=updater.DEFAULT_REPO, branch=updater.DEFAULT_BRANCH: "abc123remote",
    )
    monkeypatch.setattr(updater, "running_sha", lambda root=None: "")
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
    monkeypatch.setattr(updater, "running_sha", lambda root=None: "")

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


def test_check_for_update_uses_package_sha_over_stamp(tmp_path, monkeypatch):
    """Код на диске (package_sha) важнее stamp — иначе ложное «уже последняя»."""
    from viu import updater

    monkeypatch.setattr(updater, "find_git_root", lambda start=None: None)
    monkeypatch.setattr(updater, "package_root", lambda: tmp_path)
    write_install_stamp(tmp_path, "cursor/viu-agent-core-65c2", sha="deadbeef" * 5)
    (tmp_path / "viu").mkdir()
    (tmp_path / "viu" / "package_sha.txt").write_text("cafebabe" * 5 + "\n", encoding="utf-8")
    monkeypatch.setattr(
        updater,
        "remote_sha_github",
        lambda repo=updater.DEFAULT_REPO, branch=updater.DEFAULT_BRANCH: "deadbeef" * 5,
    )
    result = check_for_update()
    assert result.has_updates
    assert "cafebabe" in result.local_ref


def test_install_stamp(tmp_path):
    write_install_stamp(tmp_path, "cursor/test-branch", note="zip")
    stamp = tmp_path / ".viu" / "installed_version.txt"
    assert stamp.is_file()
    assert "test-branch" in stamp.read_text(encoding="utf-8")


def test_version_label_zip(tmp_path, monkeypatch):
    from viu import updater

    write_install_stamp(tmp_path, "cursor/viu-agent-core-65c2", sha="abcd1234abcd")
    monkeypatch.setattr(updater, "find_git_root", lambda start=None: None)

    def fake_root():
        return tmp_path

    monkeypatch.setattr(updater, "package_root", fake_root)
    ref = updater.current_commit()
    assert "abcd1234" in ref or "zip" in ref or "viu-agent" in ref


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


def test_version_message_includes_branch():
    msg = _version_message(
        branch="cursor/viu-agent-core-65c2",
        local="eea4d7d",
        remote="02c07b1",
        up_to_date=True,
    )
    assert "viu-agent-core-65c2" in msg
    assert "eea4d7d" in msg


def test_apply_git_fallback_hard_reset(tmp_path, monkeypatch):
    from viu import updater

    (tmp_path / ".git").mkdir()
    (tmp_path / "viu").mkdir()
    monkeypatch.setattr(updater, "usable_git_root", lambda start=None: tmp_path)
    monkeypatch.setattr(
        updater,
        "check_for_update",
        lambda repo=None, branch=updater.DEFAULT_BRANCH, remote="origin": updater.UpdateResult(
            ok=True,
            checked=True,
            has_updates=True,
            behind=1,
            local_ref="aaa",
            remote_ref="bbb",
            message="update",
        ),
    )
    calls: list[list[str]] = []

    def fake_run_git(args, cwd, timeout=120.0, retries=1):
        calls.append(list(args))
        if len(args) >= 2 and args[0] == "pull" and args[1] == "--ff-only":
            return 1, "diverged"
        if args[:2] == ["reset", "--hard"]:
            return 0, "HEAD is now at bbb"
        if args[:2] == ["rev-parse", "HEAD"]:
            return 0, "deadbeefcafe" * 2
        return 0, "ok"

    monkeypatch.setattr(updater, "_run_git", fake_run_git)
    monkeypatch.setattr(updater, "current_commit", lambda repo=None: "deadbeefcafe")
    monkeypatch.setattr(updater, "cleanup_obsolete", lambda root=None: [])

    result = updater.apply_git_update(tmp_path)
    assert result.updated
    assert any(a[:2] == ["reset", "--hard"] for a in calls)


def test_apply_git_update_writes_package_sha(tmp_path, monkeypatch):
    from viu import updater

    (tmp_path / ".git").mkdir()
    (tmp_path / "viu").mkdir()
    monkeypatch.setattr(updater, "usable_git_root", lambda start=None: tmp_path)
    monkeypatch.setattr(
        updater,
        "check_for_update",
        lambda repo=None, branch=updater.DEFAULT_BRANCH, remote="origin": updater.UpdateResult(
            ok=True,
            checked=True,
            has_updates=True,
            behind=1,
            local_ref="aaa",
            remote_ref="bbb",
            message="update",
        ),
    )
    monkeypatch.setattr(updater, "_run_git", lambda args, cwd, timeout=120.0, retries=1: (0, "ok"))
    monkeypatch.setattr(updater, "current_commit", lambda repo=None: "deadbeefcafe")
    monkeypatch.setattr(updater, "cleanup_obsolete", lambda root=None: [])

    result = updater.apply_git_update(tmp_path)
    assert result.updated
    assert (tmp_path / "viu" / "package_sha.txt").read_text(encoding="utf-8").startswith("ok")


def test_sha_needs_update_detects_mismatch(monkeypatch):
    from viu import updater

    monkeypatch.setattr(updater, "running_sha", lambda root=None: "aaa111")
    monkeypatch.setattr(updater, "remote_sha_github", lambda branch=updater.DEFAULT_BRANCH: "bbb222")
    outdated, local, remote = updater.sha_needs_update()
    assert outdated
    assert local == "aaa111"
    assert remote == "bbb222"


def test_update_viu_full_forces_when_sha_mismatch(tmp_path, monkeypatch):
    from viu import updater

    monkeypatch.setattr(updater, "package_root", lambda: tmp_path)
    monkeypatch.setattr(updater, "running_sha", lambda root=None: "oldsha")
    monkeypatch.setattr(updater, "remote_sha_github", lambda branch=updater.DEFAULT_BRANCH: "newsha")
    monkeypatch.setattr(
        updater,
        "check_for_update",
        lambda branch=updater.DEFAULT_BRANCH: updater.UpdateResult(
            ok=True,
            checked=True,
            has_updates=False,
            message="Уже последняя версия.",
        ),
    )
    applied = updater.UpdateResult(
        ok=True,
        updated=True,
        message="zip ok",
    )
    monkeypatch.setattr(updater, "apply_update_smart", lambda branch, hard_reset=False: applied)
    monkeypatch.setattr(updater, "install_package", lambda root=None: (True, "pip ok"))

    ok, text, restart = updater.update_viu_full()
    assert ok and restart
    assert "package_sha" in text or "SHA на диске" in text
    assert "zip ok" in text


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
