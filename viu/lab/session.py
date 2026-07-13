"""Сессия лаборатории — JSON + journal."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import Config
from .paths import journal_path, session_path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class LabSession:
    id: str
    topic: str
    status: str = "idle"  # idle | running | paused | awaiting_rating | completed
    step: int = 0
    steps_total: int = 9
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    last_report: str = ""
    pause_reason: str = ""
    artifacts: List[str] = field(default_factory=list)
    ratings: Optional[Dict[str, int]] = None
    rating_notes: str = ""
    launch_ok: bool = False
    inbox_ok: bool = False
    import_ok: bool = False
    import_auto: bool = False
    last_fail_step: int = -1
    last_fail_msg: str = ""
    step_fail_counts: Dict[str, int] = field(default_factory=dict)
    viu_build_stamp: str = ""
    recoveries: int = 0

    def touch(self) -> None:
        self.updated_at = _now()

    def append_artifact(self, path: str | None) -> None:
        if not path:
            return
        if path not in self.artifacts:
            self.artifacts.append(path)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LabSession":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def load_session(config: Config, topic: str) -> Optional[LabSession]:
    path = session_path(config, topic)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LabSession.from_dict(data)
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def save_session(config: Config, session: LabSession) -> Path:
    session.touch()
    path = session_path(config, session.topic)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def append_journal(config: Config, topic: str, block: str) -> Path:
    path = journal_path(config, topic)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {stamp}\n\n{block.strip()}\n")
    return path


def new_session(topic: str) -> LabSession:
    return LabSession(id=str(uuid.uuid4())[:8], topic=topic, status="running", step=0)
