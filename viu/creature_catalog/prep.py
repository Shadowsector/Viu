"""Подготовка моделей существ в Blender — шаг 1 пайплайна."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..config import Config
from .lineup import queue_creatures_from_catalog
from .models import CreatureEntry, STATUS_NORMALIZED
from .paths import (
    creature_catalog_path,
    creature_prepared_blend_path,
    creatures_inbox_dir,
    creatures_prepared_dir,
    creatures_prep_dir,
)
from .scanner import scan_creatures_inbox
from .store import CreatureCatalogStore

ADDON_NAME = "viu_creature_prep.py"
BOOTSTRAP_NAME = "viu_creature_prep_bootstrap.py"
SHARED_NAME = "viu_creature_blender_shared.py"
SESSION_NAME = "prep_session.json"
FEEDBACK_NAME = "prep_feedback.json"

_ADDON_BODY = Path(__file__).resolve().parent / "_creature_prep_addon.py"
_BOOTSTRAP_BODY = Path(__file__).resolve().parent / "_creature_prep_bootstrap.py"
_SHARED_BODY = Path(__file__).resolve().parent / "_creature_blender_shared.py"


def _install_prep_files(out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    addon = out_dir / ADDON_NAME
    bootstrap = out_dir / BOOTSTRAP_NAME
    shared = out_dir / SHARED_NAME
    for src, dst in (
        (_ADDON_BODY, addon),
        (_BOOTSTRAP_BODY, bootstrap),
        (_SHARED_BODY, shared),
    ):
        if not src.is_file():
            raise FileNotFoundError(f"Нет файла prep: {src}")
        shutil.copyfile(src, dst)
    return addon, bootstrap


def _entry_payload(e: CreatureEntry) -> Dict[str, Any]:
    return {
        "id": e.id,
        "slug": e.slug,
        "name": e.name,
        "path": e.path,
        "source_inbox": e.path,
        "prepared_path": e.prepared_path,
        "prep_ok": bool(e.prep_ok),
        "notes": (e.notes or "").split("\n")[0][:200],
    }


def needs_prep_entry(e: CreatureEntry, config: Config) -> bool:
    if e.prep_ok:
        p = e.prepared_path or str(creature_prepared_blend_path(config, e.slug))
        if Path(p).is_file():
            return False
    if creature_prepared_blend_path(config, e.slug).is_file():
        return False
    return bool(e.path and Path(e.path).is_file())


def build_prep_queue(
    config: Config,
    *,
    slug_filter: Sequence[str] = (),
    only_unprepared: bool = True,
    rescan_inbox: bool = True,
) -> Tuple[bool, str, List[CreatureEntry]]:
    scan_line = ""
    if rescan_inbox:
        added, catalog_total, scan_summary = scan_creatures_inbox(config)
        scan_line = (
            f"Скан Inbox: +{added} новых, в каталоге {catalog_total} файлов "
            f"(рекурсивно по подпапкам)."
        )
    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    inbox = creatures_inbox_dir(config)
    creatures = queue_creatures_from_catalog(store.all(), inbox)
    if slug_filter:
        want = {s.strip().lower() for s in slug_filter if s.strip()}
        creatures = [
            e
            for e in creatures
            if (e.slug or "").lower() in want
            or e.name.lower() in want
            or Path(e.path).stem.lower() in want
        ]
    if only_unprepared:
        creatures = [e for e in creatures if needs_prep_entry(e, config)]
    creatures = sorted(creatures, key=lambda e: e.name.lower())
    if not creatures:
        tail = f"\n{scan_line}" if scan_line else ""
        return False, "Очередь подготовки пуста — все уже prepared или Inbox пуст." + tail, []
    head = f"К подготовке: {len(creatures)}."
    if scan_line:
        head = f"{head} {scan_line}"
    return True, head, creatures


def write_prep_session(
    config: Config,
    creatures: Sequence[CreatureEntry],
    *,
    index: int = 0,
) -> Path:
    prep_dir = creatures_prep_dir(config)
    _install_prep_files(prep_dir)
    session = {
        "catalog_path": str(creature_catalog_path(config)),
        "feedback_path": str(prep_dir / FEEDBACK_NAME),
        "prepared_root": str(creatures_prepared_dir(config)),
        "index": max(0, min(index, len(creatures) - 1)),
        "queue": [_entry_payload(e) for e in creatures],
    }
    path = prep_dir / SESSION_NAME
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def sync_prep_feedback(config: Config) -> Tuple[int, str]:
    fb = creatures_prep_dir(config) / FEEDBACK_NAME
    if not fb.is_file():
        return 0, "Нет prep_feedback.json — в Blender ещё не жали Save."
    try:
        data = json.loads(fb.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return 0, f"Битый prep feedback: {exc}"
    rows = data.get("entries") or []
    if not rows:
        return 0, "Prep feedback пуст."

    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    n = 0
    lines: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        e = store.get(str(row.get("id") or ""))
        if e is None:
            continue
        if row.get("prepared_path"):
            e.prepared_path = str(row["prepared_path"])
        if row.get("prep_ok"):
            e.prep_ok = True
            e.status = STATUS_NORMALIZED
        if row.get("texture_manifest_path"):
            e.texture_manifest_path = str(row["texture_manifest_path"])
        if "textures_packed" in row:
            e.textures_packed = bool(row["textures_packed"])
        if row.get("prep_notes"):
            e.notes = ((e.notes or "") + "\n[prep] " + str(row["prep_notes"])).strip()
        store.upsert(e)
        n += 1
        lines.append(f"  • {e.name}: " + ("prepared ✓" if e.prep_ok else "заметка"))
        if row.get("prep_notes"):
            lines.append(f"      [prep] {str(row['prep_notes'])[:120]}")
    if n:
        store.save()
    return n, f"Синхронизировано prep: {n}\n" + "\n".join(lines[:30])


def open_creature_prep(
    config: Config,
    *,
    slug_filter: Sequence[str] = (),
    only_unprepared: bool = True,
    runner: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> Tuple[bool, str]:
    ok, msg, queue = build_prep_queue(
        config, slug_filter=slug_filter, only_unprepared=only_unprepared
    )
    if not ok:
        return False, msg
    session = write_prep_session(config, queue)
    prep_dir = creatures_prep_dir(config)
    _, bootstrap = _install_prep_files(prep_dir)

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
        f"{msg}\nОткрываю Blender — **подготовка**.\n"
        f"Панель: N → Viu → «Viu — подготовка».\n"
        f"Очередь: {names}{more}\n"
        f"Session: {session}\n"
        "После Save → во Вью «Синхр. подготовки», потом «Студия существ».",
    )
