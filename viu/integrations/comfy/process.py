"""Запуск локального ComfyUI (U:\\Viu\\ComfyUI)."""

from __future__ import annotations

import os
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
_CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def comfy_show_console() -> bool:
    """Показывать окно консоли ComfyUI (прогресс Wan). По умолчанию вкл. на Windows."""
    raw = os.environ.get("VIU_COMFY_SHOW_CONSOLE", "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return raw in ("1", "true", "yes", "on", "")


def comfy_open_browser_on_launch() -> bool:
    """Открыть http://127.0.0.1:8188 после успешного старта. По умолчанию вкл."""
    raw = os.environ.get("VIU_COMFY_OPEN_BROWSER", "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return raw in ("1", "true", "yes", "on", "")


def open_comfy_browser(config: Config) -> str:
    """Открыть UI Comfy в браузере (у Comfy нет отдельного desktop-окна)."""
    if not comfy_open_browser_on_launch():
        return ""
    import webbrowser

    url = str(getattr(config, "comfy_url", None) or "http://127.0.0.1:8188")
    try:
        webbrowser.open(url)
        return f"Браузер: {url} (это и есть окно ComfyUI)"
    except Exception as exc:  # noqa: BLE001
        return f"Не открыла браузер ({exc}). Открой сама: {url}"

# Не ставить «просто torch» с PyPI — +cpu новее многих cu-сборок и pip не даунгрейдит.
# cu124/cu121 — только до cp313. На Python 3.14 (у Дена) колёс нет → cu126/cu130.
_WHL = "https://download.pytorch.org/whl"
# (label, index_url, pkgs)
_TORCH_CUDA_STACKS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    (
        "cu124/2.6",
        f"{_WHL}/cu124",
        ("torch==2.6.0+cu124", "torchvision==0.21.0+cu124", "torchaudio==2.6.0+cu124"),
    ),
    (
        "cu121/2.5",
        f"{_WHL}/cu121",
        ("torch==2.5.1+cu121", "torchvision==0.20.1+cu121", "torchaudio==2.5.1+cu121"),
    ),
    (
        "cu126/2.13",
        f"{_WHL}/cu126",
        ("torch==2.13.0+cu126", "torchvision==0.28.0+cu126", "torchaudio==2.11.0+cu126"),
    ),
    (
        "cu130/2.13",
        f"{_WHL}/cu130",
        ("torch==2.13.0+cu130", "torchvision==0.28.0+cu130", "torchaudio==2.11.0+cu130"),
    ),
    (
        "cu126/2.9",
        f"{_WHL}/cu126",
        ("torch==2.9.1+cu126", "torchvision==0.24.1+cu126", "torchaudio==2.9.1+cu126"),
    ),
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


def _python_version(py: Path, root: Path) -> Tuple[int, int]:
    ok, out = _run_py(
        py,
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        cwd=root,
        timeout=30,
    )
    if not ok:
        return (0, 0)
    m = re.search(r"(\d+)\.(\d+)", out)
    if not m:
        return (0, 0)
    return int(m.group(1)), int(m.group(2))


def cuda_stacks_for_python(major: int, minor: int) -> List[Tuple[str, str, Tuple[str, ...]]]:
    """Подобрать CUDA-стеки под версию Python (cp314 → без cu124)."""
    if major == 0:
        return list(_TORCH_CUDA_STACKS)
    # cp314+: только cu126/cu130 (cu124/cu121 wheels = none)
    if (major, minor) >= (3, 14):
        return [s for s in _TORCH_CUDA_STACKS if s[0].startswith(("cu126", "cu130"))]
    # cp313: cu124 2.6 есть; cu126 как запас
    if (major, minor) >= (3, 13):
        prefer = ("cu124/2.6", "cu126/2.13", "cu126/2.9", "cu130/2.13")
        by_label = {s[0]: s for s in _TORCH_CUDA_STACKS}
        return [by_label[k] for k in prefer if k in by_label]
    # cp310–312: классика cu124 → cu121 → новые
    prefer = ("cu124/2.6", "cu121/2.5", "cu126/2.13", "cu126/2.9")
    by_label = {s[0]: s for s in _TORCH_CUDA_STACKS}
    return [by_label[k] for k in prefer if k in by_label]


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
    """CUDA torch под версию Python; иначе CPU. Снос +cpu обязателен."""
    want_cuda = nvidia_gpu_available()
    ok, ver, has_cuda = _torch_info(py, root)
    notes: List[str] = []
    py_ver = _python_version(py, root)
    py_label = f"{py_ver[0]}.{py_ver[1]}" if py_ver[0] else "?"

    if ok and want_cuda and has_cuda and not force_reinstall:
        return True, f"python={py} ({py_label}) torch={ver} CUDA=yes"
    if ok and (not want_cuda) and not force_reinstall:
        return True, f"python={py} ({py_label}) torch={ver} (CPU, nvidia-smi нет)"

    if ok and want_cuda and not has_cuda:
        notes.append(
            f"Был {ver} без CUDA (Python {py_label}) — сношу и ставлю CUDA-сборку "
            f"(pip --upgrade с +cpu не даунгрейдит)."
        )

    notes.append(_pip_uninstall_torch(py, cwd=root) or "uninstall torch: ok")

    if want_cuda:
        stacks = cuda_stacks_for_python(*py_ver)
        ok_p = False
        pip_out = ""
        for label, index, pkgs in stacks:
            notes.append(f"pip install --force-reinstall {pkgs[0]} ({label}, py{py_label})…")
            ok_p, pip_out = _pip_install(
                py,
                ["--no-cache-dir", "--force-reinstall", *pkgs, "--index-url", index],
                cwd=root,
            )
            if ok_p:
                notes.append(f"{label}: OK")
                break
            notes.append(f"{label} не встал: {pip_out[-400:]}")
            _pip_uninstall_torch(py, cwd=root)
        if not ok_p:
            notes.append("Все CUDA-индексы пусты для этой Python — ставлю CPU + Comfy --cpu.")
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
    if want_cuda and ("+cpu" in ver2.lower() or not cuda2):
        hint = ""
        if py_ver >= (3, 14):
            hint = " (для 3.14 нужны колёса cu126/cu130; cu124 их не имеет)."
        notes.append(
            f"torch={ver2} всё ещё без CUDA — Comfy с --cpu.{hint} "
            "Проверь драйвер NVIDIA."
        )
    else:
        notes.append(f"python={py} ({py_label}) torch={ver2} CUDA={'yes' if cuda2 else 'no'}")
    return True, "\n".join(notes)


def preflight_comfy_python(root: Path, py: Path) -> Tuple[bool, str]:
    return ensure_torch_for_comfy(root, py, force_reinstall=False)


def _pids_on_port(port: int) -> List[int]:
    pids: List[int] = []
    if sys.platform == "win32":
        try:
            ps = (
                f"(Get-NetTCPConnection -LocalPort {int(port)} -State Listen "
                f"-ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess)"
            )
            kwargs: dict = {"capture_output": True, "text": True, "timeout": 30}
            kwargs["creationflags"] = _CREATE_NO_WINDOW
            proc = subprocess.run(  # noqa: S603
                ["powershell", "-NoProfile", "-Command", ps],
                **kwargs,
            )
            for line in (proc.stdout or "").splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
        return sorted(set(pids))
    try:
        proc = subprocess.run(  # noqa: S603
            ["lsof", "-ti", f":{int(port)}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return sorted(set(pids))


def stop_comfy_on_port(port: int) -> str:
    """Остановить процесс, слушающий :port (перед рестартом с CUDA)."""
    pids = _pids_on_port(port)
    if not pids:
        return f"на :{port} никто не слушает"
    killed: List[str] = []
    for pid in pids:
        try:
            if sys.platform == "win32":
                subprocess.run(  # noqa: S603
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=_CREATE_NO_WINDOW,
                )
            else:
                import os
                import signal

                os.kill(pid, signal.SIGTERM)
            killed.append(str(pid))
        except (OSError, subprocess.TimeoutExpired):
            continue
    time.sleep(1.5)
    return f"остановила pid {', '.join(killed)} на :{port}" if killed else f":{port} — не убила"


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
    """Старт main.py.

    На Windows по умолчанию — отдельная консоль (прогресс генерации виден).
    VIU_COMFY_SHOW_CONSOLE=0 — скрытый процесс + лог .viu/logs/comfy_launch.log.
    UI Comfy — только браузер :8188, отдельного desktop-окна нет.
    """
    py = py or _python_for_comfy(root)
    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    port = _parse_port(str(url))
    log_path = _launch_log_path(config, root)
    main_py = root / "main.py"
    cmd = [
        str(py),
        str(main_py),
        "--listen",
        "127.0.0.1",
        "--port",
        str(port),
        "--enable-cors-header",
        "*",
        "--disable-cuda-malloc",
    ]
    if extra_args:
        cmd.extend(extra_args)
    show_console = comfy_show_console() and sys.platform == "win32"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_f = log_path.open("w", encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"Не открыла лог {log_path}: {exc}", None

    mode = "console" if show_console else "hidden+logfile"
    log_f.write(f"cmd: {' '.join(cmd)}\ncwd: {root}\nmode: {mode}\n\n")
    log_f.flush()
    try:
        kwargs: dict = {
            "cwd": str(root),
            "stdin": subprocess.DEVNULL,
        }
        if show_console:
            # Прогресс в окне консоли; в лог только шапка запуска.
            kwargs["creationflags"] = _CREATE_NEW_CONSOLE
            try:
                log_f.close()
            except OSError:
                pass
            log_f = None  # type: ignore[assignment]
        else:
            kwargs["stdout"] = log_f
            kwargs["stderr"] = subprocess.STDOUT
            if sys.platform == "win32":
                kwargs["creationflags"] = _CREATE_NO_WINDOW
            else:
                kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)  # noqa: S603
    except OSError as exc:
        if log_f is not None:
            try:
                log_f.close()
            except OSError:
                pass
        return False, f"Не смогла запустить ComfyUI: {exc}", None

    if log_f is not None:
        try:
            log_f.close()
        except OSError:
            pass
    hint = "консоль+браузер" if show_console else f"лог={log_path}"
    return True, f"pid={proc.pid} {hint}", proc


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


def _finalize_comfy_start(
    config: Config,
    client: ComfyClient,
    parts: List[str],
    *,
    port: int,
    wait_seconds: float,
    root: Path,
) -> Tuple[bool, str]:
    """После старта Comfy: дождаться ReActor, при FAIL — repair + второй рестарт."""
    from .face_refs import face_swap_status_line, reactor_needs_reload
    from .reactor_diag import (
        probe_reactor_deps,
        reactor_diagnose,
        repair_reactor_dependencies,
        wait_for_reactor_node,
    )

    browser_note = open_comfy_browser(config)
    if browser_note:
        parts.append(browser_note)

    if not reactor_needs_reload(config, client):
        parts.append(face_swap_status_line(config, client=client))
        return True, "\n".join(parts)

    cls = wait_for_reactor_node(client, timeout=min(60.0, wait_seconds))
    if cls:
        parts.append(face_swap_status_line(config, client=client))
        return True, "\n".join(parts)

    ok_imp, _ = probe_reactor_deps(config, timeout=30.0)
    if not ok_imp:
        parts.append("ReActor deps MISSING — pip…")
        ok_fix, fix_msg = repair_reactor_dependencies(config)
        parts.append(fix_msg)
        if ok_fix:
            parts.append(stop_comfy_on_port(port))
            py = _python_for_comfy(root)
            _, _, has_cuda = _torch_info(py, root)
            extra: List[str] = [] if has_cuda else ["--cpu"]
            ok_w2, _, tail2 = _launch_and_wait_comfy(
                config,
                root,
                client=client,
                port=port,
                wait_seconds=wait_seconds,
                extra=extra,
            )
            parts.extend(tail2)
            if ok_w2 and wait_for_reactor_node(client, timeout=min(90.0, wait_seconds)):
                parts.append(face_swap_status_line(config, client=client))
                return True, "\n".join(parts)

    parts.append(face_swap_status_line(config, client=client))
    parts.append(reactor_diagnose(config, client=client))
    return True, "\n".join(parts)


def _launch_and_wait_comfy(
    config: Config,
    root: Path,
    *,
    client: ComfyClient,
    port: int,
    wait_seconds: float,
    extra: Optional[List[str]] = None,
) -> Tuple[bool, str, List[str]]:
    """Запуск процесса Comfy и ожидание API. Возвращает (ok, wait_msg, parts)."""
    py = _python_for_comfy(root)
    log_path = _launch_log_path(config, root)
    parts: List[str] = []
    ok_l, launch_msg, proc = launch_comfy_process(
        config, root, py=py, extra_args=list(extra or [])
    )
    parts.append(launch_msg)
    if not ok_l:
        return False, "\n".join(parts), parts
    ok_w, wait_msg = wait_comfy_api(
        client, proc=proc, log_path=log_path, wait_seconds=wait_seconds
    )
    parts.append(wait_msg)
    return ok_w, wait_msg, parts


def ensure_comfy_running(
    config: Config,
    *,
    wait_seconds: float = 180.0,
    auto_install: bool = True,
    force_restart: bool = False,
    reload_if_reactor_missing: bool = True,
) -> Tuple[bool, str]:
    """Пинг API; если нет — установить при необходимости, CUDA torch, запуск, ждать."""
    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    port = _parse_port(str(url))
    client = ComfyClient(base_url=str(url), timeout=5.0)
    ok, msg = client.ping()

    root = resolve_comfy_root(config)
    if root is not None and not looks_like_comfy_root(root):
        try:
            config.comfy_root = ""
        except Exception:
            pass
        root = None

    def _reactor_reload_needed() -> bool:
        if not reload_if_reactor_missing or root is None or not ok:
            return False
        from .face_refs import reactor_needs_reload

        return reactor_needs_reload(config, client)

    if ok and (force_restart or _reactor_reload_needed()):
        reason = (
            "принудительный restart"
            if force_restart
            else "ReActor в папке, но нода не в API"
        )
        parts_reload: List[str] = [f"Comfy на :{port} — {reason}, перезапускаю…", stop_comfy_on_port(port)]
        py_r = _python_for_comfy(root) if root else None
        if root is None or py_r is None:
            return False, "\n".join(parts_reload + ["ComfyUI root не найден"])
        _, _, has_cuda_r = _torch_info(py_r, root)
        extra_r: List[str] = [] if has_cuda_r else ["--cpu"]
        ok_w, _, parts_reload_tail = _launch_and_wait_comfy(
            config,
            root,
            client=client,
            port=port,
            wait_seconds=wait_seconds,
            extra=extra_r,
        )
        parts_reload.extend(parts_reload_tail)
        if ok_w:
            return _finalize_comfy_start(
                config, client, parts_reload, port=port, wait_seconds=wait_seconds, root=root
            )
        return False, "\n".join(parts_reload)

    # Уже запущен на CPU при наличии GPU → поднять CUDA torch и перезапустить.
    if ok and root is not None and nvidia_gpu_available():
        py0 = _python_for_comfy(root)
        _, ver0, has_cuda0 = _torch_info(py0, root)
        if not has_cuda0:
            parts_up: List[str] = [
                f"Comfy уже на :{port}, но torch={ver0} без CUDA — чиню и перезапускаю…",
                stop_comfy_on_port(port),
            ]
            ok_t, t_msg = ensure_torch_for_comfy(root, py0, force_reinstall=True)
            parts_up.append(t_msg)
            if not ok_t:
                return False, "\n".join(parts_up)
            _, _, has_cuda1 = _torch_info(py0, root)
            extra0: List[str] = [] if has_cuda1 else ["--cpu"]
            if extra0:
                parts_up.append("CUDA всё ещё нет → снова --cpu")
            log_path0 = _launch_log_path(config, root)
            ok_l0, launch0, proc0 = launch_comfy_process(
                config, root, py=py0, extra_args=extra0
            )
            parts_up.append(launch0)
            if not ok_l0:
                return False, "\n".join(parts_up)
            ok_w0, wait0 = wait_comfy_api(
                client, proc=proc0, log_path=log_path0, wait_seconds=wait_seconds
            )
            parts_up.append(wait0 if ok_w0 else wait0)
            if ok_w0:
                parts_up.append(
                    f"ComfyUI OK ({'CUDA' if has_cuda1 else 'CPU'}) из {root}."
                )
                browser_note = open_comfy_browser(config)
                if browser_note:
                    parts_up.append(browser_note)
                return True, "\n".join(parts_up)
            return False, "\n".join(parts_up)
        return True, f"{msg}\ntorch={ver0} CUDA=yes"
    if ok:
        from .face_refs import face_swap_status_line

        return True, f"{msg}\n{face_swap_status_line(config, client=client)}"

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

    # Порт может быть занят чужим/зомби-процессом
    if _pids_on_port(port):
        parts.append(stop_comfy_on_port(port))

    ok_l, launch_msg, proc = launch_comfy_process(config, root, py=py, extra_args=extra)
    parts.append(launch_msg)
    if not ok_l:
        return False, "\n".join(parts)

    ok_w, wait_msg = wait_comfy_api(
        client, proc=proc, log_path=log_path, wait_seconds=wait_seconds
    )
    if ok_w:
        parts.append(f"ComfyUI OK из {root}. {wait_msg}")
        return _finalize_comfy_start(
            config, client, parts, port=port, wait_seconds=wait_seconds, root=root
        )

    parts.append(wait_msg)

    # Авто-ремонт: CPU при наличии GPU → жёсткий CUDA stack + retry
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
        parts.append("Падение при старте — принудительно сношу torch и ставлю CUDA…")
        stop_comfy_on_port(port)
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
                    browser_note = open_comfy_browser(config)
                    if browser_note:
                        parts.append(browser_note)
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
