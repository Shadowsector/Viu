"""Playtest overlay — свежий boot-лог и честный отчёт в чат."""

from __future__ import annotations

import os
import time
from pathlib import Path

from viu.tools.overlay_playtest_tool import (
    _boot_content_ok,
    _boot_log_fresh,
    _playtest_human,
    _prepare_boot_log,
)


def test_playtest_human_no_false_ok_on_stale_boot(tmp_path: Path) -> None:
    exe = tmp_path / "AnabarraOverlay.exe"
    exe.write_text("", encoding="utf-8")
    msg = _playtest_human(
        ok=False,
        build_ok=True,
        launch_attempted=True,
        boot_fresh=False,
        boot_content_ok=False,
        proc_running=False,
        out_exe=exe,
        verdict="FAIL: overlay_boot.log нет",
        eyes_miss=False,
        eye_vision="",
    )
    assert "✗" in msg
    assert "не запустился" in msg
    assert "LaunchOverlay.vbs" in msg
    assert "✓" not in msg


def test_playtest_human_ok_only_when_play_ok(tmp_path: Path) -> None:
    exe = tmp_path / "AnabarraOverlay.exe"
    exe.write_text("", encoding="utf-8")
    msg = _playtest_human(
        ok=True,
        build_ok=True,
        launch_attempted=True,
        boot_fresh=True,
        boot_content_ok=True,
        proc_running=True,
        out_exe=exe,
        verdict="OK: HWND + UpdateLayeredWindow + сцена в boot-логе.",
        eyes_miss=True,
        eye_vision="",
    )
    assert msg.startswith("✓")
    assert "Прозрачность" in msg


def test_prepare_boot_log_removes_stale_file(tmp_path: Path) -> None:
    boot = tmp_path / "overlay_boot.log"
    boot.write_text("runtime-rev=51\nUpdateLayeredWindow", encoding="utf-8")
    _prepare_boot_log(boot)
    assert not boot.is_file()


def test_boot_log_fresh_requires_mtime_after_launch(tmp_path: Path) -> None:
    boot = tmp_path / "overlay_boot.log"
    boot.write_text("old", encoding="utf-8")
    stale_mtime = time.time() - 60
    os.utime(boot, (stale_mtime, stale_mtime))
    assert not _boot_log_fresh(boot, time.time() - 5)
    boot.write_text("runtime-rev=53\nUpdateLayeredWindow init ok", encoding="utf-8")
    assert _boot_log_fresh(boot, time.time() - 1)


def test_boot_content_ok() -> None:
    assert _boot_content_ok("runtime-rev=53\nTransparency=UpdateLayeredWindow")
    assert not _boot_content_ok("Awake only, no transparency yet")
