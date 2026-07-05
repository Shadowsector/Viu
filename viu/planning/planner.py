"""Планирование многоэтапных задач.

План — это упорядоченный список шагов со статусами. Хранится в JSON,
чтобы переживать перезапуски агента (долгосрочное планирование).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

VALID_STATUSES = ("pending", "in_progress", "done", "blocked")


@dataclass
class PlanStep:
    id: int
    title: str
    status: str = "pending"
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    goal: str = ""
    steps: List[PlanStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"goal": self.goal, "steps": [s.to_dict() for s in self.steps]}

    @staticmethod
    def from_dict(d: dict) -> "Plan":
        return Plan(
            goal=d.get("goal", ""),
            steps=[
                PlanStep(
                    id=int(s["id"]),
                    title=s.get("title", ""),
                    status=s.get("status", "pending"),
                    note=s.get("note", ""),
                )
                for s in d.get("steps", [])
            ],
        )

    def render(self) -> str:
        if not self.steps:
            return "(план пуст)"
        marks = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]", "blocked": "[!]"}
        lines = [f"Цель: {self.goal}"] if self.goal else []
        for s in self.steps:
            mark = marks.get(s.status, "[ ]")
            line = f"  {mark} {s.id}. {s.title}"
            if s.note:
                line += f" — {s.note}"
            lines.append(line)
        return "\n".join(lines)


class Planner:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.plan = Plan()
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.plan = Plan.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, ValueError, KeyError):
                self.plan = Plan()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def create(self, goal: str, steps: List[str]) -> Plan:
        self.plan = Plan(
            goal=goal,
            steps=[PlanStep(id=i + 1, title=t) for i, t in enumerate(steps)],
        )
        self._save()
        return self.plan

    def update_step(self, step_id: int, status: str | None = None, note: str | None = None) -> PlanStep:
        for s in self.plan.steps:
            if s.id == step_id:
                if status is not None:
                    if status not in VALID_STATUSES:
                        raise ValueError(f"Недопустимый статус {status!r}. Разрешено: {VALID_STATUSES}")
                    s.status = status
                if note is not None:
                    s.note = note
                self._save()
                return s
        raise KeyError(f"Шаг с id={step_id} не найден")
