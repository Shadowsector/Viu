"""Пути ComfyUI / Lab Refs."""

from __future__ import annotations

import os
from collections import deque
from pathlib import Path
from typing import Optional

from ...config import Config
from ...anabarra_layout import library_root, viu_install_root

# Не заходим сюда при поиске Comfy (ложные main.py: unittest/main.py и т.п.).
_SKIP_SCAN_DIRS = frozenset(
    {
        ".git",
        "venv",
        ".venv",
        "models",
        "output",
        "input",
        "temp",
        "__pycache__",
        "node_modules",
        "python_embeded",
        "python_embedded",
        "lib",
        "site-packages",
        "unittest",
        "test",
        "tests",
        "dist-packages",
        "windowsapps",
        "$recycle.bin",
        "system volume information",
    }
)

# Признаки настоящей установки ComfyUI (НЕ достаточно одного main.py —
# у CPython есть Lib/unittest/main.py).
_COMFY_MARKERS = (
    "folder_paths.py",
    "nodes.py",
    "execution.py",
    "server.py",
    "cuda_malloc.py",
    "latent_preview.py",
)


def comfy_refs_dir(config: Config) -> Path:
    env = os.environ.get("VIU_COMFY_REFS", "").strip()
    if env:
        p = Path(env).expanduser()
    else:
        p = library_root(config) / "Lab" / "Refs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def comfy_out_dir(config: Config) -> Path:
    env = os.environ.get("VIU_COMFY_OUT", "").strip()
    if env:
        p = Path(env).expanduser()
    else:
        p = library_root(config) / "Lab" / "ComfyOut"
    p.mkdir(parents=True, exist_ok=True)
    return p


def comfy_workflows_dir(config: Config) -> Path:
    """Workflow JSON рядом с данными Viu (можно класть API-export из Comfy)."""
    p = config.data_dir / "comfy" / "workflows"
    p.mkdir(parents=True, exist_ok=True)
    return p


def comfy_seed_frames_dir(config: Config) -> Path:
    """Last-frame PNG для следующей i2v-генерации."""
    p = library_root(config) / "Lab" / "Refs" / "seeds"
    p.mkdir(parents=True, exist_ok=True)
    return p


def comfy_face_refs_dir(config: Config) -> Path:
    """Эталонные лица для ReActor / I2V (PNG/JPG)."""
    env = os.environ.get("VIU_COMFY_FACE_REFS", "").strip()
    if env:
        p = Path(env).expanduser()
    else:
        p = library_root(config) / "Lab" / "FaceRefs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def comfy_input_dir(comfy_root: Path) -> Path:
    """ComfyUI/input для LoadImage."""
    p = comfy_root / "input"
    p.mkdir(parents=True, exist_ok=True)
    return p


def looks_like_comfy_root(path: Path) -> bool:
    """Настоящий ComfyUI: main.py + хотя бы один маркер (не unittest/main.py)."""
    try:
        if not path.is_dir() or not (path / "main.py").is_file():
            return False
    except OSError:
        return False
    # Явно отсечь стандартную библиотеку Python
    parts = {p.lower() for p in path.parts}
    if "unittest" in parts or "site-packages" in parts:
        return False
    if "lib" in parts and any(p.lower().startswith("python") for p in path.parts):
        return False
    try:
        if (path / "comfy").is_dir():
            return True
        return any((path / name).exists() for name in _COMFY_MARKERS)
    except OSError:
        return False


def find_comfy_main_under(root: Path, *, max_depth: int = 3) -> Optional[Path]:
    """Искать ComfyUI внутри папки (вложенный ComfyUI/ComfyUI). Без обхода всего диска."""
    try:
        if not root.is_dir():
            return None
    except OSError:
        return None
    # Не сканировать корни дисков целиком
    try:
        if root.resolve() == root.anchor or str(root).rstrip("\\/") in (
            "C:",
            "D:",
            "U:",
            "C:\\",
            "D:\\",
            "U:\\",
            "/",
        ):
            # только прямые дети с именем ComfyUI
            for child in root.iterdir():
                if child.is_dir() and child.name.lower() == "comfyui":
                    found = find_comfy_main_under(child, max_depth=2)
                    if found is not None:
                        return found
            return None
    except OSError:
        return None

    if looks_like_comfy_root(root):
        return root.resolve()
    q: deque[tuple[Path, int]] = deque([(root, 0)])
    while q:
        cur, depth = q.popleft()
        if depth >= max_depth:
            continue
        try:
            children = list(cur.iterdir())
        except OSError:
            continue
        for child in children:
            try:
                if not child.is_dir():
                    continue
            except OSError:
                continue
            name = child.name.lower()
            if name in _SKIP_SCAN_DIRS or name.startswith("comfyui_stash_"):
                continue
            if looks_like_comfy_root(child):
                return child.resolve()
            if depth + 1 < max_depth:
                q.append((child, depth + 1))
    return None


def resolve_comfy_root(config: Config) -> Path | None:
    """Каталог установки ComfyUI. Предпочтение: U:\\Viu\\ComfyUI."""
    env = (getattr(config, "comfy_root", None) or os.environ.get("VIU_COMFY_ROOT", "")).strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    try:
        candidates.append(viu_install_root(config) / "ComfyUI")
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
    # Дети U:\Viu с именем *comfy* (не весь диск)
    try:
        viu = viu_install_root(config)
        if viu.is_dir():
            for child in viu.iterdir():
                if child.is_dir() and "comfy" in child.name.lower():
                    candidates.append(child)
    except OSError:
        pass

    seen: set[str] = set()
    for p in candidates:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if looks_like_comfy_root(p):
                return p.resolve()
            nested = find_comfy_main_under(p, max_depth=2)
            if nested is not None:
                return nested
        except OSError:
            continue

    # Сбросить ложный comfy_root (например unittest после бага сканера)
    if env and not looks_like_comfy_root(Path(env)):
        try:
            config.comfy_root = ""
        except Exception:
            pass
    return None
