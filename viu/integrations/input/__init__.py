"""Эмуляция ввода (мышь, позже клавиатура) для UI лаборатории."""

from .mouse import (
    click_screen,
    focus_window_center,
    lab_mouse_allowed,
    lab_mouse_away_only,
    lab_mouse_enabled,
)

__all__ = [
    "click_screen",
    "focus_window_center",
    "lab_mouse_allowed",
    "lab_mouse_away_only",
    "lab_mouse_enabled",
]
