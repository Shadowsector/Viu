"""Prepared blend → FBX в Library и Unity Assets."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...anabarra_layout import library_root, unity_project_path
from ...config import Config
from .exe import resolve_blender_exe
from .export_building import export_building_fbx, pack_name_from_prepared, slugify_pack_name

_TEXTURE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".webp"}


@dataclass
class ExportPipelineResult:
    ok: bool = True
    pack: str = ""
    slug: str = ""
    blend: str = ""
    library_fbx: str = ""
    unity_fbx: str = ""
    metadata: str = ""
    meshes: List[str] = field(default_factory=list)
    dollhouse_wall: str = ""
    textures: List[str] = field(default_factory=list)
    material_textures: Dict[str, str] = field(default_factory=dict)
    slot_texture_list: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""


def find_latest_prepared(config: Config) -> Optional[Path]:
    processed = library_root(config) / "Processed"
    if not processed.is_dir():
        return None
    prepared = [p for p in processed.rglob("*_prepared.blend") if p.is_file()]
    if not prepared:
        return None
    return max(prepared, key=lambda p: p.stat().st_mtime)


def library_fbx_path(config: Config, slug: str) -> Path:
    return library_root(config) / "Props" / "fbx" / slug / f"{slug}.fbx"


def unity_fbx_dir(config: Config, slug: str) -> Path:
    return unity_project_path(config) / "Assets" / "Environment" / slug


def unity_fbx_path(config: Config, slug: str) -> Path:
    return unity_fbx_dir(config, slug) / f"{slug}.fbx"


def unity_metadata_path(config: Config, slug: str) -> Path:
    return unity_fbx_dir(config, slug) / f"{slug}.viu.json"


def _find_dollhouse_wall(mesh_names: List[str]) -> str:
    for name in mesh_names:
        low = name.lower().replace("-", "_")
        if "wall_front" in low or low in ("wallfront", "front_wall"):
            return name
    for name in mesh_names:
        if "wall" in name.lower() and "front" in name.lower():
            return name
    return ""


def unity_textures_dir(config: Config, slug: str) -> Path:
    return unity_fbx_dir(config, slug) / "Textures"


def library_textures_dir(config: Config, slug: str) -> Path:
    return library_fbx_path(config, slug).parent / "Textures"


def _count_texture_files(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() in _TEXTURE_SUFFIXES)


def _copy_textures_to_unity(config: Config, slug: str) -> Tuple[int, Path]:
    src = library_textures_dir(config, slug)
    dst = unity_textures_dir(config, slug)
    if not src.is_dir():
        return 0, dst
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in src.iterdir():
        if not item.is_file() or item.suffix.lower() not in _TEXTURE_SUFFIXES:
            continue
        target = dst / item.name
        if not target.is_file() or item.stat().st_mtime > target.stat().st_mtime:
            shutil.copy2(item, target)
        copied += 1
    return copied, dst


def home_textures_missing(config: Config, slug: str) -> bool:
    return _count_texture_files(unity_textures_dir(config, slug)) == 0


def needs_export(config: Config, prepared: Path) -> bool:
    """FBX нет, blend новее или нет Textures/ в Unity."""
    slug = slugify_pack_name(pack_name_from_prepared(prepared))
    if home_textures_missing(config, slug):
        unity_fbx = unity_fbx_path(config, slug)
        if unity_fbx.is_file():
            return True
    unity_fbx = unity_fbx_path(config, slug)
    if not unity_fbx.is_file():
        lib_fbx = library_fbx_path(config, slug)
        if lib_fbx.is_file():
            return prepared.stat().st_mtime > lib_fbx.stat().st_mtime
        return True
    try:
        return prepared.stat().st_mtime > unity_fbx.stat().st_mtime
    except OSError:
        return True


def ensure_home_textures_exported(
    config: Config,
    *,
    blend_file: str | Path | None = None,
    force: bool = False,
) -> Tuple[bool, str]:
    """Перед оверлеем: если Textures/ пуст — переэкспорт из prepared.blend."""
    prepared = Path(blend_file).expanduser().resolve() if blend_file else find_latest_prepared(config)
    if prepared is None or not prepared.is_file():
        return True, "Нет prepared blend — экспорт текстур пропущен"

    slug = slugify_pack_name(pack_name_from_prepared(prepared))
    tex_n = _count_texture_files(unity_textures_dir(config, slug))
    if tex_n > 0 and not force:
        return True, f"Текстуры дома OK ({tex_n} в Assets/Environment/{slug}/Textures)"

    result = run_export_pipeline(config, blend_file=prepared, force=True)
    if not result.ok:
        return False, result.message
    tex_n = _count_texture_files(unity_textures_dir(config, slug))
    if tex_n == 0:
        return (
            False,
            "Экспорт прошёл, но Textures/ пуст. "
            "Открой prepared.blend — видны ли текстуры на сарае?",
        )
    return True, f"Текстуры дома экспортированы: {tex_n} файлов → Environment/{slug}/Textures"


def catalog_ready_for_export(config: Config, prepared: Path) -> bool:
    from ...prop_catalog.paths import catalog_path
    from ...prop_catalog.store import PropCatalogStore

    store = PropCatalogStore(catalog_path(config))
    prep_key = str(prepared.resolve()).lower()
    for entry in store.pending():
        src = (entry.source_path or "").lower()
        if prep_key in src or src in prep_key:
            return False
        if entry.mesh_name and prepared.name.lower() in src:
            return False
    return True


def run_export_pipeline(
    config: Config,
    *,
    blend_file: str | Path | None = None,
    force: bool = False,
) -> ExportPipelineResult:
    prepared = Path(blend_file).expanduser().resolve() if blend_file else find_latest_prepared(config)
    if prepared is None or not prepared.is_file():
        return ExportPipelineResult(
            ok=False,
            message="Нет *_prepared.blend в Library/Processed. Сначала «Принять asset».",
        )

    if not force and not needs_export(config, prepared):
        slug = slugify_pack_name(pack_name_from_prepared(prepared))
        uf = unity_fbx_path(config, slug)
        return ExportPipelineResult(
            ok=True,
            pack=pack_name_from_prepared(prepared),
            slug=slug,
            blend=str(prepared),
            unity_fbx=str(uf),
            message=f"FBX уже актуален: {uf}",
        )

    pack = pack_name_from_prepared(prepared)
    slug = slugify_pack_name(pack)
    lib_out = library_fbx_path(config, slug)
    unity_out = unity_fbx_path(config, slug)
    meta_out = unity_metadata_path(config, slug)

    try:
        exe = str(resolve_blender_exe(config))
    except FileNotFoundError as exc:
        return ExportPipelineResult(ok=False, pack=pack, blend=str(prepared), message=str(exc))

    try:
        report = export_building_fbx(str(prepared), str(lib_out), blender_exe=exe)
    except (OSError, RuntimeError, FileNotFoundError) as exc:
        return ExportPipelineResult(ok=False, pack=pack, blend=str(prepared), message=str(exc))

    meshes = [str(m) for m in report.get("meshes") or []]
    dollhouse = _find_dollhouse_wall(meshes)
    textures = [str(t) for t in report.get("textures") or []]
    material_textures = {str(k): str(v) for k, v in (report.get("material_textures") or {}).items()}
    slot_texture_list = [dict(x) for x in (report.get("slot_texture_list") or [])]

    unity_out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(lib_out, unity_out)
    tex_copied, tex_dir = _copy_textures_to_unity(config, slug)

    meta = {
        "pack": pack,
        "slug": slug,
        "source_blend": str(prepared),
        "meshes": meshes,
        "dollhouse_wall": dollhouse,
        "textures": textures,
        "material_textures": material_textures,
        "material_texture_list": [
            {"material": k, "texture": v} for k, v in sorted(material_textures.items())
        ],
        "slot_texture_list": slot_texture_list,
        "note": "dollhouse_wall — скрывать в Unity, когда персонаж внутри",
    }
    meta_out.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    msg = (
        f"Экспорт «{pack}» OK.\n"
        f"Library: {lib_out}\n"
        f"Unity: {unity_out}\n"
        f"Мешей: {len(meshes)}\n"
        f"Текстур: {tex_copied} → {tex_dir}"
    )
    if dollhouse:
        msg += f"\nDollhouse wall: {dollhouse} (см. {meta_out.name})"
    else:
        msg += "\n⚠ Wall_front не найден в экспорте — проверь имена в Blender."

    return ExportPipelineResult(
        ok=True,
        pack=pack,
        slug=slug,
        blend=str(prepared),
        library_fbx=str(lib_out),
        unity_fbx=str(unity_out),
        metadata=str(meta_out),
        meshes=meshes,
        dollhouse_wall=dollhouse,
        textures=textures,
        material_textures=material_textures,
        slot_texture_list=slot_texture_list,
        message=msg,
    )


def format_export_report(result: ExportPipelineResult) -> str:
    return result.message
