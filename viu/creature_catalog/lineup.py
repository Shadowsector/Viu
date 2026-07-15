"""Lineup в Blender: Шаня + существа — Вью сама запускает Blender."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..config import Config
from .models import CreatureEntry, STATUS_NORMALIZED
from .paths import creature_catalog_path, creatures_lineup_dir
from .store import CreatureCatalogStore

LINEUP_SCRIPT_NAME = "viu_creature_lineup.py"
# После дедупа — если больше, делаем отдельный .blend на каждый size_class
_SPLIT_AFTER = 12
_EXT_PREF = {".blend": 0, ".glb": 1, ".gltf": 2, ".fbx": 3, ".obj": 4}


def _shanya_candidates(config: Config) -> List[Path]:
    from ..anabarra_layout import library_root

    lib = library_root(config)
    cands: List[Path] = []
    for rel in (
        ("Lab", "Models", "CascadeurReady"),
        ("Lab", "Models", "Inbox"),
        ("Characters", "Shanya"),
        ("Blender", "Shanya"),
    ):
        d = lib.joinpath(*rel)
        if d.is_dir():
            for p in sorted(d.glob("*Shanya*.fbx")) + sorted(d.glob("*shanya*.fbx")):
                cands.append(p)
            for p in sorted(d.glob("*Shanya*.blend")) + sorted(d.glob("*Erisa*.fbx")):
                cands.append(p)
    try:
        from ..anabarra_layout import unity_project_path

        u = unity_project_path(config) / "Assets" / "Characters" / "Shanya"
        if u.is_dir():
            cands.extend(sorted(u.rglob("*.fbx")))
    except Exception:
        pass
    out: List[Path] = []
    seen = set()
    for p in cands:
        try:
            k = str(p.resolve())
        except OSError:
            k = str(p)
        if k not in seen and p.is_file():
            seen.add(k)
            out.append(p)
    return out


def resolve_shanya_path(config: Config, explicit: str = "") -> Optional[Path]:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    cands = _shanya_candidates(config)
    return cands[0] if cands else None


def _ext_rank(path: str) -> int:
    return _EXT_PREF.get(Path(path).suffix.lower(), 99)


def dedupe_by_stem(creatures: Sequence[CreatureEntry]) -> List[CreatureEntry]:
    """Один файл на имя: предпочитаем .blend → .glb → .fbx."""
    best: Dict[str, CreatureEntry] = {}
    for e in creatures:
        stem = Path(e.path).stem.lower() or e.slug or e.name.lower()
        prev = best.get(stem)
        if prev is None or _ext_rank(e.path) < _ext_rank(prev.path):
            best[stem] = e
    return sorted(best.values(), key=lambda e: (e.size_class or "", e.name.lower()))


def _write_job_files(
    out_dir: Path,
    *,
    shanya: Optional[Path],
    creatures: Sequence[CreatureEntry],
    blend_out: Path,
    spacing_m: float,
    job_name: str = "lineup_job.json",
) -> Path:
    entries = []
    for i, e in enumerate(creatures):
        entries.append(
            {
                "id": e.id,
                "name": e.name,
                "path": e.path,
                "size_class": e.size_class,
                "target_height_m": e.target_height_m or 1.0,
                "measured_height_m": e.measured_height_m or 0.0,
                "index": i,
            }
        )
    job = {
        "shanya_path": str(shanya) if shanya else "",
        "shanya_target_m": 1.70,
        "spacing_m": spacing_m,
        "output_blend": str(blend_out),
        "creatures": entries,
    }
    job_path = out_dir / job_name
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return job_path


def build_lineup_jobs(
    config: Config,
    *,
    size_filter: Sequence[str] = (),
    shanya_path: str = "",
    spacing_m: float = 1.2,
    split: Optional[bool] = None,
    all_files: bool = False,
) -> Tuple[bool, str, List[Path]]:
    """Собрать job(ы) + скрипт. По умолчанию дедуп и сплит по классам если много."""
    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    creatures = [e for e in store.all() if e.size_class]
    if size_filter:
        want = {s.strip() for s in size_filter if s.strip()}
        creatures = [
            e
            for e in creatures
            if e.size_class in want or any(a in want for a in e.size_alt)
        ]
    if not creatures:
        return (
            False,
            "Нет существ с размером. Сначала «Разметить существ».",
            [],
        )

    raw_n = len(creatures)
    if not all_files:
        creatures = dedupe_by_stem(creatures)
    deduped_n = len(creatures)

    shanya = resolve_shanya_path(config, shanya_path)
    out_dir = creatures_lineup_dir(config)
    script_path = out_dir / LINEUP_SCRIPT_NAME
    script_path.write_text(_LINEUP_BLENDER_SCRIPT, encoding="utf-8")

    do_split = split if split is not None else (deduped_n > _SPLIT_AFTER)
    job_paths: List[Path] = []

    if do_split:
        by_size: Dict[str, List[CreatureEntry]] = {}
        for e in creatures:
            by_size.setdefault(e.size_class or "unset", []).append(e)
        for size_id, group in sorted(by_size.items()):
            blend_out = out_dir / f"creature_lineup_{size_id}.blend"
            job_paths.append(
                _write_job_files(
                    out_dir,
                    shanya=shanya,
                    creatures=group,
                    blend_out=blend_out,
                    spacing_m=spacing_m,
                    job_name=f"lineup_job_{size_id}.json",
                )
            )
        # обзор: по одному представителю класса
        samples = [group[0] for _, group in sorted(by_size.items())]
        job_paths.insert(
            0,
            _write_job_files(
                out_dir,
                shanya=shanya,
                creatures=samples,
                blend_out=out_dir / "creature_lineup_overview.blend",
                spacing_m=max(spacing_m, 1.5),
                job_name="lineup_job_overview.json",
            ),
        )
    else:
        job_paths.append(
            _write_job_files(
                out_dir,
                shanya=shanya,
                creatures=creatures,
                blend_out=out_dir / "creature_lineup.blend",
                spacing_m=spacing_m,
                job_name="lineup_job.json",
            )
        )

    note = (
        f"Подготовка: было {raw_n} файлов"
        + (f", после дедупа имён: {deduped_n}" if not all_files else "")
        + (f", сцен: {len(job_paths)} (по классам + обзор)" if do_split else ", одна сцена")
        + f".\nШаня: {shanya or 'НЕ НАЙДЕНА'}\nПапка: {out_dir}"
    )
    return True, note, job_paths


def build_lineup_job(
    config: Config,
    *,
    size_filter: Sequence[str] = (),
    shanya_path: str = "",
    spacing_m: float = 1.2,
) -> Tuple[bool, str, Path]:
    """Совместимость: первый job path."""
    ok, msg, jobs = build_lineup_jobs(
        config,
        size_filter=size_filter,
        shanya_path=shanya_path,
        spacing_m=spacing_m,
    )
    if not ok or not jobs:
        return ok, msg, Path()
    return True, msg + f"\nJob: {jobs[0]}", jobs[0]


def _parse_measured(stdout: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in (stdout or "").splitlines():
        if "VIU_LINEUP_ROW" not in line:
            continue
        raw = line.split("VIU_LINEUP_ROW", 1)[-1].strip()
        try:
            rows.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return rows


def _apply_measured(config: Config, rows: Sequence[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    n = 0
    for row in rows:
        cid = str(row.get("id") or "")
        e = store.get(cid)
        if e is None:
            continue
        try:
            measured = float(row.get("measured_m") or 0)
            scale = float(row.get("scale") or 0)
        except (TypeError, ValueError):
            continue
        if measured > 0:
            e.measured_height_m = measured
        if scale > 0:
            e.scale_applied = scale
        if e.status == "sized":
            e.status = STATUS_NORMALIZED
        store.upsert(e)
        n += 1
    if n:
        store.save()
    return n


def run_blender_lineup_job(
    job_path: Path,
    *,
    config: Config,
    timeout: float = 900.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[bool, str, Path]:
    """Запустить один job через blender --background."""
    from ..integrations.blender.exe import resolve_blender_exe

    job_path = Path(job_path)
    if not job_path.is_file():
        return False, f"Job не найден: {job_path}", Path()
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Job битый: {exc}", Path()
    blend_out = Path(job.get("output_blend") or (job_path.parent / "creature_lineup.blend"))
    script_path = job_path.parent / LINEUP_SCRIPT_NAME
    if not script_path.is_file():
        script_path.write_text(_LINEUP_BLENDER_SCRIPT, encoding="utf-8")

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
        return False, f"Blender не уложился в {int(timeout)}с на {job_path.name}", Path()
    except OSError as exc:
        return False, f"Не удалось запустить Blender: {exc}", Path()

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    rows = _parse_measured(proc.stdout or "")
    updated = _apply_measured(config, rows)
    ok_mark = "VIU_LINEUP_OK" in combined
    if proc.returncode != 0 and not ok_mark:
        tail = combined.strip()[-1800:]
        return False, f"Blender код {proc.returncode} ({job_path.name}).\n{tail}", Path()
    if not blend_out.is_file():
        return False, f"Файл не создан: {blend_out}\n{combined.strip()[-1200:]}", Path()

    msg = f"OK: {blend_out.name} ({len(job.get('creatures') or [])} моделей"
    if updated:
        msg += f", рост записан у {updated}"
    msg += ")"
    return True, msg, blend_out


def open_lineup_result(path: Path) -> str:
    """Открыть .blend или папку Lineup."""
    path = Path(path)
    target = path if path.is_file() or path.is_dir() else path.parent
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
            return f"Открыла: {target}"
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
            return f"Открыла: {target}"
        subprocess.Popen(["xdg-open", str(target)])
        return f"Открыла: {target}"
    except OSError as exc:
        return f"Не смогла открыть ({exc}): {target}"


def run_creature_lineup(
    config: Config,
    *,
    size_filter: Sequence[str] = (),
    shanya_path: str = "",
    spacing_m: float = 1.2,
    split: Optional[bool] = None,
    all_files: bool = False,
    open_result: bool = True,
    timeout: float = 900.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[bool, str]:
    """Подготовить job(ы), прогнать Blender, открыть результат."""
    ok, prep, jobs = build_lineup_jobs(
        config,
        size_filter=size_filter,
        shanya_path=shanya_path,
        spacing_m=spacing_m,
        split=split,
        all_files=all_files,
    )
    if not ok or not jobs:
        return False, prep

    lines = [prep, "", "Запускаю Blender сама (тебе ничего копировать не надо)…"]
    blends: List[Path] = []
    failed = 0
    for jp in jobs:
        jok, jmsg, bout = run_blender_lineup_job(
            jp, config=config, timeout=timeout, runner=runner
        )
        lines.append(("✓ " if jok else "✗ ") + jmsg)
        if jok and bout:
            blends.append(bout)
        else:
            failed += 1

    out_dir = creatures_lineup_dir(config)
    if blends:
        # обзор первым, иначе первый успешный
        prefer = next((b for b in blends if "overview" in b.name), blends[0])
        if open_result:
            lines.append(open_lineup_result(prefer))
            if len(blends) > 1:
                lines.append(open_lineup_result(out_dir))
        lines.append("")
        lines.append("Смотри рост рядом с Шаней. Кто выбивается — снова «Разметить существ».")
        lines.append(f"Все файлы: {out_dir}")
        return failed == 0, "\n".join(lines)

    return False, "\n".join(lines)


# Исполняется внутри Blender (bpy).
# Политика: только импорт + scale корня + расстановка.
# НЕ apply modifiers, НЕ bake shape keys, НЕ трогать morphs ушей/хвостов/гениталий.
_LINEUP_BLENDER_SCRIPT = textwrap.dedent(
    r'''
"""Viu — lineup существ рядом с Шаней (сравнение роста).

Только импорт + scale корня + расстановка.
Не apply modifiers / не bake shape keys — morphs (уши, хвосты, гениталии) сохраняем.
"""
import json
import math
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector


def _argv_job():
    argv = sys.argv
    if "--" in argv:
        return Path(argv[argv.index("--") + 1])
    return Path(__file__).resolve().parent / "lineup_job.json"


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials):
        for b in list(block):
            if b.users == 0:
                block.remove(b)


def import_asset(path: Path):
    path = Path(path)
    before = set(bpy.data.objects)
    suf = path.suffix.lower()
    if suf == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suf == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif suf in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suf == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
            data_to.objects = list(data_from.objects)
        for obj in data_to.objects:
            if obj is not None:
                bpy.context.collection.objects.link(obj)
    else:
        raise RuntimeError("unsupported: " + suf)
    return [o for o in bpy.data.objects if o not in before]


def world_bounds(objects):
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    any_mesh = False
    for obj in objects:
        if obj.type != "MESH":
            continue
        any_mesh = True
        for corner in obj.bound_box:
            w = obj.matrix_world @ Vector(corner)
            mins.x = min(mins.x, w.x); mins.y = min(mins.y, w.y); mins.z = min(mins.z, w.z)
            maxs.x = max(maxs.x, w.x); maxs.y = max(maxs.y, w.y); maxs.z = max(maxs.z, w.z)
    if not any_mesh:
        return Vector((0, 0, 0)), Vector((0, 0, 1))
    return mins, maxs


def height_of(objects):
    mins, maxs = world_bounds(objects)
    return float(maxs.z - mins.z)


def place_group(objects, x, ground_z=0.0):
    mins, maxs = world_bounds(objects)
    cx = (mins.x + maxs.x) * 0.5
    cy = (mins.y + maxs.y) * 0.5
    dz = ground_z - mins.z
    dx = x - cx
    dy = 0.0 - cy
    for obj in objects:
        if obj.parent:
            continue
        obj.location.x += dx
        obj.location.y += dy
        obj.location.z += dz
    bpy.context.view_layer.update()


def scale_roots(objects, factor):
    for obj in objects:
        if obj.parent:
            continue
        obj.scale *= factor
    bpy.context.view_layer.update()


def label_empty(name, location):
    empty = bpy.data.objects.new(name[:60], None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.location = location
    bpy.context.collection.objects.link(empty)
    return empty


def main():
    job_path = _argv_job()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    clear_scene()

    spacing = float(job.get("spacing_m") or 1.2)
    x = 0.0

    shanya_path = (job.get("shanya_path") or "").strip()
    if shanya_path and Path(shanya_path).is_file():
        try:
            objs = import_asset(Path(shanya_path))
            h = height_of(objs)
            target = float(job.get("shanya_target_m") or 1.70)
            if h > 1e-4:
                scale_roots(objs, target / h)
            place_group(objs, x)
            label_empty("LABEL_Shanya", (x, -0.5, target + 0.1))
        except Exception as exc:
            print("VIU_LINEUP_WARN shanya", exc)
            traceback.print_exc()
            label_empty("MISSING_Shanya", (0, 0, 1.7))
        x += spacing
    else:
        label_empty("MISSING_Shanya", (0, 0, 1.7))
        x += spacing

    for entry in job.get("creatures") or []:
        p = Path(entry["path"])
        name = str(entry.get("name") or "?")
        if not p.is_file():
            label_empty("MISSING_" + name[:40], (x, 0, 1))
            x += spacing
            continue
        try:
            objs = import_asset(p)
            h_before = height_of(objs)
            target = float(entry.get("target_height_m") or 1.0)
            scale = 1.0
            if h_before > 1e-4 and target > 0:
                scale = target / h_before
                scale_roots(objs, scale)
            place_group(objs, x)
            label_empty(
                "LABEL_" + str(entry.get("size_class") or "") + "_" + name[:24],
                (x, -0.5, target + 0.1),
            )
            print("VIU_LINEUP_ROW", json.dumps({
                "id": entry.get("id"),
                "name": name,
                "measured_m": round(h_before, 4),
                "target_m": target,
                "scale": round(scale, 6),
            }, ensure_ascii=False))
        except Exception as exc:
            print("VIU_LINEUP_WARN", name, exc)
            traceback.print_exc()
            label_empty("FAIL_" + name[:40], (x, 0, 1))
        x += spacing

    cam_data = bpy.data.cameras.new("LineupCam")
    cam = bpy.data.objects.new("LineupCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (x * 0.5 - spacing * 0.5, -max(4.0, x * 0.55), 1.6)
    cam.rotation_euler = (math.radians(85), 0, 0)
    bpy.context.scene.camera = cam

    out = Path(job.get("output_blend") or (job_path.parent / "creature_lineup.blend"))
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print("VIU_LINEUP_OK", out)


if __name__ == "__main__":
    main()
'''
).lstrip()
