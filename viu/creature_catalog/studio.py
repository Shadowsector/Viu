"""Студия существ в Blender — по одному рядом с Шаней."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..config import Config
from .lineup import dedupe_by_stem, resolve_shanya_path
from .models import CreatureEntry
from .paths import (
    creature_catalog_path,
    creature_processed_slug_dir,
    creatures_processed_dir,
    creatures_studio_dir,
)
from .store import CreatureCatalogStore

ADDON_NAME = "viu_creature_studio.py"
BOOTSTRAP_NAME = "viu_creature_studio_bootstrap.py"
SESSION_NAME = "studio_session.json"
FEEDBACK_NAME = "studio_feedback.json"

_ADDON_BODY = Path(__file__).resolve().parent / "_creature_studio_addon.py"
_BOOTSTRAP_BODY = Path(__file__).resolve().parent / "_creature_studio_bootstrap.py"


def _install_studio_files(out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    addon = out_dir / ADDON_NAME
    bootstrap = out_dir / BOOTSTRAP_NAME
    if not _ADDON_BODY.is_file():
        raise FileNotFoundError(f"Нет аддона студии: {_ADDON_BODY}")
    if not _BOOTSTRAP_BODY.is_file():
        raise FileNotFoundError(f"Нет bootstrap студии: {_BOOTSTRAP_BODY}")
    shutil.copyfile(_ADDON_BODY, addon)
    shutil.copyfile(_BOOTSTRAP_BODY, bootstrap)
    return addon, bootstrap


def _entry_payload(e: CreatureEntry) -> Dict[str, Any]:
    return {
        "id": e.id,
        "slug": e.slug,
        "name": e.name,
        "path": e.path,
        "size_class": e.size_class,
        "target_height_m": e.target_height_m,
        "locomotion": e.locomotion,
        "photo_ok": e.photo_ok,
        "photo_front": e.photo_front,
        "photo_side": e.photo_side,
        "photo_notes": e.photo_notes,
        "prepared_path": e.prepared_path,
        "notes": (e.notes or "").split("\n")[0][:200],
    }


def build_studio_queue(
    config: Config,
    *,
    slug_filter: Sequence[str] = (),
    only_unapproved: bool = False,
    only_missing_photos: bool = False,
) -> Tuple[bool, str, List[CreatureEntry]]:
    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    creatures = dedupe_by_stem(store.sized())
    if slug_filter:
        want = {s.strip().lower() for s in slug_filter if s.strip()}
        creatures = [
            e
            for e in creatures
            if (e.slug or "").lower() in want
            or e.name.lower() in want
            or Path(e.path).stem.lower() in want
        ]
    if only_unapproved:
        creatures = [e for e in creatures if not e.photo_ok]
    if only_missing_photos:
        creatures = [e for e in creatures if e.needs_photo_lineup()]
    creatures = sorted(creatures, key=lambda e: (e.size_class or "", e.name.lower()))
    if not creatures:
        return False, "Очередь студии пуста — разметь size_class или сними фильтр.", []
    return True, f"В очереди студии: {len(creatures)}.", creatures


def resolve_shanya_studio_path(config: Config) -> Optional[Path]:
    """Для студии: FBX с телом, не rig-.blend с WGT."""
    p = resolve_shanya_path(config)
    if p is None:
        return None
    if p.suffix.lower() == ".fbx":
        return p
    if p.suffix.lower() == ".blend":
        fbx = p.with_suffix(".fbx")
        if fbx.is_file():
            return fbx
        for cand in sorted(p.parent.glob("*Shanya*.fbx")) + sorted(
            p.parent.glob("*shanya*.fbx")
        ):
            return cand
    return p


def write_studio_session(
    config: Config,
    creatures: Sequence[CreatureEntry],
    *,
    index: int = 0,
) -> Path:
    studio_dir = creatures_studio_dir(config)
    _install_studio_files(studio_dir)
    shanya = resolve_shanya_studio_path(config)
    session = {
        "catalog_path": str(creature_catalog_path(config)),
        "feedback_path": str(studio_dir / FEEDBACK_NAME),
        "reports_dir": str(studio_dir / "reports"),
        "processed_root": str(creatures_processed_dir(config)),
        "shanya_path": str(shanya) if shanya else "",
        "shanya_target_m": 1.70,
        "creature_offset_m": 1.35,
        "index": max(0, min(index, len(creatures) - 1)),
        "queue": [_entry_payload(e) for e in creatures],
    }
    path = studio_dir / SESSION_NAME
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def sync_studio_feedback(config: Config) -> Tuple[int, str]:
    """Прочитать studio_feedback.json → обновить creature_catalog."""
    fb = creatures_studio_dir(config) / FEEDBACK_NAME
    if not fb.is_file():
        return 0, "Нет studio_feedback.json — в Blender ещё не жали Save/Скрины ок."
    try:
        data = json.loads(fb.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return 0, f"Битый feedback: {exc}"
    rows = data.get("entries") or []
    if not rows:
        return 0, "Feedback пуст."

    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    n = 0
    lines: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id") or "")
        e = store.get(cid)
        if e is None:
            continue
        if row.get("target_height_m"):
            try:
                e.target_height_m = float(row["target_height_m"])
            except (TypeError, ValueError):
                pass
        if row.get("measured_height_m"):
            try:
                e.measured_height_m = float(row["measured_height_m"])
            except (TypeError, ValueError):
                pass
        for key in ("photo_front", "photo_side", "prepared_path", "photo_notes"):
            if row.get(key):
                setattr(e, key, str(row[key]))
        issue = str(row.get("issue_report") or "").strip()
        if issue:
            e.photo_notes = issue
        if "photo_ok" in row:
            e.photo_ok = bool(row["photo_ok"])
        if e.photo_ok and e.size_class:
            from .models import STATUS_READY

            e.status = STATUS_READY
        store.upsert(e)
        n += 1
        lines.append(f"  • {e.name}: " + ("скрины ок" if e.photo_ok else "обновлено"))
    if n:
        store.save()
    return n, f"Синхронизировано из Blender: {n}\n" + "\n".join(lines[:30])


def open_creature_studio(
    config: Config,
    *,
    slug_filter: Sequence[str] = (),
    only_unapproved: bool = True,
    only_missing_photos: bool = False,
    runner: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> Tuple[bool, str]:
    ok, msg, queue = build_studio_queue(
        config,
        slug_filter=slug_filter,
        only_unapproved=only_unapproved,
        only_missing_photos=only_missing_photos,
    )
    if not ok:
        return False, msg
    session = write_studio_session(config, queue)
    studio_dir = creatures_studio_dir(config)
    _, bootstrap = _install_studio_files(studio_dir)

    from ..integrations.blender.exe import resolve_blender_exe

    try:
        exe = resolve_blender_exe(config)
    except FileNotFoundError as exc:
        return False, str(exc)

    cmd = [str(exe), "--python", str(bootstrap), "--", str(session)]
    try:
        runner(cmd, start_new_session=True)
    except OSError as exc:
        return False, f"Не удалось открыть Blender: {exc}"

    names = ", ".join(e.name for e in queue[:8])
    more = f" … +{len(queue) - 8}" if len(queue) > 8 else ""
    return (
        True,
        f"{msg}\nОткрываю Blender-студию.\n"
        f"Панель: 3D View → боковая панель (N) → вкладка **Viu**.\n"
        f"Очередь: {names}{more}\n"
        f"Session: {session}\n"
        "После правок в Blender вернись во Вью → «Синхронизировать студию».",
    )


def open_photo_folder(config: Config, slug: str) -> str:
    folder = creature_processed_slug_dir(config, slug)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
        return f"Открыла: {folder}"
    except OSError as exc:
        return f"Не смогла открыть ({exc}): {folder}"
