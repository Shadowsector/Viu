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
#
# Канон: в игру уезжает тело со Smutbase (лучше CC0/CC-BY).
# Карта из HS2 Studio — только образец пропорций (временный), не в билд.
BODY_STEPS: Tuple[Dict[str, str], ...] = (
    {
        "id": "stage_pack",
        "title": "1. Положить два файла в Inbox",
        "how": (
            "Правильная схема (чтобы не тащить чужой «ванильный» меш в игру):\n"
            "\n"
            "A) ОБРАЗЕЦ — твоя карта персонажа из HS2 Studio "
            "(пропорции, которые ты накрутил). Экспорт в FBX/OBJ тем способом, "
            "которым ты уже пользуешься → в Inbox. "
            "Это лекало. В Unity оно НЕ поедет.\n"
            "\n"
            "B) РАБОЧЕЕ ТЕЛО — пак со Smutbase из U:\\Desktop Mascot\\Women "
            "(лучше лицензия CC0 или CC-BY; Erisa = CC BY-ND — как образец ок, "
            "как единственное тело в билде хуже). Это меш для игры.\n"
            "\n"
            "Не путать: не «Smutbase вокруг Smutbase». "
            "А «Smutbase обтягиваем по форме твоей HS2-карты».\n"
            "\n"
            "Клади оба в U:\\Anabarra\\Inbox\\creatures\\ "
            "(или asset_archive_stage … category=Women)."
        ),
    },
    {
        "id": "open_blender",
        "title": "2. Открыть оба в Blender",
        "how": (
            "1) Открой или импортируй ОБРАЗЕЦ (экспорт HS2-карты).\n"
            "2) Положи рядом РАБОЧЕЕ тело со Smutbase:\n"
            "   • если это .blend — File → Append → Object → mesh тела;\n"
            "   • если .fbx / .obj — File → Import.\n"
            "3) В сцене видны оба меша.\n"
            "\n"
            "Можно без Shrinkwrap: смотри на HS2-образец и правишь "
            "Smutbase руками. Образец — референс в сцене или на втором мониторе.\n"
            "\n"
            "Blender сам ничего не скачает — только откроет файлы с диска."
        ),
    },
    {
        "id": "shrinkwrap",
        "title": "3. Форма (по желанию Shrinkwrap)",
        "how": (
            "Если формы уже совпадают — шаг можно пропустить "
            "(«Шаг тела — готово» сразу).\n"
            "\n"
            "Если нужен Shrinkwrap:\n"
            "• выдели РАБОЧЕЕ тело (Smutbase);\n"
            "• Modifiers → Shrinkwrap → Target = образец (HS2-карта);\n"
            "• когда ок — Apply, Ctrl+S;\n"
            "• образец HS2 спрячь или удали — в экспорт не попадает.\n"
            "\n"
            "Erisa тут не обязательна: резон был только если хочешь "
            "её пропорции вместо своей HS2-карты. Раз карта уже твоя — "
            "лекало = HS2-экспорт."
        ),
    },
    {
        "id": "rigify",
        "title": "4. Скелет Rigify",
        "how": (
            "Риг только на РАБОЧЕМ теле (Smutbase), не на HS2-образце.\n"
            "Rigify → привязка меша → Ctrl+S.\n"
            "Проверка: инструмент rig_check."
        ),
    },
    {
        "id": "export_fbx",
        "title": "5. Выгрузить FBX в Unity",
        "how": (
            "Перед экспортом в сцене не должно остаться меша HS2-образца "
            "(или сними с него экспорт).\n"
            "Инструмент blender_export_shanya → FBX в Assets/Characters/Shanya/.\n"
            "В игру уезжает только Smutbase+Rigify."
        ),
    },
    {
        "id": "unity_humanoid",
        "title": "6. Включить Humanoid в Unity",
        "how": (
            "В Unity: модель → Rig → Humanoid → Apply.\n"
            "Потом «Запустить тестовую сцену»."
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
