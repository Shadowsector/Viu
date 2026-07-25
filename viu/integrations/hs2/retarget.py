"""Запуск Blender: HS2 FBX → humanoid FBX в Inbox."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from ...config import Config
from ...integrations.blender.exe import resolve_blender_exe
from .bone_map import bone_map_dict
from .paths import default_retarget_rig_path, hs2_fbx_dump_dir
from .fbx_import import import_fbx_dump

_BODY = Path(__file__).resolve().parent / "_retarget_blender_body.py"
_MARK_BEGIN = "<<<VIU_HS2_RETARGET_BEGIN>>>"
_MARK_END = "<<<VIU_HS2_RETARGET_END>>>"


def retarget_hs2_fbx(
    config: Config,
    source_fbx: Path,
    *,
    target_rig: Optional[Path] = None,
    out_fbx: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Ретаргет одного FBX (скелет HS2) на Mixamo rig → FBX только анимация."""
    source_fbx = source_fbx.expanduser().resolve()
    if not source_fbx.is_file():
        return False, f"Нет файла: {source_fbx}"

    rig = target_rig or default_retarget_rig_path(config)
    if rig is None or not rig.is_file():
        return False, (
            "Нет целевого рига (Mixamo X Bot).\n"
            "Положи Mixamo_XBot.fbx в Library/HS2/ или задай VIU_HS2_RETARGET_RIG."
        )

    if out_fbx is None:
        out_dir = hs2_fbx_dump_dir(config) / "_retargeted"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_fbx = out_dir / f"{source_fbx.stem}_humanoid.fbx"
    else:
        out_fbx = out_fbx.expanduser().resolve()
        out_fbx.parent.mkdir(parents=True, exist_ok=True)

    bone_map_path = out_fbx.parent / "_bone_map.json"
    bone_map_path.write_text(
        json.dumps(bone_map_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    env = {
        "VIU_HS2_SOURCE": str(source_fbx),
        "VIU_HS2_TARGET_RIG": str(rig.resolve()),
        "VIU_HS2_OUT": str(out_fbx),
        "VIU_HS2_BONE_MAP": str(bone_map_path),
        "VIU_HS2_MARK_BEGIN": _MARK_BEGIN,
        "VIU_HS2_MARK_END": _MARK_END,
    }

    try:
        exe = resolve_blender_exe(config)
    except FileNotFoundError as exc:
        return False, str(exc)

    cmd: List[str] = [
        str(exe),
        "--background",
        "--factory-startup",
        "--python",
        str(_BODY),
        "--python-exit-code",
        "2",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            env={**dict(__import__("os").environ), **env},
        )
    except subprocess.TimeoutExpired:
        return False, "Blender timeout (10 min)"
    except OSError as exc:
        return False, str(exc)

    stdout = proc.stdout or ""
    payload = _parse_markers(stdout)
    if payload and payload.get("ok"):
        msg = str(payload.get("message") or f"OK: {out_fbx}")
        if out_fbx.is_file():
            from ...inbox_layout import inbox_animations_dir
            from .fbx_import import _unique_dest, _sanitize_out_name
            from .catalog_hints import suggest_catalog_slug

            inbox_anim = inbox_animations_dir(config)
            slug = suggest_catalog_slug(source_fbx.stem)
            out_name = _sanitize_out_name(out_fbx.stem, slug)
            dest = _unique_dest(inbox_anim / out_name)
            import shutil

            shutil.copy2(out_fbx, dest)
            msg += f"\nInbox: {dest}\n→ «Принять анимацию (Inbox)»"
        return True, msg

    err = (payload or {}).get("error") or proc.stderr[-800:] or stdout[-800:]
    return False, f"Ретаргет не удался (code {proc.returncode}):\n{err}"


def _parse_markers(stdout: str) -> Optional[dict]:
    start = stdout.find(_MARK_BEGIN)
    end = stdout.find(_MARK_END)
    if start == -1 or end == -1 or end < start:
        return None
    chunk = stdout[start + len(_MARK_BEGIN) : end]
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        return None


def retarget_first_dump(config: Config) -> Tuple[bool, str]:
    """Первый FBX в fbx_dump → retarget → Inbox."""
    dump = hs2_fbx_dump_dir(config)
    fbx = next(iter(sorted(dump.glob("*.fbx"))), None)
    if fbx is None:
        fbx = next(iter(sorted(dump.rglob("*.fbx"))), None)
    if fbx is None:
        return False, f"В {dump} нет FBX для ретаргета."
    return retarget_hs2_fbx(config, fbx)
