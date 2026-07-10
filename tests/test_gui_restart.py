"""Тесты перезапуска GUI после обновления."""

from pathlib import Path
from unittest.mock import patch

from viu.gui import (
    acquire_single_instance,
    build_relaunch_command,
    release_single_instance,
)


def test_build_relaunch_command_prefers_run_gui_pyw(tmp_path, monkeypatch):
    from viu import updater

    monkeypatch.setattr(updater, "package_root", lambda: tmp_path)
    monkeypatch.setattr("viu.gui.usable_git_root", lambda: None)
    (tmp_path / "run_gui.pyw").write_text("# stub", encoding="utf-8")

    cmd, cwd = build_relaunch_command(tmp_path)
    assert cwd == str(tmp_path)
    assert cmd[-1].endswith("run_gui.pyw")


def test_release_single_instance_allows_reacquire():
    import viu.gui as gui

    port = 47616
    gui._instance_sock = acquire_single_instance(port)
    assert gui._instance_sock is not None
    release_single_instance()
    second = acquire_single_instance(port)
    assert second is not None
    release_single_instance()
    second.close()


def test_update_viu_full_sets_restart_flag(tmp_path, monkeypatch):
    from viu.updater import UpdateResult, update_viu_full

    monkeypatch.setattr(
        "viu.updater.check_for_update",
        lambda branch=...: UpdateResult(ok=True, checked=True, has_updates=True),
    )
    monkeypatch.setattr(
        "viu.updater.apply_update_smart",
        lambda branch=..., hard_reset=False: UpdateResult(
            ok=True, updated=True, message="updated"
        ),
    )
    monkeypatch.setattr("viu.updater.install_package", lambda root=None: (True, "pip ok"))

    ok, text, restart = update_viu_full()
    assert ok
    assert restart
