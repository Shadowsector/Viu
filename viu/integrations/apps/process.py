"""Закрытие / перезапуск окон: Unity, Blender, Cascadeur."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...config import Config

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Windows image name → человеческое имя
APP_IMAGES: Dict[str, Tuple[str, ...]] = {
    "unity": ("Unity.exe",),
    "blender": ("blender.exe", "Blender.exe"),
    "cascadeur": ("cascadeur.exe", "Cascadeur.exe"),
}


def _pids_for_image(image: str) -> List[int]:
    if sys.platform != "win32":
        # Linux: pgrep -f
        try:
            stem = image.replace(".exe", "")
            proc = subprocess.run(
                ["pgrep", "-f", stem],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        return [int(x) for x in (proc.stdout or "").split() if x.isdigit()]

    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            creationflags=_CREATE_NO_WINDOW,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    pids: List[int] = []
    for line in (proc.stdout or "").splitlines():
        if image.lower() not in line.lower():
            continue
        parts = line.split('","')
        if len(parts) < 2:
            continue
        try:
            pids.append(int(parts[1].strip('"')))
        except ValueError:
            continue
    return pids


def app_pids(app: str) -> List[int]:
    key = app.strip().lower()
    images = APP_IMAGES.get(key)
    if not images:
        return []
    out: List[int] = []
    for img in images:
        out.extend(_pids_for_image(img))
    return sorted(set(out))


def app_running(app: str) -> bool:
    return bool(app_pids(app))


def kill_app(app: str, *, wait_seconds: float = 2.0) -> Tuple[bool, str]:
    key = app.strip().lower()
    images = APP_IMAGES.get(key)
    if not images:
        return False, f"Неизвестное приложение: {app} (unity|blender|cascadeur)"

    pids = app_pids(key)
    if not pids:
        return True, f"{key}: не запущен."

    if sys.platform == "win32":
        errs: List[str] = []
        for img in images:
            try:
                proc = subprocess.run(
                    ["taskkill", "/F", "/IM", img],
                    capture_output=True,
                    text=True,
                    creationflags=_CREATE_NO_WINDOW,
                    timeout=30,
                )
                if proc.returncode not in (0, 128):
                    errs.append((proc.stderr or proc.stdout or "").strip())
            except (OSError, subprocess.TimeoutExpired) as exc:
                errs.append(str(exc))
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        if app_running(key):
            return False, f"{key}: не закрылся. {'; '.join(errs)}"
        return True, f"{key}: закрыла ({len(pids)} проц.)."

    for pid in pids:
        try:
            subprocess.run(["kill", "-TERM", str(pid)], timeout=10, check=False)
        except OSError:
            pass
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    return True, f"{key}: послала TERM ({len(pids)})."


def kill_apps(apps: List[str]) -> Tuple[bool, str]:
    lines: List[str] = []
    ok_all = True
    for a in apps:
        ok, msg = kill_app(a)
        lines.append(msg)
        ok_all = ok_all and ok
    return ok_all, "\n".join(lines)


def resolve_launch_exe(app: str, config: Config) -> Optional[Path]:
    key = app.strip().lower()
    try:
        if key == "unity":
            from ..unity.setup import find_unity_exe

            return find_unity_exe(config.unity_exe)
        if key == "blender":
            from ..blender.exe import resolve_blender_exe

            return resolve_blender_exe(config)
        if key == "cascadeur":
            from ..cascadeur.exe import resolve_cascadeur_exe

            return resolve_cascadeur_exe(config)
    except FileNotFoundError:
        return None
    return None


def restart_app(app: str, config: Config) -> Tuple[bool, str]:
    key = app.strip().lower()
    ok, msg = kill_app(key, wait_seconds=2.5)
    lines = [msg]
    exe = resolve_launch_exe(key, config)
    if exe is None:
        return False, "\n".join(lines) + f"\n{key}: exe не найден — не могу перезапустить."

    try:
        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | _CREATE_NO_WINDOW
            # Unity лучше с projectPath
            if key == "unity" and config.unity_project:
                from ..unity.setup import open_editor_command

                cmd = open_editor_command(Path(config.unity_project), exe)
                subprocess.Popen(cmd, **kwargs)  # noqa: S603
            else:
                subprocess.Popen([str(exe)], **kwargs)  # noqa: S603
        else:
            subprocess.Popen([str(exe)], start_new_session=True)  # noqa: S603
        lines.append(f"{key}: запускаю {exe.name}")
        return True, "\n".join(lines)
    except OSError as exc:
        return False, "\n".join(lines) + f"\nЗапуск: {exc}"


def status_apps(config: Config) -> str:
    lines = ["Приложения:"]
    for key in ("unity", "blender", "cascadeur"):
        running = "запущен" if app_running(key) else "нет"
        exe = resolve_launch_exe(key, config)
        exe_s = exe.name if exe else "exe?"
        lines.append(f"  • {key}: {running} ({exe_s})")
    return "\n".join(lines)
