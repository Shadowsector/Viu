"""Lineup в Blender: Шаня + существа — Вью сама запускает Blender."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..config import Config
from .models import CreatureEntry, STATUS_NORMALIZED
from .paths import creature_catalog_path, creatures_lineup_dir
from .store import CreatureCatalogStore

LINEUP_SCRIPT_NAME = "viu_creature_lineup.py"
_BLENDER_BODY = Path(__file__).resolve().parent / "_lineup_blender_body.py"
# После дедупа — если больше, делаем отдельный .blend на каждый size_class
_SPLIT_AFTER = 8
_EXT_PREF = {".blend": 0, ".glb": 1, ".gltf": 2, ".fbx": 3, ".obj": 4}
_DEFAULT_SPACING = 2.8


def _install_lineup_script(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / LINEUP_SCRIPT_NAME
    if not _BLENDER_BODY.is_file():
        raise FileNotFoundError(f"Нет скрипта линейки: {_BLENDER_BODY}")
    shutil.copyfile(_BLENDER_BODY, dest)
    return dest


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
    spacing_m: float = _DEFAULT_SPACING,
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
    script_path = _install_lineup_script(out_dir)

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
            final_h = float(row.get("final_m") or 0)
        except (TypeError, ValueError):
            continue
        if measured > 0:
            e.measured_height_m = measured
        if final_h > 0:
            # фактический рост после scale — для контроля
            e.notes = (
                (e.notes or "")
                + f"\nlineup_final={final_h:.3f}m target={row.get('target_m')}"
            ).strip()
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
        _install_lineup_script(job_path.parent)

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
    fails = [ln for ln in (proc.stdout or "").splitlines() if "VIU_LINEUP_HEIGHT_FAIL" in ln]
    if proc.returncode != 0 and not ok_mark:
        tail = combined.strip()[-1800:]
        return False, f"Blender код {proc.returncode} ({job_path.name}).\n{tail}", Path()
    if not blend_out.is_file():
        return False, f"Файл не создан: {blend_out}\n{combined.strip()[-1200:]}", Path()

    msg = f"OK: {blend_out.name} ({len(job.get('creatures') or [])} моделей"
    if updated:
        msg += f", рост записан у {updated}"
    msg += ")"
    if fails:
        msg += f"\n⚠ рост не сошёлся у {len(fails)} — см. красные таблички в сцене:\n"
        msg += "\n".join(fails[:12])
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
    spacing_m: float = _DEFAULT_SPACING,
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

    lines = [
        prep,
        "",
        "Запускаю Blender сама…",
        "В сцене: Шаня + таблички с именем и целевым ростом.",
        "Если рост не совпал — в «Разметить существ» поставь точный рост (м) и перезапусти линейку.",
    ]
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
        prefer = next((b for b in blends if "overview" in b.name), blends[0])
        if open_result:
            lines.append(open_lineup_result(prefer))
            if len(blends) > 1:
                lines.append(open_lineup_result(out_dir))
        lines.append("")
        lines.append(
            "Смотри таблички под моделями (имя + цель + факт). "
            "Старый открытый .blend не обновится сам — открой новый overview из Lineup."
        )
        lines.append(f"Все файлы: {out_dir}")
        return failed == 0, "\n".join(lines)

    return False, "\n".join(lines)
