"""Задание и шаги лаборатории Cascadeur."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from ..config import Config
from ..integrations.cascadeur import cascadeur_status
from ..integrations.cascadeur.launch import ensure_cascadeur_running
from ..integrations.cascadeur.window import find_cascadeur_hwnd
from ..tools.web import search_web
from .controller import lab_controller
from .models_inbox import build_models_summary, copy_random_model_to_cascadeur_inbox
from .notify import notify_lab_awaiting_rating, notify_lab_step, notify_lab_stuck
from .paths import apply_lab_vram_env, artifacts_dir, journal_path, lab_monitor_index, task_path
from .session import LabSession, append_journal, load_session, save_session

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
6. **Import FBX** — Python-команда `Viu.Lab Import` + pending JSON (или File → Import).
7. **Мышь** — фокус окна кликом в центр (`VIU_LAB_MOUSE=1`, Windows).
8. **Скрин** — зафиксировать UI после паузы (Ден может смотреть на 3-м мониторе).
9. **Отчёт** — journal + запрос оценки; в **автономном режиме** — кратко в Telegram.

Решай сама. Спроси Дена только если застряла (шаг не прошёл) или в итоговом отчёте.

## Ограничения

- **VRAM lab ~10 GB** — не грузи одновременно тяжёлые vision-модели без нужды.
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


def _append_artifact(session: LabSession, art: Optional[str]) -> None:
    session.append_artifact(art)


def _journal_tail_for_report(text: str, *, max_chars: int = 1200) -> str:
    """Последние блоки journal без мусора из web-fetch (JSON-LD и т.п.)."""
    blocks: list[str] = []
    for m in re.finditer(r"### ([^\n]+)\n\n(.*?)(?=\n### |\Z)", text, re.DOTALL):
        title = m.group(1).strip()
        body = m.group(2).strip()
        if "schema.org" in body or "@type" in body and len(body) > 400:
            body = re.sub(r"\{[^{}]*schema\.org[^{}]*\}", "", body)
            body = _WS_RE.sub(" ", body).strip()[:400]
        if title.lower() == "web":
            body = body[:450]
        else:
            body = body[:550]
        if body:
            blocks.append(f"### {title}\n{body}")
    if not blocks:
        clean = re.sub(r"\{[^{}]*schema\.org[^{}]*\}", "", text)
        return clean.strip()[-max_chars:]
    joined = "\n\n".join(blocks[-6:])
    return joined[-max_chars:]


_WS_RE = re.compile(r"\s+")


def _iteration_outcome(session: LabSession) -> Tuple[str, str]:
    """(код, человекочитаемое описание): SUCCESS | PARTIAL | FAIL."""
    if session.viewport_ok and session.capture_verdict == "MODEL_OK":
        return (
            "SUCCESS",
            "✅ Успех: модель в viewport Cascadeur (vision: MODEL_OK).",
        )
    if session.launch_ok and any(a.lower().endswith(".png") for a in session.artifacts):
        v = session.capture_verdict or "?"
        return (
            "PARTIAL",
            f"⚠ Частично: Cascadeur запущен, скрин сохранён, но модель **не** в viewport "
            f"(vision: {v}). Deploy/import-скрипт ≠ импорт в UI.",
        )
    if session.import_deployed:
        return (
            "PARTIAL",
            "⚠ Частично: команда import задеплоена, viewport не проверен.",
        )
    return ("FAIL", "❌ Цель не достигнута: нет подтверждённого скрина с моделью.")


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
    "Import FBX в Cascadeur",
    "Фокус мышью",
    "Скрин UI",
    "Отчёт",
]


def step_models_scan(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    ok, msg, art = build_models_summary(config, topic=session.topic)
    msg = msg + "\n(Blender rig-check — headless, окно не показывается.)"
    append_journal(config, session.topic, f"### Модели (rig-check)\n\n{msg}")
    if art:
        _append_artifact(session, art)
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
        query = "Cascadeur export FBX to Unity workflow retarget import"
        hits = search_web(query, max_results=5)
        body = "\n".join(f"- {h}" for h in hits) if hits else "Ничего не найдено по запросу."
        if "schema.org" in body:
            body = re.sub(r"\{[^{}]*schema\.org[^{}]*\}", "", body)
            body = _WS_RE.sub(" ", body).strip()
        append_journal(config, session.topic, f"### Web\n\n{body[:2000]}")
        return True, body[:800], None
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
        _append_artifact(session, art)
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


def step_import_fbx(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    if not session.launch_ok:
        msg = "Пропуск import: Cascadeur не запущен (шаг 5 не пройден)."
        append_journal(config, session.topic, f"### Import FBX\n\n{msg}")
        return False, msg, None

    from ..integrations.cascadeur.import_fbx import latest_inbox_fbx, trigger_fbx_import
    from ..integrations.cascadeur.window import focus_cascadeur_window

    import time

    focus_cascadeur_window()
    fbx = latest_inbox_fbx(config)
    ok, msg, opened = trigger_fbx_import(config, fbx, topic=session.topic)
    session.import_deployed = ok
    session.import_auto = opened
    session.import_ok = False
    session.viewport_ok = False
    if opened:
        session.import_ok = True  # tentative — vision на шаге скрина подтвердит
    time.sleep(2.0 if opened else 0.5)
    append_journal(config, session.topic, f"### Import FBX\n\n{msg}")
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
    from ..integrations.cascadeur.capture import capture_and_verify_cascadeur
    from ..integrations.cascadeur.window import find_cascadeur_hwnd
    from ..integrations.apps.process import app_running

    from ..integrations.cascadeur.import_fbx import latest_inbox_fbx

    if not session.launch_ok and not app_running("cascadeur"):
        msg = "Пропуск скрина: Cascadeur не запущен (шаг 5 не пройден)."
        append_journal(config, session.topic, f"### Скрин\n\n{msg}")
        return False, msg, None

    import time

    session.launch_ok = session.launch_ok or find_cascadeur_hwnd() is not None
    time.sleep(1.5)
    shot = artifacts_dir(config, session.topic) / f"cascadeur_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    mon = lab_monitor_index(config)
    has_fbx = latest_inbox_fbx(config) is not None
    ok, msg, meta = capture_and_verify_cascadeur(
        config,
        shot,
        monitor_index=mon,
        require_model=has_fbx,
    )
    verdict = str(meta.get("verdict") or "UNKNOWN")
    session.capture_verdict = verdict
    if meta.get("verdict") == "MODEL_OK":
        session.viewport_ok = True
        session.import_ok = True
    append_journal(config, session.topic, f"### Скрин\n\n{msg}")
    if ok:
        _append_artifact(session, str(shot))
    return ok, msg, str(shot) if ok else None


def step_report(config: Config, session: LabSession) -> StepResult:
    aborted = _check_abort(session)
    if aborted:
        return aborted
    jpath = journal_path(config, session.topic)
    tail = ""
    if jpath.is_file():
        try:
            raw = jpath.read_text(encoding="utf-8", errors="replace")
            tail = _journal_tail_for_report(raw)
        except OSError:
            pass
    arts = "\n".join(f"- {a}" for a in session.artifacts[-8:])
    outcome_code, outcome_text = _iteration_outcome(session)
    import_hint = ""
    if session.import_deployed and not session.viewport_ok:
        import_hint = (
            "\n--- Что сделать вручную ---\n"
            "1. Cascadeur → **New scene**\n"
            "2. **File → Import → Fbx/Dae** — preset **Scene**, Add new, Open first take\n"
            "   или **Commands → Reload scripts → Viu → LabImport**\n"
            "3. Rig Mode Helper → **No**\n"
            "4. Снова «Лаборатория» (или только шаг скрина после импорта)\n"
        )
    elif session.import_ok and not session.import_auto:
        import_hint = (
            "\n⚠ FBX открыт без ассоциации .fbx — проверь диалог Import на скрине.\n"
        )
    report = (
        f"Лаборатория Cascadeur — итерация завершена [{outcome_code}].\n\n"
        f"{outcome_text}\n\n"
        f"Артефакты:\n{arts or '(нет)'}\n"
        f"{import_hint}\n"
        "Жду оценки: техника, изобретательность, старание, полезность, ясность (1–5).\n"
        "Оценивай по факту: PARTIAL = пайплайн не доведён до модели в viewport.\n\n"
        f"Journal: {jpath}\n\n"
        "--- хвост journal ---\n"
        f"{tail}"
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
    step_import_fbx,
    step_mouse_focus,
    step_capture,
    step_report,
]

# Не переходить к следующему шагу, пока этот не удался (0-based индекс).
BLOCK_ON_FAIL = frozenset({3, 4, 5, 7})  # inbox, launch, import, capture


def _gate_before_step(config: Config, session: LabSession) -> Optional[Tuple[bool, str]]:
    """Если Cascadeur не поднят — откат к шагу запуска, не скрин/мышь."""
    if session.step in (5, 6, 7) and not session.launch_ok:
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
        session.last_fail_msg = msg[:2000]
        key = str(session.step)
        session.step_fail_counts[key] = session.step_fail_counts.get(key, 0) + 1
        n = session.step_fail_counts[key]
        tail = (
            f"\n\n⏸ Шаг не пройден ({n}×). "
            "Следующая «Лаборатория»: recover (диагностика + web + vision), не слепой повтор."
        )
        if n >= 2:
            tail += " Уже 2+ — нажми «Lab: весь цикл» или run_all для recover."
        save_session(config, session)
        notify_lab_stuck(config, session, msg, step_label=label)
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


def run_until_done(
    config: Config,
    session: LabSession,
    *,
    max_steps: int = 24,
) -> Tuple[bool, str]:
    """Выполнить шаги до awaiting_rating, паузы или блокировки (автономный цикл)."""
    lines: list[str] = []
    steps_run = 0
    topic = session.topic

    while steps_run < max_steps:
        session = load_session(config, topic) or session
        if session.status == "awaiting_rating":
            lines.append("Итерация завершена — жду оценку.")
            break
        if session.status == "completed":
            lines.append("Сессия завершена.")
            break
        if session.status not in ("running", "paused"):
            lines.append(f"Статус: {session.status}")
            break

        before_step = session.step
        ok, msg = run_one_step(config, session)
        steps_run += 1
        session = load_session(config, topic) or session
        idx = min(before_step, len(STEP_LABELS) - 1)
        label = STEP_LABELS[idx]
        lines.append(
            f"[{steps_run}] шаг {before_step + 1}/{session.steps_total} «{label}»: {msg[:500]}"
        )

        if session.status == "paused":
            lines.append("Пауза — приоритет оператора.")
            break
        if session.last_fail_step >= 0:
            break

    summary = "\n\n".join(lines[-6:]) if lines else "Нет шагов."
    if steps_run >= max_steps:
        summary += f"\n\n(лимит {max_steps} шагов — продолжи lab_step run_all=1)"
    return True, summary
