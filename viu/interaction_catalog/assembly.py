"""Assembly: клипы актёров + сокеты/SyncMarker (не dual-mocap).

1) Пишет `assembly_job.json` (план).
2) Гоняет Blender: импорт клипов, timeline markers, Empty active_socket.
Полные constraints source→socket и экспорт FBX — следующий слой.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from ..config import Config
from ..creature_catalog.sockets import list_girl_socket_ids
from .models import STATUS_ASSEMBLED, InteractionWish, SyncMarker
from .paths import actor_dir, interaction_catalog_path, interaction_scene_dir
from .store import InteractionCatalogStore

ASSEMBLY_JOB_NAME = "assembly_job.json"
ASSEMBLY_SCRIPT_NAME = "viu_interaction_assembly.py"
NSFW_SCRIPT_NAME = "viu_nsfw_attach.py"
DEFAULT_ACTIVE_SOCKET = "socket_hand_r"

_BLENDER_BODY = Path(__file__).resolve().parent / "_assembly_blender_body.py"
_NSFW_SRC = Path(__file__).resolve().parent.parent / "creature_catalog" / "nsfw_attach.py"

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


def _pick_socket_owner_role(wish: InteractionWish) -> str:
    for a in wish.actors:
        slug = (a.creature_slug or "").strip().lower()
        if a.role == "target" or slug in ("shanya", "шаня"):
            return a.role
    return wish.actors[0].role if wish.actors else "target"


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


def _install_assembly_scripts(out_dir: Path) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if not _BLENDER_BODY.is_file():
        raise FileNotFoundError(f"Нет скрипта assembly: {_BLENDER_BODY}")
    dest = out_dir / ASSEMBLY_SCRIPT_NAME
    shutil.copyfile(_BLENDER_BODY, dest)
    nsfw_dest = out_dir / NSFW_SCRIPT_NAME
    if _NSFW_SRC.is_file():
        shutil.copyfile(_NSFW_SRC, nsfw_dest)
    return dest, nsfw_dest


def build_socket_sync_job(
    config: Config,
    wish: InteractionWish,
    *,
    active_socket: str = "",
) -> Tuple[bool, str, Path]:
    """Собрать assembly_job.json + Blender-скрипт рядом."""
    scene = interaction_scene_dir(config, wish.slug)
    assembly_dir = scene / "assembly"
    exports_dir = scene / "exports"
    assembly_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    script_path, nsfw_path = _install_assembly_scripts(assembly_dir)
    socket_id = _pick_active_socket(wish, active_socket=active_socket)
    owner_role = _pick_socket_owner_role(wish)
    actors = _actor_clip_paths(config, wish)
    ch = wish.choreography
    blend_path = assembly_dir / "assembly.blend"

    job: Dict[str, Any] = {
        "version": 1,
        "mode": "socket_sync",
        "comment": (
            "Не dual-mocap: каждый актёр — свой клип; стыковка через "
            "active_socket + SyncMarker на общей timeline. "
            "IK/constraints source→socket — следующий слой."
        ),
        "interaction_slug": wish.slug,
        "assembly_blend": str(blend_path),
        "frame_start": 0,
        "fps": ch.fps,
        "duration_frames": ch.duration_frames,
        "active_socket": socket_id,
        "socket_owner_role": owner_role,
        "sync_markers": _markers_payload(wish.sync_markers),
        "actors": actors,
        "constraints_planned": [
            {
                "type": "socket_aim",
                "socket": socket_id,
                "owner_role": owner_role,
                "at_markers": [
                    m.event
                    for m in wish.sync_markers
                    if m.event.startswith("contact")
                ],
                "status": "deferred",
            },
            {
                "type": "shared_timeline",
                "frame_start": 0,
                "frame_end": max(0, ch.duration_frames - 1),
            },
        ],
        "blender_script": str(script_path),
        "nsfw_script": str(nsfw_path) if nsfw_path.is_file() else "",
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
        f"assembly_job: `{wish.slug}` socket=`{socket_id}` owner=`{owner_role}`, "
        f"актёров={len(actors)}, маркеров={len(wish.sync_markers)}.{hint}"
    )
    return True, msg, job_path


def _parse_assembly_stdout(stdout: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], bool]:
    actors: List[Dict[str, Any]] = []
    socket: Dict[str, Any] = {}
    ok = False
    for line in (stdout or "").splitlines():
        if "VIU_ASSEMBLY_ACTOR" in line:
            raw = line.split("VIU_ASSEMBLY_ACTOR", 1)[-1].strip()
            try:
                actors.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        if "VIU_ASSEMBLY_SOCKET" in line:
            raw = line.split("VIU_ASSEMBLY_SOCKET", 1)[-1].strip()
            try:
                socket = json.loads(raw)
            except json.JSONDecodeError:
                pass
        if "VIU_ASSEMBLY_OK" in line:
            ok = True
    return actors, socket, ok


def run_assembly_blender_job(
    job_path: Path,
    *,
    config: Config,
    timeout: float = 600.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[bool, str, Path]:
    from ..integrations.blender.exe import resolve_blender_exe

    job_path = Path(job_path)
    if not job_path.is_file():
        return False, f"Job не найден: {job_path}", Path()
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Job битый: {exc}", Path()

    blend_out = Path(job.get("assembly_blend") or (job_path.parent / "assembly.blend"))
    script_path = Path(job.get("blender_script") or (job_path.parent / ASSEMBLY_SCRIPT_NAME))
    if not script_path.is_file():
        _install_assembly_scripts(job_path.parent)
        script_path = job_path.parent / ASSEMBLY_SCRIPT_NAME

    try:
        exe = resolve_blender_exe(config)
    except FileNotFoundError as exc:
        return False, str(exc), Path()

    cmd = [
        str(exe),
        "--background",
        "--python",
        str(script_path),
        "--",
        str(job_path),
    ]
    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"Blender не уложился в {int(timeout)}с", Path()
    except OSError as exc:
        return False, f"Не удалось запустить Blender: {exc}", Path()

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    _actors, _socket, ok_mark = _parse_assembly_stdout(proc.stdout or "")
    if proc.returncode != 0 and not ok_mark:
        return False, f"Blender код {proc.returncode}.\n{combined.strip()[-1800:]}", Path()
    if not blend_out.is_file():
        return False, f"Файл не создан: {blend_out}\n{combined.strip()[-1200:]}", Path()

    return True, f"OK: {blend_out.name}", blend_out


def _update_catalog_assembly(config: Config, wish: InteractionWish, blend_path: Path) -> None:
    store = InteractionCatalogStore(interaction_catalog_path(config)).load()
    cur = store.get_by_slug(wish.slug) or wish
    cur.assembly_blend = str(blend_path)
    if cur.status not in (STATUS_ASSEMBLED, "verified", "linked"):
        cur.status = STATUS_ASSEMBLED
    store.upsert(cur)
    store.save()


def _open_blend(path: Path) -> str:
    path = Path(path)
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return f"Открыла: {path}"
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return f"Открыла: {path}"
        subprocess.Popen(["xdg-open", str(path)])
        return f"Открыла: {path}"
    except OSError as exc:
        return f"Не смогла открыть ({exc}): {path}"


def run_interaction_assembly(
    config: Config,
    wish: InteractionWish,
    *,
    active_socket: str = "",
    require_clips: bool = True,
    run_blender: bool = True,
    open_result: bool = False,
    timeout: float = 600.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[bool, str]:
    """Job → (опц.) Blender assembly.blend → каталог."""
    ok, msg, job_path = build_socket_sync_job(
        config, wish, active_socket=active_socket
    )
    if not ok:
        return False, msg

    job = json.loads(job_path.read_text(encoding="utf-8"))
    missing = [a["role"] for a in job.get("actors") or [] if a.get("clip_missing")]
    if require_clips and missing:
        return (
            False,
            f"Нет mocap.fbx для ролей: {', '.join(missing)}. "
            f"Сначала шаг MoCap / Control Pose.\n{msg}",
        )

    lines = [msg]
    if not run_blender:
        blend = str(job.get("assembly_blend") or "")
        store = InteractionCatalogStore(interaction_catalog_path(config)).load()
        cur = store.get_by_slug(wish.slug) or wish
        cur.assembly_blend = blend
        store.upsert(cur)
        store.save()
        lines.extend(
            [
                f"Job: {job_path}",
                f"Цель blend: {blend}",
                f"active_socket: {job.get('active_socket')}",
                "Blender не запускала (run_blender=false).",
            ]
        )
        return True, "\n".join(lines)

    if missing:
        return (
            False,
            f"Нельзя собрать без клипов: {', '.join(missing)}.\n{msg}",
        )

    lines.append("Запускаю Blender assembly…")
    jok, jmsg, blend = run_assembly_blender_job(
        job_path, config=config, timeout=timeout, runner=runner
    )
    lines.append(jmsg)
    if not jok:
        return False, "\n".join(lines)

    _update_catalog_assembly(config, wish, blend)
    lines.append(f"assembly.blend: {blend}")
    lines.append(f"active_socket: {job.get('active_socket')} (owner={job.get('socket_owner_role')})")
    lines.append("Constraints source→socket — следующий слой (сцена уже с клипами+маркерами).")
    if open_result:
        lines.append(_open_blend(blend))
    return True, "\n".join(lines)
