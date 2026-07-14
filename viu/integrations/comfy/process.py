"""Запуск локального ComfyUI (U:\\Viu\\ComfyUI)."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from ...config import Config
from .client import ComfyClient
from .paths import looks_like_comfy_root, resolve_comfy_root

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Стабильная связка под RTX 20/30/40 (у Дена 3060).
# Не ставить «просто torch» с PyPI — 2.13+cpu новее cu-сборок и pip не даунгрейдит.
_TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu124"
_TORCH_CUDA_PKGS = (
    "torch==2.6.0+cu124",
    "torchvision==0.21.0+cu124",
    "torchaudio==2.6.0+cu124",
)
_TORCH_CUDA_INDEX_ALT = "https://download.pytorch.org/whl/cu121"
_TORCH_CUDA_PKGS_ALT = (
    "torch==2.5.1+cu121",
    "torchvision==0.20.1+cu121",
    "torchaudio==2.5.1+cu121",
)
_TORCH_CPU_PKGS = ("torch", "torchvision", "torchaudio")


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


def extract_crash_summary(path: Path, *, max_chars: int = 2200) -> str:
    """Вытащить Traceback/Error из лога, а не случайный хвост dir()."""
    try:
        if not path.is_file():
            return "(лога запуска ещё нет)"
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(не прочитала лог: {exc})"
    if not text.strip():
        return "(лог пуст — процесс сразу умер или не писал вывод)"

    # Последний Traceback
    idx = text.rfind("Traceback (most recent call last)")
    if idx >= 0:
        block = text[idx:].strip()
        # обрезать огромные Did you mean: списки
        block = re.sub(
            r"Did you mean:.*?(?=\n\S|\Z)",
            "Did you mean: …",
            block,
            flags=re.DOTALL,
        )
        if len(block) > max_chars:
            block = block[: max_chars - 20] + "\n…(обрезано)"
        return block

    # Строки с Error/Exception
    lines = text.splitlines()
    err_lines = [
        ln
        for ln in lines
        if re.search(r"(Error|Exception|CRITICAL|ModuleNotFoundError|ImportError)", ln)
    ]
    if err_lines:
        chunk = "\n".join(err_lines[-40:])
        if len(chunk) > max_chars:
            chunk = chunk[-max_chars:]
        return chunk

    # fallback — конец лога без гигантских списков атрибутов
    tail = text.strip()[-max_chars:]
    if len(tail) > 200 and tail.count("'") > 80:
        return (
            "Лог похож на дамп атрибутов (часто AttributeError + torch). "
            "Полный файл: " + str(path)
        )
    return "…\n" + tail if len(text) > max_chars else tail


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


def nvidia_gpu_available() -> bool:
    try:
        kwargs: dict = {"capture_output": True, "text": True, "timeout": 15}
        if sys.platform == "win32":
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        proc = subprocess.run(["nvidia-smi", "-L"], **kwargs)  # noqa: S603
        return proc.returncode == 0 and bool((proc.stdout or "").strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def _pip_install(py: Path, args: List[str], *, cwd: Path) -> Tuple[bool, str]:
    try:
        kwargs: dict = {
            "cwd": str(cwd),
            "capture_output": True,
            "text": True,
            "timeout": 2400,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        proc = subprocess.run([str(py), "-m", "pip", "install", *args], **kwargs)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()[-1200:]
    return proc.returncode == 0, out


def _torch_info(py: Path, root: Path) -> Tuple[bool, str, bool]:
    """(ok, version_line, cuda_available)."""
    code = (
        "import torch; "
        "print(torch.__version__); "
        "print('CUDA' if torch.cuda.is_available() else 'CPU')"
    )
    ok, out = _run_py(py, code, cwd=root, timeout=90)
    if not ok:
        return False, out, False
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    ver = lines[0] if lines else out
    cuda = any(ln.upper() == "CUDA" for ln in lines)
    return True, ver, cuda


def _pip_uninstall_torch(py: Path, *, cwd: Path) -> str:
    try:
        kwargs: dict = {
            "cwd": str(cwd),
            "capture_output": True,
            "text": True,
            "timeout": 600,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        proc = subprocess.run(  # noqa: S603
            [str(py), "-m", "pip", "uninstall", "-y", "torch", "torchvision", "torchaudio"],
            **kwargs,
        )
        return ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:] or "uninstall ok"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)


def ensure_torch_for_comfy(root: Path, py: Path, *, force_reinstall: bool = False) -> Tuple[bool, str]:
    """Поставить CUDA torch (cu124); если нет GPU — CPU. Снос старого +cpu обязателен."""
    want_cuda = nvidia_gpu_available()
    ok, ver, has_cuda = _torch_info(py, root)
    notes: List[str] = []

    if ok and want_cuda and has_cuda and not force_reinstall:
        return True, f"python={py} torch={ver} CUDA=yes"
    if ok and (not want_cuda) and not force_reinstall:
        return True, f"python={py} torch={ver} (CPU, nvidia-smi нет)"

    if ok and want_cuda and not has_cuda:
        notes.append(f"Был {ver} без CUDA — сношу и ставлю cu124 (не даунгрейдится через --upgrade).")

    notes.append(_pip_uninstall_torch(py, cwd=root) or "uninstall torch: ok")

    if want_cuda:
        notes.append("pip install --force-reinstall torch==2.6.0+cu124 …")
        ok_p, pip_out = _pip_install(
            py,
            [
                "--no-cache-dir",
                "--force-reinstall",
                *_TORCH_CUDA_PKGS,
                "--index-url",
                _TORCH_CUDA_INDEX,
            ],
            cwd=root,
        )
        if not ok_p:
            notes.append(f"cu124 не встал: {pip_out[-500:]}\nПробую cu121…")
            _pip_uninstall_torch(py, cwd=root)
            ok_p, pip_out = _pip_install(
                py,
                [
                    "--no-cache-dir",
                    "--force-reinstall",
                    *_TORCH_CUDA_PKGS_ALT,
                    "--index-url",
                    _TORCH_CUDA_INDEX_ALT,
                ],
                cwd=root,
            )
        if not ok_p:
            notes.append(f"cu121 тоже: {pip_out[-500:]}\nСтавлю CPU + Comfy --cpu.")
            _pip_uninstall_torch(py, cwd=root)
            ok_p, pip_out = _pip_install(
                py,
                ["--no-cache-dir", "--force-reinstall", "--upgrade", *_TORCH_CPU_PKGS],
                cwd=root,
            )
            if not ok_p:
                return False, "\n".join(notes) + f"\nCPU: {pip_out}"
    else:
        notes.append("nvidia-smi нет — CPU torch")
        ok_p, pip_out = _pip_install(
            py,
            ["--no-cache-dir", "--force-reinstall", "--upgrade", *_TORCH_CPU_PKGS],
            cwd=root,
        )
        if not ok_p:
            return False, "\n".join(notes) + f"\n{pip_out}"

    ok2, ver2, cuda2 = _torch_info(py, root)
    if not ok2:
        return False, "\n".join(notes) + f"\nПосле установки import torch: {ver2}"
    # pip мог оставить +cpu, если index не сработал — ловим по версии
    if want_cuda and ok2 and ("+cpu" in ver2.lower() or not cuda2):
        notes.append(
            f"torch={ver2} всё ещё без CUDA — Comfy буду запускать с --cpu "
            "(медленнее, но работает). Проверь драйвер NVIDIA / CUDA 12.x."
        )
    else:
        notes.append(f"python={py} torch={ver2} CUDA={'yes' if cuda2 else 'no'}")
    return True, "\n".join(notes)


def preflight_comfy_python(root: Path, py: Path) -> Tuple[bool, str]:
    return ensure_torch_for_comfy(root, py, force_reinstall=False)


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
    extra_args: Optional[List[str]] = None,
) -> Tuple[bool, str, Optional[subprocess.Popen]]:
    """Старт main.py с логом (не глотаем stderr)."""
    py = py or _python_for_comfy(root)
    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    port = _parse_port(str(url))
    log_path = _launch_log_path(config, root)
    main_py = root / "main.py"
    cmd = [
        str(py),
        str(main_py),
        "--listen",
        "--port",
        str(port),
        "--disable-cuda-malloc",
    ]
    if extra_args:
        cmd.extend(extra_args)
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
                f"Суть ошибки:\n{extract_crash_summary(log_path)}"
            )
        ok, last = client.ping()
        if ok:
            return True, last
        time.sleep(2.0)
    extra = ""
    if proc is not None and proc.poll() is None:
        extra = f"\nПроцесс ещё жив (pid={proc.pid}), но :8188 молчит."
    return False, (
        f"API не ответил за {wait_seconds:.0f}s.\n{last}{extra}\n"
        f"Суть из лога:\n{extract_crash_summary(log_path)}"
    )


def ensure_comfy_running(
    config: Config,
    *,
    wait_seconds: float = 180.0,
    auto_install: bool = True,
) -> Tuple[bool, str]:
    """Пинг API; если нет — установить при необходимости, CUDA torch, запуск, ждать."""
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
    ok_pf, pf_msg = ensure_torch_for_comfy(root, py)
    if not ok_pf:
        parts = [pf_msg]
        if install_note:
            parts.insert(0, install_note)
        return False, "\n".join(parts)

    log_path = _launch_log_path(config, root)
    parts: List[str] = []
    if install_note:
        parts.append(install_note)
    parts.append(pf_msg)

    _, _, has_cuda = _torch_info(py, root)
    extra: List[str] = []
    if not has_cuda:
        extra.append("--cpu")
        parts.append("torch без CUDA → запуск Comfy с --cpu")

    ok_l, launch_msg, proc = launch_comfy_process(config, root, py=py, extra_args=extra)
    parts.append(launch_msg)
    if not ok_l:
        return False, "\n".join(parts)

    ok_w, wait_msg = wait_comfy_api(
        client, proc=proc, log_path=log_path, wait_seconds=wait_seconds
    )
    if ok_w:
        parts.append(f"ComfyUI OK из {root}. {wait_msg}")
        return True, "\n".join(parts)

    parts.append(wait_msg)

    # Авто-ремонт: CPU при наличии GPU → жёсткий cu124 + retry
    summary = extract_crash_summary(log_path).lower()
    should_fix_torch = (nvidia_gpu_available() and not has_cuda) or any(
        k in summary
        for k in (
            "not compiled with cuda",
            "attributeerror",
            "dll load",
            "c10.dll",
            "cuda enabled",
        )
    )
    if should_fix_torch:
        parts.append("Падение при старте — принудительно сношу torch и ставлю cu124…")
        ok_t, t_msg = ensure_torch_for_comfy(root, py, force_reinstall=True)
        parts.append(t_msg)
        if ok_t:
            _, _, has_cuda2 = _torch_info(py, root)
            extra2: List[str] = [] if has_cuda2 else ["--cpu"]
            if extra2:
                parts.append("CUDA всё ещё нет → --cpu")
            ok_l2, launch_msg2, proc2 = launch_comfy_process(
                config, root, py=py, extra_args=extra2
            )
            parts.append(launch_msg2)
            if ok_l2:
                ok_w2, wait_msg2 = wait_comfy_api(
                    client, proc=proc2, log_path=log_path, wait_seconds=wait_seconds
                )
                if ok_w2:
                    parts.append(f"ComfyUI OK после ремонта torch. {wait_msg2}")
                    return True, "\n".join(parts)
                parts.append(wait_msg2)

    parts.append(
        "Не делай comfy_install заново. Лог: "
        f"{log_path}. После правки torch — снова comfy_ensure."
    )
    return False, "\n".join(parts)


def comfy_python(config: Config) -> Optional[Path]:
    root = resolve_comfy_root(config)
    if root is None:
        return None
    return _python_for_comfy(root)
