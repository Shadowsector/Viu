"""Клиент моста Blender (сторона Вью).

Общается с надстройкой, запущенной внутри Blender, по HTTP на localhost.
Использует только стандартную библиотеку.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class BlenderBridgeError(RuntimeError):
    """Ошибка обращения к мосту Blender (нет связи или ошибка команды)."""


class BlenderClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        timeout: float = 15.0,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def _post(self, command: str, params: Optional[Dict[str, Any]] = None) -> Any:
        payload = json.dumps({"command": command, "params": params or {}}).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise BlenderBridgeError(
                f"Нет связи с Blender на {self.url} — запущен ли Blender с надстройкой? ({exc})"
            ) from exc
        except (ValueError, OSError) as exc:
            raise BlenderBridgeError(f"Ошибка обмена с Blender: {exc}") from exc

        if not isinstance(body, dict) or "ok" not in body:
            raise BlenderBridgeError(f"Некорректный ответ моста: {body!r}")
        if not body.get("ok"):
            raise BlenderBridgeError(body.get("error", "неизвестная ошибка моста"))
        return body.get("data")

    def is_alive(self) -> bool:
        try:
            self._post("ping")
            return True
        except BlenderBridgeError:
            return False

    def scene_info(self) -> Any:
        return self._post("scene_info")

    def object_info(self, name: str) -> Any:
        return self._post("object_info", {"name": name})

    def list_shape_keys(self, obj: str) -> Any:
        return self._post("list_shape_keys", {"object": obj})

    def set_shape_key(self, obj: str, key: str, value: float) -> Any:
        return self._post("set_shape_key", {"object": obj, "key": key, "value": value})

    def run_operator(self, operator: str, args: Optional[Dict[str, Any]] = None) -> Any:
        return self._post("run_operator", {"operator": operator, "args": args or {}})

    def screenshot(self, path: Optional[str] = None) -> Any:
        return self._post("screenshot", {"path": path} if path else {})

    def rename_bones(self, armature: str, mapping: Dict[str, str]) -> Any:
        return self._post("rename_bones", {"armature": armature, "mapping": mapping})

    def list_sockets(self, prefix: Optional[str] = None) -> Any:
        return self._post("list_sockets", {"prefix": prefix} if prefix else {})

    def append_object(self, blend_file: str, obj: str) -> Any:
        return self._post("append_object", {"blend_file": blend_file, "object": obj})
