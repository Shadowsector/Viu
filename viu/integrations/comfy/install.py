"""Автоустановка ComfyUI в U:\\Viu\\ComfyUI + Wan workflows + модели."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ...anabarra_layout import viu_install_root
from ...config import Config
from .model_pref import (
    PREFERRED_CLIP_VISION,
    PREFERRED_I2V,
    PREFERRED_T2V,
    PREFERRED_TEXT_ENCODER,
    PREFERRED_VAE,
)
from .paths import comfy_workflows_dir, resolve_comfy_root
from .ui_to_api import looks_like_ui_workflow, ui_workflow_to_api
from .workflows import workflow_is_stub

COMFY_GIT = "https://github.com/comfyanonymous/ComfyUI.git"

# Официальные UI-workflows → конвертим в API Format.
_WF_SOURCES = {
    "t2v.json": (
        "https://raw.githubusercontent.com/comfyanonymous/ComfyUI_examples/master/wan/text_to_video_wan.json"
    ),
    "i2v.json": (
        "https://raw.githubusercontent.com/comfyanonymous/ComfyUI_examples/master/wan/image_to_video_wan_example.json"
    ),
}

_HF_BASE = (
    "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files"
)

# Минимальный набор для T2V MoCap (без 14B I2V).
_T2V_MODELS: Tuple[Tuple[str, str, str], ...] = (
    ("diffusion_models", PREFERRED_T2V, f"{_HF_BASE}/diffusion_models/{PREFERRED_T2V}"),
    ("vae", PREFERRED_VAE, f"{_HF_BASE}/vae/{PREFERRED_VAE}"),
    ("text_encoders", PREFERRED_TEXT_ENCODER, f"{_HF_BASE}/text_encoders/{PREFERRED_TEXT_ENCODER}"),
)

_I2V_MODELS: Tuple[Tuple[str, str, str], ...] = (
    ("diffusion_models", PREFERRED_I2V, f"{_HF_BASE}/diffusion_models/{PREFERRED_I2V}"),
    ("clip_vision", PREFERRED_CLIP_VISION, f"{_HF_BASE}/clip_vision/{PREFERRED_CLIP_VISION}"),
)

ProgressCb = Optional[Callable[[str], None]]


def target_comfy_dir(config: Config) -> Path:
    raw = (getattr(config, "comfy_root", None) or os.environ.get("VIU_COMFY_ROOT", "") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return viu_install_root(config) / "ComfyUI"


def scan_comfy_candidates(config: Config) -> List[Path]:
    """Найти все каталоги с main.py рядом с Вью / типичные пути."""
    found: List[Path] = []
    roots: List[Path] = []
    try:
        roots.append(viu_install_root(config))
    except OSError:
        pass
    roots.extend(
        [
            Path("U:/Viu"),
            Path("U:/"),
            Path("C:/"),
            Path.home(),
        ]
    )
    seen: set[str] = set()
    for root in roots:
        try:
            if not root.exists():
                continue
        except OSError:
            continue
        candidates = [
            root / "ComfyUI",
            root / "Apps" / "ComfyUI",
            root,
        ]
        # неглубокий скан детей U:\Viu
        try:
            if root.name.lower() == "viu" and root.is_dir():
                for child in root.iterdir():
                    if child.is_dir():
                        candidates.append(child)
        except OSError:
            pass
        for c in candidates:
            key = str(c).lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                if (c / "main.py").is_file():
                    found.append(c.resolve())
            except OSError:
                continue
    return found


def _run(cmd: List[str], *, cwd: Optional[Path] = None, timeout: float = 600) -> Tuple[bool, str]:
    try:
        kwargs: dict = {
            "cwd": str(cwd) if cwd else None,
            "capture_output": True,
            "text": True,
            "timeout": timeout,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(cmd, **kwargs)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        return False, out[-2000:] or f"exit {proc.returncode}"
    return True, out[-1000:]


def _download(url: str, dest: Path, *, progress: ProgressCb = None) -> Tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        return True, f"уже есть: {dest.name}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Viu-ComfyInstall/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with partial.open("wb") as fh:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if progress and total:
                        progress(f"{dest.name}: {done // (1024*1024)}/{total // (1024*1024)} MB")
        partial.replace(dest)
        return True, f"скачала: {dest.name} ({dest.stat().st_size // (1024*1024)} MB)"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        try:
            if partial.is_file():
                partial.unlink()
        except OSError:
            pass
        return False, f"{dest.name}: {exc}"


def clone_comfyui(dest: Path, *, progress: ProgressCb = None) -> Tuple[bool, str]:
    if (dest / "main.py").is_file():
        return True, f"ComfyUI уже на месте: {dest}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and any(dest.iterdir()):
        # папка не пустая, но без main.py — не затираем
        return False, (
            f"Папка {dest} не пуста и без main.py. "
            "Освободи её или укажи VIU_COMFY_ROOT на готовый ComfyUI."
        )
    if progress:
        progress(f"git clone ComfyUI → {dest}")
    # clone into temp name then move if needed
    if dest.exists():
        try:
            dest.rmdir()
        except OSError:
            pass
    ok, msg = _run(["git", "clone", "--depth", "1", COMFY_GIT, str(dest)], timeout=600)
    if not ok:
        return False, f"git clone failed: {msg}"
    if not (dest / "main.py").is_file():
        return False, f"clone ok, но нет main.py в {dest}"
    return True, f"Клонировала ComfyUI → {dest}"


def pip_install_requirements(root: Path, *, progress: ProgressCb = None) -> Tuple[bool, str]:
    req = root / "requirements.txt"
    if not req.is_file():
        return True, "requirements.txt нет — пропуск"
    py = sys.executable
    # предпочитаем venv Comfy, если есть
    for cand in (
        root / "venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",
        root / "python_embeded" / "python.exe",
    ):
        if cand.is_file():
            py = str(cand)
            break
    else:
        # создать venv
        venv = root / "venv"
        if progress:
            progress("создаю venv для ComfyUI…")
        ok, msg = _run([sys.executable, "-m", "venv", str(venv)], timeout=180)
        if ok:
            py = str(
                venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            )
        else:
            if progress:
                progress(f"venv не создался ({msg[:120]}) — ставлю в текущий python")
    if progress:
        progress(f"pip install -r requirements.txt ({py})")
    ok, msg = _run([py, "-m", "pip", "install", "-r", str(req)], cwd=root, timeout=1800)
    if not ok:
        return False, f"pip: {msg}"
    return True, "зависимости ComfyUI установлены"


def download_wan_workflows(config: Config, *, force: bool = False, progress: ProgressCb = None) -> Tuple[bool, str]:
    dest = comfy_workflows_dir(config)
    lines: List[str] = []
    ok_all = True
    for name, url in _WF_SOURCES.items():
        target = dest / name
        if target.is_file() and not workflow_is_stub(target) and not force:
            lines.append(f"{name}: уже есть (не stub)")
            continue
        if progress:
            progress(f"workflow {name}…")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Viu-ComfyInstall/1.0"})
            raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
            data = json.loads(raw)
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as exc:
            ok_all = False
            lines.append(f"{name}: скачать не вышло ({exc})")
            continue
        if looks_like_ui_workflow(data):
            api = ui_workflow_to_api(data)
            api["_viu_source"] = url
        elif isinstance(data, dict) and any(
            isinstance(v, dict) and "class_type" in v for v in data.values()
        ):
            api = data
        else:
            ok_all = False
            lines.append(f"{name}: неизвестный формат JSON")
            continue
        target.write_text(json.dumps(api, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines.append(f"{name}: API Format сохранён ({len(api)} узлов)")
    # default = t2v
    t2v = dest / "t2v.json"
    default = dest / "default.json"
    if t2v.is_file() and (force or not default.is_file() or workflow_is_stub(default)):
        shutil.copy2(t2v, default)
        lines.append("default.json ← t2v.json")
    return ok_all, "\n".join(lines)


def download_wan_models(
    root: Path,
    *,
    include_i2v: bool = False,
    progress: ProgressCb = None,
) -> Tuple[bool, str]:
    models = list(_T2V_MODELS)
    if include_i2v:
        models.extend(_I2V_MODELS)
    lines: List[str] = []
    ok_all = True
    for sub, name, url in models:
        dest = root / "models" / sub / name
        if progress:
            progress(f"модель {name}…")
        ok, msg = _download(url, dest, progress=progress)
        lines.append(msg)
        ok_all = ok_all and ok
    return ok_all, "\n".join(lines)


def ensure_comfy_installed(
    config: Config,
    *,
    with_models: bool = True,
    include_i2v: bool = False,
    with_pip: bool = True,
    progress: ProgressCb = None,
) -> Tuple[bool, str]:
    """Скан → clone при необходимости → workflows → модели → (pip)."""
    lines: List[str] = []

    existing = resolve_comfy_root(config)
    if existing is None:
        scanned = scan_comfy_candidates(config)
        if scanned:
            existing = scanned[0]
            lines.append(f"Нашла ComfyUI: {existing}")
            # закрепить в runtime, если пустой comfy_root
            if not (getattr(config, "comfy_root", None) or "").strip():
                config.comfy_root = str(existing)

    dest = existing or target_comfy_dir(config)
    if existing is None:
        if progress:
            progress(f"устанавливаю ComfyUI → {dest}")
        ok, msg = clone_comfyui(dest, progress=progress)
        lines.append(msg)
        if not ok:
            return False, "\n".join(lines)
        config.comfy_root = str(dest)
    else:
        lines.append(f"Использую: {dest}")
        config.comfy_root = str(dest)

    ok_wf, wf_msg = download_wan_workflows(config, progress=progress)
    lines.append("Workflows:\n" + wf_msg)
    if not ok_wf:
        # не фатально, если есть bundled templates
        lines.append("(часть workflows не скачалась — попробую шаблоны из пакета Вью)")
        try:
            from .workflows import ensure_workflow_templates

            ensure_workflow_templates(config, overwrite_stubs=True)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"шаблоны: {exc}")

    if with_pip:
        ok_pip, pip_msg = pip_install_requirements(dest, progress=progress)
        lines.append(pip_msg)
        if not ok_pip:
            lines.append("⚠ pip не полностью — Comfy может не стартовать, повторю позже.")

    if with_models:
        ok_m, m_msg = download_wan_models(dest, include_i2v=include_i2v, progress=progress)
        lines.append("Модели:\n" + m_msg)
        if not ok_m:
            return False, "\n".join(lines)

    return True, "\n".join(lines)
