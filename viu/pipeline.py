"""Контекст asset-пайплайна — одна линия: Inbox → разметка → экспорт → Unity.

Используется режиссёром (director) и GUI для подписей и видимости кнопок.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .anabarra_layout import inbox_dir, library_root, unity_project_path
from .building_workflow import parse_building_notes, read_sidecar_for_blend
from .config import Config
from .integrations.blender.export_pipeline import (
    catalog_ready_for_export,
    needs_export as blend_needs_export,
)
from .integrations.blender.prepare_asset import find_inbox_blend, prepared_output_path
from .integrations.unity.overlay import overlay_exe_path
from .prop_catalog.paths import catalog_path
from .prop_catalog.store import PropCatalogStore


@dataclass
class PipelineContext:
    """Где мы в asset-пайплайне (и нужен ли оверлей)."""

    stage: str
    """inbox | catalog | markup | wall | export | asset_done | playtest | idle"""

    step_label: str
    """Человекочитаемая подпись, напр. «Asset 2/4 — разметка Props»."""

    has_inbox_blend: bool = False
    inbox_needs_prepare: bool = False
    prepared_path: Optional[Path] = None
    prepared_name: str = ""
    pending_file_level: int = 0
    pending_props: int = 0
    wants_wall_cut: bool = False
    catalog_ready: bool = False
    needs_fbx_export: bool = False
    overlay_built: bool = False


def _inbox_blend(config: Config) -> Optional[Path]:
    try:
        return find_inbox_blend(inbox_dir(config))
    except FileNotFoundError:
        return None


def _inbox_needs_prepare(config: Config) -> bool:
    blend = _inbox_blend(config)
    if blend is None:
        return False
    prepared = prepared_output_path(blend, library_root(config))
    try:
        if prepared.is_file() and prepared.stat().st_mtime >= blend.stat().st_mtime:
            return False
    except OSError:
        pass
    return True


def _latest_prepared(config: Config) -> Optional[Path]:
    try:
        processed = library_root(config) / "Processed"
        if not processed.is_dir():
            return None
        prepared = [p for p in processed.rglob("*_prepared.blend") if p.is_file()]
        if not prepared:
            return None
        return max(prepared, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None


def _prepared_name(prepared: Path) -> str:
    stem = prepared.stem
    if stem.lower().endswith("_prepared"):
        stem = stem[: -len("_prepared")]
    parent = prepared.parent.name
    if parent.lower() != "processed":
        return parent
    return stem


def _pending_counts(config: Config) -> tuple[int, int]:
    pending = PropCatalogStore(catalog_path(config)).pending()
    file_level = sum(
        1
        for e in pending
        if e.source_path.lower().endswith(".blend") and not e.mesh_name
    )
    mesh_level = sum(1 for e in pending if e.mesh_name)
    return file_level, mesh_level


def _overlay_built(config: Config) -> bool:
    try:
        return overlay_exe_path(unity_project_path(config)).is_file()
    except OSError:
        return False


def get_pipeline_context(config: Config) -> PipelineContext:
    has_inbox = _inbox_blend(config) is not None
    needs_prepare = _inbox_needs_prepare(config)
    file_n, prop_n = _pending_counts(config)
    prepared = _latest_prepared(config)
    prep_name = _prepared_name(prepared) if prepared else ""

    wants_wall = False
    cat_ready = False
    needs_fbx_export = False
    if prepared is not None:
        notes = parse_building_notes(read_sidecar_for_blend(prepared))
        wants_wall = notes.wants_open_wall
        cat_ready = catalog_ready_for_export(config, prepared)
        needs_fbx_export = cat_ready and blend_needs_export(config, prepared)

    overlay = _overlay_built(config)

    if needs_prepare:
        return PipelineContext(
            stage="inbox",
            step_label="Asset 1/4 — принять из Inbox",
            has_inbox_blend=True,
            inbox_needs_prepare=True,
            prepared_path=prepared,
            prepared_name=prep_name,
            pending_file_level=file_n,
            pending_props=prop_n,
            overlay_built=overlay,
        )

    if file_n:
        return PipelineContext(
            stage="catalog",
            step_label="Asset 2/4 — разложить объекты",
            has_inbox_blend=has_inbox,
            prepared_path=prepared,
            prepared_name=prep_name,
            pending_file_level=file_n,
            pending_props=prop_n,
            overlay_built=overlay,
        )

    if prop_n:
        return PipelineContext(
            stage="markup",
            step_label=f"Asset 2/4 — разметка Props ({prop_n})",
            has_inbox_blend=has_inbox,
            prepared_path=prepared,
            prepared_name=prep_name,
            pending_props=prop_n,
            overlay_built=overlay,
        )

    if prepared is not None and wants_wall:
        return PipelineContext(
            stage="wall",
            step_label="Asset 2/4 — стена dollhouse в Blender",
            has_inbox_blend=has_inbox,
            prepared_path=prepared,
            prepared_name=prep_name,
            wants_wall_cut=True,
            overlay_built=overlay,
        )

    if prepared is not None and needs_fbx_export:
        return PipelineContext(
            stage="export",
            step_label=f"Asset 3/4 — экспорт «{prep_name}» в Unity",
            has_inbox_blend=has_inbox,
            prepared_path=prepared,
            prepared_name=prep_name,
            catalog_ready=True,
            needs_fbx_export=True,
            overlay_built=overlay,
        )

    if prepared is not None and cat_ready:
        return PipelineContext(
            stage="asset_done",
            step_label=f"Asset 4/4 — «{prep_name}» в Unity",
            has_inbox_blend=has_inbox,
            prepared_path=prepared,
            prepared_name=prep_name,
            catalog_ready=True,
            overlay_built=overlay,
        )

    if overlay:
        return PipelineContext(
            stage="playtest",
            step_label="Playtest — оверлей / анимации",
            has_inbox_blend=has_inbox,
            prepared_path=prepared,
            prepared_name=prep_name,
            overlay_built=True,
        )

    return PipelineContext(
        stage="idle",
        step_label="Новый asset → Inbox",
        has_inbox_blend=has_inbox,
        prepared_path=prepared,
        prepared_name=prep_name,
        overlay_built=overlay,
    )


# Кнопки «Ещё», которые показываем только в нужной фазе.
_ACTION_VISIBILITY: dict[str, frozenset[str]] = {
    "prepare_unity_asset": frozenset({"inbox", "idle", "asset_done", "playtest", "export", "markup", "catalog", "wall"}),
    "prop_catalog": frozenset({"catalog", "markup", "wall", "export", "asset_done"}),
    "export_unity_asset": frozenset({"export", "asset_done", "wall"}),
    "unity_overlay": frozenset({"asset_done", "playtest", "idle"}),
    "overlay_depth_far": frozenset({"playtest"}),
    "overlay_depth_close": frozenset({"playtest"}),
}


def action_visible(action_id: str, ctx: PipelineContext) -> bool:
    """Скрыть лишние кнопки во время asset-пайплайна."""
    allowed = _ACTION_VISIBILITY.get(action_id)
    if allowed is None:
        return True
    if action_id in ("overlay_depth_far", "overlay_depth_close") and not ctx.overlay_built:
        return False
    if action_id == "unity_overlay" and ctx.stage in ("inbox", "catalog", "markup", "wall", "export"):
        return False
    if action_id == "prepare_unity_asset" and not ctx.has_inbox_blend:
        return False
    return ctx.stage in allowed
