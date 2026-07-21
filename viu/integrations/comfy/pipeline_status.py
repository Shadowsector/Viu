"""Сводка: генерирует ли Comfy сейчас, что ждёт, прогресс."""

from __future__ import annotations

from ...config import Config
from ...lab.comfy_director import barn_cycle_status
from ...lab.comfy_pipeline import COMFY_TOPIC, STEP_LABELS
from ...lab.session import load_session
from ...presence import is_away
from .client import ComfyClient
from .clip_review import ComfyClipStore, clip_review_path
from .scene_choice import load_scene_state, scene_choice_status_line


def comfy_pipeline_status(config: Config) -> str:
    lines = [
        "=== Comfy MoCap — что происходит ===",
        f"Режим Вью: {'нет дома (away, авто)' if is_away(config) else 'дома'}",
    ]

    st = load_scene_state(config)
    if st.awaiting_choice:
        lines.append(scene_choice_status_line(config))

    session = load_session(config, COMFY_TOPIC)
    if session is None:
        lines.append("Lab Comfy: **нет активной сессии** — сейчас не генерирует.")
    else:
        step_label = STEP_LABELS[min(session.step, len(STEP_LABELS) - 1)] if session.step < len(STEP_LABELS) else "—"
        lines.append(f"Lab Comfy: **{session.status}** · шаг {session.step + 1}/{session.steps_total} ({step_label})")
        slug = str(session.meta.get("catalog_slug") or "")
        action = str(session.meta.get("approved_action") or session.meta.get("action") or "")[:80]
        if slug:
            lines.append(f"  catalog_slug: {slug}")
            picked = session.meta.get("selected_loras") or []
            if picked:
                names = ", ".join(
                    str(p.get("file") or p) if isinstance(p, dict) else str(p) for p in picked
                )
                lines.append(f"  LoRA (выбраны): {names}")
            elif session.status == "awaiting_lora_pick":
                lines.append("  LoRA: жду выбор (comfy_lora_list)")
        if action:
            lines.append(f"  промпт: {action}")
        if slug and action and slug.replace("_", " ") not in action.lower() and "idle stand" in action.lower() and slug != "idle":
            lines.append(
                f"  ⚠ промпт не совпадает с slug ({slug}) — будет пересинхронизирован при генерации"
            )
        if session.status == "running" and session.step == 4:
            lines.append("  → **сейчас генерирует** 3 дубля (¾) в ComfyUI")
        elif session.status == "awaiting_prompt":
            lines.append("  → ждёт одобрение промпта (Telegram / чат: ок)")
        elif session.status == "awaiting_lora_pick":
            lines.append("  → ждёт выбор LoRA (lora: 1,2 / none)")
        elif session.status == "awaiting_clip_pick":
            lines.append("  → ждёт выбор лучшего дубля (дома: «Оценить клипы Comfy»)")
        elif session.status == "paused":
            lines.append(f"  → пауза: {session.pause_reason or session.last_fail_msg[:120]}")
        elif session.status in ("completed", "idle", "awaiting_rating"):
            lines.append("  → итерация завершена; away запустит следующую, если нет паузы")

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
    lines.append("")
    lines.append("--- Оценка (как это устроено) ---")
    lines.append(
        "1) Away: 3 дубля → авто take_b (score 3) → kept в Lab/Refs/kept + ComfyOut\n"
        "2) Дома: окно «Оценить клипы Comfy» или «лучший: take_b 5»\n"
        "3) После 10 kept на действие — пауза, Telegram: выбор сцены 1/2/3"
    )
    lines.append("")
    lines.append(barn_cycle_status(config))
    if not st.awaiting_choice:
        lines.append(scene_choice_status_line(config))
    return "\n".join(lines)
