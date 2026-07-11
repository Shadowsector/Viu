"""Пакет: управление окнами приложений Анабарры."""

from .process import (
    app_running,
    kill_app,
    kill_apps,
    restart_app,
    status_apps,
)

__all__ = [
    "app_running",
    "kill_app",
    "kill_apps",
    "restart_app",
    "status_apps",
]
