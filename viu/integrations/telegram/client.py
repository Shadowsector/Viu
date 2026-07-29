"""HTTP-клиент Telegram Bot API (stdlib, без pip-зависимостей)."""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


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

    @property
    def file_base(self) -> str:
        return f"https://api.telegram.org/file/bot{self._token}"

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

    def get_file(self, file_id: str) -> dict:
        result = self._call("getFile", {"file_id": str(file_id)})
        return result if isinstance(result, dict) else {}

    def download_file(self, file_path: str, dest: Union[str, Path]) -> Path:
        rel = str(file_path or "").lstrip("/")
        if not rel:
            raise TelegramError("empty file_path")
        url = f"{self.file_base}/{urllib.parse.quote(rel, safe='/')}"
        out = Path(dest)
        out.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=max(self._timeout, 120.0)) as resp:
                out.write_bytes(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(str(exc)) from exc
        return out

    def _multipart(
        self,
        method: str,
        fields: Dict[str, str],
        files: Dict[str, tuple[str, bytes, str]],
    ) -> dict:
        boundary = f"----ViuTG{int(time.time() * 1000)}"
        crlf = "\r\n"
        body = bytearray()
        for key, value in fields.items():
            body.extend(f"--{boundary}{crlf}".encode("utf-8"))
            body.extend(
                f'Content-Disposition: form-data; name="{key}"{crlf}{crlf}'.encode("utf-8")
            )
            body.extend(str(value).encode("utf-8"))
            body.extend(crlf.encode("utf-8"))
        for key, (filename, content, content_type) in files.items():
            body.extend(f"--{boundary}{crlf}".encode("utf-8"))
            body.extend(
                (
                    f'Content-Disposition: form-data; name="{key}"; '
                    f'filename="{filename}"{crlf}'
                ).encode("utf-8")
            )
            body.extend(f"Content-Type: {content_type}{crlf}{crlf}".encode("utf-8"))
            body.extend(content)
            body.extend(crlf.encode("utf-8"))
        body.extend(f"--{boundary}--{crlf}".encode("utf-8"))
        url = f"{self.api_base}/{method}"
        req = urllib.request.Request(
            url,
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=max(self._timeout, 120.0)) as resp:
                raw_body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(str(exc)) from exc
        if not raw_body.get("ok"):
            raise TelegramError(str(raw_body.get("description") or raw_body))
        result = raw_body.get("result")
        return result if isinstance(result, dict) else {}

    def send_photo(
        self,
        chat_id: int,
        photo_path: Union[str, Path],
        *,
        caption: str = "",
    ) -> dict:
        path = Path(photo_path)
        if not path.is_file():
            raise TelegramError(f"photo not found: {path}")
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        fields: Dict[str, str] = {"chat_id": str(int(chat_id))}
        cap = (caption or "").strip()
        if cap:
            fields["caption"] = cap[:1024]
        return self._multipart(
            "sendPhoto",
            fields,
            {"photo": (path.name, path.read_bytes(), mime)},
        )

    def send_video(
        self,
        chat_id: int,
        video_path: Union[str, Path],
        *,
        caption: str = "",
        supports_streaming: bool = True,
    ) -> dict:
        path = Path(video_path)
        if not path.is_file():
            raise TelegramError(f"video not found: {path}")
        mime = mimetypes.guess_type(path.name)[0] or "video/mp4"
        fields: Dict[str, str] = {
            "chat_id": str(int(chat_id)),
            "supports_streaming": "true" if supports_streaming else "false",
        }
        cap = (caption or "").strip()
        if cap:
            fields["caption"] = cap[:1024]
        return self._multipart(
            "sendVideo",
            fields,
            {"video": (path.name, path.read_bytes(), mime)},
        )


def extract_photo_file_id(message: dict) -> Optional[str]:
    """Largest photo file_id from a Telegram message, or None."""
    photos = message.get("photo")
    if not isinstance(photos, list) or not photos:
        return None
    best = max(photos, key=lambda p: int((p or {}).get("file_size") or 0))
    file_id = str(best.get("file_id") or "").strip()
    return file_id or None
