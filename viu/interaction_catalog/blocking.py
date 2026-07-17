"""Blocking Blender: актёры + маркеры + studio-камера."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..config import Config
from ..creature_catalog import CreatureCatalogStore, creature_catalog_path
from ..creature_catalog.lineup import resolve_shanya_path
from ..creature_catalog.models import CreatureEntry
from .models import InteractionWish, STATUS_BLOCKING, SyncMarker
from .paths import interaction_scene_dir

BLOCKING_SCRIPT_NAME = "viu_interaction_blocking.py"
_BLENDER_BODY = Path(__file__).resolve().parent / "_blocking_blender_body.py"

# Пилот shanya_wolf_approach — target в центре, initiator сбоку
_DEFAULT_LAYOUT: Dict[str, Dict[str, float]] = {
    "target": {"x": 0.0, "y": 0.0, "yaw_deg": 0.0},
    "initiator": {"x": 1.15, "y": 0.65, "yaw_deg": -32.0},
    "bystander": {"x": -1.8, "y": -0.5, "yaw_deg": 15.0},
    "mount": {"x": 0.0, "y": 0.0, "yaw_deg": 0.0},
    "rider": {"x": 0.0, "y": 0.0, "yaw_deg": 0.0},
}

# 3D-точки маркеров (дополняются после расстановки актёров в Blender job)
_DEFAULT_MARKER_OFFSETS: Dict[str, Tuple[float, float, float]] = {
    "start": (0.0, 0.0, 0.0),
    "contact_shoulder": (0.28, 0.12, 1.32),
    "release": (0.55, 0.45, 1.0),
    "end": (0.9, 0.7, 0.9),
}


def _install_blocking_script(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / BLOCKING_SCRIPT_NAME
    if not _BLENDER_BODY.is_file():
        raise FileNotFoundError(f"Нет скрипта blocking: {_BLENDER_BODY}")
    shutil.copyfile(_BLENDER_BODY, dest)
    return dest


def _default_target_height(slug: str, rig_kind: str) -> float:
    if slug == "shanya" or rig_kind == "humanoid":
        return 1.70
    if rig_kind == "quadruped":
        return 0.75
    return 1.0


def resolve_actor_asset(
    config: Config,
    creature_slug: str,
    *,
    rig_kind: str = "humanoid",
) -> Tuple[Optional[Path], float, str]:
    """Путь к модели, целевой рост (м), отображаемое имя."""
    slug = (creature_slug or "").strip()
    if slug.lower() in ("shanya", "шаня"):
        path = resolve_shanya_path(config)
        return path, 1.70, "Shanya"

    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    entry = store.get_by_slug(slug)
    if entry is None:
        for e in store.all():
            if e.slug == slug or e.name.lower() == slug.lower():
                entry = e
                break
    if entry is None:
        return None, _default_target_height(slug, rig_kind), slug

    path = Path(entry.path).expanduser()
    target = float(entry.target_height_m or entry.measured_height_m or 0)
    if target <= 0:
        target = _default_target_height(slug, rig_kind)
    return path if path.is_file() else None, target, entry.name or slug


def _marker_positions(wish: InteractionWish, actors: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """sync_markers + 3D координаты для empties."""
    target_h = 1.70
    for a in actors:
        if a.get("role") == "target" or a.get("slug") == "shanya":
            target_h = float(a.get("final_m") or a.get("target_m") or 1.70)
            break
    shoulder_z = target_h * 0.78
    out: List[Dict[str, Any]] = []
    for m in wish.sync_markers:
        ox, oy, oz = _DEFAULT_MARKER_OFFSETS.get(m.event, (0.0, 0.0, 0.0))
        if m.event == "contact_shoulder":
            oz = shoulder_z
        out.append(
            {
                "frame": m.frame,
                "event": m.event,
                "note": m.note,
                "x": ox,
                "y": oy,
                "z": oz,
            }
        )
    return out


def build_blocking_job(
    config: Config,
    wish: InteractionWish,
) -> Tuple[bool, str, Path]:
    """Собрать blocking_job.json + скрипт Blender."""
    blocking_dir = interaction_scene_dir(config, wish.slug) / "blocking"
    blocking_dir.mkdir(parents=True, exist_ok=True)
    _install_blocking_script(blocking_dir)

    actors_job: List[Dict[str, Any]] = []
    missing: List[str] = []
    for i, actor in enumerate(wish.actors):
        layout = dict(_DEFAULT_LAYOUT.get(actor.role) or {})
        if not layout:
            layout = {"x": float(i) * 1.4, "y": 0.0, "yaw_deg": 0.0}
        path, target_m, name = resolve_actor_asset(
            config, actor.creature_slug, rig_kind=actor.rig_kind
        )
        if path is None:
            missing.append(f"{actor.role}:{actor.creature_slug}")
            continue
        actors_job.append(
            {
                "role": actor.role,
                "slug": actor.creature_slug,
                "name": name,
                "path": str(path),
                "target_m": target_m,
                "rig_kind": actor.rig_kind,
                **layout,
            }
        )

    if missing:
        return (
            False,
            "Не найдены модели для blocking: "
            + ", ".join(missing)
            + ". Разметь creature_catalog / укажи путь к Шане.",
            Path(),
        )
    if not actors_job:
        return False, "Нет актёров в interaction.", Path()

    blend_out = blocking_dir / "blocking.blend"
    lock_out = blocking_dir / "choreography_lock.json"
    job = {
        "interaction_slug": wish.slug,
        "title_ru": wish.title_ru,
        "choreography": wish.choreography.to_dict(),
        "sync_markers": _marker_positions(wish, actors_job),
        "actors": actors_job,
        "output_blend": str(blend_out),
        "choreography_lock": str(lock_out),
    }
    job_path = blocking_dir / "blocking_job.json"
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    msg = (
        f"Blocking job: {wish.slug}\n"
        f"Актёры: {', '.join(a['role'] + ':' + a['slug'] for a in actors_job)}\n"
        f"Job: {job_path}"
    )
    return True, msg, job_path


def _parse_blocking_stdout(stdout: str) -> Tuple[List[Dict[str, Any]], bool]:
    actors: List[Dict[str, Any]] = []
    ok = False
    for line in (stdout or "").splitlines():
        if "VIU_BLOCKING_ACTOR" in line:
            raw = line.split("VIU_BLOCKING_ACTOR", 1)[-1].strip()
            try:
                actors.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        if "VIU_BLOCKING_OK" in line:
            ok = True
    return actors, ok


def run_blocking_blender_job(
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

    blend_out = Path(job.get("output_blend") or (job_path.parent / "blocking.blend"))
    script_path = job_path.parent / BLOCKING_SCRIPT_NAME
    if not script_path.is_file():
        _install_blocking_script(job_path.parent)

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
    _actors, ok_mark = _parse_blocking_stdout(proc.stdout or "")
    if proc.returncode != 0 and not ok_mark:
        return False, f"Blender код {proc.returncode}.\n{combined.strip()[-1800:]}", Path()
    if not blend_out.is_file():
        return False, f"Файл не создан: {blend_out}\n{combined.strip()[-1200:]}", Path()

    return True, f"OK: {blend_out.name}", blend_out


def _update_catalog_blocking(config: Config, wish: InteractionWish, blend_path: Path) -> None:
    from .paths import interaction_catalog_path
    from .store import InteractionCatalogStore

    store = InteractionCatalogStore(interaction_catalog_path(config)).load()
    cur = store.get_by_slug(wish.slug)
    if cur is None:
        return
    cur.blocking_blend = str(blend_path)
    if cur.status == "wished":
        cur.status = STATUS_BLOCKING
    store.upsert(cur)
    store.save()


def run_interaction_blocking(
    config: Config,
    wish: InteractionWish,
    *,
    open_result: bool = True,
    timeout: float = 600.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[bool, str]:
    """Подготовить job, прогнать Blender, обновить каталог."""
    ok, prep, job_path = build_blocking_job(config, wish)
    if not ok:
        return False, prep

    lines = [prep, "", "Запускаю Blender blocking…"]
    jok, jmsg, blend = run_blocking_blender_job(
        job_path, config=config, timeout=timeout, runner=runner
    )
    lines.append(jmsg)
    if not jok:
        return False, "\n".join(lines)

    _update_catalog_blocking(config, wish, blend)
    lock = blend.parent / "choreography_lock.json"
    if lock.is_file():
        lines.append(f"Choreography lock: {lock}")
    lines.append(f"Маркеры: {', '.join(m.event for m in wish.sync_markers)}")
    if open_result:
        lines.append(_open_blend(blend))
    return True, "\n".join(lines)


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
