"""Пути ComfyUI / Lab Refs."""

from __future__ import annotations

import os
from pathlib import Path

from ...config import Config
from ...anabarra_layout import library_root, viu_install_root


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
    # Скан детей U:\Viu на main.py (если положили не в ComfyUI/)
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
            if (p / "main.py").is_file():
                return p.resolve()
            nested = p / "ComfyUI"
            if (nested / "main.py").is_file():
                return nested.resolve()
        except OSError:
            continue
    return None
