"""Запуск локального ComfyUI (U:\\Viu\\ComfyUI)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from ...config import Config
from .client import ComfyClient
from .paths import looks_like_comfy_root, resolve_comfy_root

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _python_for_comfy(root: Path) -> Path:
    candidates = [
        root / "python_embeded" / "python.exe",
        root / "python_embedded" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",
        root / ".venv" / "bin" / "python",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return Path(sys.executable)


def _launch_log_path(config: Config, root: Path) -> Path:
    try:
        log_dir = config.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / "comfy_launch.log"
    except OSError:
        return root / "viu_comfy_launch.log"


def _tail_log(path: Path, *, max_chars: int = 1800) -> str:
    try:
        if not path.is_file():
            return "(лога запуска ещё нет)"
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(не прочитала лог: {exc})"
    text = text.strip()
    if not text:
        return "(лог пуст — процесс сразу умер или не писал вывод)"
    if len(text) > max_chars:
        return "…\n" + text[-max_chars:]
    return text


def _run_py(py: Path, code: str, *, cwd: Path, timeout: float = 60) -> Tuple[bool, str]:
    try:
        kwargs: dict = {
            "cwd": str(cwd),
            "capture_output": True,
            "text": True,
            "timeout": timeout,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        proc = subprocess.run([str(py), "-c", code], **kwargs)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode == 0, out[-1500:] or f"exit {proc.returncode}"


def preflight_comfy_python(root: Path, py: Path) -> Tuple[bool, str]:
    """Проверить, что interpreter видит torch (иначе сервер падает сразу)."""
    ok, out = _run_py(py, "import torch; print(torch.__version__)", cwd=root, timeout=90)
    if ok:
        return True, f"python={py} torch={out.strip()}"
    # частая дыра после pip install -r requirements: нет torch
    tip = (
        f"Interpreter {py} не импортирует torch.\n{out}\n"
        "Ставлю torch (CPU wheel) — для CUDA потом можно заменить."
    )
    try:
        kwargs: dict = {
            "cwd": str(root),
            "capture_output": True,
            "text": True,
            "timeout": 1800,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        proc = subprocess.run(  # noqa: S603
            [str(py), "-m", "pip", "install", "torch", "torchvision", "torchaudio"],
            **kwargs,
        )
        pip_out = ((proc.stdout or "") + (proc.stderr or "")).strip()[-800:]
        if proc.returncode != 0:
            return False, tip + f"\npip torch failed: {pip_out}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, tip + f"\npip torch: {exc}"

    ok2, out2 = _run_py(py, "import torch; print(torch.__version__)", cwd=root, timeout=90)
    if not ok2:
        return False, tip + f"\nПосле pip всё ещё нет torch: {out2}"
    return True, f"python={py} torch={out2.strip()} (поставила CPU torch)"


def _parse_port(url: str) -> int:
    try:
        from urllib.parse import urlparse

        p = urlparse(url)
        if p.port:
            return int(p.port)
    except Exception:
        pass
    return 8188


def launch_comfy_process(
    config: Config,
    root: Path,
    *,
    py: Optional[Path] = None,
) -> Tuple[bool, str, Optional[subprocess.Popen]]:
    """Старт main.py с логом (не глотаем stderr)."""
    py = py or _python_for_comfy(root)
    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    port = _parse_port(str(url))
    log_path = _launch_log_path(config, root)
    main_py = root / "main.py"
    # --listen без IP = 0.0.0.0; так надёжнее на Windows, чем только 127.0.0.1
    cmd = [str(py), str(main_py), "--listen", "--port", str(port)]
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_f = log_path.open("w", encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"Не открыла лог {log_path}: {exc}", None

    log_f.write(f"cmd: {' '.join(cmd)}\ncwd: {root}\n\n")
    log_f.flush()
    try:
        kwargs: dict = {
            "cwd": str(root),
            "stdout": log_f,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            # CREATE_NO_WINDOW, но БЕЗ DETACHED — иначе не видим падение и poll()
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
    except OSError as exc:
        try:
            log_f.close()
        except OSError:
            pass
        return False, f"Не смогла запустить ComfyUI: {exc}", None

    try:
        log_f.close()
    except OSError:
        pass
    return True, f"pid={proc.pid} log={log_path}", proc


def wait_comfy_api(
    client: ComfyClient,
    *,
    proc: Optional[subprocess.Popen],
    log_path: Path,
    wait_seconds: float,
) -> Tuple[bool, str]:
    deadline = time.time() + max(20.0, wait_seconds)
    last = ""
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False, (
                f"ComfyUI процесс завершился с кодом {proc.returncode}.\n"
                f"Лог {log_path}:\n{_tail_log(log_path)}"
            )
        ok, last = client.ping()
        if ok:
            return True, last
        time.sleep(2.0)
    extra = ""
    if proc is not None and proc.poll() is None:
        extra = f"\nПроцесс ещё жив (pid={proc.pid}), но :8188 молчит — смотри лог."
    return False, (
        f"API не ответил за {wait_seconds:.0f}s.\n{last}{extra}\n"
        f"Лог {log_path}:\n{_tail_log(log_path)}"
    )


def ensure_comfy_running(
    config: Config,
    *,
    wait_seconds: float = 180.0,
    auto_install: bool = True,
) -> Tuple[bool, str]:
    """Пинг API; если нет — установить при необходимости, preflight, запуск, ждать."""
    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    client = ComfyClient(base_url=str(url), timeout=5.0)
    ok, msg = client.ping()
    if ok:
        return True, msg

    root = resolve_comfy_root(config)
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

    py = _python_for_comfy(root)
    ok_pf, pf_msg = preflight_comfy_python(root, py)
    if not ok_pf:
        parts = [pf_msg]
        if install_note:
            parts.insert(0, install_note)
        return False, "\n".join(parts)

    log_path = _launch_log_path(config, root)
    ok_l, launch_msg, proc = launch_comfy_process(config, root, py=py)
    if not ok_l:
        parts = [launch_msg, pf_msg]
        if install_note:
            parts.insert(0, install_note)
        return False, "\n".join(parts)

    ok_w, wait_msg = wait_comfy_api(
        client, proc=proc, log_path=log_path, wait_seconds=wait_seconds
    )
    parts: List[str] = []
    if install_note:
        parts.append(install_note)
    parts.append(pf_msg)
    parts.append(launch_msg)
    if ok_w:
        parts.append(f"ComfyUI OK из {root}. {wait_msg}")
        return True, "\n".join(parts)
    parts.append(wait_msg)
    parts.append(
        "Не делай comfy_install заново — установка уже есть. "
        "Исправь ошибку из лога (часто: torch/CUDA/custom nodes) и снова comfy_ensure."
    )
    return False, "\n".join(parts)


def comfy_python(config: Config) -> Optional[Path]:
    root = resolve_comfy_root(config)
    if root is None:
        return None
    return _python_for_comfy(root)
