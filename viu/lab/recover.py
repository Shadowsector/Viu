"""Lab застряла — диагностика вместо слепого повтора кнопки."""

from __future__ import annotations

from typing import Tuple

from ..config import Config
from ..integrations.cascadeur import cascadeur_status
from ..integrations.cascadeur.window import cascadeur_window_diagnostic, find_cascadeur_hwnd
from ..tools.web import search_web
from .session import LabSession, append_journal, save_session
from .cascadeur_pipeline import STEP_LABELS


def _fail_count(session: LabSession, step: int) -> int:
    return int(session.step_fail_counts.get(str(step), 0))


def should_recover_instead_of_retry(session: LabSession) -> bool:
    if session.last_fail_step < 0:
        return False
    return _fail_count(session, session.last_fail_step) >= 2


def recover_stuck_step(config: Config, session: LabSession) -> Tuple[bool, str]:
    """Диагностика + web + journal. Не повторяет тот же шаг вслепую."""
    step = session.last_fail_step
    if step < 0:
        return True, "Застревания нет — обычный шаг."

    label = STEP_LABELS[step] if step < len(STEP_LABELS) else f"шаг {step + 1}"
    session.recoveries += 1
    lines = [
        f"🔧 Lab RECOVER — шаг {step + 1} «{label}» (попытка #{session.recoveries})",
        f"Последняя ошибка: {session.last_fail_msg[:600]}",
        "",
    ]

    ok_st, st_text = cascadeur_status(config)
    lines.append("--- cascadeur_status ---")
    lines.append(st_text)
    lines.append("")
    lines.append("--- окна ---")
    lines.append(cascadeur_window_diagnostic())

    err = session.last_fail_msg or label
    if config.allow_network:
        try:
            hits = search_web(
                f"Cascadeur {err} capture window HWND lab pipeline",
                max_results=4,
            )
            if hits:
                lines.append("")
                lines.append("--- web ---")
                lines.extend(f"- {h[:300]}" for h in hits)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"web: {exc}")

    # Vision по последнему скрину lab, если есть
    arts = [a for a in session.artifacts if a.lower().endswith(".png")]
    if arts:
        from ..integrations.cascadeur.capture import analyze_cascadeur_shot

        last_png = arts[-1]
        from pathlib import Path

        v_ok, v_text, verdict = analyze_cascadeur_shot(config, Path(last_png))
        lines.append("")
        lines.append(f"--- vision ({last_png}) ---")
        if v_ok:
            lines.append(v_text)
            lines.append(f"verdict: {verdict}")
        else:
            lines.append(v_text)

    # Авто-откат: capture fail + cascadeur не запущен → шаг launch
    if step == 7 and not find_cascadeur_hwnd():
        session.step = 4
        session.launch_ok = False
        session.last_fail_step = -1
        lines.append("")
        lines.append("↩ Cascadeur не виден — откат к шагу 5 «Запуск Cascadeur».")
    elif _fail_count(session, step) >= 4:
        session.step = 0
        session.last_fail_step = -1
        session.step_fail_counts = {}
        session.launch_ok = False
        lines.append("")
        lines.append("↻ Слишком много повторов — **новая итерация с шага 1** (auto).")

    append_journal(config, session.topic, "### Recover\n\n" + "\n".join(lines))
    save_session(config, session)

    from .notify import notify_lab_stuck

    notify_lab_stuck(
        config,
        session,
        "\n".join(lines[:12]),
        step_label=f"RECOVER «{label}»",
    )

    tail = (
        "\n\nКнопка «Лаборатория» больше не повторяет слепо — это recover. "
        "Следующий run_all начнёт с текущего шага (или с 1 после auto-reset)."
    )
    return True, "\n".join(lines) + tail
