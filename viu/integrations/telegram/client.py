"""HTTP-клиент Telegram Bot API (stdlib, без pip-зависимостей)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
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

    @staticmethod
    def _multipart_body(
        fields: Dict[str, str],
        files: Dict[str, tuple[str, bytes, str]],
    ) -> tuple[bytes, str]:
        boundary = f"----Viu{uuid.uuid4().hex}"
        chunks: list[bytes] = []
        for key, value in fields.items():
            if value is None:
                continue
            chunks.append(f"--{boundary}\r\n".encode())
            chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
            chunks.append(str(value).encode("utf-8"))
            chunks.append(b"\r\n")
        for key, (filename, data, content_type) in files.items():
            chunks.append(f"--{boundary}\r\n".encode())
            chunks.append(
                (
                    f'Content-Disposition: form-data; name="{key}"; '
                    f'filename="{filename}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode()
            )
            chunks.append(data)
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode())
        return b"".join(chunks), boundary

    def send_photo(
        self,
        chat_id: int,
        photo_path: Path,
        *,
        caption: str = "",
    ) -> dict:
        path = Path(photo_path)
        if not path.is_file():
            raise ValueError(f"photo not found: {path}")
        ext = path.suffix.lower()
        ctype = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        body, boundary = self._multipart_body(
            {"chat_id": str(chat_id), "caption": (caption or "")[:1024]},
            {"photo": (path.name, path.read_bytes(), ctype)},
        )
        req = urllib.request.Request(
            f"{self.api_base}/sendPhoto",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(str(exc)) from exc
        if not payload.get("ok"):
            raise TelegramError(str(payload.get("description") or payload))
        return payload.get("result") or {}

    def get_updates(self, *, offset: int = 0, timeout: int = 25) -> List[dict]:
        payload: Dict[str, Any] = {"timeout": timeout}
        if offset:
            payload["offset"] = offset
        result = self._call("getUpdates", payload)
        return result if isinstance(result, list) else []
