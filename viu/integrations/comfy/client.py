"""HTTP-клиент ComfyUI (локальный сервер, обычно :8188)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = str(uuid.uuid4())

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def _get(self, path: str) -> Any:
        req = urllib.request.Request(self._url(path), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ComfyError(f"ComfyUI недоступен ({self.base_url}): {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ComfyError(f"Не JSON от ComfyUI {path}: {exc}") from exc

    def _post(self, path: str, payload: dict) -> Any:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(path),
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                if not raw.strip():
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:800]
            raise ComfyError(f"ComfyUI HTTP {exc.code} {path}: {body}") from exc
        except urllib.error.URLError as exc:
            raise ComfyError(f"ComfyUI недоступен ({self.base_url}): {exc}") from exc

    def ping(self) -> Tuple[bool, str]:
        try:
            q = self._get("/queue")
            running = len(q.get("queue_running") or [])
            pending = len(q.get("queue_pending") or [])
            return True, f"ComfyUI OK {self.base_url} (running={running}, pending={pending})"
        except ComfyError as exc:
            return False, str(exc)

    def queue_prompt(self, workflow: dict) -> str:
        """Поставить workflow в очередь. Возвращает prompt_id."""
        payload = {"prompt": workflow, "client_id": self.client_id}
        result = self._post("/prompt", payload)
        if "error" in result:
            raise ComfyError(f"prompt error: {result.get('error')}")
        pid = result.get("prompt_id")
        if not pid:
            raise ComfyError(f"нет prompt_id в ответе: {result}")
        return str(pid)

    def get_history(self, prompt_id: str) -> Optional[dict]:
        hist = self._get(f"/history/{prompt_id}")
        if not isinstance(hist, dict):
            return None
        return hist.get(prompt_id)

    def get_queue(self) -> dict:
        """Текущая очередь Comfy (/queue)."""
        try:
            data = self._get("/queue")
            return data if isinstance(data, dict) else {}
        except ComfyError:
            return {}

    def queue_summary(self) -> str:
        q = self.get_queue()
        running = q.get("queue_running") or []
        pending = q.get("queue_pending") or []
        return f"running={len(running)} pending={len(pending)}"

    def interrupt(self, *, prompt_id: str | None = None) -> None:
        """Остановить текущий prompt (POST /interrupt)."""
        payload: dict = {}
        if prompt_id:
            payload["prompt_id"] = prompt_id
        self._post("/interrupt", payload)

    def clear_queue(self) -> None:
        """Очистить pending-очередь (POST /queue clear=true)."""
        self._post("/queue", {"clear": True})

    def free_memory(
        self,
        *,
        unload_models: bool = True,
        free_memory: bool = True,
    ) -> None:
        """Освободить VRAM на следующем idle-тике executor (POST /free)."""
        self._post(
            "/free",
            {
                "unload_models": bool(unload_models),
                "free_memory": bool(free_memory),
            },
        )

    def wait_history(
        self,
        prompt_id: str,
        *,
        timeout: float = 600.0,
        poll: float = 1.5,
    ) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            entry = self.get_history(prompt_id)
            if entry and entry.get("outputs") is not None:
                return entry
            time.sleep(poll)
        qs = self.queue_summary()
        raise ComfyError(
            f"Таймаут ожидания prompt_id={prompt_id} ({timeout:.0f}s). "
            f"Очередь Comfy: {qs}. "
            "Если running>0 — Wan ещё считает (увеличь timeout или смотри UI :8188). "
            "Если 0/0 — job упал (OOM/нода); открой ComfyUI и лог."
        )

    def download_view(
        self,
        filename: str,
        *,
        subfolder: str = "",
        folder_type: str = "output",
        dest: Path,
    ) -> Path:
        qs = f"filename={urllib.request.quote(filename)}"
        if subfolder:
            qs += f"&subfolder={urllib.request.quote(subfolder)}"
        qs += f"&type={urllib.request.quote(folder_type)}"
        url = self._url(f"/view?{qs}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                dest.write_bytes(resp.read())
        except urllib.error.URLError as exc:
            raise ComfyError(f"download /view failed: {exc}") from exc
        return dest

    def has_node_class(self, class_type: str) -> bool:
        """Проверить, зарегистрирована ли нода (ReActor и т.п.)."""
        try:
            info = self._get("/object_info")
        except ComfyError:
            return False
        if not isinstance(info, dict):
            return False
        return class_type in info

    def find_node_class(self, *needles: str) -> str | None:
        """Найти class_type по подстрокам (регистронезависимо)."""
        try:
            info = self._get("/object_info")
        except ComfyError:
            return None
        if not isinstance(info, dict):
            return None
        lows = [n.lower() for n in needles if n]
        for name in info:
            low = name.lower()
            if all(n in low for n in lows):
                return name
        return None

    def collect_output_files(self, history_entry: dict) -> List[Dict[str, str]]:
        """Список файлов из outputs (images / gifs / videos)."""
        files: List[Dict[str, str]] = []
        outputs = history_entry.get("outputs") or {}
        for _nid, node_out in outputs.items():
            if not isinstance(node_out, dict):
                continue
            for key in ("images", "gifs", "videos"):
                for item in node_out.get(key) or []:
                    if not isinstance(item, dict):
                        continue
                    fn = item.get("filename")
                    if not fn:
                        continue
                    files.append(
                        {
                            "filename": str(fn),
                            "subfolder": str(item.get("subfolder") or ""),
                            "type": str(item.get("type") or "output"),
                            "kind": key,
                        }
                    )
        return files
