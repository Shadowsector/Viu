"""Экспорт FBX для Cascadeur: без widget-мешей, только deform bones."""

from __future__ import annotations

import json
import subprocess
import tempfile
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...config import Config
from .export_shanya import build_export_command, parse_export_output

_MARK_BEGIN = "<<<VIU_EXPORT_JSON_BEGIN>>>"
_MARK_END = "<<<VIU_EXPORT_JSON_END>>>"

CASCADUR_EXPORT_SCRIPT = f'''
import bpy, json, sys, traceback

def emit(payload):
    print("{_MARK_BEGIN}" + json.dumps(payload, ensure_ascii=False) + "{_MARK_END}")

WIDGET_PREFIXES = ("WGT", "WGT-", "VIS_", "VIS-", "MCH-", "MCH_", "ORG-", "ORG_")
WIDGET_NAMES = frozenset({{"Circle", "Sphere", "Cube", "Plane"}})

def _is_widget_mesh(obj, arm_obj):
    if obj.type != "MESH":
        return False
    name = obj.name
    if name in WIDGET_NAMES:
        return True
    for pref in WIDGET_PREFIXES:
        if name.startswith(pref):
            return True
    low = name.lower()
    if "widget" in low or low.endswith("_rig") or "_ctrl" in low:
        return True
    if obj.parent and obj.parent_type == "BONE":
        try:
            vc = len(obj.data.vertices)
        except Exception:
            vc = 0
        has_arm = any(m.type == "ARMATURE" for m in obj.modifiers)
        if not has_arm and vc < 900:
            return True
        pb = obj.parent.name
        if pb.startswith(("WGT", "MCH", "ORG")) and vc < 1200:
            return True
    return False

def _mesh_for_character(obj, arm_obj):
    if obj.type != "MESH":
        return False
    if _is_widget_mesh(obj, arm_obj):
        return False
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object == arm_obj:
            return True
    par = obj.parent
    while par is not None:
        if par == arm_obj:
            return True
        par = par.parent
    return False

try:
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError("Нужен путь выхода после --")
    out_path = argv[argv.index("--") + 1]

    scene = bpy.context.scene
    view_layer = bpy.context.view_layer

    def _unhide_lc(lc):
        try:
            lc.exclude = False
            lc.hide_viewport = False
        except Exception:
            pass
        try:
            lc.collection.hide_viewport = False
        except Exception:
            pass
        for ch in lc.children:
            _unhide_lc(ch)

    _unhide_lc(view_layer.layer_collection)

    for col in bpy.data.collections:
        low = col.name.lower()
        if low in ("wgts", "widgets", "rig_widgets"):
            try:
                col.hide_viewport = True
            except Exception:
                pass

    hidden_widgets = 0
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            continue
        if _is_widget_mesh(obj, None):
            try:
                obj.hide_set(True)
                obj.hide_viewport = True
                hidden_widgets += 1
            except Exception:
                pass

    for obj in list(bpy.data.objects):
        if obj.type not in ("MESH", "ARMATURE"):
            continue
        if getattr(obj, "library", None):
            continue
        if obj.name in view_layer.objects:
            continue
        try:
            scene.collection.objects.link(obj)
        except RuntimeError:
            pass

    active_arm = None
    for obj in view_layer.objects:
        if obj.type == "ARMATURE":
            active_arm = obj
            break
    if active_arm is None:
        for obj in bpy.data.objects:
            if obj.type == "ARMATURE":
                active_arm = obj
                break

    if active_arm is None:
        raise RuntimeError("В сцене нет ARMATURE")

    deform_bones = 0
    non_deform = 0
    for bone in active_arm.data.bones:
        if bone.use_deform:
            deform_bones += 1
        else:
            non_deform += 1

    bpy.ops.object.select_all(action="DESELECT")
    selected = []
    skipped = []

    try:
        if active_arm.hide_viewport or active_arm.hide_get():
            active_arm.hide_set(False)
            active_arm.hide_viewport = False
    except Exception:
        pass
    try:
        active_arm.select_set(True)
        selected.append(active_arm.name)
    except RuntimeError as exc:
        raise RuntimeError(f"Не выбрать armature: {{exc}}") from exc

    for obj in list(view_layer.objects):
        if obj.type != "MESH":
            continue
        if not _mesh_for_character(obj, active_arm):
            skipped.append(obj.name)
            continue
        try:
            if obj.hide_viewport or obj.hide_get():
                obj.hide_set(False)
                obj.hide_viewport = False
            obj.select_set(True)
            selected.append(obj.name)
        except RuntimeError as exc:
            skipped.append(f"{{obj.name}}: {{exc}}")

    if len(selected) < 2:
        raise RuntimeError(
            "Нет skinned mesh для экспорта (только armature?). "
            f"Пропущено mesh: {{skipped[:8]}}"
        )

    bpy.context.view_layer.objects.active = active_arm

    bpy.ops.export_scene.fbx(
        filepath=out_path,
        use_selection=True,
        object_types={{"ARMATURE", "MESH"}},
        use_mesh_modifiers=True,
        use_armature_deform_only=True,
        bake_anim=False,
        add_leaf_bones=False,
        mesh_smooth_type="FACE",
        apply_scale_options="FBX_SCALE_ALL",
    )

    emit({{
        "ok": True,
        "output": out_path,
        "selected": selected,
        "skipped_meshes": skipped[:40],
        "hidden_widgets": hidden_widgets,
        "deform_bones": deform_bones,
        "non_deform_bones": non_deform,
        "armature": active_arm.name,
    }})
except Exception as exc:
    emit({{
        "ok": False,
        "error": str(exc),
        "traceback": traceback.format_exc()[-2000:],
    }})
    raise SystemExit(2)
'''


def export_cascadeur_fbx(
    blend_file: str,
    output_fbx: str | None = None,
    blender_exe: str = "blender",
    timeout: float = 300.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[Path, Dict[str, Any]]:
    blend = Path(blend_file).resolve()
    if not blend.is_file():
        raise FileNotFoundError(f"Blend не найден: {blend_file}")

    if output_fbx:
        out = Path(output_fbx).resolve()
    else:
        out = blend.with_name(f"{blend.stem}_cascadeur.fbx")
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(CASCADUR_EXPORT_SCRIPT)
        script_path = f.name

    try:
        cmd = build_export_command(blender_exe, str(blend), script_path, str(out))
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode != 0 and _MARK_BEGIN not in (proc.stdout or ""):
            tail = combined.strip()[-2000:]
            raise RuntimeError(f"Blender завершился с кодом {proc.returncode}.\n{tail}")
        meta = parse_export_output(proc.stdout or combined)
        if not out.is_file():
            raise RuntimeError(f"FBX не создан: {out}\n{combined.strip()[-1500:]}")
        return out, meta
    finally:
        try:
            Path(script_path).unlink()
        except OSError:
            pass


@dataclass
class CascadeurExportRow:
    source: str
    output: str = ""
    ok: bool = False
    skipped: bool = False
    message: str = ""
    deform_bones: int = 0
    hidden_widgets: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CascadeurExportReport:
    out_dir: str
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    rows: List[CascadeurExportRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rows"] = [r.to_dict() for r in self.rows]
        return d


def _should_skip_export(src: Path, dst: Path, *, force: bool) -> bool:
    if force or not dst.is_file():
        return False
    try:
        return dst.stat().st_mtime >= src.stat().st_mtime
    except OSError:
        return False


def batch_export_cascadeur_models(
    config: Config,
    *,
    topic: str = "cascadeur",
    force: bool = False,
    blender_exe: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[bool, str, Path]:
    """Все .blend из Lab/Cascadeur Inbox → CascadeurReady/*_cascadeur.fbx."""
    from ...lab.models_inbox import iter_all_model_paths
    from ...lab.paths import artifacts_dir, cascadeur_ready_dir
    from ..blender.exe import resolve_blender_exe

    out_dir = cascadeur_ready_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        exe = blender_exe or str(resolve_blender_exe(config))
    except FileNotFoundError as exc:
        return False, str(exc), out_dir

    report = CascadeurExportReport(out_dir=str(out_dir))
    lines: List[str] = [f"Папка: {out_dir}"]

    for src in iter_all_model_paths(config):
        row = CascadeurExportRow(source=str(src))
        dst = out_dir / f"{src.stem}_cascadeur.fbx"

        if src.suffix.lower() == ".fbx":
            row.skipped = True
            row.message = "уже FBX — копия без переработки"
            try:
                import shutil

                if force or not dst.is_file() or dst.stat().st_mtime < src.stat().st_mtime:
                    shutil.copy2(src, dst)
                    row.ok = True
                    row.output = str(dst)
                    row.message = "скопирован"
                    report.ok += 1
                else:
                    row.output = str(dst)
                    row.message = "актуален"
                    report.skipped += 1
            except OSError as exc:
                row.ok = False
                row.message = str(exc)
                report.failed += 1
            report.rows.append(row)
            continue

        if _should_skip_export(src, dst, force=force):
            row.skipped = True
            row.ok = True
            row.output = str(dst)
            row.message = "актуален (не старше .blend)"
            report.skipped += 1
            report.rows.append(row)
            continue

        try:
            path, meta = export_cascadeur_fbx(
                str(src), str(dst), blender_exe=exe, runner=runner,
            )
            row.ok = True
            row.output = str(path)
            row.deform_bones = int(meta.get("deform_bones") or 0)
            row.hidden_widgets = int(meta.get("hidden_widgets") or 0)
            row.message = (
                f"mesh={len(meta.get('selected') or []) - 1}, "
                f"deform={row.deform_bones}, widgets_hidden={row.hidden_widgets}"
            )
            report.ok += 1
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            row.message = str(exc)[:400]
            report.failed += 1
        report.rows.append(row)

    manifest = artifacts_dir(config, topic) / "cascadeur_export_manifest.json"
    manifest.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines.append(f"OK: {report.ok}, пропуск: {report.skipped}, ошибки: {report.failed}")
    for row in report.rows:
        mark = "✓" if row.ok and not row.skipped else ("~" if row.skipped else "✗")
        name = Path(row.source).name
        tail = row.message or row.output
        lines.append(f"  {mark} {name} — {tail}")
    lines.append(f"Manifest: {manifest}")

    ok = report.failed == 0 and (report.ok > 0 or report.skipped > 0)
    return ok, "\n".join(lines), manifest
