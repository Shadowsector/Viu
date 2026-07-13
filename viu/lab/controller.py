"""Прерывание lab при кнопках оператора и обновлении Вью."""

from __future__ import annotations

import threading

# Кнопки и инструменты lab не должны сами себя прерывать.
LAB_GUI_HOOKS = frozenset({"__lab_start__", "__lab_run_all__", "__lab_rate__"})
LAB_TOOL_NAMES = frozenset({"lab_start", "lab_step", "lab_status", "lab_rate", "lab_run_all"})
NO_LAB_INTERRUPT = LAB_GUI_HOOKS | frozenset({"__presence_toggle__"})


def action_interrupts_lab(tool: str | None) -> bool:
    """True — фоновая lab должна уступить (экспорт, оверлей, …)."""
    if not tool:
        return True
    if tool in NO_LAB_INTERRUPT or tool in LAB_TOOL_NAMES:
        return False
    return True


class LabController:
    """Кооперативная пауза: оператор (кнопки GUI) важнее фоновой лаборатории."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._paused = threading.Event()
        self._abort_step = threading.Event()

    def request_operator_priority(self, reason: str = "") -> None:
        with self._lock:
            self._paused.set()
            self._abort_step.set()
            self._pause_reason = reason

    def clear_operator_priority(self) -> None:
        with self._lock:
            self._paused.clear()
            self._abort_step.clear()
            self._pause_reason = ""

    @property
    def pause_reason(self) -> str:
        with self._lock:
            return getattr(self, "_pause_reason", "")

    def is_paused(self) -> bool:
        return self._paused.is_set()

    def should_abort_step(self) -> bool:
        return self._abort_step.is_set()

    def acknowledge_abort(self) -> None:
        self._abort_step.clear()


lab_controller = LabController()
