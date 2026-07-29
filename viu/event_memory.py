"""Память событий — не логи чата, а короткие биты приключений.

Переживает перезапуск (.viu/event_memory.json). Вью вплетает в разговор,
может гибридизировать старые события в новые. Полные chat_*.txt сюда не кладём.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Sequence

from .config import Config

_EVENT_PATH = "event_memory.json"
_MAX_EVENTS = 400


@dataclass
class StoryEvent:
    id: str
    title: str
    what: str
    where: str = ""
    who: str = ""
    senses: str = ""  # поза / визуал / ощущения
    tags: List[str] = field(default_factory=list)
    hybrid_of: List[str] = field(default_factory=list)  # id родителей
    ts: float = field(default_factory=time.time)
    source: str = "chat"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "StoryEvent":
        return StoryEvent(
            id=str(d.get("id") or uuid.uuid4().hex[:10]),
            title=str(d.get("title") or "").strip() or "событие",
            what=str(d.get("what") or d.get("text") or "").strip(),
            where=str(d.get("where") or "").strip(),
            who=str(d.get("who") or "").strip(),
            senses=str(d.get("senses") or "").strip(),
            tags=[str(t) for t in (d.get("tags") or []) if str(t).strip()],
            hybrid_of=[str(x) for x in (d.get("hybrid_of") or []) if str(x).strip()],
            ts=float(d.get("ts") or time.time()),
            source=str(d.get("source") or "chat"),
        )


def event_memory_path(config: Config) -> Path:
    return Path(config.data_dir) / _EVENT_PATH


class EventMemory:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._events: List[StoryEvent] = []
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            self._events = []
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items = raw.get("events") if isinstance(raw, dict) else raw
            self._events = [StoryEvent.from_dict(x) for x in (items or [])]
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            self._events = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "comment": "События приключений Вью/Дена — для reflect, не логи чата",
            "events": [e.to_dict() for e in self._events[-_MAX_EVENTS:]],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def all(self) -> List[StoryEvent]:
        return list(self._events)

    def recent(self, limit: int = 12) -> List[StoryEvent]:
        return list(self._events[-limit:])

    def add(
        self,
        *,
        title: str,
        what: str,
        where: str = "",
        who: str = "",
        senses: str = "",
        tags: Optional[Sequence[str]] = None,
        hybrid_of: Optional[Sequence[str]] = None,
        source: str = "chat",
    ) -> Optional[StoryEvent]:
        what_c = (what or "").strip()
        if len(what_c) < 12:
            return None
        title_c = (title or "").strip() or what_c[:48]
        # не дублировать почти то же
        if self._events:
            last = self._events[-1]
            if last.what[:120] == what_c[:120]:
                return last
        ev = StoryEvent(
            id=uuid.uuid4().hex[:10],
            title=title_c[:80],
            what=what_c[:800],
            where=(where or "").strip()[:120],
            who=(who or "").strip()[:120],
            senses=(senses or "").strip()[:280],
            tags=[str(t) for t in (tags or []) if str(t).strip()][:12],
            hybrid_of=[str(x) for x in (hybrid_of or []) if str(x).strip()][:6],
            source=source,
        )
        self._events.append(ev)
        self._save()
        return ev

    def format_digest(self, *, limit: int = 10, max_chars: int = 1600) -> str:
        recent = self.recent(limit)
        if not recent:
            return ""
        lines = [
            "--- События (помни и вплетай; можно гибридизировать в новое) ---",
        ]
        for ev in recent:
            bit = f"• [{ev.id}] {ev.title}: {ev.what}"
            if ev.where:
                bit += f" ({ev.where})"
            if ev.senses:
                bit += f" | ощущения/поза: {ev.senses}"
            if ev.hybrid_of:
                bit += f" | из {','.join(ev.hybrid_of)}"
            lines.append(bit[:320])
        if len(recent) >= 2:
            a, b = recent[-2], recent[-1]
            lines.append(
                f"Можно смешать воспоминания «{a.title}» и «{b.title}» во что-то новое."
            )
        text = "\n".join(lines)
        if len(text) > max_chars:
            return text[:max_chars].rstrip() + "\n…"
        return text


def get_event_memory(config: Config) -> EventMemory:
    return EventMemory(event_memory_path(config))


def format_events_digest(config: Config, *, limit: int = 10) -> str:
    try:
        return get_event_memory(config).format_digest(limit=limit)
    except OSError:
        return ""


def apply_event_updates(config: Config, parsed: dict) -> list[str]:
    """Из JSON reflect: event_update / events → event_memory."""
    notes: list[str] = []
    if not isinstance(parsed, dict):
        return notes
    mem = get_event_memory(config)
    chunks: list[Any] = []
    one = parsed.get("event_update")
    if isinstance(one, dict):
        chunks.append(one)
    elif isinstance(one, str) and one.strip():
        chunks.append({"title": one.strip()[:80], "what": one.strip()})
    many = parsed.get("events")
    if isinstance(many, list):
        chunks.extend([x for x in many if isinstance(x, dict)])
    for raw in chunks:
        ev = mem.add(
            title=str(raw.get("title") or ""),
            what=str(raw.get("what") or raw.get("text") or ""),
            where=str(raw.get("where") or ""),
            who=str(raw.get("who") or ""),
            senses=str(raw.get("senses") or ""),
            tags=list(raw.get("tags") or []),
            hybrid_of=list(raw.get("hybrid_of") or []),
            source="reflect",
        )
        if ev:
            notes.append(f"событие «{ev.title}» ({ev.id})")
    return notes


_SCENE_HINT = re.compile(
    r"(?is)представь|твои\s+действия|сцен|ролев|что\s+делаешь|"
    r"nsfw|эротик|секс|интим|постел|голая|голый|ласк|целу",
)


def looks_like_scene_exchange(user_text: str, assistant_text: str = "") -> bool:
    blob = f"{user_text}\n{assistant_text}"
    if _SCENE_HINT.search(blob or ""):
        return True
    return len((assistant_text or "").split()) >= 40 and bool(
        re.search(r"(?i)я\s+|мне\s+|пальц|дыхан|коже|бёдер|взгляд", assistant_text or "")
    )


def maybe_capture_scene_event(
    config: Config,
    user_text: str,
    assistant_text: str,
    *,
    source: str = "chat",
) -> Optional[StoryEvent]:
    """Если модель не прислала event_update — вырезать бит из длинной сцены."""
    if not looks_like_scene_exchange(user_text, assistant_text):
        return None
    body = re.sub(r"\s+", " ", (assistant_text or "").strip())
    if len(body) < 80:
        return None
    title = body[:56].rstrip(".,;:") + ("…" if len(body) > 56 else "")
    return get_event_memory(config).add(
        title=title,
        what=body[:500],
        who="Вью / Ден",
        tags=["сцена", "auto"],
        source=source,
    )


def maybe_capture_story_thread(
    config: Config,
    user_text: str,
    assistant_text: str,
    *,
    source: str = "chat",
) -> Optional[StoryEvent]:
    """Сюжетный чат → короткий бит в event_memory (переживает рестарт в digest)."""
    try:
        from .prompts.reflect_mode import looks_like_story_chat
    except ImportError:
        return None
    if not looks_like_story_chat(user_text or ""):
        return None
    u = re.sub(r"\s+", " ", (user_text or "").strip())
    a = re.sub(r"\s+", " ", (assistant_text or "").strip())
    if len(u) < 24 and len(a) < 40:
        return None
    # Не дублировать почти то же самое подряд
    mem = get_event_memory(config)
    recent = mem.recent(limit=3) if hasattr(mem, "recent") else []
    snippet = (u[:120] + " / " + a[:160]).strip(" /")
    for ev in recent:
        if snippet[:80] and snippet[:80] in (ev.what or ""):
            return None
    title = u[:50].rstrip(".,;:") + ("…" if len(u) > 50 else "")
    return mem.add(
        title=title or "Сюжет из чата",
        what=snippet[:500],
        who="Ден, Вью",
        tags=["story", "thread", "auto"],
        source=source,
    )


def clear_chat_transcripts(config: Config) -> dict:
    """Удалить логи чатов и сырой story_memory; события и канон не трогаем."""
    data = Path(config.data_dir)
    removed: list[str] = []
    logs = data / "logs"
    if logs.is_dir():
        for p in logs.glob("chat_*.txt"):
            try:
                p.unlink()
                removed.append(p.name)
            except OSError:
                pass
    story = data / "story_memory.json"
    if story.is_file():
        try:
            story.unlink()
            removed.append(story.name)
        except OSError:
            pass
    ingest = data / "story_ingest.json"
    if ingest.is_file():
        try:
            ingest.unlink()
            removed.append(ingest.name)
        except OSError:
            pass
    # Итоги чатов в VIU_MEMORY — обнулить секцию, не трогая привычки.
    try:
        from .viu_memory import (
            _SECTION_SUMMARIES,
            ensure_viu_memory,
            viu_memory_path,
        )

        path = ensure_viu_memory(config)
        text = path.read_text(encoding="utf-8", errors="replace")
        if _SECTION_SUMMARIES in text:
            idx = text.find(_SECTION_SUMMARIES)
            head = text[: idx + len(_SECTION_SUMMARIES)]
            rest = text[idx + len(_SECTION_SUMMARIES) :]
            next_h = re.search(r"\n## ", rest)
            tail = rest[next_h.start() :] if next_h else ""
            path.write_text(
                head + "\n\n<!-- очищено: сырые итоги чатов -->\n" + tail,
                encoding="utf-8",
            )
            removed.append(viu_memory_path(config).name + "#итоги")
    except Exception:  # noqa: BLE001
        pass
    return {"removed": removed, "kept": ["event_memory.json", "vision.md", "PLOT_CANVAS.md"]}
