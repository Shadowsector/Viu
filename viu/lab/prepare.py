"""Подготовка lab-сессии: auto-reset после обновления Viu, recover вместо слепого повтора."""

from __future__ import annotations

from typing import Literal, Optional, Tuple

from ..config import Config
from .recover import recover_stuck_step, should_recover_instead_of_retry
from .session import LabSession, load_session, new_session, save_session
from .version import build_changed_since_last_run, persist_build_stamp, viu_build_stamp

PrepareMode = Literal["fresh", "continue", "recover"]


def prepare_lab_session(
    config: Config,
    topic: str,
    *,
    force_reset: bool = False,
) -> Tuple[LabSession, PrepareMode, str]:
    """Решить: новая итерация, recover или продолжение."""
    current_stamp = viu_build_stamp(config)
    build_changed = build_changed_since_last_run(config)

    notes: list[str] = []
    session = None if force_reset else load_session(config, topic)

    try:
        return _prepare_lab_session_inner(
            config,
            topic,
            current_stamp=current_stamp,
            build_changed=build_changed,
            force_reset=force_reset,
            session=session,
            notes=notes,
        )
    finally:
        persist_build_stamp(config)


def _prepare_lab_session_inner(
    config: Config,
    topic: str,
    *,
    current_stamp: str,
    build_changed: bool,
    force_reset: bool,
    session: Optional[LabSession],
    notes: list[str],
) -> Tuple[LabSession, PrepareMode, str]:
    if force_reset:
        notes.append("reset=1 — новая итерация.")
        session = new_session(topic)
        session.viu_build_stamp = current_stamp
        if topic == "comfy":
            session.steps_total = 6
        save_session(config, session)
        return session, "fresh", "\n".join(notes)

    if session is None:
        session = new_session(topic)
        session.viu_build_stamp = current_stamp
        if topic == "comfy":
            session.steps_total = 6
        save_session(config, session)
        return session, "fresh", ""

    if build_changed or (session.viu_build_stamp and session.viu_build_stamp != current_stamp):
        notes.append(
            f"Обновление Viu ({session.viu_build_stamp or '?'} → {current_stamp}) — lab с шага 1."
        )
        session = new_session(topic)
        session.viu_build_stamp = current_stamp
        if topic == "comfy":
            session.steps_total = 6
        save_session(config, session)
        return session, "fresh", "\n".join(notes)

    if session.status == "awaiting_rating":
        return session, "continue", "Жду оценку — «Оценить лабораторию»."

    if session.status == "awaiting_prompt":
        return session, "continue", "Жду одобрение Comfy-промпта в Telegram."

    if session.status == "completed":
        notes.append("Прошлая итерация завершена — новая с шага 1.")
        session = new_session(topic)
        session.viu_build_stamp = current_stamp
        if topic == "comfy":
            session.steps_total = 6
        save_session(config, session)
        return session, "fresh", "\n".join(notes)

    if should_recover_instead_of_retry(session):
        return session, "recover", f"Застряла на шаге {session.last_fail_step + 1} — recover, не повтор."

    session.viu_build_stamp = current_stamp or session.viu_build_stamp
    session.status = "running"
    save_session(config, session)
    return session, "continue", ""


def run_lab_prepared(
    config: Config,
    topic: str,
    *,
    force_reset: bool = False,
    run_all: bool = False,
    action: str = "",
) -> Tuple[bool, str, Optional[LabSession]]:
    if topic == "comfy":
        from .comfy_pipeline import ensure_task_file, run_one_step, run_until_done
    else:
        from .cascadeur_pipeline import run_one_step, run_until_done

    session, mode, note = prepare_lab_session(config, topic, force_reset=force_reset)
    prefix = (note + "\n") if note else ""

    if topic == "comfy":
        ensure_task_file(config, action=action)
        if action.strip():
            session.meta["action"] = action.strip()
            save_session(config, session)
        if mode == "continue" and session.status == "awaiting_prompt":
            return True, prefix + "Жду одобрение Comfy-промпта в Telegram.", session

    if mode == "recover":
        if topic != "comfy":
            ok, msg = recover_stuck_step(config, session)
            session = load_session(config, topic) or session
            return ok, prefix + msg, session
        # comfy: просто продолжаем шаг
        mode = "continue"

    if run_all:
        ok, msg = run_until_done(config, session)
    else:
        ok, msg = run_one_step(config, session)
    session = load_session(config, topic) or session
    return ok, prefix + msg, session
