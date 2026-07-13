"""Форматирование прогресса lab для чата/GUI."""

from __future__ import annotations

from .cascadeur_pipeline import STEP_LABELS
from .session import LabSession


def format_lab_progress(session: LabSession, msg: str, *, continued: bool = False) -> str:
    """Человекочитаемый заголовок: какой шаг выполнен / застрял."""
    total = session.steps_total
    prefix = ""
    if continued:
        prefix = "Продолжаю итерацию (не с нуля).\n"

    if session.status == "awaiting_rating":
        head = f"Lab «{session.topic}» — итерация завершена, жду оценку"
    elif session.last_fail_step >= 0:
        n = session.last_fail_step + 1
        label = STEP_LABELS[session.last_fail_step]
        head = f"Lab «{session.topic}» — шаг {n}/{total} «{label}» — не пройден"
    elif session.step <= 0:
        n = 1
        label = STEP_LABELS[0]
        head = f"Lab «{session.topic}» — шаг {n}/{total} «{label}»"
    elif session.step >= total:
        head = f"Lab «{session.topic}» — все {total} шагов выполнены"
    else:
        n = session.step
        label = STEP_LABELS[min(n - 1, len(STEP_LABELS) - 1)]
        head = f"Lab «{session.topic}» — шаг {n}/{total} «{label}» выполнен"

    return f"{prefix}{head}\n{msg}"
