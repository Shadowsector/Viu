"""ReActor: диагностика загрузки нод, repair зависимостей."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

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

_EXTRA_PIP = (
    "insightface>=0.7.3",
    "onnxruntime>=1.16.0",
    "opencv-python-headless>=4.7.0",
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


def probe_reactor_import(config: Config) -> Tuple[bool, str]:
    """Импорт nodes.py тем же python, что и Comfy."""
    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI root не найден"
    reactor = root / "custom_nodes" / _REACTOR_DIR
    nodes_py = reactor / "nodes.py"
    if not nodes_py.is_file():
        return False, f"нет {reactor}"
    py = _python_for_comfy(root)
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
    try:
        proc = subprocess.run(
            [str(py), "-c", code],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode == 0:
        return True, out.splitlines()[-1] if out else "OK"
    return False, out[-2000:] if out else f"exit {proc.returncode}"


def repair_reactor_dependencies(config: Config) -> Tuple[bool, str]:
    """pip install requirements + insightface/onnxruntime в venv Comfy."""
    from .install import ensure_reactor_installed

    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI root не найден"
    ok, msg = ensure_reactor_installed(root)
    lines = [msg]
    py = _python_for_comfy(root)
    req = root / "custom_nodes" / _REACTOR_DIR / "requirements.txt"
    if req.is_file():
        proc = subprocess.run(
            [str(py), "-m", "pip", "install", "-r", str(req), *_EXTRA_PIP],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=1800,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        )
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-600:]
        lines.append("pip ReActor+deps: " + ("ok" if proc.returncode == 0 else f"код {proc.returncode}"))
        if tail.strip():
            lines.append(tail.strip())
        if proc.returncode != 0:
            return False, "\n".join(lines)
    ok_imp, imp = probe_reactor_import(config)
    lines.append(f"import test: {'OK' if ok_imp else 'FAIL'}")
    lines.append(imp[:1200])
    return ok_imp, "\n".join(lines)


def reactor_diagnose(config: Config, client=None) -> str:
    from .face_refs import reactor_face_swap_class

    lines: List[str] = []
    root = resolve_comfy_root(config)
    if root is None:
        return "ReActor diag: ComfyUI root не найден"
    reactor_dir = root / "custom_nodes" / _REACTOR_DIR
    lines.append(f"ReActor папка: {'есть' if reactor_dir.is_dir() else 'нет'}")
    ok_imp, imp = probe_reactor_import(config)
    lines.append(f"import nodes.py: {'OK' if ok_imp else 'FAIL'}")
    if imp:
        for ln in imp.splitlines()[-8:]:
            lines.append(f"  {ln.rstrip()}")
    if client is not None:
        found = list_reactor_node_classes(client)
        cls = reactor_face_swap_class(client)
        if cls:
            lines.append(f"API :8188: **{cls}** (+{max(0, len(found) - 1)} ReActor нод)")
        elif found:
            lines.append(f"API :8188: ReActor-похожие: {', '.join(found[:5])}")
        else:
            lines.append("API :8188: ReActor нод нет (custom_nodes не загрузились)")
    log_bit = reactor_errors_in_launch_log(config)
    if log_bit:
        lines.append("comfy_launch.log (ReActor):")
        for ln in log_bit.splitlines()[-12:]:
            lines.append(f"  {ln}")
    if not ok_imp:
        lines.append("→ comfy_reactor_fix (или comfy_install reactor=1)")
    return "\n".join(lines)


def wait_for_reactor_node(client, *, timeout: float = 90.0, poll: float = 3.0) -> str | None:
    import time

    from .face_refs import reactor_face_swap_class

    deadline = time.time() + max(10.0, timeout)
    while time.time() < deadline:
        cls = reactor_face_swap_class(client)
        if cls:
            return cls
        time.sleep(poll)
    return None
