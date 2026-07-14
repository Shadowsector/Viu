"""Пути ComfyUI / Lab Refs."""

from __future__ import annotations

import os
from collections import deque
from pathlib import Path
from typing import Optional

from ...config import Config
from ...anabarra_layout import library_root, viu_install_root

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
    }
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


def looks_like_comfy_root(path: Path) -> bool:
    """Есть main.py (установка ComfyUI)."""
    try:
        return (path / "main.py").is_file()
    except OSError:
        return False


def find_comfy_main_under(root: Path, *, max_depth: int = 4) -> Optional[Path]:
    """Искать ComfyUI внутри папки (вложенный ComfyUI/ComfyUI и т.п.)."""
    try:
        if not root.is_dir():
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
    try:
        viu = viu_install_root(config)
        if viu.is_dir():
            for child in viu.iterdir():
                if child.is_dir():
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
            nested = find_comfy_main_under(p, max_depth=3)
            if nested is not None:
                return nested
        except OSError:
            continue
    return None
