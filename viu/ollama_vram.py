"""Лимит VRAM для Ollama (OLLAMA_MAX_VRAM)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .config import Config

_DEFAULT_GB = 10.0


def ollama_vram_gb(*, runtime_gb: Optional[str] = None) -> float:
    """Гигабайты из VIU_LAB_VRAM_GB / runtime.json / дефолт 10."""
    raw = (
        os.environ.get("VIU_LAB_VRAM_GB")
        or (str(runtime_gb).strip() if runtime_gb is not None else "")
        or "10"
    ).strip() or "10"
    try:
        return max(1.0, float(raw))
    except (TypeError, ValueError):
        return _DEFAULT_GB


def apply_ollama_vram_limit(config: Optional[Config] = None) -> float:
    """Выставить OLLAMA_MAX_VRAM для процесса (и подсказка при перезапуске Ollama)."""
    runtime_gb = None
    if config is not None:
        try:
            from .runtime_settings import get

            val = get(config, "lab_vram_gb", None)
            if val is not None:
                runtime_gb = str(val)
        except Exception:
            pass
    gb = ollama_vram_gb(runtime_gb=runtime_gb)
    os.environ["OLLAMA_MAX_VRAM"] = str(int(gb * 1024 * 1024 * 1024))
    return gb
