"""Задание и шаги лаборатории Cascadeur."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from ..config import Config
from ..integrations.cascadeur import cascadeur_status
from ..integrations.cascadeur.launch import ensure_cascadeur_running
from ..integrations.cascadeur.window import find_cascadeur_hwnd
from ..integrations.screen.capture import capture_window_png
from ..tools.web import WebSearchTool
from .controller import lab_controller
from .models_inbox import build_models_summary, copy_random_model_to_cascadeur_inbox
from .notify import notify_lab_awaiting_rating, notify_lab_step
from .paths import apply_lab_vram_env, artifacts_dir, journal_path, lab_monitor_index, task_path
from .session import LabSession, append_journal, save_session

CASCADEUR_TOPIC = "cascadeur"

CASCADEUR_TASK_MD = """# Задание лаборатории: Cascadeur

Ты — **Вью**, лабораторный режим. Headless у Cascadeur нет — работай через **окно на 3-м мониторе**
(индекс 2), скрины и journal.

## Цель

Разобраться с пайплайном **FBX → Cascadeur → Export → Unity** для анимаций Шани.
Пробуй, конспектируй, показывай Дену **артефакты** (скрины, пути, вывод status).

## Пайплайн (каждая сессия)

1. **Статус** — Inbox/Export, exe, что лежит в папках.
2. **Модели** — скан `Library/Lab/Models/Inbox`, rig-check в Blender, сводка `models_summary.md`.
3. **Исследование** — web: официальные docs, rig retarget, export FBX.
4. **Inbox** — **случайная** модель из Lab Inbox → FBX в Cascadeur Inbox (или sample, если пусто).
5. **Запуск** — открыть Cascadeur, окно на монитор `VIU_LAB_MONITOR` (по умолчанию 3-й).
6. **Мышь** — фокус окна кликом в центр (`VIU_LAB_MOUSE=1`, Windows).
7. **Скрин** — зафиксировать UI после паузы (Ден может смотреть на 3-м мониторе).
8. **Отчёт** — journal + запрос оценки; в **автономном режиме** — кратко в Telegram.

## Ограничения

- **VRAM lab ~6 GB** — не грузи одновременно тяжёлые vision-модели без нужды.
- **Прерывание** — кнопки GUI и «Обновить Вью» важнее: сохрани journal и `paused`.
- **NSFW-литература / фанфики** — отложено (см. docs/VIU_LAB.md), не искать без флага.

## Чего ждёт Ден

- Честный отчёт: что получилось, что нет.
- Скрин Cascadeur в `lab/cascadeur/artifacts/`.
- Просьба выставить оценки 1–5 по пяти критериям.
"""


def ensure_task_file(config: Config) -> Path:
    path = task_path(config, CASCADEUR_TOPIC)
    if not path.is_file():
        path.write_text(CASCADEUR_TASK_MD, encoding="utf-8")
    return path


StepResult = Tuple[bool, str, Optional[str]]


def _check_abort(session: LabSession) -> Optional[StepResult]:
    if lab_controller.should_abort_step():
        session.status = "paused"
        session.pause_reason = lab_controller.pause_reason or "оператор"
        lab_controller.acknowledge_abort()
        return False, "Пауза: приоритет оператора (кнопка / обновление).", None
    return None


STEP_LABELS = [
    "Статус Cascadeur",
    "Скан моделей + rig-check",
    "Web-исследование",
    "Случайная модель → Inbox",
    "Запуск Cascadeur",
    "Фокус мышью",
    "Скрин UI",
    "Отчёт",
]


def step_models_scan(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    ok, msg, art = build_models_summary(config, topic=session.topic)
    append_journal(config, session.topic, f"### Модели (rig-check)\n\n{msg}")
    if art:
        session.artifacts.append(art)
    return ok, msg, art


def step_status(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    ok, text = cascadeur_status(config)
    append_journal(config, session.topic, f"### Статус Cascadeur\n\n{text}")
    return ok, text, None


def step_research(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    apply_lab_vram_env(config)
    if not config.allow_network:
        msg = "Сеть выключена — пропуск web-исследования."
        append_journal(config, session.topic, msg)
        return True, msg, None
    try:
        from ..tools.base import AgentContext
        from ..memory import MemoryStore
        from ..planning import Planner
        from ..tools import ToolRegistry

        ctx = AgentContext(
            config=config,
            memory=MemoryStore(config.data_dir / "memory.json"),
            planner=Planner(config.data_dir / "lab_plan.json"),
            registry=ToolRegistry(),
        )
        res = WebSearchTool().run(
            {"query": "Cascadeur export FBX to Unity workflow retarget", "max_results": 4},
            ctx,
        )
        body = res.content[:3500]
        append_journal(config, session.topic, f"### Web\n\n{body}")
        return res.ok, body[:800], None
    except Exception as exc:  # noqa: BLE001
        msg = f"Web: {exc}"
        append_journal(config, session.topic, msg)
        return True, msg, None


def step_inbox(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    ok, msg, path = copy_random_model_to_cascadeur_inbox(config, topic=session.topic)
    if not ok:
        from ..integrations.cascadeur.paths import cascadeur_inbox

        existing = sorted(cascadeur_inbox(config).glob("*.fbx"))
        if existing:
            ok = True
            msg = f"{msg}\nВ Inbox уже есть: {existing[0].name} — продолжаю."
            path = existing[0]
    session.inbox_ok = ok
    append_journal(config, session.topic, f"### Inbox (случайная модель)\n\n{msg}")
    art = str(path) if path else None
    if art:
        session.artifacts.append(art)
    return ok, msg, art


def step_launch(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    mon = lab_monitor_index(config)
    ok, msg = ensure_cascadeur_running(config, monitor_index=mon)
    session.launch_ok = ok and find_cascadeur_hwnd() is not None
    if ok and not session.launch_ok:
        ok = False
        msg = msg + "\nПроцесс есть, но окно Cascadeur не найдено — повтори шаг."
    append_journal(config, session.topic, f"### Запуск Cascadeur (монитор {mon + 1})\n\n{msg}")
    return ok, msg, None


def step_mouse_focus(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    from ..integrations.input.mouse import focus_window_center, lab_mouse_allowed

    if not lab_mouse_allowed(config):
        msg = (
            "Мышь: пропуск — ты дома (lab не трогает курсор) "
            "или VIU_LAB_MOUSE=0."
        )
        append_journal(config, session.topic, f"### Мышь\n\n{msg}")
        return True, msg, None

    hwnd = find_cascadeur_hwnd()
    if not hwnd:
        msg = "Окно Cascadeur не найдено — клик пропущен."
        append_journal(config, session.topic, f"### Мышь\n\n{msg}")
        return True, msg, None

    ok, msg = focus_window_center(hwnd)
    append_journal(config, session.topic, f"### Мышь\n\n{msg}")
    return ok, msg, None


def step_capture(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    if not session.launch_ok:
        msg = "Пропуск скрина: Cascadeur не запущен (шаг 5 не пройден)."
        append_journal(config, session.topic, f"### Скрин\n\n{msg}")
        return False, msg, None
    import time

    time.sleep(2.5)
    shot = artifacts_dir(config, session.topic) / f"cascadeur_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    hwnd = find_cascadeur_hwnd()
    if hwnd:
        ok, msg = capture_window_png(shot, hwnd=hwnd)
    else:
        ok, msg = capture_window_png(shot, title_substr="Cascadeur")
    append_journal(config, session.topic, f"### Скрин\n\n{msg}")
    if ok:
        session.artifacts.append(str(shot))
    return ok, msg, str(shot) if ok else None


def step_report(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    jpath = journal_path(config, session.topic)
    tail = ""
    if jpath.is_file():
        try:
            tail = jpath.read_text(encoding="utf-8", errors="replace")[-4000:]
        except OSError:
            pass
    arts = "\n".join(f"- {a}" for a in session.artifacts[-8:])
    report = (
        "Лаборатория Cascadeur — итерация завершена.\n\n"
        f"Артефакты:\n{arts or '(нет)'}\n\n"
        "Жду оценки: техника, изобретательность, старание, полезность, ясность (1–5).\n\n"
        f"Journal: {jpath}\n\n"
        "--- хвост journal ---\n"
        f"{tail[-1500:]}"
    )
    session.last_report = report
    session.status = "awaiting_rating"
    append_journal(config, session.topic, f"### Отчёт\n\n{report[:2000]}")
    notify_lab_awaiting_rating(config, report[:800])
    return True, report, None


STEPS: list[Callable[[Config, LabSession], StepResult]] = [
    step_status,
    step_models_scan,
    step_research,
    step_inbox,
    step_launch,
    step_mouse_focus,
    step_capture,
    step_report,
]

# Не переходить к следующему шагу, пока этот не удался (0-based индекс).
BLOCK_ON_FAIL = frozenset({3, 4, 6})  # inbox, launch, capture


def _gate_before_step(config: Config, session: LabSession) -> Optional[Tuple[bool, str]]:
    """Если Cascadeur не поднят — откат к шагу запуска, не скрин/мышь."""
    if session.step in (5, 6) and not session.launch_ok:
        session.step = 4
        save_session(config, session)
        msg = (
            "Cascadeur не запущен — шаг «Запуск» (5) не пройден.\n"
            "Следующее нажатие «Лаборатория» повторит запуск."
        )
        append_journal(config, session.topic, f"### Возврат к запуску\n\n{msg}")
        return True, msg
    return None


def run_one_step(config: Config, session: LabSession) -> Tuple[bool, str]:
    """Выполнить ровно один шаг pipeline. Возвращает (ok, human message)."""
    if session.status not in ("running", "paused"):
        if session.status == "awaiting_rating":
            return True, "Жду оценку — открой «Оценить лабораторию»."
        return True, f"Сессия: {session.status}"

    if session.status == "paused":
        session.status = "running"
        session.pause_reason = ""

    if session.step >= len(STEPS):
        session.status = "completed"
        save_session(config, session)
        return True, "Все шаги выполнены."

    gated = _gate_before_step(config, session)
    if gated is not None:
        return gated

    fn = STEPS[session.step]
    step_idx = session.step + 1
    label = STEP_LABELS[session.step] if session.step < len(STEP_LABELS) else f"шаг {step_idx}"
    ok, msg, _art = fn(config, session)
    session.steps_total = len(STEPS)
    if session.status == "paused":
        save_session(config, session)
        return True, msg

    if not ok and session.step in BLOCK_ON_FAIL:
        session.last_fail_step = session.step
        tail = "\n\n⏸ Шаг не пройден — следующий не начинаю. «Лаборатория» повторит этот шаг."
        save_session(config, session)
        return True, msg + tail

    session.last_fail_step = -1
    session.step += 1
    notify_lab_step(config, step_idx, label, msg)
    if session.step >= len(STEPS) or session.status == "awaiting_rating":
        pass
    else:
        session.status = "running"
    save_session(config, session)
    return ok, msg
