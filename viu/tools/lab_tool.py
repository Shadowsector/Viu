"""Инструменты лаборатории: Cascadeur и др."""

from __future__ import annotations

from typing import Any, Dict

from ..lab.cascadeur_pipeline import CASCADEUR_TOPIC, ensure_task_file
from ..lab.models_inbox import inbox_models_newer_than_session
from ..lab.prepare import run_lab_prepared
from ..lab.progress import format_lab_progress
from ..lab.ratings import average_score, validate_ratings
from ..lab.session import load_session, save_session
from .base import AgentContext, Tool, ToolResult


def _run_all_flag(args: Dict[str, Any]) -> bool:
    return str(args.get("run_all", "0")).lower() in ("1", "true", "yes")


class LabStartTool(Tool):
    name = "lab_start"
    description = (
        "Начать или возобновить лабораторную сессию. topic=cascadeur — "
        "пайплайн FBX/Cascadeur/скрины/отчёт. run_all=1 — весь цикл без пауз между шагами."
    )
    parameters = {
        "topic": "cascadeur (по умолчанию)",
        "reset": "1 = новая сессия",
        "run_all": "1 = выполнить все шаги до отчёта/затыка",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        topic = str(args.get("topic") or CASCADEUR_TOPIC).strip().lower()
        reset = str(args.get("reset", "0")).lower() in ("1", "true", "yes")
        run_all = _run_all_flag(args)
        if topic == CASCADEUR_TOPIC:
            ensure_task_file(ctx.config)

        if not reset:
            session = load_session(ctx.config, topic)
            if session and session.status == "awaiting_rating":
                return ToolResult(
                    True,
                    "Жду оценку — «Оценить лабораторию».\n"
                    "Новая итерация: lab_start reset=1",
                )
            if session and inbox_models_newer_than_session(ctx.config, session):
                reset = True

        ok, msg, session = run_lab_prepared(
            ctx.config, topic, force_reset=reset, run_all=run_all,
        )
        if session is None:
            return ToolResult(False, msg)
        continued = session.step > 0 and not reset and "Обновление Viu" not in msg
        body = format_lab_progress(session, msg, continued=continued)
        if run_all:
            body = "Lab: полный цикл (автономно).\n" + body
        return ToolResult(ok, body)


class LabStepTool(Tool):
    name = "lab_step"
    description = "Выполнить следующий шаг активной лабораторной сессии. run_all=1 — до конца."
    parameters = {"topic": "cascadeur (по умолчанию)", "run_all": "1 = весь оставшийся цикл"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        topic = str(args.get("topic") or CASCADEUR_TOPIC).strip().lower()
        session = load_session(ctx.config, topic)
        if session is None:
            return ToolResult(False, f"Нет сессии lab/{topic}. Сначала lab_start.")
        if session.status == "awaiting_rating":
            return ToolResult(True, "Жду оценку — «Оценить лабораторию».")
        ok, msg, session = run_lab_prepared(
            ctx.config, topic, force_reset=False, run_all=_run_all_flag(args),
        )
        session = session or load_session(ctx.config, topic)
        prefix = "Lab: полный цикл.\n" if _run_all_flag(args) else ""
        return ToolResult(ok, prefix + format_lab_progress(session, msg))


class LabRunAllTool(Tool):
    name = "lab_run_all"
    description = "Выполнить все оставшиеся шаги lab до отчёта, паузы или затыка."
    parameters = {"topic": "cascadeur (по умолчанию)", "reset": "1 = новая сессия с нуля"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        args = dict(args)
        args["run_all"] = "1"
        reset = str(args.get("reset", "0")).lower() in ("1", "true", "yes")
        return LabStartTool().run(args, ctx)


class LabStatusTool(Tool):
    name = "lab_status"
    description = "Статус лаборатории: шаг, journal, артефакты, ожидание оценки."
    parameters = {"topic": "cascadeur (по умолчанию)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        topic = str(args.get("topic") or CASCADEUR_TOPIC).strip().lower()
        session = load_session(ctx.config, topic)
        if session is None:
            return ToolResult(True, f"Lab «{topic}»: сессии нет.")
        lines = [
            f"Lab «{topic}» id={session.id}",
            f"status={session.status} step={session.step}/{session.steps_total}",
            f"updated={session.updated_at}",
        ]
        if session.pause_reason:
            lines.append(f"pause: {session.pause_reason}")
        if session.artifacts:
            lines.append("artifacts:")
            lines.extend(f"  • {a}" for a in session.artifacts[-6:])
        if session.status == "awaiting_rating":
            lines.append("")
            lines.append(session.last_report[:1200] if session.last_report else "(нет отчёта)")
        return ToolResult(True, "\n".join(lines))


class LabRateTool(Tool):
    name = "lab_rate"
    description=(
        "Оценить работу лаборатории по критериям 1–5: technique, creativity, "
        "effort, usefulness, clarity. notes — комментарий."
    )
    parameters = {
        "topic": "cascadeur",
        "technique": "1-5",
        "creativity": "1-5",
        "effort": "1-5",
        "usefulness": "1-5",
        "clarity": "1-5",
        "notes": "комментарий (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        topic = str(args.get("topic") or CASCADEUR_TOPIC).strip().lower()
        session = load_session(ctx.config, topic)
        if session is None:
            return ToolResult(False, "Нет сессии для оценки.")
        values = {}
        for key in ("technique", "creativity", "effort", "usefulness", "clarity"):
            raw = args.get(key)
            if raw is None or raw == "":
                continue
            try:
                values[key] = int(raw)
            except (TypeError, ValueError):
                return ToolResult(False, f"Оценка {key} должна быть числом 1–5")
        ok_val, err = validate_ratings(values)
        if not ok_val:
            return ToolResult(False, err)
        session.ratings = values
        session.rating_notes = str(args.get("notes") or "").strip()
        session.status = "completed"
        avg = average_score(values)
        save_session(ctx.config, session)
        from ..lab.session import append_journal

        append_journal(
            ctx.config,
            topic,
            f"### Оценка Дена\n\n{values}\n\n{session.rating_notes}\n\nСреднее: {avg:.1f}/5",
        )
        return ToolResult(
            True,
            f"Спасибо! Средняя оценка {avg:.1f}/5. Сессия завершена.\n"
            f"Journal: .viu/lab/{topic}/journal.md",
        )
