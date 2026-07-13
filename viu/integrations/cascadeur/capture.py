"""Скрин Cascadeur + vision-проверка."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ...config import Config
from ..screen.capture import capture_window_png
from .launch import ensure_cascadeur_running
from .window import cascadeur_window_diagnostic, find_cascadeur_hwnd, focus_cascadeur_window

_CASCADEUR_VISION_PROMPT = (
    "Скрин окна Cascadeur (редактор 3D-анимации). Ответь кратко по-русски:\n"
    "1) Это welcome/start screen или 3D viewport?\n"
    "2) Видна модель/персонаж или пустая сцена?\n"
    "3) Есть диалог (Import, Rig mode)?\n"
    "4) Вердикт одной строкой: WELCOME | MODEL_OK | EMPTY_SCENE | DIALOG | UNKNOWN\n"
)


def _parse_verdict(vision_text: str) -> str:
    if not vision_text:
        return "UNKNOWN"
    for tag in ("MODEL_OK", "WELCOME", "EMPTY_SCENE", "DIALOG", "UNKNOWN"):
        if tag in vision_text.upper():
            return tag
    m = re.search(r"вердикт[^\n]*?:?\s*(\w+)", vision_text, re.I)
    if m:
        return m.group(1).upper()
    return "UNKNOWN"


def capture_cascadeur_png(
    config: Config,
    path: Path,
    *,
    monitor_index: int = 2,
    relaunch: bool = True,
) -> Tuple[bool, str, Optional[int]]:
    """Скрин окна Cascadeur по HWND (не по заголовку)."""
    focus_cascadeur_window()
    hwnd = find_cascadeur_hwnd()
    if not hwnd and relaunch:
        ensure_cascadeur_running(config, monitor_index=monitor_index)
        focus_cascadeur_window()
        hwnd = find_cascadeur_hwnd()
    if not hwnd:
        return False, "Окно Cascadeur не найдено.\n" + cascadeur_window_diagnostic(), None
    ok, msg = capture_window_png(path, hwnd=hwnd)
    return ok, msg, hwnd


def analyze_cascadeur_shot(config: Config, path: Path) -> Tuple[bool, str, str]:
    """Vision-анализ скрина. (ok, text, verdict_tag)."""
    from ..vision_eye import ask_vision, pick_vision_model

    if not path.is_file():
        return False, "Нет PNG для vision.", "UNKNOWN"
    if not pick_vision_model(config.base_url):
        return False, "Vision-модель не установлена (ollama pull llava).", "UNKNOWN"
    ok, text = ask_vision(path, prompt=_CASCADEUR_VISION_PROMPT, config=config)
    verdict = _parse_verdict(text if ok else "")
    return ok, text, verdict


def capture_and_verify_cascadeur(
    config: Config,
    path: Path,
    *,
    monitor_index: int = 2,
    require_model: bool = True,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Скрин + опционально vision. require_model: fail если WELCOME."""
    meta: Dict[str, Any] = {"verdict": "UNKNOWN", "vision_ok": False, "hwnd": None}
    ok, msg, hwnd = capture_cascadeur_png(config, path, monitor_index=monitor_index)
    meta["hwnd"] = hwnd
    if not ok:
        return False, msg, meta

    v_ok, v_text, verdict = analyze_cascadeur_shot(config, path)
    meta["vision_ok"] = v_ok
    meta["verdict"] = verdict
    meta["vision"] = v_text

    lines = [msg]
    if v_ok:
        lines.append("--- vision ---")
        lines.append(v_text)
        if require_model and verdict in ("WELCOME", "EMPTY_SCENE"):
            lines.append(
                f"\n⏸ Vision: {verdict} — модель не в viewport. "
                "Import FBX (File→Import или Viu.LabImport) и повтори."
            )
            return False, "\n".join(lines), meta
    else:
        lines.append(f"(vision: {v_text})")

    return True, "\n".join(lines), meta
