"""Точки взаимодействия Дена со Вью: папки и файлы.

Меню «Места» в GUI открывает их в проводнике / редакторе.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from .config import Config


@dataclass(frozen=True)
class Place:
    place_id: str
    label: str
    kind: str  # "folder" | "file"
    group: str
    hint: str
    resolve: Callable[[Config], Path]
    ensure: bool = True  # создать папку/файл-каркас, если нет


def _open_path(path: Path) -> tuple[bool, str]:
    """Открыть папку в проводнике или файл в редакторе по умолчанию."""
    try:
        path = path.resolve()
    except OSError:
        pass
    target = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except OSError as exc:
        return False, f"Не открыла ({exc}):\n{target}"
    return True, target


def open_place(config: Config, place: Place) -> tuple[bool, str]:
    """Разрешить путь, при необходимости создать, открыть."""
    try:
        path = place.resolve(config)
    except Exception as exc:  # noqa: BLE001
        return False, f"{place.label}: не удалось найти путь ({exc})"

    if place.ensure:
        try:
            if place.kind == "folder":
                path.mkdir(parents=True, exist_ok=True)
            elif place.kind == "file":
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.is_file():
                    # ensure_* helpers already write defaults when called via resolve
                    path.touch(exist_ok=True)
        except OSError as exc:
            return False, f"{place.label}: не создать ({exc})\n{path}"

    ok, msg = _open_path(path)
    if not ok:
        return False, f"{place.label}: {msg}"
    kind_ru = "папка" if place.kind == "folder" else "файл"
    return True, f"{place.label} ({kind_ru}):\n{msg}"


def _vision(config: Config) -> Path:
    from .vision import ensure_vision

    return ensure_vision(config)


def _characters(config: Config) -> Path:
    from .characters_vision import ensure_characters_vision

    return ensure_characters_vision(config)


def _logs(config: Config) -> Path:
    p = config.data_dir / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _comfy_kept(config: Config) -> Path:
    from .integrations.comfy.clip_review import comfy_kept_dir

    return comfy_kept_dir(config)


def _comfy_rejected(config: Config) -> Path:
    from .integrations.comfy.clip_review import comfy_rejected_dir

    return comfy_rejected_dir(config)


def _girl_sockets(config: Config) -> Path:
    from .creature_catalog.paths import girl_sockets_doc_path

    return girl_sockets_doc_path(config)


def _creature_catalog(config: Config) -> Path:
    from .creature_catalog.paths import creature_catalog_path

    return creature_catalog_path(config)


def all_places() -> List[Place]:
    """Канонический список входов/выходов."""
    from .anabarra_layout import inbox_dir, library_root, mascot_archive_dir
    from .creature_catalog.paths import (
        creatures_inbox_dir,
        creatures_lineup_dir,
        creatures_processed_dir,
    )
    from .integrations.cascadeur.paths import cascadeur_export, cascadeur_inbox
    from .integrations.comfy.paths import (
        comfy_out_dir,
        comfy_refs_dir,
        comfy_seed_frames_dir,
        comfy_workflows_dir,
    )
    from .lab.paths import cascadeur_ready_dir, models_inbox_dir

    return [
        # --- Входы: куда класть ---
        Place(
            "viu_inbox",
            "Inbox паков (разбор)",
            "folder",
            "Входы",
            "Один пак за раз → «Следующий шаг» / разбор. U:\\Viu\\Inbox",
            inbox_dir,
        ),
        Place(
            "models_inbox",
            "Модели → Lab Inbox",
            "folder",
            "Входы",
            "Персонажи .blend/.fbx для rig-check и Cascadeur.",
            models_inbox_dir,
        ),
        Place(
            "creatures_inbox",
            "Существа → Inbox",
            "folder",
            "Входы",
            "Монстры/четвероногие → «Разметить существ».",
            creatures_inbox_dir,
        ),
        Place(
            "cascadeur_inbox",
            "Cascadeur Inbox",
            "folder",
            "Входы",
            "FBX/blend прямо в очередь Cascadeur.",
            cascadeur_inbox,
        ),
        # --- Выходы: что Вью собрала ---
        Place(
            "comfy_refs",
            "Клипы Comfy (Refs)",
            "folder",
            "Выходы",
            "Свежие MP4 от Wan / MoCap-кандидаты.",
            comfy_refs_dir,
        ),
        Place(
            "comfy_kept",
            "Клипы kept (отобранные)",
            "folder",
            "Выходы",
            "То, что оставили после «Оценить клипы».",
            _comfy_kept,
        ),
        Place(
            "comfy_rejected",
            "Клипы rejected",
            "folder",
            "Выходы",
            "Отбракованные дубли.",
            _comfy_rejected,
        ),
        Place(
            "comfy_seeds",
            "Seed-кадры (last frame)",
            "folder",
            "Выходы",
            "PNG для следующей i2v-генерации.",
            comfy_seed_frames_dir,
        ),
        Place(
            "comfy_out",
            "ComfyOut (сырой вывод)",
            "folder",
            "Выходы",
            "Промежуточный вывод Comfy, если настроен.",
            comfy_out_dir,
        ),
        Place(
            "cascadeur_ready",
            "CascadeurReady (FBX)",
            "folder",
            "Выходы",
            "Чистые FBX из Blender batch → Import в Cascadeur.",
            cascadeur_ready_dir,
        ),
        Place(
            "animations",
            "Animations → Unity",
            "folder",
            "Выходы",
            "Готовые FBX анимаций (Cascadeur export / staging).",
            cascadeur_export,
        ),
        Place(
            "creatures_lineup",
            "Линейка существ (рендеры)",
            "folder",
            "Выходы",
            "Сравнение роста Шаня + монстры.",
            creatures_lineup_dir,
        ),
        Place(
            "creatures_processed",
            "Существа Processed",
            "folder",
            "Выходы",
            "Обработанные модели существ.",
            creatures_processed_dir,
        ),
        # --- Редакторы / данные ---
        Place(
            "vision",
            "Vision (направление)",
            "file",
            "Файлы",
            "Общие идеи, сюжет, техбэклог — .viu/vision.md",
            _vision,
        ),
        Place(
            "characters_vision",
            "Персонажи (CHARACTERS_VISION)",
            "file",
            "Файлы",
            "Характеры/интим — локально, не на GitHub.",
            _characters,
        ),
        Place(
            "girl_sockets",
            "Сокеты девушек (JSON)",
            "file",
            "Файлы",
            "oral/vaginal/anal/hand — .viu/girl_sockets.json",
            _girl_sockets,
            ensure=False,
        ),
        Place(
            "creature_catalog",
            "Каталог существ (JSON)",
            "file",
            "Файлы",
            "size_class / locomotion — .viu/creature_catalog.json",
            _creature_catalog,
            ensure=False,
        ),
        Place(
            "comfy_workflows",
            "Comfy workflows (API JSON)",
            "folder",
            "Файлы",
            "Свои workflow рядом с данными Вью.",
            comfy_workflows_dir,
        ),
        Place(
            "logs",
            "Логи Вью",
            "folder",
            "Файлы",
            "chat_*.txt и отладочные логи.",
            _logs,
        ),
        Place(
            "library",
            "Library (склад)",
            "folder",
            "Корни",
            "U:\\Anabarra\\Library — после разбора Inbox.",
            library_root,
        ),
        Place(
            "data_dir",
            "Данные .viu",
            "folder",
            "Корни",
            "Каталоги, vision, логи, lab.",
            lambda c: c.data_dir,
        ),
        Place(
            "mascot",
            "Desktop Mascot (архив)",
            "folder",
            "Корни",
            "Сотни файлов — Вью не сканирует; копируй пак → Inbox.",
            mascot_archive_dir,
            ensure=False,
        ),
    ]


def places_by_group() -> dict[str, List[Place]]:
    out: dict[str, List[Place]] = {}
    for p in all_places():
        out.setdefault(p.group, []).append(p)
    return out


def find_place(place_id: str) -> Optional[Place]:
    for p in all_places():
        if p.place_id == place_id:
            return p
    return None


def describe_places(config: Config) -> str:
    """Текст со всеми путями (для чата / отладки)."""
    lines = ["Точки взаимодействия со Вью:", ""]
    for group, items in places_by_group().items():
        lines.append(f"## {group}")
        for place in items:
            try:
                path = place.resolve(config)
            except Exception as exc:  # noqa: BLE001
                path = f"(ошибка: {exc})"
            lines.append(f"- {place.label}: {path}")
            if place.hint:
                lines.append(f"  ({place.hint})")
        lines.append("")
    return "\n".join(lines)
