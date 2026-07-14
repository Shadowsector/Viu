"""Отложенные напоминания Дена (после N сообщений пользователя)."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Config

_LOCK = threading.Lock()


def _path(config: Config) -> Path:
    return config.data_dir / "reminders.json"


def _read(config: Config) -> Dict[str, Any]:
    path = _path(config)
    if not path.is_file():
        return {"version": 1, "user_messages": 0, "items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "user_messages": 0, "items": []}
    if not isinstance(data, dict):
        return {"version": 1, "user_messages": 0, "items": []}
    data.setdefault("user_messages", 0)
    data.setdefault("items", [])
    return data


def _write(config: Config, data: Dict[str, Any]) -> None:
    config.ensure_dirs()
    path = _path(config)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def schedule(
    config: Config,
    text: str,
    *,
    after_user_messages: int = 10,
    tag: str = "",
) -> Tuple[bool, str]:
    """Напомнить после N следующих сообщений пользователя в чате."""
    text = (text or "").strip()
    if not text:
        return False, "Пустой текст напоминания."
    n = max(1, int(after_user_messages))
    with _LOCK:
        data = _read(config)
        base = int(data.get("user_messages") or 0)
        item = {
            "id": uuid.uuid4().hex[:10],
            "text": text[:2000],
            "tag": (tag or "").strip()[:64],
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "trigger_at_user_messages": base + n,
            "after_n": n,
            "status": "pending",
        }
        # Не дублировать тот же tag pending
        if item["tag"]:
            for old in data.get("items") or []:
                if old.get("status") == "pending" and old.get("tag") == item["tag"]:
                    old["text"] = item["text"]
                    old["trigger_at_user_messages"] = item["trigger_at_user_messages"]
                    old["after_n"] = n
                    _write(config, data)
                    return True, (
                        f"Обновила напоминание «{item['tag']}»: "
                        f"через ~{n} твоих сообщений в чате."
                    )
        data.setdefault("items", []).append(item)
        _write(config, data)
    return True, f"Напомню через ~{n} твоих сообщений в чате (#{item['id']})."


def on_user_message(config: Config) -> List[str]:
    """Вызывать на каждое сообщение Дена. Возвращает тексты сработавших напоминаний."""
    fired: List[str] = []
    with _LOCK:
        data = _read(config)
        data["user_messages"] = int(data.get("user_messages") or 0) + 1
        cur = data["user_messages"]
        for it in data.get("items") or []:
            if it.get("status") != "pending":
                continue
            if cur >= int(it.get("trigger_at_user_messages") or 0):
                it["status"] = "fired"
                it["fired_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                fired.append(str(it.get("text") or "").strip())
        _write(config, data)
    return [t for t in fired if t]


def list_pending(config: Config) -> List[Dict[str, Any]]:
    with _LOCK:
        data = _read(config)
    return [i for i in (data.get("items") or []) if i.get("status") == "pending"]
