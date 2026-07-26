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
# Канон 2026-07: рабочее тело = Tracer cutdown (Smutbase, Beerware).
# HS2-карта — опциональное лекало; Shrinkwrap можно пропустить.
BODY_STEPS: Tuple[Dict[str, str], ...] = (
    {
        "id": "stage_pack",
        "title": "1. Положить Tracer в Inbox",
        "how": (
            "Рабочее тело сейчас: **Tracer cutdown** со Smutbase (лицензия Beerware).\n"
            "Скины Classic / OW2 / … лежат отдельными .blend; в паке есть скрипт "
            "в сайдбаре Blender, который их подцепляет.\n"
            "\n"
            "1) Папка пака из U:\\Desktop Mascot\\Women (или свежий скачан) →\n"
            "   U:\\Anabarra\\Inbox\\creatures\\Tracer\\ "
            "(или asset_archive_stage … category=Women).\n"
            "2) Provenance уже знает пилот shanya_tracer_beerware "
            "(кнопка/чат: asset_provenance action=ensure_pilots).\n"
            "\n"
            "HS2-карту в Inbox класть НЕ обязательно — только если захочешь "
            "подогнать пропорции Shrinkwrap’ом (шаг 3)."
        ),
    },
    {
        "id": "open_blender",
        "title": "2. Открыть Tracer в Blender",
        "how": (
            "1) File → Open — главный .blend пака Tracer (cutdown).\n"
            "2) Если просят скрипт/сайдбар для скинов — включи add-on из пака "
            "по их README/видео; для Шани хватит одного скина (например Classic).\n"
            "3) Сохрани копию под Анабарру, например "
            "U:\\Anabarra\\Library\\Blender\\Shanya_Tracer.blend "
            "(чтобы не портить оригинал в хламнике).\n"
            "\n"
            "Автор просит кредит (Twitter/Bsky) — Beerware; для личной Анабарры ок."
        ),
    },
    {
        "id": "shrinkwrap",
        "title": "3. Форма (Shrinkwrap — по желанию)",
        "how": (
            "Большого резона нет, если пропорции Tracer уже устраивают — "
            "жми «Шаг тела — готово» и дальше к проверке рига.\n"
            "\n"
            "Если всё же хочешь фигуру как у своей HS2-карты:\n"
            "• импортируй экспорт карты как лекало;\n"
            "• Shrinkwrap на меше Tracer, Target = HS2;\n"
            "• Apply → HS2 убрать из сцены (в Unity не поедет).\n"
            "\n"
            "Erisa больше не нужна как основной пилот."
        ),
    },
    {
        "id": "rigify",
        "title": "4. Риг уже есть — проверить",
        "how": (
            "У Tracer риг уже в паке — **Rigify заново не ставим**.\n"
            "\n"
            "1) Убедись, что в сцене один нужный скин + арматура.\n"
            "2) Во Вью: инструмент rig_check (сверка с Humanoid).\n"
            "3) Если карта костей кривая — rig_map / правка имён, не новый Rigify.\n"
            "4) Ctrl+S.\n"
            "\n"
            "Ок → «Шаг тела — готово» → сразу экспорт FBX."
        ),
    },
    {
        "id": "export_fbx",
        "title": "5. Выгрузить FBX в Unity",
        "how": (
            "Экспорт уже зариганного Tracer (тело Шани) + нужный скин.\n"
            "Инструмент blender_export_shanya → Assets/Characters/Shanya/.\n"
            "Если экспорт ругается на WGT/виджеты — он их прячет сам; "
            "лишние скин-.blend пака в сцену не тащи."
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
        "Рабочее тело: Tracer cutdown (Beerware) со Smutbase.",
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
            "Сбросить чеклист на шаг: body_pipeline action=set step=rigify",
            "Подробнее: docs/NOW.md",
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


def reset_progress(config: Config, *, at_step: str = "stage_pack") -> Tuple[bool, str]:
    """Сбросить галочки (смена пилота тела — например на Tracer)."""
    if not any(s["id"] == at_step for s in BODY_STEPS):
        return False, "неизвестный step"
    state = BodyPipelineState(current_step=at_step, done_steps=[], notes="reset: tracer pilot")
    save_state(config, state)
    return True, f"чеклист сброшен → {at_step}"
