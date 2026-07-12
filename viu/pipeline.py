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
    step_label: str
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
    has_inbox_animation: bool = False
    pending_animation_reviews: int = 0


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


def _inbox_animation_count(config: Config) -> int:
    from .drop_router import _find_inbox_animation_fbx

    try:
        return len(_find_inbox_animation_fbx(inbox_dir(config)))
    except OSError:
        return 0


def _pending_animation_reviews(config: Config) -> int:
    try:
        from .animation_catalog import AnimationCatalogStore, animation_catalog_path

        return len(AnimationCatalogStore(animation_catalog_path(config)).load().pending_reviews())
    except OSError:
        return 0


def get_pipeline_context(config: Config) -> PipelineContext:
    has_inbox = _inbox_blend(config) is not None
    needs_prepare = _inbox_needs_prepare(config)
    file_n, prop_n = _pending_counts(config)
    prepared = _latest_prepared(config)
    prep_name = _prepared_name(prepared) if prepared else ""
    anim_inbox = _inbox_animation_count(config)
    anim_pending = _pending_animation_reviews(config)

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
            step_label="Asset 1/4 — принять .blend из Inbox",
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

    if anim_pending:
        return PipelineContext(
            stage="anim_review",
            step_label=f"Анимации — описать ({anim_pending})",
            has_inbox_blend=has_inbox,
            prepared_path=prepared,
            prepared_name=prep_name,
            overlay_built=overlay,
            has_inbox_animation=anim_inbox > 0,
            pending_animation_reviews=anim_pending,
        )

    if anim_inbox:
        return PipelineContext(
            stage="anim_inbox",
            step_label="Анимация в Inbox — «Принять анимацию»",
            has_inbox_blend=has_inbox,
            prepared_path=prepared,
            prepared_name=prep_name,
            overlay_built=overlay,
            has_inbox_animation=True,
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
        step_label="Inbox: .blend или анимация",
        has_inbox_blend=has_inbox,
        prepared_path=prepared,
        prepared_name=prep_name,
        overlay_built=overlay,
    )


_ACTION_VISIBILITY: dict[str, frozenset[str]] = {
    "route_inbox": frozenset({"inbox", "idle", "catalog", "markup", "wall", "export", "asset_done", "playtest"}),
    "prepare_unity_asset": frozenset({"inbox", "idle", "asset_done"}),
    "prop_catalog": frozenset({"catalog", "markup", "wall", "export", "asset_done"}),
    "export_unity_asset": frozenset({"export", "asset_done", "wall"}),
    "accept_animation": frozenset({"anim_inbox", "idle", "playtest", "asset_done", "anim_review"}),
    "animation_catalog": frozenset({"anim_review", "anim_inbox", "playtest", "asset_done", "idle"}),
    "unity_apply": frozenset({"anim_review", "playtest", "asset_done", "idle", "anim_inbox"}),
    "unity_overlay": frozenset({"asset_done", "playtest", "idle", "anim_inbox", "anim_review"}),
    "unity_overlay_validate": frozenset({"asset_done", "playtest", "idle"}),
    "unity_overlay_rebind": frozenset({"asset_done", "playtest", "idle"}),
    "unity_overlay_build": frozenset({"asset_done", "playtest", "idle"}),
    "overlay_depth_far": frozenset({"playtest"}),
    "overlay_depth_close": frozenset({"playtest"}),
    "cascadeur_status": frozenset({"idle", "playtest", "asset_done", "anim_review", "anim_inbox"}),
}


def action_visible(action_id: str, ctx: PipelineContext) -> bool:
    allowed = _ACTION_VISIBILITY.get(action_id)
    if allowed is None:
        return True
    if action_id in ("overlay_depth_far", "overlay_depth_close") and not ctx.overlay_built:
        return False
    if action_id == "unity_overlay" and ctx.stage in (
        "inbox", "catalog", "markup", "wall", "export"
    ):
        return False
    if action_id == "prepare_unity_asset" and not ctx.has_inbox_blend:
        return False
    if action_id == "accept_animation" and not ctx.has_inbox_animation and ctx.pending_animation_reviews == 0:
        if ctx.stage not in ("idle", "playtest", "asset_done"):
            return False
    return ctx.stage in allowed
