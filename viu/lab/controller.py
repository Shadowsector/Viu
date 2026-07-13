"""Прерывание lab при кнопках оператора и обновлении Вью."""

from __future__ import annotations

import threading


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
