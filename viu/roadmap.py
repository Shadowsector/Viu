"""Дорожная карта разработки «Анабарры» — чтобы Вью знала, куда движемся.

Хранится в .viu/roadmap.json (переживает перезапуски). Вью читает текущий
фокус, продвигает вехи и обращается к Дену только на развилках.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

STATUSES = ("pending", "in_progress", "done", "blocked")

# Стартовая карта. Отражает договорённый план (Walk → локомоция → рост →
# тестовая сцена → дом на панели задач → карта-снежинка → проактивность Вью).
DEFAULT_MILESTONES: List[dict] = [
    {"id": 1, "title": "Модель Шани и скелет в Blender", "status": "done"},
    {"id": 2, "title": "Экспорт FBX в Unity, Humanoid", "status": "done"},
    {"id": 3, "title": "Idle-анимация играет в Unity", "status": "done"},
    {"id": 4, "title": "Walk + локомоция (A/D, Idle↔Walk)", "status": "done",
     "note": "клипы в Animations/, Speed, ShanyaLocomotion — петля клипов донастраивается"},
    {"id": 5, "title": "Рост-референс: Шаня ~1.7 м в сцене", "status": "in_progress",
     "note": "масштаб персонажа, пол/сетка для ориентира"},
    {"id": 6, "title": "Тестовая сцена GameTest (пол, свет, камера)", "status": "pending",
     "note": "пол, свет, камера следует за Шаней"},
    {"id": 7, "title": "Дом ~25 см на панели задач, прозрачная стена", "status": "pending"},
    {"id": 8, "title": "Карта-снежинка: лучи, ветвления, экспедиции", "status": "pending"},
    {"id": 9, "title": "Проактивность Вью: автоскан + вопросы по делу", "status": "in_progress",
     "note": "автоскан Animations готов; автопилот развивается"},
]


@dataclass
class Milestone:
    id: int
    title: str
    status: str = "pending"
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Roadmap:
    milestones: List[Milestone] = field(default_factory=list)

    @staticmethod
    def default() -> "Roadmap":
        return Roadmap([Milestone(**m) for m in DEFAULT_MILESTONES])

    @staticmethod
    def from_dict(d: dict) -> "Roadmap":
        items = d.get("milestones") or []
        return Roadmap(
            [
                Milestone(
                    id=int(m["id"]),
                    title=m.get("title", ""),
                    status=m.get("status", "pending"),
                    note=m.get("note", ""),
                )
                for m in items
            ]
        )

    def to_dict(self) -> dict:
        return {"milestones": [m.to_dict() for m in self.milestones]}

    def current_focus(self) -> Optional[Milestone]:
        for m in self.milestones:
            if m.status in ("in_progress", "blocked"):
                return m
        for m in self.milestones:
            if m.status == "pending":
                return m
        return None

    def progress(self) -> tuple[int, int]:
        done = sum(1 for m in self.milestones if m.status == "done")
        return done, len(self.milestones)

    def render(self) -> str:
        marks = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]", "blocked": "[!]"}
        done, total = self.progress()
        lines = [f"Дорожная карта Анабарры — {done}/{total} готово:"]
        focus = self.current_focus()
        for m in self.milestones:
            mark = marks.get(m.status, "[ ]")
            star = "  ← сейчас" if focus and m.id == focus.id else ""
            line = f"  {mark} {m.id}. {m.title}{star}"
            if m.note:
                line += f"\n       ({m.note})"
            lines.append(line)
        return "\n".join(lines)


class RoadmapStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.roadmap = Roadmap.default()
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.roadmap = Roadmap.from_dict(
                    json.loads(self.path.read_text(encoding="utf-8"))
                )
            except (json.JSONDecodeError, ValueError, KeyError):
                self.roadmap = Roadmap.default()
        else:
            self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.roadmap.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def set_status(self, milestone_id: int, status: str, note: Optional[str] = None) -> Milestone:
        if status not in STATUSES:
            raise ValueError(f"Статус {status!r} недопустим. Разрешено: {STATUSES}")
        for m in self.roadmap.milestones:
            if m.id == milestone_id:
                m.status = status
                if note is not None:
                    m.note = note
                self.save()
                return m
        raise KeyError(f"Веха id={milestone_id} не найдена")
