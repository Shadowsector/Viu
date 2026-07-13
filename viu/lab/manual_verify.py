"""Проверка ручного импорта в Cascadeur — скрин + vision без полного цикла."""

from __future__ import annotations

from ..config import Config
from .session import LabSession, append_journal, save_session

CAPTURE_STEP = 7  # 0-based: шаг 8 «Скрин UI»


def resume_for_manual_verify(config: Config, session: LabSession) -> LabSession:
    """После ручного File→Import: только скрин, vision, новый отчёт."""
    append_journal(
        config,
        session.topic,
        "### Ручной import\n\n"
        "Ден импортировал модель вручную (не Commands) — lab проверяет viewport.",
    )
    session.status = "running"
    session.step = CAPTURE_STEP
    session.launch_ok = True
    session.import_deployed = True
    session.import_ok = False
    session.viewport_ok = False
    session.capture_verdict = ""
    session.last_fail_step = -1
    session.step_fail_counts = {}
    save_session(config, session)
    return session
