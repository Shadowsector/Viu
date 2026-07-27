"""Два состояния Вью: чат (reflect) и работа (work).

Это внутренняя кухня — Дену вслух не называем «reflect/work».
Снаружи: обычный разговор vs «сделай / следующий шаг».
"""

from __future__ import annotations

from enum import Enum

from .integrations.telegram.router import route_telegram_message


class Mode(str, Enum):
    """Единственные два режима мозга."""

    REFLECT = "reflect"  # простой разговор, JSON thought+final, без tools
    WORK = "work"  # инструменты, system.md, inbox/lab/unity…


def route_message(text: str, *, waiting_for_user: bool = False) -> Mode:
    """Единая точка выбора режима для GUI и Telegram."""
    raw = route_telegram_message(text, waiting_for_user=waiting_for_user)
    return Mode.WORK if raw == Mode.WORK.value else Mode.REFLECT


def is_reflect(mode: Mode | str) -> bool:
    return Mode(mode) == Mode.REFLECT


def is_work(mode: Mode | str) -> bool:
    return Mode(mode) == Mode.WORK


def mode_log_label(mode: Mode | str) -> str:
    """Короткая метка для логов (не для чата Дена)."""
    return "чат" if is_reflect(mode) else "работа"


# Канон для промптов / документации (не утекает в чат).
MODE_CONTRACT = """
REFLECT (простой разговор):
  - обычный чат, идеи, флирт, сцены, мнение о сюжете;
  - только JSON thought/final (или final_parts);
  - без инструментов; память — короткий digest, не весь VIU_MEMORY.md;
  - личность: system с REFLECT_VOICE (жизнь/характер); vision-мечта всегда в bare;
    Modelfile — jailbreak. VIU_REFLECT_NO_SYSTEM=1 — только отладка без system.

WORK (работа):
  - явные команды: «следующий шаг», «сделай…», handoff/GitHub, диагностика;
  - читает system.md, вызывает tools, пишет файлы;
  - без истории чата; модель work/code.
""".strip()
