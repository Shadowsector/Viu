"""Проверка и завершение процесса Unity Editor (Windows/Linux)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def unity_lockfile(project_root: Path) -> Path:
    return project_root / "Temp" / "UnityLockfile"


def unity_pids() -> List[int]:
    """PID процессов Unity.exe (редактор, не Hub)."""
    if sys.platform == "win32":
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Unity.exe", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                creationflags=_CREATE_NO_WINDOW,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        pids: List[int] = []
        for line in (proc.stdout or "").splitlines():
            if "Unity.exe" not in line:
                continue
            # "Unity.exe","12345","Console","1","123 456 K"
            parts = line.split('","')
            if len(parts) < 2:
                continue
            try:
                pids.append(int(parts[1].strip('"')))
            except ValueError:
                continue
        return pids

    try:
        proc = subprocess.run(
            ["pgrep", "-x", "Unity"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    pids: List[int] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def unity_process_running() -> bool:
    return bool(unity_pids())


def kill_unity_processes(wait_seconds: float = 2.0) -> Tuple[bool, str]:
    """Завершить все Unity.exe. Возвращает (успех, сообщение)."""
    pids = unity_pids()
    if not pids:
        return True, "Unity.exe не запущен."

    if sys.platform == "win32":
        try:
            proc = subprocess.run(
                ["taskkill", "/F", "/IM", "Unity.exe"],
                capture_output=True,
                text=True,
                creationflags=_CREATE_NO_WINDOW,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"Не удалось завершить Unity: {exc}"
        if proc.returncode not in (0, 128):  # 128 = процесс уже завершён
            err = (proc.stderr or proc.stdout or "").strip()
            return False, f"taskkill вернул {proc.returncode}: {err}"
    else:
        for pid in pids:
            try:
                subprocess.run(["kill", "-TERM", str(pid)], timeout=10, check=False)
            except OSError:
                pass

    if wait_seconds > 0:
        time.sleep(wait_seconds)
    if unity_process_running():
        return False, "Unity.exe всё ещё в процессах — закрой вручную в Диспетчере задач."
    return True, f"Закрыл Unity ({len(pids)} проц.)."


def clear_unity_lockfile(project_root: Path) -> bool:
    lock = unity_lockfile(project_root)
    if lock.is_file():
        try:
            lock.unlink()
            return True
        except OSError:
            return False
    return False


def prepare_unity_for_batch(project_root: Path, *, auto_kill: bool = True) -> Tuple[bool, str]:
    """
  Подготовить проект к batchmode: закрыть Unity и убрать lockfile.
  Если Unity.exe не запущен, но lockfile остался после сбоя — просто удаляем его.
  """
    notes: List[str] = []
    lock = unity_lockfile(project_root)

    if unity_process_running():
        if not auto_kill:
            return (
                False,
                "Unity сейчас запущен. Закрой окно редактора и повтори — "
                "или дай Вью закрыть его самой (она умеет).",
            )
        ok, msg = kill_unity_processes()
        notes.append(msg)
        if not ok:
            return False, msg

    if lock.is_file():
        if clear_unity_lockfile(project_root):
            notes.append("Убрала старый Temp/UnityLockfile (Unity уже был закрыт).")
        else:
            return (
                False,
                "Не могу удалить Temp/UnityLockfile — проверь права на папку проекта.",
            )

    if notes:
        return True, " ".join(notes)
    return True, ""


def unity_blocks_batch(project_root: Path) -> bool:
    """True, если batchmode сейчас невозможен (живой процесс или lockfile)."""
    return unity_process_running() or unity_lockfile(project_root).is_file()
