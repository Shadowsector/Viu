"""Скан папок на 3D-ассеты для каталога."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Tuple

from .models import (
    ASSET_SUFFIXES,
    PropEntry,
    prop_id_for_mesh,
    prop_id_for_path,
    suggest_category_for_role,
    suggest_role,
)
from .store import PropCatalogStore

_SIDECAR_NOTE_NAMES = ("notes.txt", "описание.txt", "readme.txt", "README.txt")


def _sidecar_notes(path: Path) -> str:
    """Текст из notes.txt рядом с файлом или в папке-паке."""
    for base in (path.parent, path.parent.parent):
        for name in _SIDECAR_NOTE_NAMES:
            sidecar = base / name
            if sidecar.is_file():
                try:
                    return sidecar.read_text(encoding="utf-8", errors="replace").strip()[:4000]
                except OSError:
                    continue
    return ""


def mesh_objects_in_blend(path: Path, blender_exe: str = "") -> List[str]:
    """Имена MESH-объектов в .blend (через фоновый Blender)."""
    if path.suffix.lower() != ".blend":
        return []
    try:
        from ..integrations.blender.headless import dump_blend_info

        data = dump_blend_info(str(path), blender_exe=blender_exe or "blender")
        objs = data.get("objects") or []
        return sorted(
            {o.get("name", "") for o in objs if o.get("type") == "MESH" and o.get("name")}
        )
    except (OSError, RuntimeError, ValueError, ImportError):
        return []


def _remove_stale_file_entry(path: Path, store: PropCatalogStore) -> None:
    """Убирает старую карточку «целый файл», если появились меши."""
    file_pid = prop_id_for_path(path)
    old = store.get(file_pid)
    if old and not old.reviewed and not old.mesh_name:
        del store.items[file_pid]
        store.save()


def _entry_for_mesh(path: Path, mesh_name: str, all_meshes: List[str]) -> PropEntry:
    role = suggest_role(mesh_name)
    category = suggest_category_for_role(role)
    notes = _sidecar_notes(path)
    return PropEntry(
        id=prop_id_for_mesh(path, mesh_name),
        source_path=str(path),
        display_name=mesh_name.replace("_", " "),
        category=category if category != "unknown" else "unknown",
        mesh_name=mesh_name,
        role=role,
        mesh_names=list(all_meshes),
        notes=notes,
        reviewed=False,
    )


def _entry_for_file(path: Path, mesh_names: List[str]) -> PropEntry:
    return PropEntry(
        id=prop_id_for_path(path),
        source_path=str(path),
        display_name=path.stem.replace("_", " "),
        mesh_names=mesh_names,
        notes=_sidecar_notes(path),
        reviewed=False,
    )


def scan_blend_file(
    path: Path,
    store: PropCatalogStore,
    *,
    blender_exe: str = "",
    mesh_reader: Callable[[Path, str], List[str]] | None = None,
) -> Tuple[int, int]:
    """Скан одного .blend: по карточке на каждый MESH."""
    path = path.expanduser().resolve()
    reader = mesh_reader or mesh_objects_in_blend
    meshes = reader(path, blender_exe)
    new_count = 0
    seen = 0

    if meshes:
        _remove_stale_file_entry(path, store)
        for mesh_name in meshes:
            pid = prop_id_for_mesh(path, mesh_name)
            if store.get(pid):
                seen += 1
                continue
            store.upsert(_entry_for_mesh(path, mesh_name, meshes))
            new_count += 1
        return new_count, seen

    pid = prop_id_for_path(path)
    if store.get(pid):
        return 0, 1
    store.upsert(_entry_for_file(path, []))
    return 1, 0


def scan_folder(
    folder: Path,
    store: PropCatalogStore,
    *,
    recursive: bool = True,
    blender_exe: str = "",
    mesh_reader: Callable[[Path, str], List[str]] | None = None,
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
        if path.suffix.lower() == ".blend":
            n, s = scan_blend_file(
                path, store, blender_exe=blender_exe, mesh_reader=mesh_reader
            )
            new_count += n
            seen += s
            continue
        pid = prop_id_for_path(path)
        if store.get(pid):
            seen += 1
            continue
        store.upsert(_entry_for_file(path, []))
        new_count += 1
    return new_count, seen
