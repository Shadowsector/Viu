"""Подготовка .blend из Inbox для Unity: текстуры, фон, свет, pack, save."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ...anabarra_layout import inbox_dir, library_root
from ...config import Config
from .exe import resolve_blender_exe
from ...prop_catalog.pack_layout import repair_split_pack

_MARK_BEGIN = "<<<VIU_PREPARE_JSON_BEGIN>>>"
_MARK_END = "<<<VIU_PREPARE_JSON_END>>>"

# Имена мешей/объектов — прячем только явную «землю под ногами», не деревья/туман.
BACKGROUND_NAME_RE = re.compile(
    r"^(ground|terrain|world_floor|plane_ground|floor_outside|outside_ground|"
    r"exterior_ground|skydome|horizon|backdrop)$|"
    r"(^ground_|_ground$|ground_plane|terrain_plane)",
    re.IGNORECASE,
)

TEXTURE_DIR_NAMES = ("Textures", "textures", "TEXTURES", "tex", "maps", "Maps")


def find_blend_for_prepare(
    config: Config,
    *,
    blend_file: Optional[str] = None,
    allow_library_fallback: bool = False,
) -> tuple[Path, str]:
    """Inbox (по умолчанию). Library — только с allow_library_fallback=True (агент)."""
    if blend_file:
        p = Path(blend_file).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Файл не найден: {p}")
        return p, "указанный файл"

    inbox = inbox_dir(config)
    try:
        return find_inbox_blend(inbox), "Inbox"
    except FileNotFoundError as exc:
        if not allow_library_fallback:
            raise FileNotFoundError(
                f"{exc}\n\n"
                "«Принять asset» работает только с Inbox.\n"
                "Положи папку или .blend в U:\\Anabarra\\Inbox и нажми «▶ Следующий шаг».\n"
                "Переprepare старого файла из Library — укажи путь в чате или "
                "allow_library_fallback=1 (агент)."
            ) from exc

    lib = library_root(config)
    candidates: List[Path] = []
    for folder in (lib / "Blender", lib):
        if not folder.is_dir():
            continue
        for p in folder.rglob("*.blend"):
            if "_prepared" in p.stem.lower():
                continue
            if "Processed" in p.parts:
                continue
            candidates.append(p)

    if not candidates:
        raise FileNotFoundError(
            f"Нет .blend для подготовки.\n"
            f"  Inbox: {inbox} — пуст\n"
            f"  Library: {lib / 'Blender'} — тоже пуст\n"
            "Положи blend+textures в U:\\Anabarra\\Inbox."
        )
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return latest, f"Library ({latest.name})"


def find_inbox_blend(inbox: Path) -> Path:
    """Один .blend в Inbox или в единственной подпапке-паке."""
    inbox = inbox.expanduser().resolve()
    if not inbox.is_dir():
        raise FileNotFoundError(f"Inbox не найден: {inbox}")

    top = sorted(inbox.glob("*.blend"))
    if len(top) == 1:
        return top[0]
    if len(top) > 1:
        raise FileNotFoundError(
            f"В Inbox несколько .blend ({len(top)}). Оставь один пак за раз."
        )

    packs: List[Path] = []
    for sub in sorted(p for p in inbox.iterdir() if p.is_dir() and not p.name.startswith(".")):
        blends = sorted(sub.glob("*.blend"))
        if blends:
            packs.append(sub)
            if len(blends) > 1:
                raise FileNotFoundError(
                    f"В папке {sub.name} несколько .blend — оставь один главный файл."
                )

    if len(packs) == 1:
        return sorted(packs[0].glob("*.blend"))[0]
    if not packs:
        raise FileNotFoundError(
            f"Inbox пуст или без .blend: {inbox}\n"
            "Положи hut.blend или папку hut_pack\\hut.blend + Textures."
        )
    raise FileNotFoundError(
        f"В Inbox {len(packs)} папок с blend. Обрабатываем по одной — убери лишние."
    )


def prepared_output_path(blend: Path, lib: Path) -> Path:
    """Library/Processed/<pack>/<stem>_prepared.blend"""
    pack_name = blend.parent.name if blend.parent.name.lower() != "inbox" else blend.stem
    if pack_name.lower() == "blender":
        pack_name = blend.stem
    out_dir = lib / "Processed" / pack_name
    return out_dir / f"{blend.stem}_prepared.blend"


def _texture_search_dirs(blend: Path, library_root: Optional[Path] = None) -> List[Path]:
    dirs: List[Path] = []
    seen: set[str] = set()
    bases = [blend.parent, blend.parent.parent]
    if library_root:
        ref = library_root / "References" / "images"
        if ref.is_dir():
            bases.append(ref)
        bases.append(library_root)
    for base in bases:
        if not base.is_dir():
            continue
        for name in TEXTURE_DIR_NAMES:
            p = base / name
            key = str(p.resolve()).lower()
            if p.is_dir() and key not in seen:
                seen.add(key)
                dirs.append(p.resolve())
    return dirs


PREPARE_SCRIPT = f'''
import sys
import bpy
import json
import os
import re
from pathlib import Path

MARK_BEGIN = "{_MARK_BEGIN}"
MARK_END = "{_MARK_END}"
BG_RE = re.compile(r"{BACKGROUND_NAME_RE.pattern}", re.IGNORECASE)
TEXTURE_DIR_NAMES = {TEXTURE_DIR_NAMES!r}

out_path = Path(sys.argv[-1])
hide_background = sys.argv[-2] == "1"
pack_textures = sys.argv[-3] == "1"
simplify_world = sys.argv[-4] == "1"
remove_sun = sys.argv[-5] == "1"

report = {{
    "source": bpy.data.filepath,
    "output": str(out_path),
    "relinked_images": [],
    "packed_count": 0,
    "hidden_objects": [],
    "removed_lights": [],
    "kept_lights": [],
    "meshes": [],
    "world_simplified": False,
    "errors": [],
}}


def texture_dirs():
    blend = Path(bpy.data.filepath).resolve()
    dirs = []
    seen = set()
    for base in (blend.parent, blend.parent.parent):
        if not base.is_dir():
            continue
        for name in TEXTURE_DIR_NAMES:
            p = (base / name).resolve()
            if p.is_dir() and str(p) not in seen:
                seen.add(str(p))
                dirs.append(p)
    return dirs


def find_image_file(name: str, dirs):
    name = name.strip()
    if not name:
        return None
    base = os.path.basename(name)
    for d in dirs:
        direct = d / base
        if direct.is_file():
            return direct
        for hit in d.rglob(base):
            if hit.is_file():
                return hit
    return None


def relink_images():
    dirs = texture_dirs()
    for img in bpy.data.images:
        if img.packed_file:
            continue
        if not img.filepath and not img.name:
            continue
        abs_path = bpy.path.abspath(img.filepath) if img.filepath else ""
        if abs_path and os.path.isfile(abs_path):
            continue
        candidate = find_image_file(img.filepath or img.name, dirs)
        if candidate:
            img.filepath = str(candidate)
            report["relinked_images"].append({{"name": img.name, "path": str(candidate)}})


def suggest_role(name: str) -> str:
    low = name.lower()
    if low.startswith("shell") or "wall" in low or "floor" in low or "ceiling" in low:
        return "shell"
    if low.startswith("interactive") or low.startswith("inter_"):
        return "interactive"
    if low.startswith("decor"):
        return "decor"
    if BG_RE.search(name):
        return "background"
    return ""


def hide_background_objects():
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            continue
        if BG_RE.search(obj.name):
            obj.hide_set(True)
            obj.hide_viewport = True
            obj.hide_render = True
            report["hidden_objects"].append(obj.name)


def handle_lights():
    for obj in list(bpy.data.objects):
        if obj.type != "LIGHT":
            continue
        ltype = obj.data.type
        if remove_sun and ltype == "SUN":
            report["removed_lights"].append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            report["kept_lights"].append(f"{{obj.name}} ({{ltype}})")


def simplify_world_env():
    world = bpy.context.scene.world
    if not world:
        return
    world.use_nodes = True
    nt = world.node_tree
    for node in nt.nodes:
        if node.type == "TEX_ENVIRONMENT":
            node.mute = True
    bg = nt.nodes.get("Background")
    if bg:
        try:
            bg.inputs["Color"].default_value = (0.04, 0.04, 0.05, 1.0)
            bg.inputs["Strength"].default_value = 0.0
        except (KeyError, TypeError):
            pass
    report["world_simplified"] = True


def collect_meshes():
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.hide_viewport:
            continue
        report["meshes"].append({{
            "name": obj.name,
            "suggest_role": suggest_role(obj.name),
            "vertices": len(obj.data.vertices) if obj.data else 0,
        }})


relink_images()
if hide_background:
    hide_background_objects()
if simplify_world:
    simplify_world_env()
handle_lights()
collect_meshes()

if pack_textures:
    try:
        bpy.ops.file.pack_all()
        report["packed_count"] = sum(1 for i in bpy.data.images if i.packed_file)
    except RuntimeError as exc:
        report["errors"].append(f"pack_all: {{exc}}")

try:
    bpy.ops.file.make_paths_relative()
except RuntimeError as exc:
    report["errors"].append(f"make_paths_relative: {{exc}}")

out_path.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out_path))
print(MARK_BEGIN + json.dumps(report, ensure_ascii=False) + MARK_END)
'''


def parse_prepare_output(stdout: str) -> Dict[str, Any]:
    start = stdout.find(_MARK_BEGIN)
    end = stdout.find(_MARK_END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("Не найден отчёт подготовки в выводе Blender.")
    chunk = stdout[start + len(_MARK_BEGIN) : end]
    return json.loads(chunk)


def build_prepare_command(
    blender_exe: str, blend_file: str, script_path: str, output_blend: str, *, options: Dict[str, bool]
) -> List[str]:
    flags = [
        "1" if options.get("remove_sun", True) else "0",
        "1" if options.get("simplify_world", True) else "0",
        "1" if options.get("pack_textures", True) else "0",
        "1" if options.get("hide_background", True) else "0",
        output_blend,
    ]
    return [
        blender_exe,
        "--background",
        blend_file,
        "--python",
        script_path,
        "--python-exit-code",
        "1",
        "--",
        *flags,
    ]


def prepare_blend_for_unity(
    blend_file: Path,
    output_blend: Path,
    *,
    blender_exe: str = "blender",
    config: Optional[Config] = None,
    hide_background: bool = True,
    pack_textures: bool = True,
    simplify_world: bool = True,
    remove_sun: bool = True,
    timeout: float = 300.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Dict[str, Any]:
    blend_file = blend_file.expanduser().resolve()
    output_blend = output_blend.expanduser().resolve()
    if not blend_file.is_file():
        raise FileNotFoundError(f"Файл не найден: {blend_file}")

    exe = resolve_blender_exe(config, override=blender_exe)

    options = {
        "hide_background": hide_background,
        "pack_textures": pack_textures,
        "simplify_world": simplify_world,
        "remove_sun": remove_sun,
    }

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(PREPARE_SCRIPT)
        script_path = f.name

    try:
        cmd = build_prepare_command(
            str(exe), str(blend_file), script_path, str(output_blend), options=options
        )
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Blender prepare code {proc.returncode}\nstderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
            )
        report = parse_prepare_output(proc.stdout)
        lib = library_root(config) if config else None
        report["texture_dirs"] = [str(p) for p in _texture_search_dirs(blend_file, lib)]
        report["blender_exe"] = str(exe)
        return report
    finally:
        try:
            Path(script_path).unlink()
        except OSError:
            pass


def open_blend_in_blender(blend_file: Path, blender_exe: str = "blender", config: Optional[Config] = None) -> None:
    """Открыть .blend в GUI Blender (для ручной доводки)."""
    blend_file = blend_file.expanduser().resolve()
    exe = str(resolve_blender_exe(config, override=blender_exe))
    if sys.platform == "win32":
        subprocess.Popen([exe, str(blend_file)], close_fds=True)  # noqa: S603
    else:
        subprocess.Popen([exe, str(blend_file)], start_new_session=True)  # noqa: S603


def archive_inbox_after_prepare(config: Config, *, source_label: str) -> List[str]:
    """После успешного prepare из Inbox — перенести пак в Library и очистить Inbox."""
    if source_label != "Inbox":
        return []
    from ...prop_catalog.organizer import cleanup_empty_dirs, execute_moves, plan_inbox_sort

    inbox = inbox_dir(config)
    lib = library_root(config)
    plans = plan_inbox_sort(inbox, lib)
    lines = execute_moves(plans, dry_run=False)
    for rel in cleanup_empty_dirs(inbox):
        lines.append(f"очистка Inbox: {rel}")
    return lines


def run_inbox_prepare_pipeline(
    config: Config,
    *,
    blend_file: Optional[str] = None,
    open_blender: bool = True,
    catalog_store: Optional[Any] = None,
    allow_library_fallback: bool = False,
) -> Dict[str, Any]:
    """Полный цикл: найти blend → repair textures → prepare → Processed → Blender."""
    from ...prop_catalog.scanner import scan_folder

    inbox = inbox_dir(config)
    lib = library_root(config)
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "Processed").mkdir(parents=True, exist_ok=True)

    source, source_label = find_blend_for_prepare(
        config,
        blend_file=blend_file or None,
        allow_library_fallback=allow_library_fallback,
    )
    repairs = repair_split_pack(source, lib)
    output = prepared_output_path(source, lib)

    report = prepare_blend_for_unity(
        source,
        output,
        blender_exe=config.blender_exe,
        config=config,
    )
    report["inbox"] = str(inbox)
    report["library"] = str(lib)
    report["source_label"] = source_label
    report["repairs"] = repairs

    if catalog_store is not None:
        from ...prop_catalog.scanner import apply_auto_reviews_to_store

        n, seen = scan_folder(output.parent, catalog_store, blender_exe=config.blender_exe)
        auto_n = apply_auto_reviews_to_store(catalog_store)
        report["catalog_new"] = n
        report["catalog_seen"] = seen
        report["catalog_auto_reviewed"] = auto_n
        report["catalog_pending"] = len(catalog_store.pending())

    if source_label == "Inbox":
        try:
            report["inbox_archived"] = archive_inbox_after_prepare(config, source_label=source_label)
        except OSError as exc:
            report.setdefault("errors", []).append(f"archive_inbox: {exc}")
            report["inbox_archived"] = []

    if open_blender:
        try:
            open_blend_in_blender(output, config.blender_exe, config=config)
            report["blender_opened"] = True
        except OSError as exc:
            report["blender_opened"] = False
            report.setdefault("errors", []).append(f"open_blender: {exc}")

    return report


def format_prepare_report(report: Dict[str, Any]) -> str:
    lines = [
        "Подготовка asset для Unity — готово.",
        f"Источник ({report.get('source_label', '?')}): {report.get('source', '?')}",
        f"Сохранено: {report.get('output', '?')}",
    ]
    if report.get("blender_exe"):
        lines.append(f"Blender: {report['blender_exe']}")
    repairs = report.get("repairs") or []
    if repairs:
        lines.append("")
        lines.extend(repairs)
    lines.append("")
    relinked = report.get("relinked_images") or []
    lines.append(f"Текстуры перепривязано: {len(relinked)}")
    if relinked[:5]:
        for item in relinked[:5]:
            lines.append(f"  • {item.get('name')} ← {Path(item.get('path', '')).name}")
    lines.append(f"Запаковано в .blend: {report.get('packed_count', 0)} изображений")

    hidden = report.get("hidden_objects") or []
    if hidden:
        lines.append(f"\nСкрыт фон/земля ({len(hidden)}):")
        for name in hidden[:15]:
            lines.append(f"  • {name}")
        if len(hidden) > 15:
            lines.append(f"  … ещё {len(hidden) - 15}")

    kept = report.get("kept_lights") or []
    removed = report.get("removed_lights") or []
    if kept or removed:
        lines.append("\nСвет:")
        for name in kept:
            lines.append(f"  ✓ {name}")
        for name in removed:
            lines.append(f"  ✗ убран {name} (SUN/global)")

    if report.get("catalog_pending") is not None:
        pending = int(report["catalog_pending"])
        auto_n = int(report.get("catalog_auto_reviewed") or 0)
        lines.append(
            f"\nКаталог: авто-разметка {auto_n} (Building/Landscape/фон). "
            f"Осталось Props: {pending}."
        )
        if pending:
            lines.append("Нажми «Следующий шаг» — откроется окно разметки (не Blender!).")

    meshes = report.get("meshes") or []
    if meshes and report.get("catalog_pending") is None:
        lines.append(f"\nОбъектов в файле: {len(meshes)} (разметка — во Вью, не переименовывай в Blender).")

    if report.get("blender_opened"):
        lines.append("\nBlender открыт — только осмотр: стены, свет, нет ли явного мусора.")
        lines.append("Переименовывать 90 объектов НЕ нужно. Ctrl+S — если что-то поправил руками.")
        lines.append("Разметка ролей — «Следующий шаг» во Вью.")

    try:
        from ...building_workflow import open_wall_checklist, parse_building_notes, read_sidecar_for_blend

        src = Path(str(report.get("source") or ""))
        if src.is_file():
            notes = parse_building_notes(read_sidecar_for_blend(src))
            if notes.wants_open_wall:
                out_label = Path(str(report.get("output") or src)).stem
                lines.append("\n" + open_wall_checklist(notes, blend_label=out_label))
            elif notes.building_type:
                lines.append(
                    f"\nnotes.txt: building_type={notes.building_type}. "
                    "Для отрезания стены добавь open_wall=front"
                )
    except Exception:  # noqa: BLE001
        pass

    archived = report.get("inbox_archived") or []
    if archived:
        lines.append("\nInbox очищен — исходники в Library:")
        for line in archived[:6]:
            lines.append(f"  • {line}")
        if len(archived) > 6:
            lines.append(f"  … ещё {len(archived) - 6}")

    errors = report.get("errors") or []
    if errors:
        lines.append("\nПредупреждения:")
        for err in errors:
            lines.append(f"  ! {err}")

    return "\n".join(lines)
