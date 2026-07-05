"""Пути Unity-проекта (вне песочницы Viu, но только VIU_UNITY_PROJECT)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...config import Config


def unity_project_root(config: Config, override: Optional[str] = None) -> Path:
    raw = override or config.unity_project or ""
    if not raw:
        return Path("U:/Anabarra/Unity/Anabarra")
    return Path(raw).expanduser().resolve()


def resolve_in_unity_project(project_root: Path, rel: str) -> Path:
    """Разрешает путь относительно корня Unity-проекта; запрет выхода наружу."""
    root = project_root.resolve()
    candidate = (root / rel).resolve() if rel else root
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Путь вне Unity-проекта: {rel}")
    return candidate
