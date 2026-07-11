"""Глаза Вью: скрин окна + vision (Ollama VL) + handoff Cursor — без «Ден, посмотри»."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict

from ..escalate import escalate_failure
from ..integrations.github.api import upload_gist
from ..integrations.github.handoff import append_handoff, push_handoff
from ..integrations.vision_eye import (
    _DEFAULT_PROMPT,
    observe_window,
    pick_vision_model,
)
from ..integrations.screen.capture import list_windows
from .base import AgentContext, Tool, ToolResult


class ScreenCaptureTool(Tool):
    name = "screen_capture"
    description = (
        "Снять скрин окна Windows по подстроке заголовка "
        "(AnabarraOverlay, Unity, Anabarra). Без Дена."
    )
    parameters = {
        "title": "подстрока заголовка (по умолчанию AnabarraOverlay)",
        "prefix": "префикс имени файла",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.screen.capture import capture_window_png, default_shot_path

        title = str(args.get("title") or "AnabarraOverlay")
        prefix = str(args.get("prefix") or "eye")
        path = default_shot_path(ctx.config.data_dir, prefix=prefix)
        ok, msg = capture_window_png(path, title_substr=title)
        if not ok:
            # fallback: Unity Editor
            if title.lower() != "unity":
                ok2, msg2 = capture_window_png(path, title_substr="Unity")
                if ok2:
                    return ToolResult(True, msg2 + f"\n(искала {title}, взяла Unity)")
            wins = [t for _, t in list_windows()[:20]]
            return ToolResult(False, msg + f"\nОкна: {wins}")
        return ToolResult(True, msg)


class VisionObserveTool(Tool):
    name = "vision_observe"
    description = (
        "Глаза: скрин окна → Ollama VL (если есть) → вердикт. "
        "Скрин+отчёт в handoff Cursor. Дена не спрашивать «посмотри»."
    )
    parameters = {
        "title": "подстрока окна (AnabarraOverlay / Unity / Anabarra)",
        "prompt": "вопрос vision-модели (опционально)",
        "escalate_if_bad": "1 = при BROKEN/NO_* сразу escalate Cursor",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        title = str(args.get("title") or "AnabarraOverlay")
        prompt = str(args.get("prompt") or _DEFAULT_PROMPT)
        escalate_bad = str(args.get("escalate_if_bad", "1")).lower() not in (
            "0",
            "false",
            "no",
        )

        # Пробуем overlay, потом Unity
        result = observe_window(ctx.config, title_substr=title, prompt=prompt, prefix="eye")
        if not result["capture_ok"] and "unity" not in title.lower():
            result = observe_window(
                ctx.config, title_substr="Unity", prompt=prompt, prefix="eye_unity"
            )

        lines = [
            f"capture: {result['capture_msg']}",
            f"path: {result.get('path') or '—'}",
        ]
        vl = pick_vision_model(ctx.config.base_url)
        lines.append(f"vision model: {vl or 'нет (ollama pull llava)'}")

        if result.get("vision_ok"):
            lines.append("--- vision ---")
            lines.append(result["vision"])
        elif result.get("vision"):
            lines.append("--- vision ---")
            lines.append(result["vision"])

        # Gist со скрином (base64) для Cursor
        gist_msg = ""
        path = result.get("path") or ""
        if path and Path(path).is_file():
            from ..env_file import github_token

            token = github_token()
            b64 = base64.b64encode(Path(path).read_bytes()).decode("ascii")
            note = (
                f"Viu eyes screenshot\nwindow≈{title}\n"
                f"vision:\n{result.get('vision') or '(no VL)'}\n"
            )
            if token:
                g_ok, gist_msg = upload_gist(
                    Path(path).name + ".b64.txt",
                    note + "\n--- base64 png ---\n" + b64,
                    token=token,
                    description="Viu eyes screenshot",
                )
                lines.append(f"gist: {gist_msg}")
            else:
                lines.append("gist: нет VIU_GITHUB_TOKEN — скрин только локально")

            try:
                append_handoff(
                    "EYES observe",
                    "\n".join(lines)[:8000],
                    author="Viu",
                )
                push_handoff(message="Viu eyes observe")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"handoff: {exc}")

        text = "\n".join(lines)
        bad = _looks_bad(result.get("vision") or "")
        if escalate_bad and (bad or not result.get("capture_ok")):
            _, esc = escalate_failure(
                ctx,
                tool_name="vision_observe",
                error_text=text,
            )
            text += "\n\n--- escalate ---\n" + esc
            return ToolResult(False, text)

        ok = bool(result.get("capture_ok")) and not bad
        return ToolResult(ok, text)


def _looks_bad(vision_text: str) -> bool:
    low = vision_text.lower()
    for token in (
        "broken_idle",
        "no_home",
        "no_character",
        "no_overlay",
        "искажен",
        "корёж",
        "кореж",
        "сломан",
        "нет дома",
        "не виден",
        "t-pose",
        "t pose",
    ):
        if token in low:
            return True
    if "вердикт" in low and "ok" in low and "broken" not in low:
        return False
    return False
