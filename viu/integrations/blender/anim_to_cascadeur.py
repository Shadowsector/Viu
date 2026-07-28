"""Blender-клип → Cascadeur Inbox → pending import (полировка)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ...config import Config
from ..cascadeur.import_fbx import trigger_fbx_import
from ..cascadeur.launch import ensure_cascadeur_running
from ..cascadeur.paths import cascadeur_inbox
from .exe import resolve_blender_exe
from .export_cascadeur import export_cascadeur_anim_fbx
from .make_anim import ANIM_PRESETS, make_simple_anim


def blender_anims_dir(config: Config) -> Path:
    root = Path(config.library_root or config.data_dir) / "Lab" / "Anims"
    root.mkdir(parents=True, exist_ok=True)
    (root / "BlenderOut").mkdir(parents=True, exist_ok=True)
    (root / "CascadeurReady").mkdir(parents=True, exist_ok=True)
    return root


def run_blender_anim_to_cascadeur(
    config: Config,
    blend_file: str,
    *,
    preset: str = "idle",
    action_name: str = "",
    skip_make: bool = False,
    open_cascadeur: bool = True,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Сделать клип в Blender (если нужно) → FBX с анимацией → Inbox Cascadeur.

    Дальше Ден/Вью: Commands → Viu.LabImport или File→Import (Animations ✓).
    """
    blend = Path(blend_file).expanduser()
    if not blend.is_file():
        return False, f"Blend не найден: {blend_file}", {}

    preset_n = (preset or "idle").strip().lower()
    if not skip_make and preset_n not in ANIM_PRESETS:
        return False, f"preset: {', '.join(ANIM_PRESETS)}", {}

    notes: list[str] = []
    meta: Dict[str, Any] = {"preset": preset_n, "source_blend": str(blend)}

    try:
        blender_exe = resolve_blender_exe(config)
    except FileNotFoundError as exc:
        return False, str(exc), meta

    work_blend = blend
    if not skip_make:
        out_blend = (
            blender_anims_dir(config)
            / "BlenderOut"
            / f"{blend.stem}_viu_{preset_n}.blend"
        )
        try:
            work_blend, anim_meta = make_simple_anim(
                str(blend),
                preset=preset_n,
                action_name=action_name or f"viu_{preset_n}",
                out_blend=str(out_blend),
                blender_exe=blender_exe,
            )
        except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
            return False, f"Blender make_anim: {exc}", meta
        meta["anim"] = anim_meta
        notes.append(
            f"Клип «{anim_meta.get('action')}» ({anim_meta.get('frames')} кадров) "
            f"→ {work_blend}"
        )
    else:
        notes.append(f"Без make_anim — экспортирую как есть: {work_blend}")

    fbx_out = (
        blender_anims_dir(config)
        / "CascadeurReady"
        / f"{work_blend.stem}_anim.fbx"
    )
    try:
        fbx_path, export_meta = export_cascadeur_anim_fbx(
            str(work_blend),
            str(fbx_out),
            blender_exe=blender_exe,
        )
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        return False, f"Export anim FBX: {exc}", meta
    meta["export"] = export_meta
    notes.append(f"FBX с анимацией: {fbx_path}")

    inbox = cascadeur_inbox(config)
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / fbx_path.name
    try:
        shutil.copy2(fbx_path, dest)
    except OSError as exc:
        return False, f"Не скопировать в Cascadeur Inbox: {exc}", meta
    meta["inbox_fbx"] = str(dest)
    notes.append(f"Inbox: {dest}")

    if open_cascadeur:
        ok_run, run_msg = ensure_cascadeur_running(config)
        notes.append(run_msg)
        if not ok_run:
            notes.append("Cascadeur не поднялся — FBX уже в Inbox, импорт вручную.")
            return True, "\n".join(notes), meta

    ok_imp, imp_msg, opened = trigger_fbx_import(
        config, dest, topic="cascadeur", mode="animation"
    )
    notes.append(imp_msg)
    meta["import_opened"] = opened
    if not ok_imp:
        return False, "\n".join(notes), meta

    notes.append(
        "\nДальше в Cascadeur: полируй клип (физика/позы), "
        "Export → U:\\Anabarra\\Animations → «Обновить аниматор»."
    )
    return True, "\n".join(notes), meta
