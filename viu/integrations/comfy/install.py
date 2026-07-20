"""Автоустановка ComfyUI в U:\\Viu\\ComfyUI + Wan workflows + модели."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
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
from .paths import (
    comfy_workflows_dir,
    find_comfy_main_under,
    looks_like_comfy_root,
    resolve_comfy_root,
)
from .ui_to_api import looks_like_ui_workflow, ui_workflow_to_api
from .workflows import workflow_is_stub

COMFY_GIT = "https://github.com/comfyanonymous/ComfyUI.git"

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
    """Найти установки ComfyUI только в безопасных местах (не весь C:\\)."""
    found: List[Path] = []
    candidates: List[Path] = []
    try:
        viu = viu_install_root(config)
        candidates.append(viu / "ComfyUI")
        if viu.is_dir():
            for child in viu.iterdir():
                if child.is_dir() and "comfy" in child.name.lower():
                    candidates.append(child)
    except OSError:
        pass
    candidates.extend(
        [
            Path("U:/Viu/ComfyUI"),
            Path("U:/ComfyUI"),
            Path("U:/Apps/ComfyUI"),
            Path.home() / "ComfyUI",
            Path.home() / "Documents" / "ComfyUI",
            Path("C:/ComfyUI"),
        ]
    )
    seen: set[str] = set()
    for c in candidates:
        key = str(c).lower()
        if key in seen:
            continue
        seen.add(key)
        nested = find_comfy_main_under(c, max_depth=2)
        if nested is not None:
            found.append(nested)
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
                        progress(
                            f"{dest.name}: {done // (1024 * 1024)}/{total // (1024 * 1024)} MB"
                        )
        partial.replace(dest)
        return True, f"скачала: {dest.name} ({dest.stat().st_size // (1024 * 1024)} MB)"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        try:
            if partial.is_file():
                partial.unlink()
        except OSError:
            pass
        return False, f"{dest.name}: {exc}"


def _stash_nonempty_dir(dest: Path) -> Tuple[Path, List[str]]:
    """Перенести содержимое dest в соседний ComfyUI_stash_<time>, dest остаётся пустым."""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    stash = dest.parent / f"ComfyUI_stash_{stamp}"
    n = 0
    while stash.exists():
        n += 1
        stash = dest.parent / f"ComfyUI_stash_{stamp}_{n}"
    stash.mkdir(parents=True, exist_ok=False)
    moved: List[str] = []
    for item in list(dest.iterdir()):
        target = stash / item.name
        shutil.move(str(item), str(target))
        moved.append(item.name)
    return stash, moved


def _merge_models_from_stash(stash: Path, dest: Path) -> str:
    """Вернуть модели из stash в новую установку (не затирая уже скачанное)."""
    candidates = [stash / "models"]
    try:
        for child in stash.iterdir():
            if child.is_dir() and (child / "models").is_dir():
                candidates.append(child / "models")
    except OSError:
        pass
    src = next((c for c in candidates if c.is_dir()), None)
    if src is None:
        return ""
    dst = dest / "models"
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for root, _dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        out_dir = dst / rel
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            s = Path(root) / name
            d = out_dir / name
            if d.exists():
                continue
            try:
                shutil.copy2(s, d)
                copied += 1
            except OSError:
                continue
    if copied:
        return f"Вернула {copied} файл(ов) моделей из {stash.name}."
    return f"Модели из {stash.name} уже на месте или пусты."


def clone_comfyui(dest: Path, *, progress: ProgressCb = None) -> Tuple[bool, str, Optional[Path]]:
    """Поставить ComfyUI в dest. Если папка занята — ищем вложенный main.py или stash+clone."""
    dest = Path(dest)
    nested = find_comfy_main_under(dest, max_depth=4)
    if nested is not None:
        return True, f"ComfyUI уже есть (нашла main.py): {nested}", nested

    dest.parent.mkdir(parents=True, exist_ok=True)
    stash: Optional[Path] = None
    try:
        nonempty = dest.exists() and any(dest.iterdir())
    except OSError:
        nonempty = False

    if nonempty:
        if progress:
            progress(
                f"папка {dest} занята без main.py — прячу содержимое в stash и ставлю Comfy заново"
            )
        try:
            stash, moved = _stash_nonempty_dir(dest)
        except OSError as exc:
            return False, f"Не смогла освободить {dest}: {exc}", None
        note = f"Старое содержимое → {stash.name} ({len(moved)} шт.)."
    else:
        note = ""
        if dest.exists():
            try:
                dest.rmdir()
            except OSError:
                pass

    if progress:
        progress(f"git clone ComfyUI → {dest}")
    ok, msg = _run(["git", "clone", "--depth", "1", COMFY_GIT, str(dest)], timeout=600)
    if not ok:
        if stash is not None and stash.is_dir():
            try:
                for item in stash.iterdir():
                    shutil.move(str(item), str(dest / item.name))
                stash.rmdir()
                note += " Clone failed — вернула stash обратно."
            except OSError:
                note += f" Clone failed; stash остался в {stash}."
        return False, f"git clone failed: {msg}\n{note}".strip(), None

    if not (dest / "main.py").is_file():
        return False, f"clone ok, но нет main.py в {dest}\n{note}".strip(), None

    extras = []
    if note:
        extras.append(note)
    if stash is not None:
        merge_msg = _merge_models_from_stash(stash, dest)
        if merge_msg:
            extras.append(merge_msg)
    text = f"Клонировала ComfyUI → {dest}"
    if extras:
        text += "\n" + "\n".join(extras)
    return True, text, dest.resolve()


def pip_install_requirements(root: Path, *, progress: ProgressCb = None) -> Tuple[bool, str]:
    req = root / "requirements.txt"
    if not req.is_file():
        return True, "requirements.txt нет — пропуск"
    py = sys.executable
    for cand in (
        root / "venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",
        root / "python_embeded" / "python.exe",
    ):
        if cand.is_file():
            py = str(cand)
            break
    else:
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


def download_wan_workflows(
    config: Config, *, force: bool = False, progress: ProgressCb = None
) -> Tuple[bool, str]:
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
    with_reactor: bool = False,
    progress: ProgressCb = None,
) -> Tuple[bool, str]:
    """Скан → clone/repair при необходимости → workflows → модели → (pip)."""
    lines: List[str] = []

    existing = resolve_comfy_root(config)
    if existing is None:
        scanned = scan_comfy_candidates(config)
        if scanned:
            existing = scanned[0]
            lines.append(f"Нашла ComfyUI: {existing}")

    dest = existing or target_comfy_dir(config)

    need_install = existing is None or not looks_like_comfy_root(Path(dest))
    if need_install:
        nested = find_comfy_main_under(target_comfy_dir(config), max_depth=4)
        if nested is not None:
            dest = nested
            lines.append(f"Нашла вложенный ComfyUI: {dest}")
            need_install = False

    if need_install:
        target = target_comfy_dir(config)
        # не ставить в ложный путь (unittest и т.п.)
        if not str(target).lower().endswith("comfyui") and "comfy" not in target.name.lower():
            try:
                target = viu_install_root(config) / "ComfyUI"
            except OSError:
                target = Path("U:/Viu/ComfyUI")
        if progress:
            progress(f"устанавливаю ComfyUI → {target}")
        ok, msg, root = clone_comfyui(target, progress=progress)
        lines.append(msg)
        if not ok or root is None or not looks_like_comfy_root(root):
            return False, "\n".join(lines)
        dest = root
    else:
        lines.append(f"Использую: {dest}")

    if not looks_like_comfy_root(Path(dest)):
        return False, "\n".join(lines) + f"\nПуть не ComfyUI: {dest}"

    config.comfy_root = str(dest)

    ok_wf, wf_msg = download_wan_workflows(config, progress=progress)
    lines.append("Workflows:\n" + wf_msg)
    try:
        from .workflows import ensure_workflow_templates

        merged = ensure_workflow_templates(config, overwrite_stubs=not ok_wf)
        if merged:
            lines.append("Шаблоны Viu (SaveVideo rev4): " + ", ".join(p.name for p in merged))
    except Exception as exc:  # noqa: BLE001
        lines.append(f"шаблоны: {exc}")
    if not ok_wf:
        lines.append("(часть workflows не скачалась с GitHub — использую шаблоны из пакета Вью)")

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

    if with_reactor:
        ok_r, r_msg = ensure_reactor_installed(Path(dest), progress=progress)
        lines.append("ReActor:\n" + r_msg)
        if not ok_r:
            lines.append("⚠ ReActor не установился полностью.")

    return True, "\n".join(lines)


REACTOR_GIT = "https://github.com/Gourieff/ComfyUI-ReActor.git"
_INSWAPPER_URL = (
    "https://huggingface.co/ezioruan/inswapper_128.onnx/resolve/main/inswapper_128.onnx"
)


def _python_for_comfy_root(root: Path) -> str:
    for cand in (
        root / "venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",
        root / "python_embeded" / "python.exe",
    ):
        if cand.is_file():
            return str(cand)
    return sys.executable


def ensure_reactor_installed(
    root: Path, *, progress: ProgressCb = None
) -> Tuple[bool, str]:
    """ComfyUI-ReActor + inswapper для подмены лица в MoCap."""
    root = Path(root)
    dest = root / "custom_nodes" / "ComfyUI-ReActor"
    lines: List[str] = []

    if dest.is_dir() and (dest / "nodes.py").is_file():
        lines.append(f"ReActor: уже есть ({dest.name})")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if progress:
            progress("git clone ComfyUI-ReActor…")
        ok, msg = _run(
            ["git", "clone", "--depth", "1", REACTOR_GIT, str(dest)],
            timeout=300,
        )
        if not ok:
            return False, f"ReActor clone failed: {msg}"
        lines.append(f"ReActor: клонировала → {dest}")

    req = dest / "requirements.txt"
    if req.is_file():
        py = _python_for_comfy_root(root)
        if progress:
            progress("pip install ReActor requirements…")
        ok, msg = _run([py, "-m", "pip", "install", "-r", str(req)], timeout=1800)
        lines.append(msg[:500] if msg else "ReActor pip ok")
        if not ok:
            lines.append("⚠ ReActor pip не полностью — перезапусти Comfy и повтори.")

    inswapper = root / "models" / "insightface" / "inswapper_128.onnx"
    if not inswapper.is_file():
        if progress:
            progress("inswapper_128.onnx…")
        ok, msg = _download(_INSWAPPER_URL, inswapper, progress=progress)
        lines.append(msg)
        if not ok:
            lines.append("⚠ inswapper не скачался — ReActor может скачать сам при первом swap.")

    lines.append("Перезапусти Comfy (comfy_ensure), чтобы подхватить ReActor.")
    return True, "\n".join(lines)
