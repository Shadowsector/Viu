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
    """Разбор ответа VL-модели (llava часто пишет «Start Screen», не WELCOME)."""
    if not vision_text:
        return "UNKNOWN"
    upper = vision_text.upper()
    # Явные теги из промпта (если модель их вывела)
    for tag in ("MODEL_OK", "WELCOME", "EMPTY_SCENE", "DIALOG", "UNKNOWN"):
        if tag in upper:
            return tag

    low = vision_text.lower()
    model_hints = (
        "model_ok",
        "модель видна",
        "персонаж вид",
        "видна модель",
        "character visible",
        "3d viewport",
        "viewport с модель",
    )
    if any(h in low for h in model_hints):
        return "MODEL_OK"

    dialog_hints = ("import", "rig mode", "rig mode helper", "диалог")
    if sum(1 for h in dialog_hints if h in low) >= 2 or (
        "import" in low and ("rig" in low or "диалог" in low)
    ):
        return "DIALOG"

    welcome_hints = (
        "start screen",
        "welcome",
        "стартов",
        "welcome screen",
        "start screen или",
        "это start",
    )
    if any(h in low for h in welcome_hints):
        return "WELCOME"

    empty_hints = ("пустая сцена", "empty scene", "нет модел", "нет персонаж", "no model", "no character")
    if any(h in low for h in empty_hints):
        return "EMPTY_SCENE"

    m = re.search(r"вердикт[^\n]*?:?\s*(\w+)", vision_text, re.I)
    if m:
        return m.group(1).upper()
    return "UNKNOWN"


_NOT_OK_VERDICTS = frozenset({"WELCOME", "EMPTY_SCENE", "DIALOG"})


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
        lines.append(f"verdict: {verdict}")
        if require_model and (verdict in _NOT_OK_VERDICTS or verdict == "UNKNOWN"):
            hint = {
                "WELCOME": "стартовый экран Cascadeur",
                "EMPTY_SCENE": "пустой viewport",
                "DIALOG": "открыт диалог Import/Rig — импорт не завершён",
                "UNKNOWN": "vision не уверена — модель не подтверждена",
            }.get(verdict, verdict)
            lines.append(
                f"\n⏸ Vision: {verdict} ({hint}). "
                "Нужен viewport с моделью: New scene → File→Import (Scene) "
                "или Commands → Viu → LabImport."
            )
            return False, "\n".join(lines), meta
    else:
        lines.append(f"(vision: {v_text})")
        if require_model:
            lines.append(
                "\n⏸ Vision недоступна — модель в viewport не подтверждена "
                "(ollama pull llava)."
            )
            return False, "\n".join(lines), meta

    return True, "\n".join(lines), meta
