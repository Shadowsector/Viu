"""Сюжетная память диалога — простой RAG по ключевым словам.

Хранит ходы Дена и Вью в `.viu/story_memory.json`, переживает перезапуск.
Старые чаты подтягивает из `.viu/logs/chat_*.txt`.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from .config import Config

_STORY_PATH_NAME = "story_memory.json"
_INGEST_META = "story_ingest.json"
# Полные реплики для сюжетного RAG (раньше 1200 — обрезало GDD-ответы).
_STORY_BEAT_MAX = 8000


@dataclass
class StoryBeat:
    role: str  # user | assistant
    text: str
    ts: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)
    source: str = "chat"  # chat | telegram | log | vision

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "StoryBeat":
        return StoryBeat(
            role=str(d.get("role") or "user"),
            text=str(d.get("text") or "").strip(),
            ts=float(d.get("ts") or 0.0),
            tags=list(d.get("tags") or []),
            source=str(d.get("source") or "chat"),
        )


def story_memory_path(config: Config) -> Path:
    return Path(config.data_dir) / _STORY_PATH_NAME


def _ingest_meta_path(config: Config) -> Path:
    return Path(config.data_dir) / _INGEST_META


class StoryMemory:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._beats: List[StoryBeat] = []
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            self._beats = []
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items = raw.get("beats") if isinstance(raw, dict) else raw
            self._beats = [StoryBeat.from_dict(x) for x in (items or [])]
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            self._beats = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "comment": "Сюжетные ходы Дена и Вью — для reflect RAG",
            "beats": [b.to_dict() for b in self._beats[-2000:]],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def add(
        self,
        role: str,
        text: str,
        *,
        tags: Optional[Sequence[str]] = None,
        source: str = "chat",
        ts: Optional[float] = None,
    ) -> Optional[StoryBeat]:
        clean = (text or "").strip()
        if not clean:
            return None
        # не плодим дубли подряд
        if self._beats:
            last = self._beats[-1]
            if last.role == role and last.text == clean[:_STORY_BEAT_MAX]:
                return last
        beat = StoryBeat(
            role=role,
            text=clean[:_STORY_BEAT_MAX],
            ts=float(ts if ts is not None else time.time()),
            tags=list(tags or []),
            source=source,
        )
        self._beats.append(beat)
        self._save()
        return beat

    def add_exchange(
        self,
        user_text: str,
        assistant_text: str,
        *,
        source: str = "chat",
        tags: Optional[Sequence[str]] = None,
    ) -> None:
        tag_list = list(tags or [])
        self.add("user", user_text, tags=tag_list, source=source)
        self.add("assistant", assistant_text, tags=tag_list, source=source)

    def all(self) -> List[StoryBeat]:
        return list(self._beats)

    def recent(self, limit: int = 12) -> List[StoryBeat]:
        return list(self._beats[-limit:])

    def search(self, query: str, limit: int = 8) -> List[StoryBeat]:
        terms = [t for t in re.split(r"\W+", (query or "").lower()) if len(t) > 2]
        if not terms:
            return self.recent(limit)
        scored: list[tuple[int, float, StoryBeat]] = []
        for beat in self._beats:
            hay = (beat.text + " " + " ".join(beat.tags)).lower()
            score = sum(hay.count(t) for t in terms)
            if score > 0:
                scored.append((score, beat.ts, beat))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [b for _, _, b in scored[:limit]]

    def as_chat_history(self, limit: int = 16) -> List[dict]:
        """Для GUI/Telegram: role/content как у LLM."""
        out: List[dict] = []
        for beat in self.recent(limit):
            out.append({"role": beat.role, "content": beat.text})
        return out

    def format_context(self, query: str, *, recent_n: int = 10, search_n: int = 6) -> str:
        """Текст для system-заметок reflect."""
        recent = self.recent(recent_n)
        found = self.search(query, limit=search_n) if query.strip() else []
        # убрать дубли search, уже попавшие в recent
        recent_ids = {(b.ts, b.role, b.text[:80]) for b in recent}
        extra = [b for b in found if (b.ts, b.role, b.text[:80]) not in recent_ids]

        lines: List[str] = []
        if recent:
            lines.append("### Недавние сюжетные реплики (помни и продолжай)")
            for b in recent:
                who = "Ден" if b.role == "user" else "Вью"
                text = re.sub(
                    r"\b20\d{2}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?\b",
                    "",
                    b.text,
                )
                text = re.sub(r"\s{2,}", " ", text).strip(" ,;—-")
                if not text:
                    continue
                lines.append(f"- **{who}:** {text[:900]}")
        if extra:
            lines.append("### Похожее из более ранней памяти")
            for b in extra:
                who = "Ден" if b.role == "user" else "Вью"
                text = re.sub(
                    r"\b20\d{2}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?\b",
                    "",
                    b.text,
                )
                text = re.sub(r"\s{2,}", " ", text).strip(" ,;—-")
                if not text:
                    continue
                lines.append(f"- **{who}:** {text[:700]}")
        if not lines or all(l.startswith("###") for l in lines):
            return ""
        lines.append(
            "Опирайся на эти ходы: не предлагай с нуля то, что уже решили; "
            "если Ден развивает сюжет — продолжай его нить."
        )
        return "\n".join(lines)


def get_story_memory(config: Config) -> StoryMemory:
    return StoryMemory(story_memory_path(config))


_LOG_LINE_RE = re.compile(
    r"^(?:\d{1,2}:\d{2}:\d{2}\s+)?(ты|Вью|размышляет|система|ошибка|шаг):\s*(.*)$"
)


def _parse_chat_log(path: Path) -> List[StoryBeat]:
    beats: List[StoryBeat] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    mtime = path.stat().st_mtime
    for i, line in enumerate(text.splitlines()):
        m = _LOG_LINE_RE.match(line.strip())
        if not m:
            continue
        who, body = m.group(1), m.group(2).strip()
        if who not in ("ты", "Вью") or not body:
            continue
        if body.startswith("[") and who == "Вью":
            # tool dumps
            if body.startswith("[") and "]" in body[:40]:
                # keep Telegram-looking user lines; skip tool OK blocks for Viu
                if not body.startswith("[Telegram]"):
                    # Viu tool results often `[Label] OK`
                    continue
        role = "user" if who == "ты" else "assistant"
        # strip [Telegram] prefix for cleaner memory
        if body.startswith("[Telegram]"):
            body = body[len("[Telegram]") :].strip()
        if body.startswith("[") and role == "user":
            # [Переэкспорт…] — не сюжет
            if re.match(r"^\[\S", body):
                continue
        beats.append(
            StoryBeat(
                role=role,
                text=body[:_STORY_BEAT_MAX],
                ts=mtime + i * 0.001,
                tags=["log"],
                source="log",
            )
        )
    return beats


def ingest_chat_logs(config: Config, *, force: bool = False) -> tuple[int, str]:
    """Подтянуть старые chat_*.txt в story_memory (один раз на файл)."""
    logs_dir = Path(config.data_dir) / "logs"
    if not logs_dir.is_dir():
        return 0, "Нет папки logs — подтягивать нечего."

    meta_path = _ingest_meta_path(config)
    done: dict = {}
    if meta_path.is_file() and not force:
        try:
            done = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            done = {}

    store = get_story_memory(config)
    added = 0
    files = sorted(logs_dir.glob("chat_*.txt"))
    for path in files:
        key = path.name
        stamp = f"{path.stat().st_mtime_ns}:{path.stat().st_size}"
        if not force and done.get(key) == stamp:
            continue
        for beat in _parse_chat_log(path):
            store.add(
                beat.role,
                beat.text,
                tags=beat.tags,
                source="log",
                ts=beat.ts,
            )
            added += 1
        done[key] = stamp

    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(done, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return added, f"Из логов: +{added} реплик в story_memory ({len(files)} файлов)."


_ingested_this_process = False


def ensure_logs_ingested(config: Config) -> tuple[int, str]:
    """Один раз за процесс подтянуть chat-логи."""
    global _ingested_this_process
    if _ingested_this_process:
        return 0, ""
    _ingested_this_process = True
    return ingest_chat_logs(config)
