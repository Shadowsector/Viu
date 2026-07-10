"""Режиссёр: один «Следующий шаг» вместо десяти кнопок.

Смотрит Inbox, каталог, roadmap — и говорит Вью, что делать.
Человеку — одна фраза по-русски.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .building_workflow import open_wall_checklist, parse_building_notes, read_sidecar_for_blend
from .config import Config
from .pipeline import PipelineContext, get_pipeline_context
from .roadmap import RoadmapStore


@dataclass
class StepPlan:
    """Что сделать сейчас."""

    message: str
    tool: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    human_after: str = ""
    idle: bool = False
    stage: str = ""
    step_label: str = ""

    def short_line(self) -> str:
        first = self.message.strip().split("\n")[0]
        return first[:120]


def _roadmap_store(config: Config) -> RoadmapStore:
    return RoadmapStore(config.data_dir / "roadmap.json")


def _prepared_pack_name(prepared: Path) -> str:
    stem = prepared.stem
    if stem.lower().endswith("_prepared"):
        stem = stem[: -len("_prepared")]
    return prepared.parent.name if prepared.parent.name.lower() != "processed" else stem


def _with_ctx(plan: StepPlan, ctx: PipelineContext) -> StepPlan:
    plan.stage = ctx.stage
    plan.step_label = ctx.step_label
    if ctx.step_label and not plan.message.startswith("["):
        plan.message = f"[{ctx.step_label}]\n{plan.message}"
    return plan


def plan_next_step(config: Config) -> StepPlan:
    """Asset-пайплайн (1–4), потом playtest. Одна кнопка — один шаг."""
    ctx = get_pipeline_context(config)

    if ctx.inbox_needs_prepare:
        return _with_ctx(
            StepPlan(
                message=(
                    "В Inbox новый .blend.\n"
                    "Сейчас: текстуры, pack, фон, свет → Processed.\n"
                    "Blender откроется для осмотра — переименовывать 90 объектов не нужно.\n"
                    "Сарай с дырой: положи notes.txt рядом (open_wall=front)."
                ),
                tool="prepare_unity_asset",
                tool_args={"open_blender": "1"},
                human_after="Дальше — снова «Следующий шаг» → разметка Props (окно Вью, не Blender).",
            ),
            ctx,
        )

    if ctx.stage == "catalog":
        return _with_ctx(
            StepPlan(
                message=(
                    f"Prepared «{ctx.prepared_name}» — нужно разложить объекты по коллекциям.\n"
                    "Building / Landscape → shell автоматически. Тебе — только Props."
                ),
                tool="__prop_catalog__",
                human_after="Откроется «Очередь разметки».",
            ),
            ctx,
        )

    if ctx.stage == "markup":
        return _with_ctx(
            StepPlan(
                message=(
                    f"«{ctx.prepared_name}» — осталось {ctx.pending_props} Props.\n"
                    "На каждом: вес + галочки (сидеть, взять…). "
                    "Building/Landscape уже shell — не трогай."
                ),
                tool="__prop_catalog__",
                human_after="Закончил — «Готово — закрыть» в окне разметки.",
            ),
            ctx,
        )

    if ctx.stage == "wall" and ctx.prepared_path is not None:
        notes = parse_building_notes(read_sidecar_for_blend(ctx.prepared_path))
        return _with_ctx(
            StepPlan(
                message=open_wall_checklist(notes, blend_label=ctx.prepared_path.stem),
                idle=True,
                human_after=(
                    "Отдели Wall_front в Blender (не удаляй!) → Ctrl+S → «Следующий шаг»."
                ),
            ),
            ctx,
        )

    if ctx.stage == "export" and ctx.prepared_path is not None:
        pack = _prepared_pack_name(ctx.prepared_path)
        return _with_ctx(
            StepPlan(
                message=(
                    f"«{pack}» разметен.\n"
                    "Сейчас: FBX → Library/Props/fbx и Unity/Assets/Environment/."
                ),
                tool="export_unity_asset",
                human_after="Проверь папку в Unity. Dollhouse: меш Wall_front должен быть в FBX.",
            ),
            ctx,
        )

    # Asset в Unity — можно новый Inbox или (опционально) оверлей.
    if ctx.stage == "asset_done":
        slug = ctx.prepared_name.replace(" ", "_")
        return _with_ctx(
            StepPlan(
                message=(
                    f"«{ctx.prepared_name}» в Unity (Assets/Environment/{slug}/).\n"
                    "Новый домик → положи в Inbox → «Следующий шаг».\n"
                    "Оверлей (Шаня у панели) — только если хочешь playtest, кнопка в «Ещё — Unity»."
                ),
                idle=True,
                human_after="Inbox пуст? Положи следующий .blend.",
            ),
            ctx,
        )

    # Playtest / roadmap — не перебиваем незавершённый asset.
    if ctx.prepared_path is not None and not ctx.catalog_ready and ctx.stage not in (
        "markup",
        "catalog",
        "wall",
        "export",
        "asset_done",
    ):
        return _with_ctx(
            StepPlan(
                message=(
                    f"«{ctx.prepared_name}» в Processed — добей разметку Props, "
                    "потом экспорт."
                ),
                idle=True,
            ),
            ctx,
        )

    focus = _roadmap_store(config).roadmap.current_focus()
    title = (focus.title if focus else "").lower()

    if focus and any(k in title for k in ("панел", "оверлей", "дом", "taskbar")):
        if not ctx.overlay_built:
            return _with_ctx(
                StepPlan(
                    message=(
                        "Playtest: собрать оверлей — Шаня у панели задач.\n"
                        "Unity **закрыт**. 5–15 мин. (Не связано с импортом домика.)"
                    ),
                    tool="unity_overlay",
                    human_after="После сборки — AnabarraOverlay.exe, A/D.",
                ),
                get_pipeline_context(config),
            )
        return _with_ctx(
            StepPlan(
                message=(
                    "Оверлей собран — AnabarraOverlay.exe.\n"
                    "A/D — ходьба, W/S — глубина, Esc — выход.\n"
                    "Подкрутить глубину: «Ещё — Unity → Оверлей: в глубину» (только после сборки)."
                ),
                idle=True,
                human_after="Новый asset → Inbox → «Следующий шаг».",
            ),
            get_pipeline_context(config),
        )

    if focus:
        return _with_ctx(
            StepPlan(
                message=(
                    f"План: «{focus.title}».\n"
                    "Asset-пайплайн: Inbox → «Следующий шаг» (4 шага).\n"
                    "Или напиши в чат справа."
                ),
                idle=True,
            ),
            ctx,
        )

    return _with_ctx(
        StepPlan(
            message="Положи .blend в U:\\Viu\\Inbox → «Следующий шаг».",
            idle=True,
        ),
        ctx,
    )


def format_banner(plan: StepPlan) -> str:
    lines = ["▶ " + plan.message.replace("\n", "\n  ")]
    if plan.human_after:
        lines.append("→ " + plan.human_after)
    return "\n".join(lines)
