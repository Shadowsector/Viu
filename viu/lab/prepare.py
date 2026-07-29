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
        preserved: dict = {}
        if topic == "comfy":
            old = load_session(config, topic)
            if old is not None:
                # Только LoRA-пресет между кадрами. Промпт/slug/action — НЕ тащить:
                # иначе «sit on a bed» залипает на новый touch_self и Wan снимает не то.
                for key in (
                    "lora_last_pick",
                    "selected_loras",
                    "i2v_seed_enabled",
                    "i2v_seed_path",
                    "i2v_seed_comfy",
                ):
                    val = (old.meta or {}).get(key)
                    if val is None or val == "" or val == []:
                        continue
                    preserved[key] = val
                # Также из постоянного state эталона
                try:
                    from ..integrations.comfy.seed_pose import load_seed_state

                    st = load_seed_state(config)
                    if st.get("enabled") and st.get("path"):
                        preserved["i2v_seed_enabled"] = True
                        preserved["i2v_seed_path"] = st["path"]
                        preserved["i2v_seed_comfy"] = st.get("comfy_name") or "viu_pose_seed.png"
                except Exception:
                    pass
        session = new_session(topic)
        if preserved:
            session.meta.update(preserved)
            notes.append("Пресет LoRA с прошлой сессии сохранён.")
        session.viu_build_stamp = current_stamp
        if topic == "comfy":
            session.steps_total = 6
        if topic == "interaction":
            session.steps_total = 8
        save_session(config, session)
        return session, "fresh", "\n".join(notes)

    if session is None:
        session = new_session(topic)
        session.viu_build_stamp = current_stamp
        if topic == "comfy":
            session.steps_total = 6
        if topic == "interaction":
            session.steps_total = 8
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
        if topic == "interaction":
            session.steps_total = 8
        save_session(config, session)
        return session, "fresh", "\n".join(notes)

    if session.status == "awaiting_rating":
        from ..presence import is_away

        shoot_now = bool((session.meta or {}).get("shoot_intent")) or bool(
            (session.meta or {}).get("auto_approved_shoot")
        )
        if topic == "comfy" and (is_away(config) or shoot_now):
            from .session import append_journal

            who = "away" if is_away(config) else "shoot"
            append_journal(
                config,
                topic,
                f"### Оценка ({who} auto)\n\n"
                "Пропущена — Вью снимает следующий кадр без блокировки GPU.",
            )
            # Сохранить ручной Wan / slug между итерациями.
            preserved: dict = {}
            for key in (
                "wan_positive",
                "wan_negative",
                "prompt_user_edited",
                "prompt_edit_slug",
                "action",
                "approved_action",
                "catalog_slug",
                "enters_from",
                "exits_to",
                "looped",
                "draft",
                "lora_last_pick",
                "selected_loras",
                "shoot_intent",
                "auto_approved_shoot",
            ):
                val = (session.meta or {}).get(key)
                if val is None or val == "" or val == []:
                    continue
                preserved[key] = val
            session.rating_notes = f"{who}: auto-пропуск оценки"
            session.status = "completed"
            save_session(config, session)
            notes.append(f"{who}: оценка lab пропущена — новая итерация.")
            session = new_session(topic)
            session.viu_build_stamp = current_stamp
            session.steps_total = 6
            if preserved:
                session.meta.update(preserved)
            save_session(config, session)
            return session, "fresh", "\n".join(notes)
        return session, "continue", "Жду оценку — «Оценить лабораторию»."

    if session.status == "awaiting_prompt":
        return session, "continue", "Жду одобрение Comfy-промпта в Telegram."

    if session.status == "paused" and (session.pause_reason or "") in (
        "comfy_offline",
        "operator",
    ):
        if should_recover_instead_of_retry(session) or session.pause_reason == "comfy_offline":
            return (
                session,
                "recover",
                f"Пауза ({session.pause_reason}) — recover, не слепой повтор.",
            )

    if session.status == "completed":
        notes.append("Прошлая итерация завершена — новая с шага 1.")
        session = new_session(topic)
        session.viu_build_stamp = current_stamp
        if topic == "comfy":
            session.steps_total = 6
        if topic == "interaction":
            session.steps_total = 8
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
    meta_extra: Optional[dict] = None,
) -> Tuple[bool, str, Optional[LabSession]]:
    if topic == "comfy":
        from .comfy_pipeline import ensure_task_file, run_one_step, run_until_done
    elif topic == "interaction":
        from .interaction_pipeline import ensure_task_file, run_one_step, run_until_done
    else:
        from .cascadeur_pipeline import run_one_step, run_until_done

    session, mode, note = prepare_lab_session(config, topic, force_reset=force_reset)
    prefix = (note + "\n") if note else ""

    if topic == "comfy":
        ensure_task_file(config, action=action)
        if action.strip():
            session.meta["action"] = action.strip()
        if meta_extra:
            for k, v in meta_extra.items():
                if v is None or v == "" or v == []:
                    continue
                session.meta[k] = v
        save_session(config, session)
        # Ждём TG только если реально стоим на approve/lora без shoot.
        # shoot_intent + approved → продолжаем (разблокировка «Comfy не стартует»).
        if mode == "continue" and session.status == "awaiting_prompt":
            if session.meta.get("shoot_intent") or session.meta.get("approved"):
                from .comfy_pipeline import apply_prompt_decision

                action = str(session.meta.get("action") or action or "")
                apply_prompt_decision(config, session, "approve", action)
                session = load_session(config, topic) or session
            else:
                return True, prefix + "Жду одобрение Comfy-промпта в Telegram.", session
        if mode == "continue" and session.status == "awaiting_lora_pick":
            if session.meta.get("shoot_intent") or session.meta.get("auto_approved_shoot"):
                from .comfy_pipeline import apply_lora_pick_decision

                last = [
                    int(x)
                    for x in (session.meta.get("lora_last_pick") or [])
                    if str(x).isdigit()
                ]
                apply_lora_pick_decision(config, session, last)
                session = load_session(config, topic) or session
            else:
                return True, prefix + "Жду выбор LoRA в Telegram (lora: 1 | none).", session

    if topic == "interaction":
        slug = ""
        if meta_extra:
            slug = str(meta_extra.get("catalog_slug") or "").strip()
        ensure_task_file(config, catalog_slug=slug)
        if meta_extra:
            for k, v in meta_extra.items():
                if v is None or v == "" or v == []:
                    continue
                session.meta[k] = v
        save_session(config, session)

    if mode == "recover":
        ok, msg = recover_stuck_step(config, session)
        session = load_session(config, topic) or session
        return ok, prefix + msg, session

    if run_all:
        ok, msg = run_until_done(config, session)
    else:
        ok, msg = run_one_step(config, session)
    session = load_session(config, topic) or session
    return ok, prefix + msg, session
