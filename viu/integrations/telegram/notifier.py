"""Фоновый Telegram-бот: шлёт вопросы/ошибки/медиа, принимает ответы Дена."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from ...config import Config
from ...inbox_layout import inbox_references_dir
from .client import TelegramClient, TelegramError, extract_photo_file_id
from . import settings


class TelegramNotifier:
    def __init__(
        self,
        config: Config,
        *,
        on_reply: Callable[[str], None],
        get_status: Callable[[], str],
    ) -> None:
        self.config = config
        self._on_reply = on_reply
        self._get_status = get_status
        self._token = settings.token(config)
        self._client: Optional[TelegramClient] = None
        if self._token:
            self._client = TelegramClient(self._token)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._offset = 0
        self._last_send_at = 0.0
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return settings.enabled(self.config) and self._client is not None

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="viu-telegram", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _poll_loop(self) -> None:
        assert self._client is not None
        while not self._stop.is_set():
            try:
                updates = self._client.get_updates(offset=self._offset, timeout=25)
            except TelegramError:
                time.sleep(5.0)
                continue
            except Exception:  # noqa: BLE001
                time.sleep(5.0)
                continue
            for upd in updates:
                uid = int(upd.get("update_id") or 0)
                if uid >= self._offset:
                    self._offset = uid + 1
                self._handle_update(upd)

    def _download_photo(self, file_id: str) -> Path:
        assert self._client is not None
        info = self._client.get_file(file_id)
        rel = str(info.get("file_path") or "").strip()
        if not rel:
            raise TelegramError("getFile вернул пустой file_path")
        ext = Path(rel).suffix.lower() or ".jpg"
        stamp = time.strftime("%Y%m%d_%H%M%S")
        short = file_id[-10:].replace("/", "_")
        dest = inbox_references_dir(self.config) / f"tg_{stamp}_{short}{ext}"
        return self._client.download_file(rel, dest)

    def _handle_update(self, upd: dict) -> None:
        # Inline-кнопки Comfy (промпт / LoRA).
        cb = upd.get("callback_query")
        if isinstance(cb, dict):
            self._handle_callback(cb)
            return

        msg = upd.get("message") or upd.get("edited_message")
        if not isinstance(msg, dict):
            return
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return
        chat_id = int(chat_id)
        text = (msg.get("text") or "").strip()
        caption = (msg.get("caption") or "").strip()
        file_id = extract_photo_file_id(msg)

        from_user = msg.get("from") or {}
        user_id = from_user.get("id")
        if user_id is not None:
            user_id = int(user_id)

        # Только Ден (VIU_TELEGRAM_OWNER_IDS / дефолт 103833998). Чужих молча игнор.
        if not settings.is_owner_sender(
            self.config, chat_id=chat_id, user_id=user_id
        ):
            return

        allowed = settings.chat_id(self.config)
        if allowed is None or allowed != chat_id:
            # Первый /start или любое сообщение владельца в личке — привязка.
            if chat_id > 0:
                settings.set_chat_id(self.config, chat_id)
                allowed = chat_id
                if text.startswith("/start"):
                    self._send_raw(
                        chat_id,
                        "Привет, Ден! Это Вью.\n"
                        f"Chat ID сохранён: {chat_id}\n"
                        "Пиши сюда — ответ попадёт в чат Вью на ПК.\n"
                        "Можно кидать фото-рефы с подписью.\n"
                        "Команды: /status\n"
                        "Чужие аккаунты бот игнорирует.",
                    )
                    return

        if allowed is None:
            return
        if chat_id != allowed:
            return

        if text.startswith("/status"):
            self._send_raw(chat_id, self._get_status())
            return
        if text.startswith("/start"):
            self._send_raw(
                chat_id,
                "Вью на связи. Пиши текст или кидай фото — продолжим.\n"
                "Для Comfy жми кнопки под сообщениями (Снимать / LoRA).",
            )
            return
        if text.startswith("/"):
            return

        if file_id:
            try:
                path = self._download_photo(file_id)
            except Exception as exc:  # noqa: BLE001
                self._send_raw(chat_id, f"Не скачала фото: {exc}")
                return
            payload = f"[tg_photo:{path}]"
            if caption:
                payload = f"{payload}\n{caption}"
            self._on_reply(payload)
            return

        if not text:
            return

        self._on_reply(text)

    def _handle_callback(self, cb: dict) -> None:
        assert self._client is not None
        cb_id = str(cb.get("id") or "")
        data = str(cb.get("data") or "").strip()
        from_user = cb.get("from") or {}
        user_id = from_user.get("id")
        if user_id is not None:
            user_id = int(user_id)
        msg = cb.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            try:
                self._client.answer_callback_query(cb_id, text="Нет chat_id")
            except TelegramError:
                pass
            return
        chat_id = int(chat_id)

        if not settings.is_owner_sender(
            self.config, chat_id=chat_id, user_id=user_id
        ):
            try:
                self._client.answer_callback_query(cb_id, text="Не для тебя", show_alert=True)
            except TelegramError:
                pass
            return

        allowed = settings.chat_id(self.config)
        if allowed is None and chat_id > 0:
            settings.set_chat_id(self.config, chat_id)
            allowed = chat_id
        if allowed is None or chat_id != allowed:
            try:
                self._client.answer_callback_query(cb_id, text="Чат не привязан")
            except TelegramError:
                pass
            return

        last_lora: list[int] = []
        try:
            from ...lab.comfy_pipeline import COMFY_TOPIC
            from ...lab.session import load_session

            sess = load_session(self.config, COMFY_TOPIC)
            if sess is not None:
                last_lora = [
                    int(x)
                    for x in (sess.meta.get("lora_last_pick") or [])
                    if str(x).isdigit()
                ]
        except Exception:  # noqa: BLE001
            last_lora = []

        from ..comfy.tg_buttons import callback_to_chat_text

        text = callback_to_chat_text(data, last_lora=last_lora or None)
        try:
            if text:
                self._client.answer_callback_query(cb_id, text="Ок…")
            else:
                self._client.answer_callback_query(cb_id, text="Не поняла кнопку")
        except TelegramError:
            pass
        if text:
            self._on_reply(text)

    def _send_raw(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: Optional[dict] = None,
    ) -> bool:
        if self._client is None:
            return False
        try:
            self._client.send_message(chat_id, text, reply_markup=reply_markup)
            return True
        except TelegramError:
            return False

    def _throttle(self, min_interval: float = 1.5) -> bool:
        with self._lock:
            now = time.monotonic()
            if now - self._last_send_at < min_interval:
                return False
            self._last_send_at = now
            return True

    def send(self, text: str, *, force: bool = False) -> bool:
        """Отправить сообщение в привязанный чат."""
        if not self.enabled:
            return False
        chat_id = settings.chat_id(self.config)
        if chat_id is None:
            return False
        if not force and not self._throttle():
            return False
        return self._send_raw(chat_id, text)

    def notify_question(self, question: str) -> bool:
        body = (
            "❓ Вопрос от Вью\n\n"
            f"{question.strip()}\n\n"
            "Ответь сюда — на ПК Вью продолжит с этого места."
        )
        return self.send(body, force=True)

    def notify_error(self, text: str) -> bool:
        if not settings.notify_errors(self.config):
            return False
        return self.send(f"⚠️ Ошибка\n\n{text.strip()}", force=True)

    def notify_done(self, text: str) -> bool:
        if not settings.notify_done(self.config):
            return False
        preview = text.strip()
        if len(preview) > 500:
            preview = preview[:497] + "…"
        return self.send(f"✅ Готово\n\n{preview}")

    def notify_chat(self, text: str) -> bool:
        return self.send(text.strip(), force=True)

    def notify_info(self, text: str) -> bool:
        return self.send(text)

    def notify_photo(self, photo_path: str | Path, *, caption: str = "") -> bool:
        if not self.enabled or self._client is None:
            return False
        chat_id = settings.chat_id(self.config)
        if chat_id is None:
            return False
        try:
            self._client.send_photo(chat_id, photo_path, caption=caption)
            return True
        except TelegramError:
            return False

    def notify_video(self, video_path: str | Path, *, caption: str = "") -> bool:
        if not self.enabled or self._client is None:
            return False
        chat_id = settings.chat_id(self.config)
        if chat_id is None:
            return False
        try:
            self._client.send_video(chat_id, video_path, caption=caption)
            return True
        except TelegramError:
            return False

    def test_connection(self) -> tuple[bool, str]:
        if not self.enabled:
            return False, "Задай VIU_TELEGRAM_TOKEN (и перезапусти Вью)."
        assert self._client is not None
        try:
            me = self._client.get_me()
        except TelegramError as exc:
            return False, f"Telegram API: {exc}"
        chat_id = settings.chat_id(self.config)
        if chat_id is None:
            owners = settings.owner_ids(self.config)
            hint = (
                f"Напиши боту /start со своего Telegram (id {next(iter(owners))})."
                if len(owners) == 1
                else "Напиши боту /start со своего Telegram (owner allowlist)."
            )
            return (
                True,
                f"Бот @{me.get('username', '?')} жив. {hint}",
            )
        ok = self._send_raw(
            chat_id,
            "Тест от Вью ✓\nЕсли видишь это — связь работает.",
        )
        if ok:
            return True, f"Сообщение отправлено (@{me.get('username', '?')})."
        return False, "Бот отвечает, но sendMessage не прошёл — проверь chat_id."
