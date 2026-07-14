"""Пути ComfyUI / Lab Refs."""

from __future__ import annotations

import os
from pathlib import Path

from ...config import Config
from ...anabarra_layout import library_root


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


def resolve_comfy_root(config: Config) -> Path | None:
    """Каталог установки ComfyUI, если найден."""
    env = (getattr(config, "comfy_root", None) or os.environ.get("VIU_COMFY_ROOT", "")).strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser())
    candidates.extend(
        [
            Path("U:/ComfyUI"),
            Path("U:/Apps/ComfyUI"),
            Path.home() / "ComfyUI",
            Path.home() / "Documents" / "ComfyUI",
            Path("C:/ComfyUI"),
        ]
    )
    for p in candidates:
        try:
            if (p / "main.py").is_file() or (p / "ComfyUI" / "main.py").is_file():
                if (p / "ComfyUI" / "main.py").is_file():
                    return (p / "ComfyUI").resolve()
                return p.resolve()
        except OSError:
            continue
    return None
