"""Очередь осмысленных вопросов к Дену (когда его нет дома)."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Config

_LOCK = threading.Lock()

# Слишком мелкие / операторские — не копить.
_TRIVIAL = re.compile(
    r"(?i)^(ок|да|нет|продолжай|нажми|закрой|открой|перезапусти|"
    r"где кнопка|какой путь к unity\.exe\??)$"
)


def _path(config: Config) -> Path:
    return config.data_dir / "decision_queue.json"


def _read(config: Config) -> Dict[str, Any]:
    path = _path(config)
    if not path.is_file():
        return {"version": 1, "items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "items": []}
    if not isinstance(data, dict):
        return {"version": 1, "items": []}
    data.setdefault("items", [])
    return data


def _write(config: Config, data: Dict[str, Any]) -> None:
    config.ensure_dirs()
    path = _path(config)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _qid(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:12]


def is_meaningful(question: str, *, kind: str = "") -> bool:
    q = (question or "").strip()
    if len(q) < 20:
        return False
    if _TRIVIAL.match(q):
        return False
    # Операционные «нажми Play» — не вектор.
    low = q.lower()
    if any(x in low for x in ("нажми", "кликни", "пришли лог", "пришли скрин")):
        return False
    if kind in ("pipeline", "vision", "design", "scope", "story"):
        return True
    # Эвристика: выбор / вектор / пайплайн.
    markers = (
        "или",
        "выбер",
        "как лучше",
        "направление",
        "пайплайн",
        "pipeline",
        "приоритет",
        "сначала",
        "каскадёр",
        "cascadeur",
        "оверлей",
        "дом",
        "анимац",
        "nsfw",
        "бюджет",
        "деньг",
    )
    return any(m in low for m in markers) or "?" in q


def enqueue(
    config: Config,
    question: str,
    *,
    kind: str = "decision",
    context: str = "",
) -> Tuple[bool, str]:
    """Добавить вопрос. False = отклонён как несмысленный / дубликат."""
    q = (question or "").strip()
    if not q:
        return False, "Пустой вопрос."
    if not is_meaningful(q, kind=kind):
        return False, (
            "Вопрос слишком мелкий для очереди (операционка). "
            "В режиме «меня нет» такие не копятся — решай сама или пропусти."
        )

    item = {
        "id": _qid(q),
        "question": q,
        "kind": (kind or "decision").strip() or "decision",
        "context": (context or "").strip()[:800],
        "status": "open",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with _LOCK:
        data = _read(config)
        items: List[Dict[str, Any]] = list(data.get("items") or [])
        for old in items:
            if old.get("id") == item["id"] and old.get("status") == "open":
                return True, f"Уже в очереди (#{item['id']}): {q[:120]}"
        items.append(item)
        data["items"] = items
        _write(config, data)
    return True, f"В очередь решений #{item['id']} ({item['kind']}): {q}"


def list_open(config: Config) -> List[Dict[str, Any]]:
    with _LOCK:
        data = _read(config)
    return [i for i in (data.get("items") or []) if i.get("status") == "open"]


def count_open(config: Config) -> int:
    return len(list_open(config))


def render_open(config: Config) -> str:
    items = list_open(config)
    if not items:
        return "Очередь решений пуста."
    lines = [f"Открытых вопросов: {len(items)}"]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. [{it.get('kind')}] #{it.get('id')}")
        lines.append(f"   {it.get('question')}")
        if it.get("context"):
            lines.append(f"   контекст: {it['context'][:200]}")
    return "\n".join(lines)


def answer(config: Config, item_id: str, reply: str) -> Tuple[bool, str]:
    reply = (reply or "").strip()
    with _LOCK:
        data = _read(config)
        for it in data.get("items") or []:
            if it.get("id") == item_id and it.get("status") == "open":
                it["status"] = "answered"
                it["answer"] = reply[:2000]
                it["answered_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                _write(config, data)
                return True, f"Записала ответ на #{item_id}."
    return False, f"Открытый вопрос #{item_id} не найден."


def dismiss(config: Config, item_id: str) -> Tuple[bool, str]:
    with _LOCK:
        data = _read(config)
        for it in data.get("items") or []:
            if it.get("id") == item_id and it.get("status") == "open":
                it["status"] = "dismissed"
                it["answered_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                _write(config, data)
                return True, f"Сняла #{item_id} с очереди."
    return False, f"#{item_id} не найден."


def flush_prompt_for_home(config: Config) -> Optional[str]:
    """Текст для чата, когда Ден вернулся домой."""
    items = list_open(config)
    if not items:
        return None
    return (
        f"Ден дома. В очереди {len(items)} осмысленных вопрос(ов) — "
        f"см. «Очередь вопросов» или decision_queue_show.\n"
        + render_open(config)
    )
