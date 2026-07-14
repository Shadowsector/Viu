"""Запуск локального ComfyUI (U:\\Viu\\ComfyUI)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from ...config import Config
from .client import ComfyClient
from .paths import resolve_comfy_root, looks_like_comfy_root

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)


def _python_for_comfy(root: Path) -> Path:
    candidates = [
        root / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
        root / "python_embeded" / "python.exe",
        root / "venv" / "bin" / "python",
        root / ".venv" / "bin" / "python",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return Path(sys.executable)


def ensure_comfy_running(
    config: Config,
    *,
    wait_seconds: float = 90.0,
    auto_install: bool = True,
) -> Tuple[bool, str]:
    """Пинг API; если нет — (опционально) установить, запустить main.py, дождаться."""
    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    client = ComfyClient(base_url=str(url), timeout=5.0)
    ok, msg = client.ping()
    if ok:
        return True, msg

    root = resolve_comfy_root(config)
    # Защита: никогда не запускать чужой main.py (unittest и т.п.)
    if root is not None and not looks_like_comfy_root(root):
        try:
            config.comfy_root = ""
        except Exception:
            pass
        root = None

    install_note = ""
    if root is None and auto_install:
        from .install import ensure_comfy_installed

        ok_i, install_note = ensure_comfy_installed(
            config, with_models=True, include_i2v=False, with_pip=True
        )
        root = resolve_comfy_root(config)
        if root is not None and not looks_like_comfy_root(root):
            root = None
        if not ok_i and root is None:
            return False, install_note

    if root is None:
        return False, (
            install_note
            or "ComfyUI не найден. Запусти comfy_install — Вью поставит в U:\\Viu\\ComfyUI."
        )
    if not looks_like_comfy_root(root):
        return False, f"Путь не похож на ComfyUI: {root}"

    main_py = root / "main.py"
    py = _python_for_comfy(root)
    cmd = [str(py), str(main_py), "--listen", "127.0.0.1", "--port", "8188"]
    try:
        kwargs: dict = {
            "cwd": str(root),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = _DETACHED | _CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)  # noqa: S603
    except OSError as exc:
        return False, f"Не смогла запустить ComfyUI: {exc}"

    deadline = time.time() + max(15.0, wait_seconds)
    last = msg
    while time.time() < deadline:
        time.sleep(2.0)
        ok, last = client.ping()
        if ok:
            parts = [f"ComfyUI запущена из {root}. {last}"]
            if install_note:
                parts.insert(0, install_note)
            return True, "\n".join(parts)
    parts = [
        f"Запустила ComfyUI ({root}), но API не ответил за {wait_seconds:.0f}s.\n{last}"
    ]
    if install_note:
        parts.insert(0, install_note)
    return False, "\n".join(parts)


def comfy_python(config: Config) -> Optional[Path]:
    root = resolve_comfy_root(config)
    if root is None:
        return None
    return _python_for_comfy(root)
