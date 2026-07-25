"""Чеклист «тело Шани» простыми словами.

Не делает магию за тебя в Blender — показывает, какой шаг сейчас
и что нажать. Состояние: ``.viu/body_pipeline.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Config

# Шаги для человека без жаргона. id стабильные.
BODY_STEPS: Tuple[Dict[str, str], ...] = (
    {
        "id": "stage_pack",
        "title": "1. Положить тело в Inbox",
        "how": (
            "В хламнике U:\\Desktop Mascot\\Women найди папку с телом (Erisa).\n"
            "В чате: asset_archive_stage source=… category=Women\n"
            "Или скопируй папку руками в U:\\Anabarra\\Inbox\\creatures\\"
        ),
    },
    {
        "id": "open_blender",
        "title": "2. Открыть в Blender",
        "how": (
            "Открой .blend из Inbox.\n"
            "Рядом должно быть «своё» тело (то, которое пойдёт в игру) — "
            "Erisa тут только как образец формы."
        ),
    },
    {
        "id": "shrinkwrap",
        "title": "3. Подогнать форму (Shrinkwrap)",
        "how": (
            "Erisa = образец пропорций.\n"
            "На своём теле поставь модификатор Shrinkwrap (как ты уже делал).\n"
            "Когда форма ок — сохрани .blend (Ctrl+S)."
        ),
    },
    {
        "id": "rigify",
        "title": "4. Скелет Rigify",
        "how": (
            "Добавь риг Rigify на готовое тело.\n"
            "Проверка во Вью: инструмент rig_check.\n"
            "Снова сохрани .blend."
        ),
    },
    {
        "id": "export_fbx",
        "title": "5. Выгрузить FBX в Unity",
        "how": (
            "Инструмент blender_export_shanya — спрячет лишние кружки рига и сделает FBX.\n"
            "Файл должен оказаться в Assets/Characters/Shanya/."
        ),
    },
    {
        "id": "unity_humanoid",
        "title": "6. Включить Humanoid в Unity",
        "how": (
            "В Unity: клик по модели → Rig → Humanoid → Apply.\n"
            "Потом можно снова «Запустить тестовую сцену»."
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
            "Сделал шаг? Нажми кнопку «Шаг тела — готово» или в чате: body_pipeline action=done",
            "Подробнее простыми словами: docs/NOW.md",
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
        msg = "все шаги тела отмечены — Idle сделаем позже"
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
