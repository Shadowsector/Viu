"""ReActor: диагностика загрузки нод, repair зависимостей."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Tuple

from ...config import Config
from .paths import resolve_comfy_root
from .process import _launch_log_path, _python_for_comfy

_REACTOR_DIR = "ComfyUI-ReActor"
_LOG_MARKERS = (
    "reactor",
    "insightface",
    "onnxruntime",
    "opencv",
    "segment_anything",
    "ultralytics",
    "custom_nodes",
    "importerror",
    "modulenotfounderror",
    "cannot import",
    "traceback",
)

# Минимум для ReActor; ultralytics/sam тянутся из requirements.txt отдельно.
_CORE_DEPS = (
    "numpy",
    "onnx",
    "cv2",
    "onnxruntime",
    "insightface",
    "torch",
)

_PIP_STEPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("opencv", ("opencv-python-headless>=4.7.0",)),
    ("onnxruntime", ("onnxruntime>=1.16.0",)),
    ("insightface", ("insightface>=0.7.3",)),
)


def _launch_log_path_for_config(config: Config, root: Path) -> Path:
    return _launch_log_path(config, root)


def list_reactor_node_classes(client) -> List[str]:
    from .client import ComfyClient

    if not isinstance(client, ComfyClient):
        return []
    try:
        info = client._get("/object_info")
    except Exception:
        return []
    if not isinstance(info, dict):
        return []
    return sorted(n for n in info if "reactor" in n.lower())


def reactor_errors_in_launch_log(config: Config, *, tail_lines: int = 80) -> str:
    root = resolve_comfy_root(config)
    if root is None:
        return ""
    log = _launch_log_path_for_config(config, root)
    if not log.is_file():
        return ""
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if not text.strip():
        return ""
    hits: List[str] = []
    for ln in text.splitlines():
        low = ln.lower()
        if any(m in low for m in _LOG_MARKERS):
            hits.append(ln.rstrip())
    if not hits:
        idx = text.lower().rfind("traceback")
        if idx >= 0:
            hits = text[idx:].splitlines()[:40]
    if not hits:
        return ""
    block = "\n".join(hits[-tail_lines:])
    if len(block) > 1800:
        block = block[-1800:]
    return block


def _run_py_snippet(
    config: Config,
    code: str,
    *,
    timeout: float = 45.0,
    cwd: Path | None = None,
) -> Tuple[bool, str]:
    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI root не найден"
    py = _python_for_comfy(root)
    try:
        proc = subprocess.run(
            [str(py), "-c", code],
            cwd=str(cwd or root),
            capture_output=True,
            text=True,
            timeout=max(5.0, timeout),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        )
    except subprocess.TimeoutExpired as exc:
        return False, f"таймаут {exc.timeout}s (python -c)"
    except OSError as exc:
        return False, str(exc)
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode == 0:
        return True, out.splitlines()[-1] if out else "OK"
    return False, out[-2000:] if out else f"exit {proc.returncode}"


def probe_reactor_deps(config: Config, *, timeout: float = 45.0) -> Tuple[bool, str, List[str]]:
    """Быстро: есть ли базовые модули в venv Comfy (без import nodes.py)."""
    checks = "\n".join(
        f"    importlib.import_module({mod!r})"
        for mod in ("numpy", "onnx", "cv2", "onnxruntime", "insightface", "torch")
    )
    code = f"""
import importlib, sys
missing = []
for mod in {list(_CORE_DEPS)!r}:
    try:
        importlib.import_module('cv2' if mod == 'cv2' else mod)
    except Exception as exc:
        missing.append(f"{{mod}}: {{exc}}")
if missing:
    print("MISSING")
    print("\\n".join(missing))
    sys.exit(1)
print("OK deps")
"""
    ok, msg = _run_py_snippet(config, code, timeout=timeout)
    missing: List[str] = []
    if not ok and msg:
        for ln in msg.splitlines():
            if ": " in ln and not ln.startswith("MISSING"):
                missing.append(ln.split(":", 1)[0].strip())
    return ok, msg, missing


def probe_reactor_import(config: Config, *, full: bool = False, timeout: float = 120.0) -> Tuple[bool, str]:
    """full=True — тяжёлый import nodes.py (может занять минуты)."""
    if not full:
        ok, msg, _ = probe_reactor_deps(config, timeout=min(timeout, 60.0))
        return ok, msg

    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI root не найден"
    reactor = root / "custom_nodes" / _REACTOR_DIR
    nodes_py = reactor / "nodes.py"
    if not nodes_py.is_file():
        return False, f"нет {reactor}"
    code = f"""
import traceback
import importlib.util
path = {str(nodes_py)!r}
try:
    spec = importlib.util.spec_from_file_location("viu_reactor_nodes", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    keys = list(getattr(mod, "NODE_CLASS_MAPPINGS", {{}}).keys())
    print("OK " + ",".join(keys[:6]))
except Exception:
    traceback.print_exc()
    raise SystemExit(1)
"""
    return _run_py_snippet(config, code, timeout=timeout)


def _pip_install(
    py: Path,
    root: Path,
    args: List[str],
    *,
    timeout: float = 300.0,
    label: str = "",
) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(
            [str(py), "-m", "pip", "install", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=max(30.0, timeout),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        )
    except subprocess.TimeoutExpired:
        return False, f"{label or 'pip'}: таймаут {int(timeout)}s — повтори или поставь вручную в Comfy venv"
    tail = ((proc.stdout or "") + (proc.stderr or ""))[-400:]
    if proc.returncode != 0:
        return False, f"{label or 'pip'}: код {proc.returncode}\n{tail.strip()}"
    return True, f"{label or 'pip'}: ok"


def repair_reactor_dependencies(
    config: Config,
    *,
    progress: Callable[[str], None] | None = None,
    skip_requirements: bool = False,
) -> Tuple[bool, str]:
    """pip install по шагам; без тяжёлого import nodes.py."""
    from .install import ensure_reactor_installed

    def _note(msg: str) -> None:
        if progress:
            progress(msg)

    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI root не найден"
    ok, msg = ensure_reactor_installed(root)
    lines: List[str] = [msg]
    py = _python_for_comfy(root)
    req = root / "custom_nodes" / _REACTOR_DIR / "requirements.txt"

    deps_ok, deps_msg, missing = probe_reactor_deps(config, timeout=40.0)
    lines.append(f"deps: {'OK' if deps_ok else 'MISSING'}")
    if not deps_ok and deps_msg:
        for ln in deps_msg.splitlines()[-6:]:
            if ln.strip():
                lines.append(f"  {ln.strip()[:200]}")

    if not skip_requirements and req.is_file() and not deps_ok:
        _note("pip: ReActor requirements.txt…")
        ok_req, req_msg = _pip_install(
            py, root, ["-r", str(req)], timeout=420.0, label="requirements.txt"
        )
        lines.append(req_msg)
        if not ok_req:
            return False, "\n".join(lines)
        deps_ok, deps_msg, missing = probe_reactor_deps(config, timeout=45.0)

    for label, pkgs in _PIP_STEPS:
        if deps_ok:
            break
        _note(f"pip: {label}…")
        ok_p, p_msg = _pip_install(py, root, list(pkgs), timeout=300.0, label=label)
        lines.append(p_msg)
        if not ok_p:
            return False, "\n".join(lines)
        deps_ok, deps_msg, missing = probe_reactor_deps(config, timeout=45.0)

    deps_ok2, deps_msg2, _ = probe_reactor_deps(config, timeout=60.0)
    lines.append(f"deps после pip: {'OK' if deps_ok2 else 'FAIL'}")
    if deps_msg2 and not deps_ok2:
        lines.append(deps_msg2[-800:])

    from .reactor_diag import patch_reactor_nsfw_filter

    ok_patch, patch_msg = patch_reactor_nsfw_filter(root)
    lines.append(patch_msg)

    lines.append("→ перезапуск Comfy (comfy_ensure restart=1)")
    return deps_ok2, "\n".join(lines)


def reactor_diagnose(config: Config, client=None, *, full_import: bool = False) -> str:
    from .face_refs import reactor_face_swap_class

    lines: List[str] = []
    root = resolve_comfy_root(config)
    if root is None:
        return "ReActor diag: ComfyUI root не найден"
    reactor_dir = root / "custom_nodes" / _REACTOR_DIR
    lines.append(f"ReActor папка: {'есть' if reactor_dir.is_dir() else 'нет'}")
    ok_dep, dep_msg, missing = probe_reactor_deps(config)
    lines.append(f"venv deps: {'OK' if ok_dep else 'MISSING ' + ', '.join(missing[:5])}")
    if dep_msg and not ok_dep:
        for ln in dep_msg.splitlines()[-4:]:
            if ln.strip():
                lines.append(f"  {ln.rstrip()}")
    if full_import:
        ok_imp, imp = probe_reactor_import(config, full=True, timeout=90.0)
        lines.append(f"import nodes.py: {'OK' if ok_imp else 'FAIL/timeout'}")
        if imp:
            for ln in imp.splitlines()[-4:]:
                lines.append(f"  {ln.rstrip()}")
    if client is not None:
        found = list_reactor_node_classes(client)
        cls = reactor_face_swap_class(client)
        if cls:
            lines.append(f"API :8188: **{cls}** (+{max(0, len(found) - 1)} ReActor нод)")
        elif found:
            lines.append(f"API :8188: ReActor-похожие: {', '.join(found[:5])}")
        else:
            lines.append("API :8188: ReActor нод нет")
    log_bit = reactor_errors_in_launch_log(config)
    if log_bit:
        lines.append("comfy_launch.log:")
        for ln in log_bit.splitlines()[-8:]:
            lines.append(f"  {ln}")
    return "\n".join(lines)


def wait_for_reactor_node(client, *, timeout: float = 45.0, poll: float = 2.0) -> str | None:
    import time

    from .face_refs import reactor_face_swap_class

    deadline = time.time() + max(8.0, timeout)
    while time.time() < deadline:
        cls = reactor_face_swap_class(client)
        if cls:
            return cls
        time.sleep(poll)
    return None


_VIU_NSFW_PATCH_MARKER = "# viu: mocap — NSFW filter off (ReActor black-frame bug)"


def patch_reactor_nsfw_filter(root: Path) -> Tuple[bool, str]:
    """Отключить ReActor NSFW-detector — иначе NSFW MoCap → 1 чёрный кадр → ~4 KB mp4."""
    sfw = root / "custom_nodes" / _REACTOR_DIR / "scripts" / "reactor_sfw.py"
    if not sfw.is_file():
        return False, "reactor_sfw.py не найден"
    try:
        text = sfw.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"не читается reactor_sfw.py: {exc}"
    if _VIU_NSFW_PATCH_MARKER in text:
        return True, "ReActor NSFW filter уже отключён (Viu)"
    patch = f"""

{_VIU_NSFW_PATCH_MARKER}
def nsfw_image(img_data, model_path: str):
    \"\"\"Viu MoCap: не резать кадры (иначе пустой mp4).\"\"\"
    return False
"""
    try:
        sfw.write_text(text.rstrip() + patch, encoding="utf-8")
    except OSError as exc:
        return False, f"не записать reactor_sfw.py: {exc}"
    return True, "ReActor NSFW filter отключён — перезапусти Comfy (comfy_ensure restart=1)"

