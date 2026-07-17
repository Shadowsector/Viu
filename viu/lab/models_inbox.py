"""Inbox моделей лаборатории: скан, rig-check в Blender, сводка для Cascadeur."""

from __future__ import annotations

import json
import random
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..integrations.blender.exe import resolve_blender_exe
from ..integrations.blender.headless import dump_blend_info
from ..integrations.blender.export_cascadeur import export_cascadeur_fbx
from ..integrations.cascadeur.paths import cascadeur_inbox
from ..integrations.rig import analyze_skeleton, is_complex_rig, map_to_humanoid
from ..tools import rig_tool as rt
from .paths import artifacts_dir, cascadeur_ready_dir, models_inbox_dir, models_summary_json, models_summary_md


@dataclass
class ModelRigEntry:
    path: str
    name: str
    kind: str
    armature: Optional[str] = None
    bone_count: int = 0
    rig_type: str = "unknown"
    cascadeur_score: int = 0
    cascadeur_grade: str = "unknown"
    missing_required: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _grade(score: int) -> str:
    if score >= 70:
        return "good"
    if score >= 40:
        return "maybe"
    return "poor"


def _score_rig(bones: List[str], armature: Optional[str]) -> ModelRigEntry:
    entry = ModelRigEntry(
        path="",
        name="",
        kind="blend",
        armature=armature,
        bone_count=len(bones),
    )
    if not bones:
        entry.cascadeur_score = 0
        entry.cascadeur_grade = "poor"
        entry.notes = "Скелет не найден"
        return entry

    if is_complex_rig(bones):
        hm = map_to_humanoid(bones)
        entry.rig_type = hm.rig_type
        entry.missing_required = list(hm.missing_required)
        if not hm.missing_required:
            entry.cascadeur_score = 78
            entry.notes = f"Сложный риг ({hm.rig_type}), Humanoid-карта OK"
        else:
            entry.cascadeur_score = max(15, 55 - len(hm.missing_required) * 8)
            entry.notes = f"Сложный риг, не хватает слотов: {', '.join(hm.missing_required[:4])}"
    else:
        report = analyze_skeleton(bones)
        entry.rig_type = "simple"
        entry.missing_required = list(report.missing_required)
        if report.ok:
            entry.cascadeur_score = 92
            entry.notes = "Простой риг, все обязательные кости на месте"
        else:
            entry.cascadeur_score = max(10, 50 - len(report.missing_required) * 10)
            entry.notes = f"Не хватает: {', '.join(report.missing_required[:5])}"

    entry.cascadeur_grade = _grade(entry.cascadeur_score)
    return entry


def _analyze_blend(config: Config, path: Path) -> ModelRigEntry:
    entry = ModelRigEntry(path=str(path), name=path.name, kind="blend")
    try:
        scene = dump_blend_info(str(path), blender_exe=_blender_exe(config))
    except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
        entry.notes = f"Blender: {exc}"
        entry.cascadeur_score = 0
        entry.cascadeur_grade = "poor"
        return entry

    objects = scene.get("objects") or []
    arm_name, bones = rt._pick_armature(objects)  # noqa: SLF001
    if not bones:
        entry.notes = "Арматура персонажа не найдена"
        entry.cascadeur_score = 0
        entry.cascadeur_grade = "poor"
        return entry

    scored = _score_rig(bones, arm_name)
    entry.armature = scored.armature
    entry.bone_count = scored.bone_count
    entry.rig_type = scored.rig_type
    entry.cascadeur_score = scored.cascadeur_score
    entry.cascadeur_grade = scored.cascadeur_grade
    entry.missing_required = scored.missing_required
    entry.notes = scored.notes
    return entry


def _analyze_fbx(path: Path) -> ModelRigEntry:
    return ModelRigEntry(
        path=str(path),
        name=path.name,
        kind="fbx",
        rig_type="fbx",
        cascadeur_score=50,
        cascadeur_grade="maybe",
        notes="FBX — rig-check без импорта в Blender; годность уточняется в Cascadeur",
    )


def _blender_exe(config: Config) -> str:
    return str(resolve_blender_exe(config))


def _model_dirs(config: Config) -> tuple[Path, Path]:
    return models_inbox_dir(config), cascadeur_inbox(config)


def iter_all_model_paths(config: Config) -> List[Path]:
    """Все .blend/.fbx: Lab/Models/Inbox и Library/Cascadeur/Inbox."""
    paths: set[Path] = set()
    for folder in _model_dirs(config):
        for ext in ("*.blend", "*.fbx"):
            paths.update(folder.glob(ext))
    return sorted({p.resolve() for p in paths}, key=lambda p: p.name.lower())


def list_model_files(config: Config) -> List[Path]:
    return iter_all_model_paths(config)


def inbox_models_newer_than_session(config: Config, session) -> bool:
    """True — в inbox появились модели после старта текущей сессии."""
    from datetime import datetime, timezone

    try:
        since = datetime.fromisoformat(session.created_at.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return False
    if session.step <= 0:
        return False
    for path in iter_all_model_paths(config):
        try:
            if path.stat().st_mtime > since + 1.0:
                return True
        except OSError:
            continue
    return False


def scan_models_inbox(config: Config) -> List[ModelRigEntry]:
    entries: List[ModelRigEntry] = []
    for path in list_model_files(config):
        if path.suffix.lower() == ".blend":
            entries.append(_analyze_blend(config, path))
        else:
            entries.append(_analyze_fbx(path))
    return entries


def _render_summary_md(entries: List[ModelRigEntry], inbox: Path) -> str:
    lines = [
        "# Сводка моделей (Lab → Cascadeur)",
        "",
        f"Папка: `{inbox}`",
        f"Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "| Модель | Кости | Тип | Оценка | Каскадёр |",
        "|--------|-------|-----|--------|----------|",
    ]
    for e in sorted(entries, key=lambda x: (-x.cascadeur_score, x.name.lower())):
        grade_ru = {"good": "✓ норм", "maybe": "~ может", "poor": "✗ плохо", "unknown": "?"}.get(
            e.cascadeur_grade, e.cascadeur_grade
        )
        lines.append(
            f"| {e.name} | {e.bone_count or '—'} | {e.rig_type} | {e.cascadeur_score}/100 | {grade_ru} |"
        )
        if e.notes:
            lines.append(f"| | | | | _{e.notes}_ |")
    lines.extend(
        [
            "",
            "## Легенда",
            "",
            "- **good** (≥70) — скелет выглядит пригодным для retarget в Cascadeur",
            "- **maybe** — стоит попробовать вручную",
            "- **poor** — вероятно проблемы с ригом",
            "",
        ]
    )
    good = [e.name for e in entries if e.cascadeur_grade == "good"]
    poor = [e.name for e in entries if e.cascadeur_grade == "poor"]
    if good:
        lines.append(f"**Рекомендованы:** {', '.join(good)}")
    if poor:
        lines.append(f"**Сомнительные:** {', '.join(poor)}")
    return "\n".join(lines) + "\n"


def build_models_summary(config: Config, *, topic: str = "cascadeur") -> Tuple[bool, str, Optional[str]]:
    """Скан inbox, rig-check, models_summary.md + .json в artifacts."""
    inbox = models_inbox_dir(config)
    entries = scan_models_inbox(config)
    art = artifacts_dir(config, topic)
    md_path = models_summary_md(config, topic)
    json_path = models_summary_json(config, topic)

    payload: Dict[str, Any] = {
        "inbox": str(inbox),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(entries),
        "models": [e.to_dict() for e in entries],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_summary_md(entries, inbox), encoding="utf-8")

    if not entries:
        msg = (
            f"Inbox пуст.\n"
            f"• `{inbox}` или `{cascadeur_inbox(config)}` — положи .blend или .fbx\n"
            "Вью конвертирует .blend → FBX для Cascadeur."
        )
        return True, msg, str(json_path)

    good = sum(1 for e in entries if e.cascadeur_grade == "good")
    maybe = sum(1 for e in entries if e.cascadeur_grade == "maybe")
    poor = sum(1 for e in entries if e.cascadeur_grade == "poor")
    msg = (
        f"Проверено моделей: {len(entries)} (good={good}, maybe={maybe}, poor={poor}).\n"
        f"Сводка: {md_path.name}\n"
        f"JSON: {json_path.name}"
    )
    return True, msg, str(json_path)


def _model_to_fbx(
    config: Config,
    model: Path,
    cache_dir: Path | None = None,
    *,
    output: Path | None = None,
) -> Tuple[bool, str, Optional[Path]]:
    if model.suffix.lower() == ".fbx":
        return True, model.name, model
    try:
        exe = _blender_exe(config)
    except FileNotFoundError as exc:
        return False, str(exc), None
    if output is not None:
        out = output
    elif cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        out = cache_dir / f"{model.stem}_lab.fbx"
    else:
        out = model.with_suffix(".fbx")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        path, _meta = export_cascadeur_fbx(str(model), str(out), blender_exe=exe)
        return True, f"Экспорт Cascadeur FBX: {path.name}", path
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        return False, f"Экспорт FBX: {exc}", None


def prepare_cascadeur_inbox(
    config: Config,
    *,
    topic: str = "cascadeur",
) -> Tuple[bool, str, Optional[Path]]:
    """Cascadeur Inbox: FBX готов, .blend → FBX, иначе модель из Lab Inbox."""
    inbox = cascadeur_inbox(config)
    fbxs = sorted(inbox.glob("*.fbx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if fbxs:
        return True, f"Inbox FBX: {fbxs[0].name}", fbxs[0]

    blends = sorted(inbox.glob("*.blend"), key=lambda p: p.stat().st_mtime, reverse=True)
    if blends:
        pick = blends[0] if len(blends) == 1 else random.choice(blends)
        out = inbox / f"{pick.stem}.fbx"
        ok, msg, fbx = _model_to_fbx(config, pick, output=out)
        if ok and fbx:
            return True, f"Конвернул в Inbox: {pick.name} → {fbx.name}", fbx
        return False, msg, None

    ready_dir = cascadeur_ready_dir(config)
    ready_fbx = sorted(ready_dir.glob("*_cascadeur.fbx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if ready_fbx:
        pick = random.choice(ready_fbx) if len(ready_fbx) > 1 else ready_fbx[0]
        dst = inbox / pick.name
        try:
            shutil.copy2(pick, dst)
        except OSError as exc:
            return False, str(exc), None
        return True, f"Из CascadeurReady: {pick.name} → Inbox", dst

    lab_dir = models_inbox_dir(config)
    lab_files: List[Path] = []
    for ext in ("*.blend", "*.fbx"):
        lab_files.extend(lab_dir.glob(ext))
    lab_files = sorted({p.resolve() for p in lab_files}, key=lambda p: p.name.lower())

    if lab_files:
        pick = random.choice(lab_files)
        cache = artifacts_dir(config, topic) / "fbx_cache"
        ok, msg, fbx = _model_to_fbx(config, pick, cache)
        if not ok or fbx is None:
            return False, msg, None
        dst = inbox / f"lab_{fbx.name}"
        try:
            shutil.copy2(fbx, dst)
        except OSError as exc:
            return False, str(exc), None
        grade = ""
        if pick.suffix.lower() == ".blend":
            for entry in scan_models_inbox(config):
                if Path(entry.path).resolve() == pick.resolve():
                    grade = f" (rig: {entry.cascadeur_score}/100, {entry.cascadeur_grade})"
                    break
        return True, f"Из Lab Inbox: {pick.name} → {dst.name}{grade}", dst

    from ..integrations.cascadeur.launch import seed_inbox_sample_fbx

    return seed_inbox_sample_fbx(config)


def copy_random_model_to_cascadeur_inbox(
    config: Config,
    *,
    topic: str = "cascadeur",
) -> Tuple[bool, str, Optional[Path]]:
    """Случайная модель → Cascadeur Inbox (FBX). См. prepare_cascadeur_inbox."""
    return prepare_cascadeur_inbox(config, topic=topic)
