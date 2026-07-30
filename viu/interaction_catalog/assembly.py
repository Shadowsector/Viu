"""Assembly: клипы актёров + сокеты/SyncMarker (не dual-mocap).

Сборка — stub: пишет `assembly_job.json` с путями клипов, активным сокетом
и маркерами синхронизации. Полноценные Blender constraints — позже.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..creature_catalog.sockets import list_girl_socket_ids
from .models import InteractionWish, SyncMarker
from .paths import actor_dir, interaction_catalog_path, interaction_scene_dir
from .store import InteractionCatalogStore

ASSEMBLY_JOB_NAME = "assembly_job.json"
DEFAULT_ACTIVE_SOCKET = "socket_hand_r"

# Маркер контакта → предпочитаемый girl socket (пилот / NSFW).
_MARKER_SOCKET_HINTS: Dict[str, str] = {
    "contact_shoulder": "socket_hand_r",
    "contact_oral": "socket_oral",
    "contact_vaginal": "socket_vaginal",
    "contact_anal": "socket_anal",
    "contact_hand": "socket_hand_r",
    "contact_cleavage": "socket_cleavage",
}


def _pick_active_socket(
    wish: InteractionWish,
    *,
    active_socket: str = "",
) -> str:
    """Выбрать id сокета: явный аргумент → notes → маркер → default."""
    known = set(list_girl_socket_ids())
    explicit = (active_socket or "").strip()
    if explicit in known:
        return explicit
    notes = (wish.notes or "").lower()
    for sid in known:
        if sid in notes or sid.replace("socket_", "") in notes:
            return sid
    for m in wish.sync_markers:
        hint = _MARKER_SOCKET_HINTS.get(m.event.strip().lower(), "")
        if hint in known:
            return hint
    return DEFAULT_ACTIVE_SOCKET if DEFAULT_ACTIVE_SOCKET in known else next(iter(known), "")


def _actor_clip_paths(config: Config, wish: InteractionWish) -> List[Dict[str, Any]]:
    """Один клип на актёра — отдельные FBX, не dual-mocap."""
    out: List[Dict[str, Any]] = []
    for a in wish.actors:
        adir = actor_dir(config, wish.slug, a.role)
        mocap = adir / "mocap.fbx"
        export_name = f"{wish.slug}_{a.role}.fbx"
        out.append(
            {
                "role": a.role,
                "creature_slug": a.creature_slug,
                "rig_kind": a.rig_kind,
                "motion_path": a.motion_path,
                "clip_fbx": str(mocap) if mocap.is_file() else "",
                "clip_missing": not mocap.is_file(),
                "expected_mocap": str(mocap),
                "export_fbx": str(
                    interaction_scene_dir(config, wish.slug) / "exports" / export_name
                ),
            }
        )
    return out


def _markers_payload(markers: List[SyncMarker]) -> List[Dict[str, Any]]:
    return [m.to_dict() for m in markers]


def build_socket_sync_job(
    config: Config,
    wish: InteractionWish,
    *,
    active_socket: str = "",
) -> Tuple[bool, str, Path]:
    """Собрать assembly_job.json: клипы + active socket + SyncMarkers."""
    scene = interaction_scene_dir(config, wish.slug)
    assembly_dir = scene / "assembly"
    exports_dir = scene / "exports"
    assembly_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    socket_id = _pick_active_socket(wish, active_socket=active_socket)
    actors = _actor_clip_paths(config, wish)
    ch = wish.choreography
    blend_path = assembly_dir / "assembly.blend"

    job: Dict[str, Any] = {
        "version": 1,
        "mode": "socket_sync",
        "comment": (
            "Не dual-mocap: каждый актёр — свой клип; стыковка через "
            "active_socket + SyncMarker на общей timeline."
        ),
        "interaction_slug": wish.slug,
        "assembly_blend": str(blend_path),
        "frame_start": 0,
        "fps": ch.fps,
        "duration_frames": ch.duration_frames,
        "active_socket": socket_id,
        "sync_markers": _markers_payload(wish.sync_markers),
        "actors": actors,
        "constraints_planned": [
            {
                "type": "socket_aim",
                "socket": socket_id,
                "at_markers": [
                    m.event
                    for m in wish.sync_markers
                    if m.event.startswith("contact") or m.event in ("contact_shoulder",)
                ],
            },
            {
                "type": "shared_timeline",
                "frame_start": 0,
                "frame_end": max(0, ch.duration_frames - 1),
            },
        ],
        "blender_script": "",  # полный скрипт constraints — позже
    }

    job_path = assembly_dir / ASSEMBLY_JOB_NAME
    job_path.write_text(
        json.dumps(job, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    missing = [a["role"] for a in actors if a.get("clip_missing")]
    hint = ""
    if missing:
        hint = f" Клипы ещё нет: {', '.join(missing)} (actors/<role>/mocap.fbx)."
    msg = (
        f"assembly_job: `{wish.slug}` socket=`{socket_id}`, "
        f"актёров={len(actors)}, маркеров={len(wish.sync_markers)}.{hint}"
    )
    return True, msg, job_path


def run_interaction_assembly(
    config: Config,
    wish: InteractionWish,
    *,
    active_socket: str = "",
    require_clips: bool = False,
) -> Tuple[bool, str]:
    """Scaffold: записать job и обновить каталог. Blender constraints — позже."""
    ok, msg, job_path = build_socket_sync_job(
        config, wish, active_socket=active_socket
    )
    if not ok:
        return False, msg

    job = json.loads(job_path.read_text(encoding="utf-8"))
    if require_clips:
        missing = [a["role"] for a in job.get("actors") or [] if a.get("clip_missing")]
        if missing:
            return (
                False,
                f"Нет mocap.fbx для ролей: {', '.join(missing)}. "
                f"Сначала шаг MoCap / Control Pose.",
            )

    blend = str(job.get("assembly_blend") or "")
    store = InteractionCatalogStore(interaction_catalog_path(config)).load()
    cur = store.get_by_slug(wish.slug) or wish
    cur.assembly_blend = blend
    store.upsert(cur)
    store.save()

    lines = [
        msg,
        f"Job: {job_path}",
        f"Цель blend: {blend}",
        f"active_socket: {job.get('active_socket')}",
        "Constraints в Blender — следующий слой (сейчас только план в JSON).",
    ]
    return True, "\n".join(lines)
