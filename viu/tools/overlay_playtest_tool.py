"""Автономный playtest оверлея — без кнопок Дена."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from ..integrations.unity.overlay import overlay_exe_path
from ..integrations.unity.paths import unity_project_root
from ..integrations.unity.process import (
    clear_unity_lockfile,
    kill_unity_processes,
    unity_process_running,
)
from ..integrations.unity.setup import (
    batch_overlay_build_command,
    deploy_animation_pipeline,
    editor_scripts_healthy,
    find_unity_exe,
    open_editor_command,
)
from ..integrations.unity.overlay_tune import deploy_tune_template
from ..support import collect_support_bundle, upload_bundle_to_gist
from .base import AgentContext, Tool, ToolResult


class OverlayPlaytestTool(Tool):
    name = "overlay_playtest"
    description = (
        "Собрать оверлей, запустить LaunchOverlay.bat (bitblt), подождать, "
        "прочитать overlay_boot.log и вернуть вердикт. Дена не дёргать."
    )
    parameters = {
        "timeout": "таймаут сборки сек (по умолчанию 1800)",
        "wait_sec": "сколько ждать после запуска exe (по умолчанию 18)",
        "launch": "запускать ли exe (по умолчанию true)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = unity_project_root(ctx.config)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")

        lines: List[str] = []

        # 1. Закрыть Unity Editor, если мешает batch
        ok_kill, kill_msg = kill_unity_processes()
        lines.append(f"Unity close: {kill_msg}" if kill_msg else "Unity close: ok")
        time.sleep(2.0)

        ok, msg = deploy_animation_pipeline(root)
        lines.append(msg)
        if not ok:
            return ToolResult(False, "\n".join(lines))

        healthy, hint = editor_scripts_healthy(root)
        if not healthy:
            lines.append(hint)
            return ToolResult(False, "\n".join(lines))

        exe = find_unity_exe(ctx.config.unity_exe)
        if exe is None:
            return ToolResult(
                False,
                "\n".join(lines) + "\nUnity.exe не найден (VIU_UNITY_EXE).",
            )

        cmd = batch_overlay_build_command(root, exe)
        timeout = float(args.get("timeout") or 1800)
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=str(root)
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "\n".join(lines) + f"\nТаймаут сборки {timeout}s")

        log_path = root / "viu_overlay_build.log"
        important: list[str] = []
        if log_path.is_file():
            important = [
                ln
                for ln in log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                if "[Viu]" in ln or "error CS" in ln or "Exception" in ln
            ][-20:]

        if proc.returncode != 0:
            detail = "\n".join(important) if important else "(см. viu_overlay_build.log)"
            return ToolResult(False, "\n".join(lines) + "\nСборка FAIL\n" + detail)

        out_exe = overlay_exe_path(root)
        launcher = out_exe.parent / "LaunchOverlay.bat"
        deploy_tune_template(root, overwrite=False)
        lines.append(f"Сборка OK: {out_exe}")
        if important:
            lines.append("--- build ---")
            lines.extend(important[-8:])

        launch = str(args.get("launch", "true")).lower() not in ("0", "false", "no")
        verdict = ""
        if launch and out_exe.is_file():
            boot = out_exe.parent / "overlay_boot.log"
            if boot.is_file():
                try:
                    boot.unlink()
                except OSError:
                    pass
            try:
                cwd = str(out_exe.parent)
                if sys.platform == "win32" and launcher.is_file():
                    subprocess.Popen(["cmd", "/c", "start", "", str(launcher)], cwd=cwd)  # noqa: S603
                    lines.append(f"Запуск: {launcher}")
                elif sys.platform == "win32":
                    subprocess.Popen(  # noqa: S603
                        [
                            "cmd", "/c", "start", "", str(out_exe),
                            "-force-d3d11-bitblt-model", "-popupwindow",
                        ],
                        cwd=cwd,
                    )
                    lines.append(f"Запуск exe + bitblt: {out_exe}")
                else:
                    lines.append("(не Windows — запуск пропущен)")
            except OSError as exc:
                lines.append(f"Запуск не удался: {exc}")

            wait_sec = float(args.get("wait_sec") or 18)
            time.sleep(wait_sec)

            boot = out_exe.parent / "overlay_boot.log"
            if boot.is_file():
                boot_text = boot.read_text(encoding="utf-8", errors="replace")
                lines.append("--- overlay_boot.log ---")
                # Awake/AfterWindow в начале; ColorKey раньше заливал хвост
                head = boot_text[:1200]
                tail = boot_text[-1200:]
                if len(boot_text) > 2400 and head != tail:
                    lines.append(head.rstrip())
                    lines.append("…")
                    lines.append(tail.lstrip())
                else:
                    lines.append(boot_text[-2500:])
                verdict = _verdict(boot_text)
                lines.append("--- вердикт ---")
                lines.append(verdict)
            else:
                verdict = "FAIL: overlay_boot.log нет"
                lines.append(
                    "overlay_boot.log нет — окно могло не стартовать или скрипт не доехал. "
                    "Проверь AnabarraOverlay в диспетчере задач."
                )

        # Вернуть Editor Дену — playtest не должен оставлять Unity мёртвым.
        reopen = str(args.get("reopen_unity", "true")).lower() not in ("0", "false", "no")
        if reopen:
            try:
                if not unity_process_running() and exe is not None:
                    clear_unity_lockfile(root)
                    cmd_open = open_editor_command(root, exe)
                    kwargs: Dict[str, Any] = {"cwd": str(root)}
                    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                    subprocess.Popen(cmd_open, **kwargs)  # noqa: S603
                    lines.append("Unity Editor снова открыт для Дена.")
                elif unity_process_running():
                    lines.append("Unity Editor уже в процессах.")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"Не смогла reopen Unity: {exc}")

        # Bundle + gist для Cursor
        try:
            bundle = collect_support_bundle(ctx.config)
            lines.append(f"Support bundle: {bundle}")
            g_ok, g_msg = upload_bundle_to_gist(bundle, description="Viu overlay_playtest")
            lines.append(g_msg)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"Bundle: {exc}")

        text = "\n".join(lines)
        build_ok = proc.returncode == 0
        play_ok = build_ok and (not verdict or verdict.startswith("OK:"))
        return ToolResult(play_ok, text)


def _verdict(boot_text: str) -> str:
    low = boot_text.lower()
    if "hwnd не найден" in low or "hwnd=0" in low:
        return "FAIL: окно Unity не найдено (HWND)."
    if "setlayeredwindowattributes=false" in low:
        return "FAIL: ColorKey не применился — снова magenta / flip-model?"
    if "setlayeredwindowattributes=true" in low or "colorkey pass" in low:
        if "shanya=false" in low or "shanya=(false)" in low or "name=нет" in low:
            return (
                "WARN: прозрачность ок, но Шаня не в сцене "
                "(пересобери: FindModelPath должен брать Shanya_Erisa, не Fall/Run)."
            )
        if "home=нет" in low:
            return "WARN: прозрачность ок, дом не найден в сцене (Environment FBX?)."
        if "renderers=0/" in low:
            return "WARN: прозрачность ок, но нет видимых мешей."
        return "OK: HWND + ColorKey. Смотри рабочий стол — Шаня/дом должны быть видны."
    if "hwnd ok" in low:
        return "PARTIAL: HWND есть, ColorKey в логе не подтверждён."
    return "UNKNOWN: смотри boot-лог выше."
