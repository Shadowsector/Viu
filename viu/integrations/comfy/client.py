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

    @staticmethod
    def _prompt_ids_in_queue(queue: dict) -> dict[str, str]:
        """prompt_id → running | pending."""
        found: dict[str, str] = {}
        for key, label in (("queue_running", "running"), ("queue_pending", "pending")):
            for item in queue.get(key) or []:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                pid = str(item[1])
                if pid not in found:
                    found[pid] = label
        return found

    def prompt_queue_state(self, prompt_id: str) -> str:
        """running | pending | gone | done (outputs в history)."""
        entry = self.get_history(prompt_id)
        if entry and entry.get("outputs") is not None:
            return "done"
        states = self._prompt_ids_in_queue(self.get_queue())
        return states.get(prompt_id, "gone")

    def queue_summary(self) -> str:
        q = self.get_queue()
        running = q.get("queue_running") or []
        pending = q.get("queue_pending") or []
        return f"running={len(running)} pending={len(pending)}"

    def queue_counts(self) -> tuple[int, int]:
        q = self.get_queue()
        running = len(q.get("queue_running") or [])
        pending = len(q.get("queue_pending") or [])
        return running, pending

    def interrupt(self) -> Tuple[bool, str]:
        try:
            self._post("/interrupt", {})
            return True, "interrupt отправлен"
        except ComfyError as exc:
            return False, str(exc)

    def clear_queue(self) -> Tuple[bool, str]:
        try:
            self._post("/queue", {"clear": True})
            return True, "очередь очищена"
        except ComfyError as exc:
            return False, str(exc)

    def reset_queue(self) -> Tuple[bool, str]:
        """Прервать текущий job и очистить pending."""
        ok_i, msg_i = self.interrupt()
        ok_c, msg_c = self.clear_queue()
        if ok_i and ok_c:
            return True, f"{msg_i}; {msg_c}"
        return ok_c or ok_i, f"{msg_i}; {msg_c}"

    def wait_history(
        self,
        prompt_id: str,
        *,
        timeout: float = 600.0,
        poll: float = 1.5,
        gone_grace: float = 25.0,
        stall_sec: float = 0.0,
        ping_fail_limit: int = 3,
        auto_reset_on_hang: bool = False,
    ) -> dict:
        """Ждать outputs; при зависании — interrupt/reset (опционально)."""
        started = time.time()
        deadline = started + timeout
        seen_in_queue = False
        running_since: float | None = None
        ping_fails = 0
        last_state = ""

        def _hang_reset(reason: str) -> str:
            if not auto_reset_on_hang:
                return ""
            ok, msg = self.reset_queue()
            if ok:
                return f" Авто-сброс очереди: {msg}."
            return f" Авто-сброс не удался: {msg}."

        while time.time() < deadline:
            try:
                entry = self.get_history(prompt_id)
                ping_fails = 0
            except ComfyError as exc:
                ping_fails += 1
                if ping_fails >= ping_fail_limit:
                    tail = _hang_reset("api_down")
                    raise ComfyError(
                        f"ComfyUI не отвечает во время job {prompt_id} "
                        f"({ping_fails} подряд): {exc}.{tail}"
                    ) from exc
                time.sleep(poll)
                continue

            if entry and entry.get("outputs") is not None:
                return entry

            state = self.prompt_queue_state(prompt_id)
            if state in ("running", "pending"):
                seen_in_queue = True
                if state == "running":
                    if running_since is None:
                        running_since = time.time()
                    elif (
                        stall_sec > 0
                        and time.time() - running_since >= stall_sec
                    ):
                        tail = _hang_reset("stall")
                        raise ComfyError(
                            f"Зависание job {prompt_id}: running {stall_sec:.0f}s "
                            f"без outputs.{tail}"
                        )
                last_state = state
            elif state == "done":
                return entry or {}
            elif seen_in_queue and (time.time() - started) >= gone_grace:
                tail = _hang_reset("gone")
                raise ComfyError(
                    f"Job {prompt_id} пропал из очереди без outputs "
                    f"(OOM/краш ноды?).{tail}"
                )
            elif not seen_in_queue and (time.time() - started) >= gone_grace:
                tail = _hang_reset("never_started")
                raise ComfyError(
                    f"Job {prompt_id} не появился в очереди за {gone_grace:.0f}s.{tail}"
                )
            else:
                last_state = state

            time.sleep(poll)

        qs = self.queue_summary()
        tail = _hang_reset("timeout")
        raise ComfyError(
            f"Таймаут ожидания prompt_id={prompt_id} ({timeout:.0f}s). "
            f"Очередь Comfy: {qs}; state={last_state or 'unknown'}.{tail} "
            "Если running>0 — Wan ещё считает (увеличь VIU_COMFY_TIMEOUT_EACH). "
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
