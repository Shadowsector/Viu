"""Политика очереди Comfy перед lab-генерацией — не забивать GPU старыми jobs."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from .client import ComfyClient
    from ...config import Config


def comfy_timeout_each(config: Config | None = None) -> float:
    raw = (os.environ.get("VIU_COMFY_TIMEOUT_EACH") or "").strip()
    if not raw and config is not None:
        raw = str(getattr(config, "comfy_timeout_each", "") or "").strip()
    try:
        return max(300.0, min(7200.0, float(raw or "2400")))
    except ValueError:
        return 2400.0


def comfy_lab_autoclear_queue(config: Config | None = None) -> bool:
    raw = (os.environ.get("VIU_COMFY_LAB_CLEAR_QUEUE") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    if config is not None and hasattr(config, "comfy_lab_clear_queue"):
        return bool(getattr(config, "comfy_lab_clear_queue", True))
    return True


def comfy_max_pending_for_lab(config: Config | None = None) -> int:
    raw = (os.environ.get("VIU_COMFY_MAX_PENDING") or "").strip()
    if not raw and config is not None:
        raw = str(getattr(config, "comfy_max_pending", "") or "").strip()
    try:
        return max(0, min(50, int(raw or "0")))
    except ValueError:
        return 0


def prepare_queue_for_triple(
    config: Config,
    client: ComfyClient,
) -> Tuple[bool, str]:
    """Перед 3 дублями: пустая очередь или авто-сброс чужих jobs."""
    running, pending = client.queue_counts()
    if running == 0 and pending == 0:
        return True, ""

    if comfy_lab_autoclear_queue(config):
        ok, msg = client.reset_queue()
        if not ok:
            return False, (
                f"Не смогла очистить очередь Comfy (было running={running} pending={pending}): {msg}"
            )
        return True, (
            f"Очередь Comfy сброшена перед генерацией (было running={running} pending={pending})."
        )

    limit = comfy_max_pending_for_lab(config)
    if pending > limit:
        return False, (
            f"Очередь Comfy занята: running={running} pending={pending}. "
            f"Лимит pending={limit}. "
            "Дождись окончания, напиши comfy_queue_reset — авто-сброс перед lab уже включён."
        )
    return True, f"Очередь: running={running} pending={pending} — продолжаю."


def should_stop_triple_after_fail(message: str) -> bool:
    """Не ставить следующие дубли после таймаута — иначе pending растёт."""
    low = (message or "").lower()
    return (
        "таймаут" in low
        or "timeout" in low
        or "зависание" in low
        or "пропал из очереди" in low
        or "не отвечает во время job" in low
    )


def comfy_stall_sec(config: Config | None = None) -> float:
    raw = (os.environ.get("VIU_COMFY_STALL_SEC") or "").strip()
    if not raw and config is not None:
        raw = str(getattr(config, "comfy_stall_sec", "") or "").strip()
    try:
        return max(0.0, min(7200.0, float(raw or "0")))
    except ValueError:
        return 0.0


def comfy_auto_reset_on_hang(config: Config | None = None) -> bool:
    raw = (os.environ.get("VIU_COMFY_AUTO_RESET_ON_HANG") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    if config is not None and hasattr(config, "comfy_auto_reset_on_hang"):
        return bool(getattr(config, "comfy_auto_reset_on_hang", True))
    return True


def comfy_retry_on_hang(config: Config | None = None) -> int:
    raw = (os.environ.get("VIU_COMFY_RETRY_ON_HANG") or "").strip()
    if not raw and config is not None:
        raw = str(getattr(config, "comfy_retry_on_hang", "") or "").strip()
    try:
        return max(0, min(3, int(raw or "1")))
    except ValueError:
        return 1


def comfy_gone_grace_sec(config: Config | None = None) -> float:
    raw = (os.environ.get("VIU_COMFY_GONE_GRACE_SEC") or "").strip()
    if not raw and config is not None:
        raw = str(getattr(config, "comfy_gone_grace_sec", "") or "").strip()
    try:
        return max(5.0, min(120.0, float(raw or "25")))
    except ValueError:
        return 25.0


def wait_options_for_lab(config: Config) -> dict:
    """Параметры wait_history для lab-генерации."""
    return {
        "gone_grace": comfy_gone_grace_sec(config),
        "stall_sec": comfy_stall_sec(config),
        "auto_reset_on_hang": comfy_auto_reset_on_hang(config),
    }


def should_retry_after_hang(message: str) -> bool:
    low = (message or "").lower()
    return should_stop_triple_after_fail(message) or "авто-сброс" in low
