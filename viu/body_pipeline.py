"""Чеклист «тело Шани» простыми словами.

Дирижёр кнопок «Blender — существа», не параллельный ручной Blender.
Канон: ``docs/SHANYA_PIPELINE.md``. Состояние: ``.viu/body_pipeline.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Config

# id стабильные. Смысл — полуавтомат Вью (prep / студия / FBX).
BODY_STEPS: Tuple[Dict[str, str], ...] = (
    {
        "id": "stage_pack",
        "title": "1. Tracer → Inbox как существо shanya",
        "how": (
            "Рабочее тело: **Tracer cutdown** (Beerware). Риг уже в паке.\n"
            "\n"
            "Положи пак сюда (как обычное существо):\n"
            "  U:\\Anabarra\\Inbox\\creatures\\shanya\\\n"
            "Один основной скин + textures по README пака.\n"
            "\n"
            "Чат: asset_provenance action=ensure_pilots\n"
            "Полный план: docs/SHANYA_PIPELINE.md\n"
            "\n"
            "HS2 сюда не кладём как меш — только потом анимации (фаза B)."
        ),
    },
    {
        "id": "open_blender",
        "title": "2. Очистить модель + текстуры (кнопка Вью)",
        "how": (
            "Жми в сайдбаре:\n"
            "  **Blender — существа → 1. Очистить модель**\n"
            "\n"
            "Вью поднимет prep: упакует/перепривяжет текстуры "
            "(наше «запечь» сейчас → texture_manifest), "
            "сохранит prepared.blend.\n"
            "\n"
            "Один скин Tracer. Лишние скин-.blend пака не тащи в prepared.\n"
            "После Ctrl+S: кнопка **4. Забрать правки в каталог**."
        ),
    },
    {
        "id": "shrinkwrap",
        "title": "3. Рост в студии (форма — по желанию)",
        "how": (
            "Главное — **рост**, не Shrinkwrap.\n"
            "\n"
            "Кнопка: **Blender — существа → 3. Фото роста и эталон**\n"
            "• класс humanoid, рост ~1.70 м;\n"
            "• «Применить рост»;\n"
            "• скрины front/side.\n"
            "\n"
            "Shrinkwrap на HS2-лекало — только если пропорции бесят; "
            "HS2-меш в Unity не едет.\n"
            "\n"
            "Потом **4. Забрать правки в каталог**."
        ),
    },
    {
        "id": "rigify",
        "title": "4. Риг пака — только проверить",
        "how": (
            "Rigify **не** ставим — у Tracer риг уже есть.\n"
            "\n"
            "Инструмент: rig_check (при необходимости rig_map).\n"
            "Цель: Unity съест как Humanoid.\n"
            "Ок → эталон FBX."
        ),
    },
    {
        "id": "export_fbx",
        "title": "5. Эталон FBX (студия / export)",
        "how": (
            "В студии: **Сохранить эталон FBX** → "
            "Processed/shanya/shanya_ready.fbx (+ manifest).\n"
            "\n"
            "Запасной путь: blender_export_shanya из prepared.blend.\n"
            "\n"
            "Куда:\n"
            "  • Unity: Assets/Characters/Shanya/\n"
            "  • эталон для монстров: Lab/Models/CascadeurReady/Shanya.fbx\n"
            "\n"
            "Тот же полуавтомат, что для других существ."
        ),
    },
    {
        "id": "unity_humanoid",
        "title": "6. Unity Humanoid + тестовая сцена",
        "how": (
            "FBX → Rig → Humanoid → Apply.\n"
            "Кнопка: **▶ Запустить тестовую сцену**.\n"
            "\n"
            "Фаза A готова. Фаза B: PR #66 → анимации HS2 на этот Humanoid.\n"
            "docs/SHANYA_PIPELINE.md"
        ),
    },
)


@dataclass
class BodyPipelineState:
    current_step: str = "stage_pack"
    done_steps: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "BodyPipelineState":
        return cls(
            current_step=str(raw.get("current_step") or "stage_pack"),
            done_steps=[str(x) for x in (raw.get("done_steps") or [])],
            notes=str(raw.get("notes") or ""),
        )


def state_path(config: Config) -> Path:
    return Path(config.data_dir) / "body_pipeline.json"


def load_state(config: Config) -> BodyPipelineState:
    path = state_path(config)
    if not path.is_file():
        return BodyPipelineState()
    try:
        return BodyPipelineState.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return BodyPipelineState()


def save_state(config: Config, state: BodyPipelineState) -> Path:
    path = state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _step_index(step_id: str) -> int:
    for i, s in enumerate(BODY_STEPS):
        if s["id"] == step_id:
            return i
    return 0


def current_step_info(state: BodyPipelineState) -> Dict[str, str]:
    idx = _step_index(state.current_step)
    return dict(BODY_STEPS[idx])


def render_checklist(config: Config) -> str:
    state = load_state(config)
    cur = state.current_step
    lines = [
        "Тело Шани — что делать сейчас (просто)",
        "Tracer → конвейер существ (prep / рост / FBX). См. docs/SHANYA_PIPELINE.md",
        "",
    ]
    for s in BODY_STEPS:
        if s["id"] in state.done_steps:
            mark = "[x]"
        elif s["id"] == cur:
            mark = "[→]"
        else:
            mark = "[ ]"
        lines.append(f"  {mark} {s['title']}")
    info = current_step_info(state)
    lines.extend(
        [
            "",
            f"Сейчас: {info['title']}",
            "",
            info["how"],
            "",
            "Сделал шаг? «Шаг тела — готово» или body_pipeline action=done",
            "Сброс: body_pipeline action=reset",
            "Канон: docs/SHANYA_PIPELINE.md",
        ]
    )
    if state.notes:
        lines.extend(["", f"Заметка: {state.notes}"])
    return "\n".join(lines)


def mark_step_done(
    config: Config, step_id: Optional[str] = None
) -> Tuple[BodyPipelineState, str]:
    state = load_state(config)
    sid = step_id or state.current_step
    if sid not in state.done_steps:
        state.done_steps.append(sid)
    idx = _step_index(sid)
    if idx + 1 < len(BODY_STEPS):
        state.current_step = BODY_STEPS[idx + 1]["id"]
        msg = (
            f"шаг «{BODY_STEPS[idx]['title']}» отмечен. "
            f"Дальше: {BODY_STEPS[idx + 1]['title']}"
        )
    else:
        state.current_step = sid
        msg = "фаза A (тело) отмечена — дальше HS2-анимации (PR #66)"
    save_state(config, state)
    return state, msg


def set_step(config: Config, step_id: str) -> Tuple[bool, str]:
    if not any(s["id"] == step_id for s in BODY_STEPS):
        ids = ", ".join(s["id"] for s in BODY_STEPS)
        return False, f"неизвестный шаг. Можно: {ids}"
    state = load_state(config)
    state.current_step = step_id
    save_state(config, state)
    return True, f"текущий шаг: {step_id}"


def reset_progress(config: Config, *, at_step: str = "stage_pack") -> Tuple[bool, str]:
    """Сбросить галочки."""
    if not any(s["id"] == at_step for s in BODY_STEPS):
        return False, "неизвестный step"
    state = BodyPipelineState(
        current_step=at_step, done_steps=[], notes="reset: shanya creature pipeline"
    )
    save_state(config, state)
    return True, f"чеклист сброшен → {at_step}"
