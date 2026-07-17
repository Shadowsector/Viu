"""Метка сборки Viu — auto-reset lab после обновления."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..config import Config

_STAMP_FILE = "viu_build_stamp.txt"


def viu_build_stamp(config: Config | None = None) -> str:
    """Короткий идентификатор текущей сборки (git SHA или version)."""
    try:
        from ..updater import package_root

        root = package_root()
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        from .. import __version__

        return str(__version__)
    except Exception:
        return "unknown"


def persist_build_stamp(config: Config) -> str:
    stamp = viu_build_stamp(config)
    path = config.data_dir / "lab" / _STAMP_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stamp + "\n", encoding="utf-8")
    return stamp


def saved_build_stamp(config: Config) -> str:
    path = config.data_dir / "lab" / _STAMP_FILE
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def build_changed_since_last_run(config: Config) -> bool:
    current = viu_build_stamp(config)
    saved = saved_build_stamp(config)
    if not saved:
        return False
    return saved != current
