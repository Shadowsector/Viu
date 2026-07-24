"""Уступить GPU ComfyUI, пока Ollama (reflect) думает."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...config import Config


def comfy_yield_on_chat_enabled() -> bool:
    """Пауза Comfy на время reflect-запроса (по умолчанию вкл.)."""
    raw = os.environ.get("VIU_COMFY_YIELD_ON_CHAT", "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return raw in ("1", "true", "yes", "on", "")


def comfy_yield_free_vram() -> bool:
    """После interrupt — POST /free (unload_models + free_memory)."""
    raw = os.environ.get("VIU_COMFY_YIELD_FREE_VRAM", "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return raw in ("1", "true", "yes", "on", "")


def comfy_yield_interrupt_running() -> bool:
    """Жёстко рвать текущий job Comfy при чате.

    По умолчанию выкл.: чат только ставит lab на паузу, не убивает Wan mid-render
    и не спамит Global interrupt в лог. Вкл.: VIU_COMFY_YIELD_INTERRUPT=1.
    """
    raw = os.environ.get("VIU_COMFY_YIELD_INTERRUPT", "0").strip().lower()
    if raw in ("0", "false", "no", "off", ""):
        return False
    return raw in ("1", "true", "yes", "on")


def _comfy_url(config: Config) -> str:
    return str(getattr(config, "comfy_url", None) or "http://127.0.0.1:8188")


def yield_comfy_for_llm(config: Config) -> str:
    """Уступить GPU под LLM. По умолчанию — soft (без interrupt)."""
    if not comfy_yield_on_chat_enabled():
        return ""
    from .client import ComfyClient, ComfyError

    client = ComfyClient(base_url=_comfy_url(config), timeout=8.0)
    parts: list[str] = []
    try:
        ok, _ping = client.ping()
        if not ok:
            return ""
        before = client.queue_summary()
        q = client.get_queue()
        running_n = len(q.get("queue_running") or [])
        pending_n = len(q.get("queue_pending") or [])

        # Пустая очередь — не дёргать /interrupt (иначе спам «Global interrupt»).
        if running_n == 0 and pending_n == 0:
            return ""

        # Soft: lab уже на паузе через lab_controller; GPU job не убиваем.
        if not comfy_yield_interrupt_running():
            return (
                f"comfy_yield: soft skip ({before}; "
                "чат не рвёт MoCap — VIU_COMFY_YIELD_INTERRUPT=1 чтобы убивать job)"
            )

        if running_n:
            client.interrupt()
            parts.append("interrupt")
        if pending_n:
            try:
                client.clear_queue()
                parts.append(f"clear_pending={pending_n}")
            except ComfyError:
                pass
        if parts and comfy_yield_free_vram():
            client.free_memory(unload_models=True, free_memory=True)
            parts.append("free_vram")
        if not parts:
            return ""
        after = client.queue_summary()
        return f"comfy_yield: {before} → {', '.join(parts)} → {after}"
    except ComfyError as exc:
        return f"comfy_yield_fail: {exc}"
