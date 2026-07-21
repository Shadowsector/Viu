"""Wardrobe в Blender — наборы одежды и видимость мешей."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..config import Config
from .lineup import queue_creatures_from_catalog
from .models import CreatureEntry
from .models import GENITAL_PROFILE_LABELS, GENITAL_PROFILES
from .appearance import (
    HAIR_COLOR_IDS,
    HAIR_COLOR_LABELS,
    SKIN_TONE_IDS,
    SKIN_TONE_LABELS,
)
from .paths import (
    creature_catalog_path,
    creature_outfit_sets_path,
    creature_prepared_blend_path,
    creatures_inbox_dir,
    creatures_wardrobe_dir,
)
from .scanner import scan_creatures_inbox
from .studio import is_prepared_for_studio
from .note_utils import append_pipeline_note
from .store import CreatureCatalogStore

ADDON_NAME = "viu_creature_wardrobe.py"
BOOTSTRAP_NAME = "viu_creature_wardrobe_bootstrap.py"
SHARED_NAME = "viu_creature_blender_shared.py"
SESSION_NAME = "wardrobe_session.json"
FEEDBACK_NAME = "wardrobe_feedback.json"

_ADDON_BODY = Path(__file__).resolve().parent / "_creature_wardrobe_addon.py"
_BOOTSTRAP_BODY = Path(__file__).resolve().parent / "_creature_wardrobe_bootstrap.py"
_SHARED_BODY = Path(__file__).resolve().parent / "_creature_blender_shared.py"


def _install_wardrobe_files(out_dir: Path) -> Tuple[Path, Path]:
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
            raise FileNotFoundError(f"Нет файла wardrobe: {src}")
        shutil.copyfile(src, dst)
    return addon, bootstrap


def _entry_payload(e: CreatureEntry, config: Config) -> Dict[str, Any]:
    prep = e.prepared_path or str(creature_prepared_blend_path(config, e.slug))
    return {
        "id": e.id,
        "slug": e.slug,
        "name": e.name,
        "path": prep,
        "outfit_sets_path": str(creature_outfit_sets_path(config, e.slug)),
        "genital_profile": e.genital_profile or "none",
        "genital_rig": e.genital_rig or "none",
        "skin_tone": e.skin_tone or "default",
        "hair_color": e.hair_color or "default",
    }


def build_wardrobe_queue(
    config: Config,
    *,
    slug_filter: Sequence[str] = (),
    rescan_inbox: bool = False,
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
        ]
    creatures = sorted(creatures, key=lambda e: e.name.lower())
    if not creatures:
        return False, "Очередь wardrobe пуста — сначала prepared.blend.", []
    return True, f"К wardrobe: {len(creatures)}.", creatures


def write_wardrobe_session(
    config: Config,
    creatures: Sequence[CreatureEntry],
    *,
    index: int = 0,
) -> Path:
    wardrobe_dir = creatures_wardrobe_dir(config)
    _install_wardrobe_files(wardrobe_dir)
    session = {
        "catalog_path": str(creature_catalog_path(config)),
        "feedback_path": str(wardrobe_dir / FEEDBACK_NAME),
        "index": max(0, min(index, len(creatures) - 1)),
        "genital_profiles": [
            {"id": g, "label": GENITAL_PROFILE_LABELS.get(g, g)} for g in GENITAL_PROFILES
        ],
        "skin_tones": [
            {"id": sid, "label": SKIN_TONE_LABELS.get(sid, sid)} for sid in SKIN_TONE_IDS
        ],
        "hair_colors": [
            {"id": hid, "label": HAIR_COLOR_LABELS.get(hid, hid)} for hid in HAIR_COLOR_IDS
        ],
        "queue": [_entry_payload(e, config) for e in creatures],
    }
    path = wardrobe_dir / SESSION_NAME
    path.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def sync_wardrobe_feedback(config: Config) -> Tuple[int, str]:
    fb = creatures_wardrobe_dir(config) / FEEDBACK_NAME
    if not fb.is_file():
        return 0, "Нет wardrobe_feedback.json."
    try:
        data = json.loads(fb.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return 0, f"Битый wardrobe feedback: {exc}"
    rows = data.get("entries") or []
    if not rows:
        return 0, "Wardrobe feedback пуст."

    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    n = 0
    lines: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        e = store.get(str(row.get("id") or ""))
        if e is None:
            continue
        if row.get("outfit_sets_path"):
            e.outfit_sets_path = str(row["outfit_sets_path"])
        gp = str(row.get("genital_profile") or "").strip()
        if gp in GENITAL_PROFILES:
            e.genital_profile = gp
        gr = str(row.get("genital_rig") or "").strip()
        if gr in ("none", "pending", "attached"):
            e.genital_rig = gr
        from .appearance import normalize_hair_color, normalize_skin_tone

        if row.get("skin_tone"):
            e.skin_tone = normalize_skin_tone(str(row["skin_tone"]))
        if row.get("hair_color"):
            e.hair_color = normalize_hair_color(str(row["hair_color"]))
        e.sync_nsfw_capable()
        if row.get("wardrobe_notes"):
            e.notes = append_pipeline_note(e.notes or "", "wardrobe", str(row["wardrobe_notes"]))
        store.upsert(e)
        n += 1
        confirmed = row.get("outfit_sets_confirmed") or 0
        lines.append(f"  • {e.name}: наборов {confirmed}")
        if row.get("wardrobe_notes"):
            lines.append(f"      [wardrobe] {str(row['wardrobe_notes'])[:120]}")
    if n:
        store.save()
    return n, f"Синхронизировано wardrobe: {n}\n" + "\n".join(lines[:30])


def open_creature_wardrobe(
    config: Config,
    *,
    slug_filter: Sequence[str] = (),
    runner: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> Tuple[bool, str]:
    ok, msg, queue = build_wardrobe_queue(config, slug_filter=slug_filter)
    if not ok:
        return False, msg
    session = write_wardrobe_session(config, queue)
    wardrobe_dir = creatures_wardrobe_dir(config)
    _, bootstrap = _install_wardrobe_files(wardrobe_dir)

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
    return (
        True,
        f"{msg}\nBlender → N → Viu → **Wardrobe**.\n"
        f"Очередь: {names}\n"
        "Тип (Casual…) + вариант 1–3 → Сохранить. Кожа/волосы/гениталии — блок «Внешность».\n"
        "Потом «Синхр. wardrobe» → «Студия существ».",
    )
