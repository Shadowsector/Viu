"""Lab застряла — диагностика вместо слепого повтора кнопки."""

from __future__ import annotations

from typing import Tuple

from ..config import Config
from ..integrations.cascadeur import cascadeur_status
from ..integrations.cascadeur.window import cascadeur_window_diagnostic, find_cascadeur_hwnd
from ..tools.web import search_web
from .session import LabSession, append_journal, save_session


def _fail_count(session: LabSession, step: int) -> int:
    return int(session.step_fail_counts.get(str(step), 0))


def should_recover_instead_of_retry(session: LabSession) -> bool:
    if session.last_fail_step < 0:
        return False
    return _fail_count(session, session.last_fail_step) >= 2


def recover_stuck_step(config: Config, session: LabSession) -> Tuple[bool, str]:
    """Диагностика. Не повторяет тот же шаг вслепую."""
    if session.topic == "comfy":
        return _recover_comfy(config, session)
    return _recover_cascadeur(config, session)


def _recover_comfy(config: Config, session: LabSession) -> Tuple[bool, str]:
    from ..integrations.comfy.client import ComfyClient
    from ..integrations.comfy.process import ensure_comfy_running
    from .comfy_pipeline import STEP_LABELS as COMFY_LABELS

    step = session.last_fail_step
    if step < 0:
        step = session.step
    label = COMFY_LABELS[step] if 0 <= step < len(COMFY_LABELS) else f"шаг {step + 1}"
    session.recoveries += 1
    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    lines = [
        f"🔧 Lab Comfy RECOVER — шаг {step + 1} «{label}» (#{session.recoveries})",
        f"Последняя ошибка: {(session.last_fail_msg or '')[:600]}",
        "",
    ]

    client = ComfyClient(base_url=str(url), timeout=3.0)
    ok_ping, ping_msg = client.ping()
    lines.append(f"--- ping {url} ---")
    lines.append(ping_msg)

    if not ok_ping:
        lines.append("")
        lines.append("Пробую поднять ComfyUI (ensure_comfy_running)…")
        ok_run, run_msg = ensure_comfy_running(
            config, auto_install=False, wait_seconds=120.0
        )
        lines.append(run_msg[:1200])
        if ok_run:
            session.last_fail_step = -1
            session.step_fail_counts = {}
            session.status = "running"
            # генерация — шаг 4; online — 0
            if step >= 4:
                session.step = 4
            else:
                session.step = 0
            lines.append("")
            lines.append("↩ Comfy снова на связи — следующий Lab-клик продолжит генерацию.")
            append_journal(config, session.topic, "### Recover Comfy\n\n" + "\n".join(lines))
            save_session(config, session)
            return True, "\n".join(lines)

        session.status = "paused"
        session.pause_reason = "comfy_offline"
        session.last_fail_step = step
        lines.append("")
        lines.append(
            "⏸ ComfyUI не отвечает на :8188.\n"
            "Запусти Comfy вручную (ярлык / U:\\Viu\\ComfyUI) или `comfy_ensure`,\n"
            "потом снова «Lab: весь цикл». Пока offline — lab на паузе, без слепых повторов."
        )
        append_journal(config, session.topic, "### Recover Comfy\n\n" + "\n".join(lines))
        save_session(config, session)
        from .notify import notify_lab_stuck

        notify_lab_stuck(config, session, "\n".join(lines[:14]), step_label=f"RECOVER «{label}»")
        return False, "\n".join(lines)

    # API жив — сброс очереди и счётчика, повтор генерации
    reset_ok, reset_msg = client.reset_queue()
    lines.append("")
    lines.append("--- сброс очереди Comfy ---")
    lines.append(reset_msg if reset_ok else f"не удалось: {reset_msg}")

    if _fail_count(session, step) >= 6:
        session.step = 0
        session.last_fail_step = -1
        session.step_fail_counts = {}
        session.status = "running"
        lines.append("↻ Много провалов — откат к шагу 1 «Comfy online».")
    else:
        session.step = 4 if step >= 4 else step
        session.last_fail_step = -1
        session.step_fail_counts = {}
        session.status = "running"
        lines.append("↩ API жив — сбросила счётчик; следующий клик = снова «3 дубля».")

    append_journal(config, session.topic, "### Recover Comfy\n\n" + "\n".join(lines))
    save_session(config, session)
    return True, "\n".join(lines)


def _recover_cascadeur(config: Config, session: LabSession) -> Tuple[bool, str]:
    from .cascadeur_pipeline import STEP_LABELS

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

    arts = [a for a in session.artifacts if a.lower().endswith(".png")]
    if arts:
        from pathlib import Path

        from ..integrations.cascadeur.capture import analyze_cascadeur_shot

        last_png = arts[-1]
        v_ok, v_text, verdict = analyze_cascadeur_shot(config, Path(last_png))
        lines.append("")
        lines.append(f"--- vision ({last_png}) ---")
        if v_ok:
            lines.append(v_text)
            lines.append(f"verdict: {verdict}")
        else:
            lines.append(v_text)

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
