"""Telegram-уведомления лаборатории в автономном режиме."""

from __future__ import annotations

from ..config import Config
from ..presence import is_away


def _send(config: Config, text: str) -> bool:
    from ..integrations.telegram import settings
    from ..integrations.telegram.client import TelegramClient, TelegramError

    if not settings.enabled(config):
        return False
    token = settings.token(config)
    chat_id = settings.chat_id(config)
    if not token or chat_id is None:
        return False
    try:
        TelegramClient(token).send_message(chat_id, text.strip())
        return True
    except TelegramError:
        return False


def _quiet_invent_or_still(config: Config) -> bool:
    """Invent/still из чата — без пошагового спама в Telegram."""
    try:
        from .session import load_session
        from ..integrations.comfy.shoot_settings import mode_is_image, shoot_mode_from_meta

        sess = load_session(config, "comfy")
        meta = (sess.meta if sess else {}) or {}
        if meta.get("auto_invent_shoot"):
            return True
        if mode_is_image(shoot_mode_from_meta(meta)):
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


def notify_lab_step(config: Config, step_index: int, step_label: str, message: str) -> bool:
    """Краткий отчёт после шага lab (только если Ден away).

    Invent/still из чата — молчим: Дену картинка/одно сообщение, не «Lab — шаг N».
    """
    if not is_away(config):
        return False
    if _quiet_invent_or_still(config):
        return False
    preview = (message or "").strip()
    if len(preview) > 280:
        preview = preview[:277] + "…"
    body = f"🧪 Lab · {step_index}. {step_label}\n{preview}"
    return _send(config, body)


def notify_lab_awaiting_rating(config: Config, report_preview: str) -> bool:
    """Итог итерации — Ден может зайти удалённо и поставить оценку."""
    if not is_away(config):
        return False
    if _quiet_invent_or_still(config):
        # PNG уже ушёл в TG — без простыни MoCap.
        return False
    preview = (report_preview or "").strip()
    if len(preview) > 400:
        preview = preview[:397] + "…"
    body = (
        "🧪 Lab готова\n\n"
        f"{preview}\n\n"
        "На ПК — «Оценить лабораторию» (1–5) или /status."
    )
    return _send(config, body)


def notify_lab_stuck(config: Config, session, msg: str, *, step_label: str = "") -> bool:
    """Застряла на шаге — кратко в Telegram + очередь решений (только away)."""
    if not is_away(config):
        return False
    label = step_label or f"шаг {getattr(session, 'step', 0) + 1}"
    preview = (msg or "").strip()
    if len(preview) > 450:
        preview = preview[:447] + "…"
    body = (
        f"🧪 Lab — застряла: «{label}»\n\n"
        f"{preview}\n\n"
        "Решаю сама дальше не могу — посмотри journal или ответь в очереди вопросов."
    )
    sent = _send(config, body)
    try:
        from ..decision_queue import enqueue

        enqueue(
            config,
            f"Lab Cascadeur застряла на «{label}». Как поступить: повторить, пропустить шаг или остановить?",
            kind="pipeline",
            context=preview[:600],
        )
    except Exception:
        pass
    return sent
