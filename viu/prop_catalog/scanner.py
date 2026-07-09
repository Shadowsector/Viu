"""Скан папок на 3D-ассеты для каталога."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from .models import (
    ASSET_SUFFIXES,
    PropEntry,
    apply_auto_review,
    prop_id_for_mesh,
    prop_id_for_path,
    suggest_role_and_category,
)
from .store import PropCatalogStore

_SIDECAR_NOTE_NAMES = ("notes.txt", "описание.txt", "readme.txt", "README.txt")

# Коллекции, которые не попадают в очередь разметки (свет — не prop).
SKIP_COLLECTIONS = frozenset({"lights", "light"})


def _asset_pack_key(path: Path) -> str:
    """Old Stables_1 / Old Stables_prepared → old stables."""
    stem = path.stem.lower()
    stem = re.sub(r"_prepared(_\d+)?$", "", stem)
    stem = re.sub(r"_\d+$", "", stem)
    return stem


def _source_priority(source_path: str) -> tuple[int, str]:
    p = Path(source_path)
    name = p.name.lower()
    if "_prepared" in name or "processed" in str(p).lower():
        return (0, source_path)
    if "library" in str(p).lower() and "blender" in str(p).lower():
        return (2, source_path)
    return (1, source_path)


def merge_duplicate_meshes(store: PropCatalogStore) -> int:
    """Один меш из Old Stables_1.blend и *_prepared.blend — одна разметка."""
    groups: dict[tuple[str, str], list[PropEntry]] = defaultdict(list)
    for entry in store.items.values():
        if not entry.mesh_name:
            continue
        key = (_asset_pack_key(Path(entry.source_path)), entry.mesh_name.lower())
        groups[key].append(entry)

    merged = 0
    for entries in groups.values():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda e: _source_priority(e.source_path))
        canonical = entries[0]
        reviewed = next((e for e in entries if e.reviewed), None)

        if reviewed and reviewed.id != canonical.id:
            data = reviewed.to_dict()
            data["id"] = canonical.id
            data["source_path"] = canonical.source_path
            store.upsert(PropEntry.from_dict(data))
            merged += 1

        for dup in entries[1:]:
            if dup.id == canonical.id:
                continue
            if reviewed or dup.reviewed:
                dup.reviewed = True
                dup.notes = (
                    dup.notes + f"\nДубликат — разметка в {Path(canonical.source_path).name}"
                ).strip()
                store.upsert(dup)
                merged += 1
            elif canonical.reviewed:
                dup.reviewed = True
                dup.notes = (
                    dup.notes + f"\nДубликат — см. {Path(canonical.source_path).name}"
                ).strip()
                store.upsert(dup)
                merged += 1

    if merged:
        store.save()
    return merged


def _sidecar_notes(path: Path) -> str:
    for base in (path.parent, path.parent.parent):
        for name in _SIDECAR_NOTE_NAMES:
            sidecar = base / name
            if sidecar.is_file():
                try:
                    return sidecar.read_text(encoding="utf-8", errors="replace").strip()[:4000]
                except OSError:
                    continue
    return ""


def _resolve_exe(blender_exe: str, config: Any = None) -> str:
    from ..integrations.blender.exe import resolve_blender_exe

    return str(resolve_blender_exe(config, override=blender_exe or ""))


def mesh_entries_in_blend(
    path: Path,
    blender_exe: str = "",
    config: Any = None,
) -> List[Dict[str, Any]]:
    """MESH-объекты с коллекциями Blender (как в Outliner)."""
    if path.suffix.lower() != ".blend":
        return []
    try:
        from ..integrations.blender.headless import dump_blend_info

        exe = _resolve_exe(blender_exe, config)
        data = dump_blend_info(str(path), blender_exe=exe)
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        raise RuntimeError(
            f"Не удалось прочитать .blend через Blender ({path.name}): {exc}"
        ) from exc

    entries: List[Dict[str, Any]] = []
    for obj in data.get("objects") or []:
        if obj.get("type") != "MESH":
            continue
        name = (obj.get("name") or "").strip()
        if not name:
            continue
        cols = obj.get("collections") or []
        collection = cols[0] if cols else ""
        if collection.lower() in SKIP_COLLECTIONS:
            continue
        entries.append(
            {
                "name": name,
                "collection": collection,
                "vertices": obj.get("vertices", 0),
            }
        )
    entries.sort(key=lambda e: (e.get("collection", "").lower(), e.get("name", "").lower()))
    return entries


def mesh_objects_in_blend(path: Path, blender_exe: str = "") -> List[str]:
    """Обратная совместимость — только имена."""
    try:
        return [e["name"] for e in mesh_entries_in_blend(path, blender_exe)]
    except RuntimeError:
        return []


def rescan_file_level_blends(store: PropCatalogStore, *, blender_exe: str = "", config: Any = None) -> Tuple[int, int]:
    """Пересканировать .blend, которые попали в каталог «целиком»."""
    stale_paths = sorted(
        {
            e.source_path
            for e in store.items.values()
            if e.source_path.lower().endswith(".blend")
            and not e.mesh_name
            and not e.reviewed
        }
    )
    new_total = seen_total = 0
    for raw in stale_paths:
        n, s = scan_blend_file(Path(raw), store, blender_exe=blender_exe, config=config)
        new_total += n
        seen_total += s
    return new_total, seen_total


def _remove_stale_file_entry(path: Path, store: PropCatalogStore) -> None:
    file_pid = prop_id_for_path(path)
    old = store.get(file_pid)
    if old and not old.reviewed and not old.mesh_name:
        del store.items[file_pid]
        store.save()


def _entry_for_mesh(
    path: Path,
    mesh_name: str,
    all_meshes: List[str],
    *,
    collection: str = "",
) -> PropEntry:
    role, category = suggest_role_and_category(mesh_name, collection)
    notes = _sidecar_notes(path)
    if collection and collection.lower() in ("landscape", "environment"):
        notes = (notes + f"\nКоллекция {collection} — фон, Вью пометит shell автоматически.").strip()
    entry = PropEntry(
        id=prop_id_for_mesh(path, mesh_name),
        source_path=str(path),
        display_name=mesh_name.replace("_", " "),
        category=category if category != "unknown" else "unknown",
        mesh_name=mesh_name,
        collection=collection,
        role=role,
        mesh_names=list(all_meshes),
        notes=notes.strip(),
        reviewed=False,
    )
    return apply_auto_review(entry)


def apply_auto_reviews_to_store(store: PropCatalogStore) -> int:
    """Пересмотреть очередь — авто-shell для Building/Landscape и decor по имени."""
    changed = 0
    for entry in list(store.items.values()):
        if entry.reviewed:
            continue
        before = entry.reviewed
        updated = apply_auto_review(PropEntry.from_dict(entry.to_dict()))
        if updated.reviewed and not before:
            store.upsert(updated)
            changed += 1
    if changed:
        store.save()
    return changed


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
    config: Any = None,
    mesh_reader: Callable[..., List[Dict[str, Any]]] | None = None,
) -> Tuple[int, int]:
    """Скан .blend: карточка на каждый MESH (с коллекцией из Outliner)."""
    path = path.expanduser().resolve()

    if mesh_reader:
        raw = mesh_reader(path, blender_exe)
        if raw and isinstance(raw[0], str):
            mesh_list = [{"name": n, "collection": ""} for n in raw]
        else:
            mesh_list = raw
    else:
        try:
            mesh_list = mesh_entries_in_blend(path, blender_exe, config=config)
        except RuntimeError:
            mesh_list = []

    new_count = 0
    seen = 0
    all_names = [m["name"] for m in mesh_list]

    if mesh_list:
        _remove_stale_file_entry(path, store)
        for item in mesh_list:
            mesh_name = item["name"]
            pid = prop_id_for_mesh(path, mesh_name)
            if store.get(pid):
                seen += 1
                continue
            store.upsert(
                _entry_for_mesh(
                    path,
                    mesh_name,
                    all_names,
                    collection=item.get("collection", ""),
                )
            )
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
    config: Any = None,
    mesh_reader: Callable[..., Any] | None = None,
) -> Tuple[int, int]:
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
                path,
                store,
                blender_exe=blender_exe,
                config=config,
                mesh_reader=mesh_reader,
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
