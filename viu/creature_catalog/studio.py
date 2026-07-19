"""Студия существ в Blender — разметка + Шаня + эталон FBX."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..config import Config
from .lineup import queue_creatures_from_catalog, resolve_shanya_path
from .models import (
    ALL_SIZE_IDS,
    CONTACT_MODES,
    GENITAL_PROFILE_LABELS,
    GENITAL_PROFILES,
    LOCOMOTION,
    CreatureEntry,
    STATUS_READY,
    STATUS_SIZED,
    size_spec,
)
from .paths import (
    creature_catalog_path,
    creature_prepared_blend_path,
    creature_processed_slug_dir,
    creatures_inbox_dir,
    creatures_processed_dir,
    creatures_studio_dir,
)
from .scanner import scan_creatures_inbox
from .store import CreatureCatalogStore

ADDON_NAME = "viu_creature_studio.py"
BOOTSTRAP_NAME = "viu_creature_studio_bootstrap.py"
SHARED_NAME = "viu_creature_blender_shared.py"
SESSION_NAME = "studio_session.json"
FEEDBACK_NAME = "studio_feedback.json"

_ADDON_BODY = Path(__file__).resolve().parent / "_creature_studio_addon.py"
_BOOTSTRAP_BODY = Path(__file__).resolve().parent / "_creature_studio_bootstrap.py"
_SHARED_BODY = Path(__file__).resolve().parent / "_creature_blender_shared.py"


def _install_studio_files(out_dir: Path) -> Tuple[Path, Path]:
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
            raise FileNotFoundError(f"Нет файла студии: {src}")
        shutil.copyfile(src, dst)
    return addon, bootstrap


def _prepared_path_for(e: CreatureEntry, config: Config) -> Optional[Path]:
    if e.prepared_path:
        p = Path(e.prepared_path)
        if p.is_file():
            return p
    cand = creature_prepared_blend_path(config, e.slug)
    if cand.is_file():
        return cand
    return None


def is_prepared_for_studio(e: CreatureEntry, config: Config) -> bool:
    if e.prep_ok:
        return _prepared_path_for(e, config) is not None
    return _prepared_path_for(e, config) is not None


def _entry_payload(e: CreatureEntry, config: Config) -> Dict[str, Any]:
    prep = _prepared_path_for(e, config)
    load_path = str(prep) if prep else e.path
    return {
        "id": e.id,
        "slug": e.slug,
        "name": e.name,
        "path": load_path,
        "source_inbox": e.path,
        "size_class": e.size_class,
        "target_height_m": e.target_height_m,
        "locomotion": e.locomotion,
        "genital_profile": e.genital_profile or "none",
        "contact_modes": list(e.contact_modes or []),
        "photo_ok": e.photo_ok,
        "photo_front": e.photo_front,
        "photo_side": e.photo_side,
        "photo_notes": e.photo_notes,
        "prepared_path": str(prep) if prep else "",
        "ready_fbx_path": e.ready_fbx_path,
        "notes": (e.notes or "").split("\n")[0][:200],
    }


def build_studio_queue(
    config: Config,
    *,
    slug_filter: Sequence[str] = (),
    only_unapproved: bool = False,
    only_missing_photos: bool = False,
    rescan_inbox: bool = True,
) -> Tuple[bool, str, List[CreatureEntry]]:
    if rescan_inbox:
        scan_creatures_inbox(config)
    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    inbox = creatures_inbox_dir(config)
    creatures = queue_creatures_from_catalog(store.all(), inbox)
    creatures = [e for e in creatures if is_prepared_for_studio(e, config)]
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
    creatures = sorted(creatures, key=lambda e: (e.size_class or "zzz", e.name.lower()))
    if not creatures:
        return (
            False,
            "Очередь студии пуста — сначала «Подготовить модели» (prepared.blend).",
            [],
        )
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
    if not shanya:
        print(
            "VIU_STUDIO_SHANYA WARN: Shanya.fbx не найден — "
            "положите в Lab/Models/CascadeurReady/ или задайте VIU_SHANYA_FBX",
            flush=True,
        )
    size_meta = []
    for sid in ALL_SIZE_IDS:
        spec = size_spec(sid) or {}
        label = spec.get("label_ru") or sid
        size_meta.append({"id": sid, "label": label, "target_m": spec.get("target_m", 1.0)})
    session = {
        "catalog_path": str(creature_catalog_path(config)),
        "feedback_path": str(studio_dir / FEEDBACK_NAME),
        "reports_dir": str(studio_dir / "reports"),
        "processed_root": str(creatures_processed_dir(config)),
        "shanya_path": str(shanya) if shanya else "",
        "shanya_target_m": 1.70,
        "creature_offset_m": 1.35,
        "size_classes": size_meta,
        "locomotion_options": [x for x in LOCOMOTION if x != "unknown"],
        "genital_profiles": [
            {"id": g, "label": GENITAL_PROFILE_LABELS.get(g, g)} for g in GENITAL_PROFILES
        ],
        "contact_modes": list(CONTACT_MODES),
        "index": max(0, min(index, len(creatures) - 1)),
        "queue": [_entry_payload(e, config) for e in creatures],
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
        sc = str(row.get("size_class") or "").strip()
        if sc and sc in ALL_SIZE_IDS:
            spec = size_spec(sc)
            e.size_class = sc
            e.status = STATUS_SIZED
            e.reviewed = True
            if spec and not row.get("target_height_m"):
                e.target_height_m = float(spec["target_m"])
        loco = str(row.get("locomotion") or "").strip()
        if loco and loco in LOCOMOTION:
            e.locomotion = loco
        if row.get("outfit_sets_path"):
            e.outfit_sets_path = str(row["outfit_sets_path"])
        if row.get("texture_manifest_path"):
            e.texture_manifest_path = str(row["texture_manifest_path"])
        if "textures_packed" in row:
            e.textures_packed = bool(row["textures_packed"])
        gp = str(row.get("genital_profile") or "").strip()
        if gp in GENITAL_PROFILES:
            e.genital_profile = gp
        gr = str(row.get("genital_rig") or "").strip()
        if gr in ("none", "pending", "attached"):
            e.genital_rig = gr
        if row.get("contact_modes") is not None:
            e.contact_modes = [
                m for m in (row.get("contact_modes") or []) if m in CONTACT_MODES
            ]
        e.sync_nsfw_capable()
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
        for key in ("photo_front", "photo_side", "prepared_path", "photo_notes", "ready_fbx_path", "texture_manifest_path"):
            if row.get(key):
                setattr(e, key, str(row[key]))
        issue = str(row.get("issue_report") or "").strip()
        if issue:
            e.photo_notes = issue
        if "photo_ok" in row:
            e.photo_ok = bool(row["photo_ok"])
        if e.photo_ok and e.size_class:
            e.status = STATUS_READY
        store.upsert(e)
        n += 1
        tag = "скрины ок" if e.photo_ok else (e.size_class or "обновлено")
        lines.append(f"  • {e.name}: {tag}")
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
    shanya = resolve_shanya_studio_path(config)

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
    shanya_line = (
        f"Шаня: {shanya}\n"
        if shanya
        else "⚠ Шаня не найдена — положите Shanya.fbx в Lab/Models/CascadeurReady/ "
        "или задайте VIU_SHANYA_FBX перед запуском.\n"
    )
    return (
        True,
        f"{msg}\n{shanya_line}"
        f"Открываю Blender — **студия + разметка**.\n"
        f"Панель: N → Viu → «Viu — студия».\n"
        f"Очередь: {names}{more}\n"
        f"Session: {session}\n"
        "Разметка (класс/ноги), рост vs Шаня, скрины, **эталон FBX**.\n"
        "Потом во Вью → «Синхр. студии».",
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
