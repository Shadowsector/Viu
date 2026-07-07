"""Профиль глубины оверлея — overlay_tune.json рядом с exe."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from .overlay import OVERLAY_BUILD_DIR

DEFAULT_TUNE: Dict[str, Any] = {
    "feetLiftMeters": 0.005,
    "characterHeightMeters": 1.77,
    "activeLane": "taskbar",
    "taskbar": {
        "viewCenterAboveFeet": 1.0,
        "distanceZ": 10.0,
        "orthoHalfHeight": 1.15,
    },
    "attention": {
        "viewCenterAboveFeet": 1.15,
        "distanceZ": 6.0,
        "orthoHalfHeight": 0.88,
    },
}

_TEMPLATE = Path(__file__).parent / "templates" / "overlay_tune.json"


def tune_file_path(project_root: Path) -> Path:
    return (project_root / OVERLAY_BUILD_DIR / "overlay_tune.json").resolve()


def load_tune(project_root: Path | None = None) -> Dict[str, Any]:
    if project_root is not None:
        path = tune_file_path(project_root)
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    if _TEMPLATE.is_file():
        return json.loads(_TEMPLATE.read_text(encoding="utf-8"))
    return deepcopy(DEFAULT_TUNE)


def write_tune_lane(project_root: Path, lane: str) -> Path:
    """lane: taskbar | attention"""
    lane = lane.strip().lower()
    if lane not in ("taskbar", "attention"):
        raise ValueError(f"lane must be taskbar or attention, got {lane!r}")
    data = load_tune(project_root)
    data["activeLane"] = lane
    dest = tune_file_path(project_root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def deploy_tune_template(project_root: Path) -> Path:
    dest = tune_file_path(project_root)
    if dest.is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = load_tune(None)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest
