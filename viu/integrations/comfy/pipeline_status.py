"""Сводка: генерирует ли Comfy сейчас, что ждёт, прогресс."""

from __future__ import annotations

from ...config import Config
from ...integrations.comfy.focus import (
    action_is_stale,
    focus_cycle_status,
    focus_mode_label,
    resolve_focus_slugs,
)
from ...lab.comfy_pipeline import COMFY_TOPIC, STEP_LABELS
from ...lab.paths import journal_path
from ...lab.session import load_session, save_session
from ...integrations.comfy.angles import mocap_take_count
from ...presence import is_away
from .client import ComfyClient
from .clip_review import ComfyClipStore, clip_review_path
from .scene_choice import load_scene_state, scene_choice_status_line


def comfy_pipeline_status_brief(config: Config) -> str:
    """Одна строка для статус-бара GUI."""
    session = load_session(config, COMFY_TOPIC)
    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    api = "?"
    try:
        ok, _ = ComfyClient(base_url=str(url), timeout=2.0).ping()
        api = "8188✓" if ok else "8188✗"
    except Exception:
        api = "8188✗"

    if session is None:
        return f"Comfy {api} · lab нет"

    step_label = (
        STEP_LABELS[min(session.step, len(STEP_LABELS) - 1)]
        if session.step < len(STEP_LABELS)
        else "—"
    )
    slug = str(session.meta.get("catalog_slug") or "").strip()
    slug_bit = f" · {slug}" if slug else ""
    try:
        from .show_profile import is_show_profile

        if is_show_profile(session.meta):
            slug_bit = " · ШОУ" + slug_bit
    except Exception:
        pass
    focus_bit = f" · фокус {focus_mode_label(config)}"
    st = session.status
    if st == "awaiting_prompt":
        hint = "жду «Снять»"
    elif st == "awaiting_lora_pick":
        hint = "жду LoRA"
    elif st == "awaiting_clip_pick":
        hint = "жду клип"
    elif st == "running":
        hint = f"шаг {session.step + 1}/{session.steps_total} {step_label}"
    elif st == "paused":
        hint = f"пауза: {(session.pause_reason or '')[:40]}"
    else:
        hint = st
    return f"Comfy {api} · {hint}{slug_bit}{focus_bit}"


def comfy_pipeline_status(config: Config) -> str:
    lines = [
        "=== Comfy MoCap — что происходит ===",
        f"Режим Вью: {'нет дома (away, авто)' if is_away(config) else 'дома'}",
    ]

    st = load_scene_state(config)
    if st.awaiting_choice:
        lines.append(scene_choice_status_line(config))

    try:
        from .shot_queue import format_queue_brief

        lines.append(format_queue_brief(config))
    except Exception:
        pass

    try:
        from .seed_pose import i2v_status_line

        lines.append(i2v_status_line(config))
    except Exception:
        pass

    try:
        from .show_profile import status_line as show_status_line

        sess0 = load_session(config, COMFY_TOPIC)
        meta0 = sess0.meta if sess0 is not None else None
        lines.append(show_status_line(config, meta0))
    except Exception:
        pass

    session = load_session(config, COMFY_TOPIC)
    if session is None:
        lines.append("Lab Comfy: **нет активной сессии** — сейчас не генерирует.")
    else:
        step_label = STEP_LABELS[min(session.step, len(STEP_LABELS) - 1)] if session.step < len(STEP_LABELS) else "—"
        lines.append(f"Lab Comfy: **{session.status}** · шаг {session.step + 1}/{session.steps_total} ({step_label})")
        slug = str(session.meta.get("catalog_slug") or "")
        if slug:
            from ...lab.comfy_director import sync_session_shot_from_slug

            action = str(session.meta.get("approved_action") or session.meta.get("action") or "")
            if action_is_stale(config, slug, action):
                synced = sync_session_shot_from_slug(config, session)
                save_session(config, session)
                lines.append(f"  catalog_slug: {slug}")
                lines.append(f"  промпт: {synced} (обновлён — был старый шаблон)")
            else:
                if slug:
                    lines.append(f"  catalog_slug: {slug}")
                action = str(session.meta.get("approved_action") or session.meta.get("action") or "")[:80]
                if action:
                    lines.append(f"  действие: {action}")
        else:
            action = str(session.meta.get("approved_action") or session.meta.get("action") or "")[:80]
            if action:
                lines.append(f"  действие: {action}")
        draft = str(session.meta.get("draft") or "").strip()
        if draft:
            one_line = draft.replace("\n", " ")[:200]
            lines.append(f"  Wan-промпт (кратко): {one_line}…")
            lines.append(f"  полный черновик: {journal_path(config, COMFY_TOPIC)}")
        elif session.status in ("awaiting_prompt", "running", "awaiting_clip_pick", "awaiting_rating"):
            lines.append(
                f"  черновик промпта: после шага «Черновик» — {journal_path(config, COMFY_TOPIC)}"
            )
        if slug:
            picked = session.meta.get("selected_loras") or []
            if picked:
                names = ", ".join(
                    str(p.get("file") or p) if isinstance(p, dict) else str(p) for p in picked
                )
                lines.append(f"  LoRA (выбраны): {names}")
            elif session.status == "awaiting_lora_pick":
                lines.append("  LoRA: жду выбор (comfy_lora_list)")
        if session.status == "running" and session.step == 5:
            from .show_profile import is_show_profile, show_take_count

            if is_show_profile(session.meta):
                lines.append(
                    f"  → **сейчас генерирует** шоу-дубль ×{show_take_count()}"
                )
            else:
                lines.append(
                    f"  → **сейчас генерирует** {mocap_take_count()} дублей (¾) в ComfyUI"
                )
        elif session.status == "awaiting_prompt":
            lines.append("  → панель съёмки: Telegram «Снять» / Промпт / LoRA")
        elif session.status == "awaiting_lora_pick":
            lines.append("  → ждёт LoRA (кнопка на панели или lora: 1)")
        elif session.status == "awaiting_clip_pick":
            lines.append(
                "  → ждёт оценку видео: «Оценить видео» / Студия "
                "(не Cascadeur lab)"
            )
        elif session.status == "paused":
            lines.append(f"  → пауза: {session.pause_reason or session.last_fail_msg[:120]}")
        elif session.status in ("completed", "idle", "awaiting_rating"):
            lines.append(
                "  → итерация завершена; away — следующий кадр без оценки (авто)"
            )

    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    client = ComfyClient(base_url=str(url), timeout=3.0)
    ok, ping = client.ping()
    lines.append(f"ComfyUI :8188: {'онлайн' if ok else 'НЕ ОТВЕЧАЕТ — ' + ping}")
    if ok:
        try:
            q = client.get_queue()
            running = len(q.get("queue_running") or [])
            pending = len(q.get("queue_pending") or [])
            lines.append(f"  очередь Comfy: running={running}, pending={pending}")
            from .queue_manage import format_queue_slugs_line, queue_stale_for_slug

            slug_line = format_queue_slugs_line(client)
            if slug_line:
                lines.append(slug_line)
            session_slug = ""
            if session is not None:
                session_slug = str(session.meta.get("catalog_slug") or "").strip()
            if session_slug and (running or pending):
                stale, mismatched = queue_stale_for_slug(client, session_slug)
                if stale:
                    sample = ", ".join(mismatched[:2])
                    lines.append(
                        f"  ⚠ в очереди чужие job ({sample}) — lab ждёт **{session_slug}**. "
                        "comfy_queue_clear или дождись сброса при следующем 3×¾."
                    )
            if running or pending:
                lines.append(
                    "  (ComfyUI/output: Girl_<slug>_take_* — читаемые имена; "
                    "копии → Lab/ComfyOut и Lab/Refs)"
                )
        except Exception:
            pass

    store = ComfyClipStore(clip_review_path(config)).load()
    cand = sum(1 for c in store.clips if c.status == "candidate")
    kept = sum(1 for c in store.clips if c.status == "kept")
    lines.append(f"Клипы: kept={kept}, на оценку (candidate)={cand}")
    lines.append(f"Фокус съёмки: {', '.join(resolve_focus_slugs(config)) or 'все'}")
    lines.append("")
    lines.append(focus_cycle_status(config))
    if not st.awaiting_choice:
        lines.append(scene_choice_status_line(config))
    return "\n".join(lines)
