"""Строка активности Вью для GUI — что сейчас делает (LLM / Comfy / lab)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import Config


@dataclass(frozen=True)
class ActivityView:
    mode: str  # idle | llm | tool | comfy | wait
    line: str
    led_color: str
    led_dim: str
    blink: bool


def _clip(text: str, limit: int = 120) -> str:
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def _comfy_session_line(config: Config) -> Optional[ActivityView]:
    try:
        from .lab.comfy_pipeline import COMFY_TOPIC, STEP_LABELS
        from .lab.session import load_session
    except ImportError:
        return None

    session = load_session(config, COMFY_TOPIC)
    if session is None:
        return None

    status = (session.status or "").strip()
    if status in ("", "idle", "completed") and session.step <= 0:
        return None

    step_n = min(session.step, len(STEP_LABELS) - 1)
    step_label = STEP_LABELS[step_n] if step_n >= 0 else "—"
    slug = str(session.meta.get("catalog_slug") or "").strip()

    if status == "awaiting_prompt":
        return ActivityView(
            "wait",
            "Жду одобрение промпта (напиши «ок»)",
            "#ffd54f",
            "#f9a825",
            True,
        )
    if status == "awaiting_lora_pick":
        return ActivityView(
            "wait",
            "Жду выбор LoRA (lora: 1,2 / none)",
            "#ffd54f",
            "#f9a825",
            True,
        )
    if status == "awaiting_clip_pick":
        return ActivityView(
            "wait",
            "Жду выбор лучшего дубля Comfy",
            "#ffd54f",
            "#f9a825",
            True,
        )
    if status == "paused":
        why = _clip(session.pause_reason or session.last_fail_msg or "пауза", 80)
        return ActivityView(
            "comfy",
            f"Comfy lab на паузе: {why}",
            "#ef5350",
            "#c62828",
            False,
        )
    if status == "running":
        if session.step == 4:
            extra = f" · {slug}" if slug else ""
            return ActivityView(
                "comfy",
                f"Comfy: генерация 3 дубля (¾){extra}",
                "#ab47bc",
                "#6a1b9a",
                True,
            )
        return ActivityView(
            "comfy",
            f"Comfy lab: шаг {session.step + 1}/{session.steps_total} — {step_label}",
            "#ab47bc",
            "#6a1b9a",
            True,
        )
    if status in ("awaiting_rating",):
        return ActivityView(
            "wait",
            "Lab готова — жду оценку (Cascadeur)",
            "#ffd54f",
            "#f9a825",
            False,
        )
    if slug or status not in ("idle", ""):
        return ActivityView(
            "comfy",
            f"Comfy lab: {status} · {step_label}",
            "#ab47bc",
            "#6a1b9a",
            status == "running",
        )
    return None


def _comfy_queue_hint(config: Config) -> Optional[str]:
    try:
        from .integrations.comfy.client import ComfyClient
    except ImportError:
        return None
    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    client = ComfyClient(base_url=str(url), timeout=2.5)
    ok, _ = client.ping()
    if not ok:
        return "ComfyUI не отвечает на :8188"
    try:
        q = client.get_queue()
        running = len(q.get("queue_running") or [])
        pending = len(q.get("queue_pending") or [])
        if running or pending:
            return f"очередь Comfy: {running} в работе, {pending} ждут"
    except Exception:
        pass
    return None


def activity_view(
    config: Config,
    *,
    llm_busy: bool = False,
    tool_busy: bool = False,
    hint: str = "",
    work_mode: bool = False,
) -> ActivityView:
    """Короткая строка + режим LED для полоски над чатом."""
    hint = _clip(hint, 100)

    if llm_busy:
        if work_mode:
            line = "Работаю над задачей (инструменты)…"
        elif hint:
            line = f"Думаю: {hint}"
        else:
            line = "Думаю над твоим запросом…"
        return ActivityView("llm", line, "#ffb74d", "#f57c00", True)

    comfy = _comfy_session_line(config)
    if comfy is not None:
        if tool_busy and hint and comfy.mode != "wait":
            line = f"{comfy.line} · {_clip(hint, 60)}"
            return ActivityView(comfy.mode, line, comfy.led_color, comfy.led_dim, comfy.blink)
        return comfy

    if tool_busy:
        queue = _comfy_queue_hint(config)
        if queue:
            return ActivityView(
                "comfy",
                f"Comfy: {queue}",
                "#ab47bc",
                "#6a1b9a",
                True,
            )
        if hint:
            return ActivityView(
                "tool",
                _clip(hint, 120),
                "#42a5f5",
                "#1565c0",
                True,
            )
        return ActivityView(
            "tool",
            "Скрипт / lab — выполняю…",
            "#42a5f5",
            "#1565c0",
            True,
        )

    if hint:
        return ActivityView("idle", _clip(hint, 120), "#66bb6a", "#2e7d32", False)

    return ActivityView(
        "idle",
        "Готова · жду сообщение",
        "#66bb6a",
        "#2e7d32",
        False,
    )
