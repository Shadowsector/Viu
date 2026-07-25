"""Пути Honey Select 2 и рабочие папки в Anabarra."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from ...anabarra_layout import library_root
from ...config import Config

# Типичные установки (Windows / Steam).
_HS2_STEAM_NAMES = (
    "Honey Select 2",
    "HoneySelect2",
    "Honey Select 2 DX",
)


def _env_hs2_root() -> str:
    return (os.environ.get("VIU_HS2_ROOT") or "").strip()


def resolve_hs2_root(config: Optional[Config] = None) -> Optional[Path]:
    """Корень игры (папка с abdata/). None если не найден."""
    raw = _env_hs2_root()
    if not raw and config is not None:
        raw = (getattr(config, "hs2_root", "") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if (p / "abdata").is_dir():
            return p.resolve()
        if p.is_dir():
            return p.resolve()

    if os.name == "nt":
        steam_roots: List[Path] = []
        for key in ("ProgramFiles(x86)", "ProgramFiles"):
            base = os.environ.get(key)
            if base:
                steam_roots.append(Path(base) / "Steam" / "steamapps" / "common")
        for root in steam_roots:
            if not root.is_dir():
                continue
            for name in _HS2_STEAM_NAMES:
                cand = root / name
                if (cand / "abdata").is_dir():
                    return cand.resolve()
    return None


def hs2_abdata_dir(hs2_root: Path) -> Path:
    return hs2_root / "abdata"


def hs2_work_root(config: Config) -> Path:
    """U:\\Anabarra\\Library\\HS2 — дампы, JSON, реестр скана."""
    p = library_root(config) / "HS2"
    p.mkdir(parents=True, exist_ok=True)
    return p


def hs2_fbx_dump_dir(config: Config) -> Path:
    """Сюда MeshExporter / Studio NEO кладут FBX (или VIU_HS2_FBX_DUMP)."""
    raw = (os.environ.get("VIU_HS2_FBX_DUMP") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p.resolve()
    p = hs2_work_root(config) / "fbx_dump"
    p.mkdir(parents=True, exist_ok=True)
    return p


def hs2_clip_json_dir(config: Config) -> Path:
    p = hs2_work_root(config) / "clips_json"
    p.mkdir(parents=True, exist_ok=True)
    return p


def hs2_scan_cache_path(config: Config) -> Path:
    return hs2_work_root(config) / "animation_scan.json"


def default_retarget_rig_path(config: Config) -> Optional[Path]:
    """Mixamo / humanoid FBX для ретаргета (VIU_HS2_RETARGET_RIG)."""
    raw = (os.environ.get("VIU_HS2_RETARGET_RIG") or "").strip()
    if raw:
        p = Path(raw).expanduser()
        return p if p.is_file() else None
    candidates = [
        library_root(config) / "HS2" / "Mixamo_XBot.fbx",
        library_root(config) / "HS2" / "X Bot.fbx",
        library_root(config) / "References" / "Mixamo_XBot.fbx",
    ]
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return None


def abdata_animation_roots(hs2_root: Path) -> List[Path]:
    """Подпапки abdata, где чаще всего лежат AnimationClip."""
    ab = hs2_abdata_dir(hs2_root)
    rels = [
        "list/animation",
        "animation",
        "studio/animation",
        "chara/animation",
    ]
    out: List[Path] = []
    for rel in rels:
        p = ab / rel.replace("/", os.sep)
        if p.is_dir():
            out.append(p)
    if not out and ab.is_dir():
        out.append(ab)
    return out
