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


def _comfy_url(config: Config) -> str:
    return str(getattr(config, "comfy_url", None) or "http://127.0.0.1:8188")


def yield_comfy_for_llm(config: Config) -> str:
    """Interrupt + опционально free VRAM. ComfyUI процесс остаётся живым."""
    if not comfy_yield_on_chat_enabled():
        return ""
    from .client import ComfyClient, ComfyError

    client = ComfyClient(base_url=_comfy_url(config), timeout=8.0)
    parts: list[str] = []
    try:
        ok, ping = client.ping()
        if not ok:
            return ""
        before = client.queue_summary()
        client.interrupt()
        parts.append("interrupt")
        if comfy_yield_free_vram():
            client.free_memory(unload_models=True, free_memory=True)
            parts.append("free_vram")
        after = client.queue_summary()
        return f"comfy_yield: {before} → {', '.join(parts)} → {after}"
    except ComfyError as exc:
        return f"comfy_yield_fail: {exc}"
