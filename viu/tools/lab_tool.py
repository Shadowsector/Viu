"""Инструменты лаборатории: Cascadeur и др."""

from __future__ import annotations

from typing import Any, Dict

from ..lab.cascadeur_pipeline import CASCADEUR_TOPIC, ensure_task_file
from ..lab.models_inbox import inbox_models_newer_than_session
from ..lab.manual_verify import resume_for_manual_verify
from ..lab.prepare import run_lab_prepared
from ..lab.progress import format_lab_progress
from ..lab.ratings import average_score, validate_ratings
from ..lab.session import load_session, save_session
from .base import AgentContext, Tool, ToolResult


def _run_all_flag(args: Dict[str, Any]) -> bool:
    return str(args.get("run_all", "0")).lower() in ("1", "true", "yes")


def _verify_flag(args: Dict[str, Any]) -> bool:
    return str(args.get("verify", "0")).lower() in ("1", "true", "yes")


class LabStartTool(Tool):
    name = "lab_start"
    description = (
        "Начать или возобновить лабораторную сессию. "
        "topic=cascadeur — FBX/Cascadeur. topic=comfy — Wan video → Lab/Refs "
        "(промпт в Telegram, 3 дубля ¾). topic=interaction — совместные анимации "
        "(multi-actor; docs/INTERACTION_PIPELINE.md). "
        "run_all=1 — весь цикл. action= для comfy (действие в кадре). "
        "verify=1 — после ручного import Cascadeur."
    )
    parameters = {
        "topic": "cascadeur | comfy | interaction",
        "reset": "1 = новая сессия",
        "run_all": "1 = выполнить все шаги до отчёта/затыка",
        "verify": "1 = проверить ручной import (скрин + vision)",
        "action": "для comfy: действие персонажа (sit down, walk, …)",
        "catalog_slug": "slug из каталога анимаций или interaction_catalog",
        "enters_from": "через запятую",
        "exits_to": "через запятую",
        "shot_reason": "почему этот кадр",
        "shoot": "1 = одобрить промпт и снять (кнопка MoCap); поднять Comfy",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        topic = str(args.get("topic") or CASCADEUR_TOPIC).strip().lower()
        reset = str(args.get("reset", "0")).lower() in ("1", "true", "yes")
        run_all = _run_all_flag(args)
        verify = _verify_flag(args)
        action = str(args.get("action") or "").strip()
        ensure_prefix = ""
        if topic == "comfy":
            from ..integrations.comfy.process import ensure_comfy_running

            ok_e, msg_e = ensure_comfy_running(
                ctx.config, auto_install=True, wait_seconds=180.0
            )
            ensure_prefix = msg_e.strip() + "\n\n"
            if not ok_e:
                return ToolResult(
                    False,
                    ensure_prefix
                    + "ComfyUI не запустился — генерация невозможна.\n"
                    "Проверь U:\\Viu\\ComfyUI и `.viu/logs/comfy_launch.log`, "
                    "или отдельно «подними comfy» / comfy_ensure.",
                )
        if topic == CASCADEUR_TOPIC:
            ensure_task_file(ctx.config)
        if topic == "comfy":
            from ..lab.comfy_pipeline import ensure_task_file as ensure_comfy_task
            from ..lab.comfy_director import infer_slug_from_action, invent_next_shot

            # Без явного slug — invent полный план, чтобы граф не терялся
            shoot_flag = str(args.get("shoot") or "").lower() in ("1", "true", "yes")
            if not str(args.get("catalog_slug") or "").strip():
                if not action or action.lower() in ("auto", "сам", "сама", "invent"):
                    plan = invent_next_shot(ctx.config, consume_queue=shoot_flag)
                    action = plan.action
                    args = dict(args)
                    args["catalog_slug"] = plan.catalog_slug
                    args["enters_from"] = ",".join(plan.enters_from)
                    args["exits_to"] = ",".join(plan.exits_to)
                    args["shot_reason"] = plan.reason
                    if plan.wan_positive:
                        args["_wan_positive"] = plan.wan_positive
                    if plan.wan_negative:
                        args["_wan_negative"] = plan.wan_negative
                    if (plan.lora_mode or "inherit") != "inherit":
                        from ..integrations.comfy.shot_queue import (
                            ShotQueueItem,
                            apply_item_lora_to_session,
                        )

                        apply_item_lora_to_session(
                            ctx.config,
                            ShotQueueItem(
                                id="from-plan",
                                catalog_slug=plan.catalog_slug,
                                action=plan.action,
                                lora_mode=plan.lora_mode or "inherit",
                                lora_indices=list(plan.lora_indices or []),
                            ),
                        )
                else:
                    inferred = infer_slug_from_action(action)
                    if inferred:
                        args = dict(args)
                        args["catalog_slug"] = inferred
            ensure_comfy_task(ctx.config, action=action)
        if topic == "interaction":
            from ..lab.interaction_pipeline import ensure_task_file as ensure_interaction_task

            slug = str(args.get("catalog_slug") or "").strip()
            ensure_interaction_task(ctx.config, catalog_slug=slug)

        session = None if reset else load_session(ctx.config, topic)

        if (
            not reset
            and session
            and session.status == "awaiting_rating"
            and (verify or run_all)
            and topic == CASCADEUR_TOPIC
        ):
            resume_for_manual_verify(ctx.config, session)
            session = load_session(ctx.config, topic)
            from ..lab.cascadeur_pipeline import run_until_done

            ok, msg = run_until_done(ctx.config, session)
            session = load_session(ctx.config, topic) or session
            prefix = (
                "Ручной import — проверяю viewport (скрин + vision, без полного цикла).\n"
            )
            body = prefix + format_lab_progress(session, msg)
            if run_all:
                body = "Lab: проверка ручного import.\n" + body
            return ToolResult(ok, body)

        if not reset and session and session.status == "awaiting_rating":
            shoot = str(args.get("shoot") or "").lower() in ("1", "true", "yes")
            # Comfy MoCap: оценка не должна блокировать новую съёмку / shoot.
            if topic == "comfy" and (shoot or run_all):
                from ..lab.session import append_journal

                session.rating_notes = (
                    session.rating_notes or "auto-skip: новая MoCap-съёмка"
                )
                session.status = "running"
                session.step = 0
                session.meta["shoot_intent"] = True
                if shoot:
                    session.meta["auto_approved_shoot"] = True
                session.meta.pop("lora_pick_done", None)
                session.meta.pop("clip_batch_id", None)
                session.meta.pop("clip_candidate_ids", None)
                save_session(ctx.config, session)
                append_journal(
                    ctx.config,
                    topic,
                    "### Оценка (auto-skip)\n\n"
                    "Пропущена — Ден нажал съёмку / lab run_all.",
                )
                # fall through → run_lab_prepared
            else:
                return ToolResult(
                    True,
                    "Жду оценку — «Оценить лабораторию».\n"
                    "Или «Лаборатория» / lab_start verify=1 — проверить ручной import без reset.\n"
                    "Для Comfy: «MoCap: снять клип» закроет оценку и поставит новую очередь.",
                )

        if not reset and session and session.status == "awaiting_prompt":
            if str(args.get("shoot") or "").lower() in ("1", "true", "yes"):
                session.meta["shoot_intent"] = True
                save_session(ctx.config, session)
                ok, msg, session = run_lab_prepared(
                    ctx.config,
                    topic,
                    force_reset=False,
                    run_all=run_all,
                    action=action,
                    meta_extra={"shoot_intent": True},
                )
                session = session or load_session(ctx.config, topic)
                body = format_lab_progress(session, msg)
                if run_all:
                    body = "Lab: полный цикл (автономно).\n" + body
                if ensure_prefix:
                    body = ensure_prefix + body
                return ToolResult(ok, body)
            return ToolResult(
                True,
                ensure_prefix
                + "Жду одобрение Comfy-промпта (ок / правки: … / стоп).\n"
                "Или снова «MoCap: снять клип» — одобрю и запущу Comfy.",
            )

        if not reset and topic == CASCADEUR_TOPIC:
            session = load_session(ctx.config, topic)
            if session and inbox_models_newer_than_session(ctx.config, session):
                reset = True

        def _csv(key: str) -> list:
            return [p.strip() for p in str(args.get(key) or "").split(",") if p.strip()]

        if topic == "comfy":
            meta_extra = {
                "catalog_slug": str(args.get("catalog_slug") or "").strip(),
                "enters_from": _csv("enters_from"),
                "exits_to": _csv("exits_to"),
                "shot_reason": str(args.get("shot_reason") or "").strip(),
            }
            if str(args.get("looped") or "").lower() in ("1", "true", "yes"):
                meta_extra["looped"] = True
            elif str(args.get("looped") or "").lower() in ("0", "false", "no"):
                meta_extra["looped"] = False
            if str(args.get("shoot") or "").lower() in ("1", "true", "yes"):
                meta_extra["shoot_intent"] = True
            wan_pos = str(args.get("_wan_positive") or "").strip()
            wan_neg = str(args.get("_wan_negative") or "").strip()
            if wan_pos:
                meta_extra["wan_positive"] = wan_pos
                meta_extra["prompt_user_edited"] = True
                meta_extra["prompt_edit_slug"] = str(
                    args.get("catalog_slug") or ""
                ).strip()
            if wan_neg:
                meta_extra["wan_negative"] = wan_neg
        elif topic == "interaction":
            meta_extra = {
                "catalog_slug": str(args.get("catalog_slug") or "").strip(),
            }
        else:
            meta_extra = None

        ok, msg, session = run_lab_prepared(
            ctx.config,
            topic,
            force_reset=reset,
            run_all=run_all,
            action=action,
            meta_extra=meta_extra,
        )
        if session is None:
            return ToolResult(False, msg)
        continued = session.step > 0 and not reset and "Обновление Viu" not in msg
        body = format_lab_progress(session, msg, continued=continued)
        if run_all:
            body = "Lab: полный цикл (автономно).\n" + body
        if ensure_prefix:
            body = ensure_prefix + body
        return ToolResult(ok, body)


class LabStepTool(Tool):
    name = "lab_step"
    description = "Выполнить следующий шаг активной лабораторной сессии. run_all=1 — до конца."
    parameters = {"topic": "cascadeur | comfy | interaction", "run_all": "1 = весь оставшийся цикл"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        topic = str(args.get("topic") or CASCADEUR_TOPIC).strip().lower()
        session = load_session(ctx.config, topic)
        if session is None:
            return ToolResult(False, f"Нет сессии lab/{topic}. Сначала lab_start.")
        if session.status == "awaiting_prompt":
            return ToolResult(
                True,
                "Жду одобрение Comfy-промпта в Telegram (ок / правки: … / стоп).",
            )
        if session.status == "awaiting_rating":
            if _run_all_flag(args) or _verify_flag(args):
                if topic != CASCADEUR_TOPIC:
                    return ToolResult(True, "Жду оценку — «Оценить лабораторию».")
                resume_for_manual_verify(ctx.config, session)
                session = load_session(ctx.config, topic)
                from ..lab.cascadeur_pipeline import run_until_done

                ok, msg = run_until_done(ctx.config, session)
                session = load_session(ctx.config, topic) or session
                prefix = "Lab: проверка ручного import.\n"
                return ToolResult(ok, prefix + format_lab_progress(session, msg))
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
    parameters = {
        "topic": "cascadeur | comfy | interaction",
        "reset": "1 = новая сессия с нуля",
        "action": "для comfy: действие в кадре",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        args = dict(args)
        args["run_all"] = "1"
        return LabStartTool().run(args, ctx)


class LabStatusTool(Tool):
    name = "lab_status"
    description = "Статус лаборатории: шаг, journal, артефакты, ожидание оценки/промпта."
    parameters = {"topic": "cascadeur | comfy"}

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
        if session.meta:
            action = session.meta.get("action") or session.meta.get("approved_action")
            if action:
                lines.append(f"action: {action}")
        if session.artifacts:
            lines.append("artifacts:")
            lines.extend(f"  • {a}" for a in session.artifacts[-6:])
        if session.status == "awaiting_prompt":
            lines.append("")
            lines.append("Жду Telegram: ок / правки: … / стоп")
            draft = (session.meta or {}).get("draft")
            if draft:
                lines.append(str(draft)[:800])
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
