"""Скан папок на 3D-ассеты для каталога."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from .models import ASSET_SUFFIXES, PropEntry, prop_id_for_path
from .store import PropCatalogStore


def _mesh_hints_for_file(path: Path, blender_exe: str = "") -> List[str]:
    if path.suffix.lower() != ".blend":
        return []
    try:
        from ..integrations.blender.headless import dump_blend_info

        data = dump_blend_info(str(path), blender_exe=blender_exe or "blender")
        objs = data.get("objects") or []
        return [o.get("name", "") for o in objs if o.get("type") == "MESH"][:40]
    except (OSError, RuntimeError, ValueError, ImportError):
        return []


def scan_folder(
    folder: Path,
    store: PropCatalogStore,
    *,
    recursive: bool = True,
    blender_exe: str = "",
) -> Tuple[int, int]:
    """Возвращает (новых, уже в каталоге)."""
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"Папка не найдена: {folder}")

    new_count = 0
    seen = 0
    glob = folder.rglob("*") if recursive else folder.glob("*")
    for path in sorted(glob):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ASSET_SUFFIXES:
            continue
        pid = prop_id_for_path(path)
        if store.get(pid):
            seen += 1
            continue
        mesh_names = _mesh_hints_for_file(path, blender_exe)
        entry = PropEntry(
            id=pid,
            source_path=str(path),
            display_name=path.stem.replace("_", " "),
            mesh_names=mesh_names,
            reviewed=False,
        )
        store.upsert(entry)
        new_count += 1
    return new_count, seen
