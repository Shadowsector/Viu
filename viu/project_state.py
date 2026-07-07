"""Снимок состояния проекта Анабарра — что сделано, где мы, что дальше.

Только чтение. Собирает: фокус дорожной карты, состояние папки анимаций
Unity и конкретную рекомендацию следующего шага.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import Config
from .roadmap import RoadmapStore


def _roadmap_store(config: Config) -> RoadmapStore:
    return RoadmapStore(config.data_dir / "roadmap.json")


def _unity_root(config: Config) -> Optional[Path]:
    raw = config.unity_project
    if not raw:
        return None
    root = Path(raw).expanduser()
    return root if (root / "Assets").is_dir() else None


def next_step(config: Config) -> str:
    """Конкретная рекомендация следующего действия к текущему фокусу."""
    store = _roadmap_store(config)
    focus = store.roadmap.current_focus()
    if focus is None:
        return "Все вехи готовы. Пора придумать новую цель — спроси Дена."

    # Специальная логика для активной вехи Walk/локомоции.
    if "walk" in focus.title.lower() or "локомоц" in focus.title.lower():
        root = _unity_root(config)
        if root is None:
            return (
                f"Фокус: «{focus.title}». Unity-проект не найден "
                f"({config.unity_project or 'путь не задан'}). "
                "Задай VIU_UNITY_PROJECT или уточни у Дена путь к проекту."
            )
        try:
            from .integrations.unity.animation_scan import scan_animations_folder

            scan = scan_animations_folder(root)
        except Exception as exc:  # noqa: BLE001
            return f"Фокус: «{focus.title}». Не удалось просканировать Animations: {exc}"

        states = {c.suggested_state for c in scan.clips if c.suggested_state}
        if scan.questions:
            return (
                f"Фокус: «{focus.title}». В Animations есть непонятные файлы — "
                "нужно решение Дена (ask_user) или запись в viu_clips.json:\n"
                + "\n".join(f"  • {q}" for q in scan.questions)
            )
        if "Walk" not in states:
            return (
                f"Фокус: «{focus.title}». Нет клипа Walk. "
                "Действие: кнопка «Импорт FBX анимации…» — выбрать Walking FBX "
                "(например, скачанный с Mixamo). Вью положит его в проект и соберёт Animator."
            )
        non_humanoid = [c.file_name for c in scan.clips if not c.is_humanoid]
        if non_humanoid:
            return (
                f"Фокус: «{focus.title}». Клипы есть, но не Humanoid: "
                f"{', '.join(non_humanoid)}. Действие: «Обновить аниматор» "
                "(unity_sync_animations) — выставит Humanoid и соберёт Animator."
            )
        return (
            f"Фокус: «{focus.title}». Idle и Walk на месте и Humanoid, Animator собран. "
            "Действие: unity_prepare_scene («Тест: Шаня стоит и ходит») — Вью сама "
            "закроет Unity если мешает, соберёт пробную сцену и откроет редактор; "
            "пользователю останется нажать Play. "
            "После проверки отметь веху 4 как done (roadmap_update)."
        )

    if "рост" in focus.title.lower() or "gametest" in focus.title.lower() or "сцена" in focus.title.lower():
        return (
            f"Фокус: «{focus.title}». Walk/Idle работают — дальше нормальная сцена: "
            "пол, свет, камера за Шаней, масштаб ~1.7 м. "
            "Сначала «Обновить аниматор» (loop на FBX), потом «Что делаем дальше?»."
        )

    if "панел" in focus.title.lower() or "оверлей" in focus.title.lower() or "дом" in focus.title.lower():
        return (
            f"Фокус: «{focus.title}». Действие: кнопка «Оверлей: Шаня на панели» "
            "(unity_overlay) — Unity закрыт, сборка 5–15 мин. После запуска A/D на рабочем столе."
        )

    return (
        f"Фокус: «{focus.title}». "
        + (f"Заметка: {focus.note}. " if focus.note else "")
        + "Разбей на конкретный шаг: сначала project_status, потом действуй "
        "по безопасным шагам, а на развилке спроси Дена (ask_user)."
    )


def project_status(config: Config) -> str:
    store = _roadmap_store(config)
    parts = [store.roadmap.render(), ""]

    root = _unity_root(config)
    if root is None:
        parts.append(
            f"Unity: проект не найден ({config.unity_project or 'путь не задан'})."
        )
    else:
        parts.append(f"Unity-проект: {root}")
        try:
            from .integrations.unity.animation_scan import scan_animations_folder

            scan = scan_animations_folder(root)
            parts.append(scan.render())
        except Exception as exc:  # noqa: BLE001
            parts.append(f"Скан анимаций не удался: {exc}")

    parts.append("")
    parts.append("Следующий шаг:")
    parts.append("  " + next_step(config).replace("\n", "\n  "))
    return "\n".join(parts)
