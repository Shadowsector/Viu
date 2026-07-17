"""Форматирование прогресса lab для чата/GUI."""

from __future__ import annotations

from .session import LabSession


def _step_labels(topic: str) -> list[str]:
    t = (topic or "").strip().lower()
    if t == "comfy":
        from .comfy_pipeline import STEP_LABELS as labels

        return list(labels)
    if t == "interaction":
        from .interaction_pipeline import STEP_LABELS as labels

        return list(labels)
    from .cascadeur_pipeline import STEP_LABELS as labels

    return list(labels)


def format_lab_progress(session: LabSession, msg: str, *, continued: bool = False) -> str:
    """Человекочитаемый заголовок: какой шаг выполнен / застрял."""
    total = session.steps_total
    labels = _step_labels(session.topic)
    prefix = ""
    if continued:
        prefix = "Продолжаю итерацию (не с нуля).\n"

    def label_at(idx: int) -> str:
        if 0 <= idx < len(labels):
            return labels[idx]
        return f"шаг {idx + 1}"

    if session.status == "awaiting_rating":
        outcome = ""
        if session.capture_verdict and not session.viewport_ok:
            outcome = f" [PARTIAL — vision: {session.capture_verdict}]"
        elif session.viewport_ok:
            outcome = " [SUCCESS]"
        head = f"Lab «{session.topic}» — итерация завершена{outcome}, жду оценку"
    elif session.status == "awaiting_prompt":
        head = f"Lab «{session.topic}» — жду одобрение промпта в Telegram"
    elif session.last_fail_step >= 0:
        n = session.last_fail_step + 1
        label = label_at(session.last_fail_step)
        cnt = session.step_fail_counts.get(str(session.last_fail_step), 0)
        extra = f" ({cnt}×)" if cnt else ""
        head = f"Lab «{session.topic}» — ЗАСТРЯЛА шаг {n}/{total} «{label}»{extra}"
        if cnt >= 2:
            head += " → следующий клик = RECOVER"
    elif session.step <= 0:
        n = 1
        label = label_at(0)
        head = f"Lab «{session.topic}» — шаг {n}/{total} «{label}»"
    elif session.step >= total:
        head = f"Lab «{session.topic}» — все {total} шагов выполнены"
    else:
        n = session.step
        label = label_at(min(n - 1, max(len(labels) - 1, 0)))
        head = f"Lab «{session.topic}» — шаг {n}/{total} «{label}» выполнен"

    return f"{prefix}{head}\n{msg}"
