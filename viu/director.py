"""Режиссёр: один «Следующий шаг» вместо десяти кнопок.

Смотрит Inbox, каталог, roadmap — и говорит Вью, что делать.
Человеку — одна фраза по-русски.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .anabarra_layout import inbox_dir, library_root, unity_project_path
from .config import Config
from .integrations.blender.prepare_asset import find_inbox_blend, prepared_output_path
from .integrations.unity.overlay import overlay_exe_path
from .prop_catalog.paths import catalog_path
from .prop_catalog.store import PropCatalogStore
from .roadmap import RoadmapStore


@dataclass
class StepPlan:
    """Что сделать сейчас."""

    message: str
    tool: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    human_after: str = ""
    idle: bool = False

    def short_line(self) -> str:
        first = self.message.strip().split("\n")[0]
        return first[:120]


def _roadmap_store(config: Config) -> RoadmapStore:
    return RoadmapStore(config.data_dir / "roadmap.json")


def _catalog_store(config: Config) -> PropCatalogStore:
    return PropCatalogStore(catalog_path(config))


def _inbox_needs_prepare(config: Config) -> bool:
    """Inbox с .blend, для которого ещё нет свежего *_prepared.blend."""
    try:
        blend = find_inbox_blend(inbox_dir(config))
    except FileNotFoundError:
        return False
    prepared = prepared_output_path(blend, library_root(config))
    try:
        if prepared.is_file() and prepared.stat().st_mtime >= blend.stat().st_mtime:
            return False
    except OSError:
        pass
    return True


def _pending_catalog(config: Config) -> tuple[list, list]:
    store = _catalog_store(config)
    pending = store.pending()
    file_level = [
        e
        for e in pending
        if e.source_path.lower().endswith(".blend") and not e.mesh_name
    ]
    mesh_level = [e for e in pending if e.mesh_name]
    return file_level, mesh_level


def _overlay_exe_exists(config: Config) -> bool:
    try:
        root = unity_project_path(config)
        exe = overlay_exe_path(root)
        return exe.is_file()
    except OSError:
        return False


def _latest_prepared_pack(config: Config) -> Optional[Path]:
    """Самый свежий *_prepared.blend в Library/Processed."""
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


def _prepared_pack_name(prepared: Path) -> str:
    stem = prepared.stem
    if stem.lower().endswith("_prepared"):
        stem = stem[: -len("_prepared")]
    return prepared.parent.name if prepared.parent.name.lower() != "processed" else stem


def plan_next_step(config: Config) -> StepPlan:
    """Приоритет: Inbox → разложить blend → разметка → дом/оверлей → подсказка."""
    if _inbox_needs_prepare(config):
        return StepPlan(
            message=(
                "В Inbox лежит новый файл.\n"
                "Сейчас: приму asset — текстуры, pack, уберу лишний фон, открою Blender.\n"
                "Тебе: глянуть в Blender — всё ли на месте. Переименовывать меши не нужно."
            ),
            tool="prepare_unity_asset",
            tool_args={"open_blender": "1"},
            human_after="После prepare — снова «Следующий шаг» → разметка Props во Вью.",
        )

    file_level, mesh_level = _pending_catalog(config)
    if file_level:
        names = ", ".join(Path(e.source_path).name for e in file_level[:3])
        return StepPlan(
            message=(
                f"Есть .blend без списка объектов ({names}).\n"
                "Сейчас: разложу по Building / Props, как в Scene Collection Blender."
            ),
            tool="__rescan_catalog__",
            human_after="Откроется окно разметки — или снова «Следующий шаг».",
        )

    if mesh_level:
        n = len(mesh_level)
        sample = mesh_level[0].list_label()
        return StepPlan(
            message=(
                f"Осталось разметить {n} предметов из Props (например: {sample}).\n"
                "Building и Landscape Вью уже пометила shell — не трогай.\n"
                "На каждом Prop: вес + галочки (сидеть, открыть…). Shell — кнопка «Shell — пропустить»."
            ),
            tool="__prop_catalog__",
            human_after="Разметил Props — «Готово — закрыть» в окне каталога.",
        )

    # Каталог закрыт — если есть свежий prepared-asset, не уводим в «Walk» по roadmap.
    prepared = _latest_prepared_pack(config)
    if prepared is not None:
        pack = _prepared_pack_name(prepared)
        if not _overlay_exe_exists(config):
            return StepPlan(
                message=(
                    f"Asset «{pack}» готов в Processed, разметка завершена.\n"
                    "Следующий шаг: собрать оверлей — Шаня у панели задач.\n"
                    "Unity должен быть **закрыт** (5–15 минут сборки)."
                ),
                tool="unity_overlay",
                human_after=(
                    "Экспорт сарая/домика в Unity как prefab — позже. "
                    "Сейчас — оверлей и проверка A/D."
                ),
            )
        return StepPlan(
            message=(
                f"Asset «{pack}» разметен и лежит в Processed.\n"
                "Оверлей собран — запусти AnabarraOverlay.exe, проверь A/D.\n"
                "Импорт сцены в Unity (prefab) — в следующей версии Вью."
            ),
            idle=True,
            human_after="Новый asset → Inbox → «Следующий шаг».",
        )

    focus = _roadmap_store(config).roadmap.current_focus()
    title = (focus.title if focus else "").lower()

    if focus and any(k in title for k in ("панел", "оверлей", "дом", "taskbar")):
        if not _overlay_exe_exists(config):
            return StepPlan(
                message=(
                    "Пора собрать оверлей — Шаня у панели задач.\n"
                    "Unity должен быть **закрыт**. Сборка 5–15 минут, потом запустится exe."
                ),
                tool="unity_overlay",
                human_after="После сборки запусти оверлей, проверь A/D. Потом — снова «Следующий шаг».",
            )
        return StepPlan(
            message=(
                "Оверлей уже собран.\n"
                "Запусти AnabarraOverlay.exe, проверь ходьбу A/D и W/S (глубина).\n"
                "Настройки: overlay_tune.json рядом с exe, F5 сохраняет."
            ),
            idle=True,
            human_after="Новый asset → Inbox → «Следующий шаг».",
        )

    if focus:
        return StepPlan(
            message=(
                f"Сейчас по плану: «{focus.title}».\n"
                "Положи новый asset в U:\\Viu\\Inbox — или напиши в чат справа, что хочешь."
            ),
            idle=True,
        )

    return StepPlan(
        message="План на сегодня выполнен. Новый asset → Inbox → «Следующий шаг».",
        idle=True,
    )


def format_banner(plan: StepPlan) -> str:
    lines = ["▶ " + plan.message.replace("\n", "\n  ")]
    if plan.human_after:
        lines.append("→ " + plan.human_after)
    return "\n".join(lines)
