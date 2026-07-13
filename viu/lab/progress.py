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
        outcome = ""
        if session.capture_verdict and not session.viewport_ok:
            outcome = f" [PARTIAL — vision: {session.capture_verdict}]"
        elif session.viewport_ok:
            outcome = " [SUCCESS]"
        head = f"Lab «{session.topic}» — итерация завершена{outcome}, жду оценку"
    elif session.last_fail_step >= 0:
        n = session.last_fail_step + 1
        label = STEP_LABELS[session.last_fail_step]
        cnt = session.step_fail_counts.get(str(session.last_fail_step), 0)
        extra = f" ({cnt}×)" if cnt else ""
        head = f"Lab «{session.topic}» — ЗАСТРЯЛА шаг {n}/{total} «{label}»{extra}"
        if cnt >= 2:
            head += " → следующий клик = RECOVER"
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
