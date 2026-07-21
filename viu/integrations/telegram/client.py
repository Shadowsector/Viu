"""HTTP-клиент Telegram Bot API (stdlib, без pip-зависимостей)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, bot_token: str, *, timeout: float = 35.0) -> None:
        self._token = bot_token.strip()
        self._timeout = timeout
        if not self._token:
            raise ValueError("empty bot token")

    @property
    def api_base(self) -> str:
        return f"https://api.telegram.org/bot{self._token}"

    def _call(self, method: str, payload: Optional[Dict[str, Any]] = None) -> dict:
        url = f"{self.api_base}/{method}"
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(str(exc)) from exc
        if not body.get("ok"):
            raise TelegramError(str(body.get("description") or body))
        if "result" in body:
            return body["result"]
        return {}

    def get_me(self) -> dict:
        return self._call("getMe")

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        disable_preview: bool = True,
    ) -> dict:
        text = (text or "").strip()
        if not text:
            raise ValueError("empty message")
        if len(text) <= 4000:
            return self._call(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": disable_preview,
                },
            )
        chunk_size = 3800
        last: dict = {}
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            if i + chunk_size < len(text):
                chunk = chunk + "…"
            last = self._call(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": disable_preview,
                },
            )
        return last

    def get_updates(self, *, offset: int = 0, timeout: int = 25) -> List[dict]:
        payload: Dict[str, Any] = {"timeout": timeout}
        if offset:
            payload["offset"] = offset
        result = self._call("getUpdates", payload)
        return result if isinstance(result, list) else []
