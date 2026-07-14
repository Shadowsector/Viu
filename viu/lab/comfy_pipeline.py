"""Лаборатория Comfy → видео для Cascadeur MoCap."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ..config import Config
from ..integrations.comfy.approval import send_prompt_for_approval
from ..integrations.comfy.generate import run_triple_angles
from ..integrations.comfy.model_pref import PREFERRED_FAMILY, probe_models
from ..integrations.comfy.process import ensure_comfy_running
from ..integrations.comfy.prompts import draft_bundle
from ..integrations.comfy.workflows import (
    ensure_workflow_templates,
    list_workflows,
    workflow_is_stub,
)
from ..integrations.comfy.paths import comfy_workflows_dir, resolve_comfy_root
from .controller import lab_controller
from .notify import notify_lab_awaiting_rating, notify_lab_step
from .paths import task_path
from .session import LabSession, append_journal, load_session, save_session

COMFY_TOPIC = "comfy"

StepResult = Tuple[bool, str, Optional[str]]

STEP_LABELS = [
    "Comfy online",
    "Модели Wan",
    "Черновик промпта",
    "Одобрение Telegram",
    "3 ракурса",
    "Отчёт",
]


def ensure_task_file(config: Config, *, action: str = "") -> Path:
    path = task_path(config, COMFY_TOPIC)
    if not path.is_file() or action.strip():
        body = (
            "# Lab Comfy → Cascadeur MoCap\n\n"
            "Вью сама: ComfyUI (U:\\Viu\\ComfyUI) → Wan 2.1 → 3 ракурса → Lab/Refs.\n"
            "Промпт — на одобрение в Telegram.\n\n"
            f"## action\n\n{(action or 'idle stand, subtle breathing').strip()}\n"
        )
        path.write_text(body, encoding="utf-8")
    return path


def read_action_from_task(config: Config) -> str:
    path = task_path(config, COMFY_TOPIC)
    if not path.is_file():
        return "idle stand, subtle breathing"
    text = path.read_text(encoding="utf-8")
    if "## action" in text.lower():
        after = text.lower().split("## action", 1)[1]
        lines = [ln.strip() for ln in after.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        if lines:
            # recover original casing from file
            raw_after = text.split("## action", 1)[1] if "## action" in text else text.split("## Action", 1)[-1]
            for ln in raw_after.splitlines():
                s = ln.strip()
                if s and not s.startswith("#"):
                    return s
    return "idle stand, subtle breathing"


def _import_workflows_from_comfy_install(config: Config) -> List[str]:
    """Подтянуть API JSON из U:\\Viu\\ComfyUI\\user\\… если Вью-шаблоны ещё stub."""
    root = resolve_comfy_root(config)
    if root is None:
        return []
    dest = comfy_workflows_dir(config)
    imported: List[str] = []
    search_roots = [
        root / "user" / "default" / "workflows",
        root / "user" / "workflows",
        root / "workflows",
    ]
    keywords = ("wan", "t2v", "i2v", "text_to_video", "image_to_video")
    for sroot in search_roots:
        if not sroot.is_dir():
            continue
        for src in sroot.rglob("*.json"):
            name_l = src.name.lower()
            if not any(k in name_l for k in keywords):
                continue
            target_name = "i2v.json" if "i2v" in name_l or "image" in name_l else "t2v.json"
            target = dest / target_name
            if target.is_file() and not workflow_is_stub(target):
                continue
            try:
                import json
                import shutil

                data = json.loads(src.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "nodes" in data:
                    continue  # UI format
                shutil.copy2(src, target)
                if target_name == "t2v.json":
                    default = dest / "default.json"
                    if (not default.is_file()) or workflow_is_stub(default):
                        shutil.copy2(src, default)
                imported.append(f"{src.name} → {target_name}")
            except (OSError, json.JSONDecodeError, ValueError):
                continue
    return imported


def step_ensure_comfy(config: Config, session: LabSession) -> StepResult:
    if lab_controller.should_abort_step():
        lab_controller.acknowledge_abort()
        session.status = "paused"
        session.pause_reason = "operator"
        return True, "Пауза lab (оператор).", None
    ok, msg = ensure_comfy_running(config)
    append_journal(config, COMFY_TOPIC, f"### Comfy online\n\n{msg}")
    if not ok:
        return False, msg, None
    ensure_workflow_templates(config)
    imported = _import_workflows_from_comfy_install(config)
    if imported:
        msg += "\nИмпорт workflow: " + "; ".join(imported)
    return True, msg, None


def step_models(config: Config, session: LabSession) -> StepResult:
    probe = probe_models(config)
    lines = [f"Модель: {PREFERRED_FAMILY}", f"root={probe.root}"]
    lines.extend(f"• {n}" for n in probe.notes)
    msg = "\n".join(lines)
    append_journal(config, COMFY_TOPIC, f"### Модели\n\n{msg}")
    session.meta["model_ready_t2v"] = probe.ready_t2v
    session.meta["model_ready_i2v"] = probe.ready_i2v
    # Не блокируем жёстко — генерация всё равно проверит workflow.
    if not probe.ready_t2v:
        return True, msg + "\n⚠ T2V ещё не готов — скачаю/доставлю модели отдельно, промпт можно одобрять.", None
    return True, msg, None


def step_draft_prompt(config: Config, session: LabSession) -> StepResult:
    action = str(session.meta.get("action") or "").strip() or read_action_from_task(config)
    session.meta["action"] = action
    draft = draft_bundle(action)
    session.meta["draft"] = draft
    append_journal(config, COMFY_TOPIC, f"### Черновик промпта\n\n{draft}")
    return True, f"Черновик готов для «{action[:80]}».", None


def step_request_approval(config: Config, session: LabSession) -> StepResult:
    action = str(session.meta.get("action") or read_action_from_task(config))
    draft = str(session.meta.get("draft") or draft_bundle(action))
    sent, msg = send_prompt_for_approval(config, action, draft)
    session.status = "awaiting_prompt"
    session.meta["approval_sent"] = sent
    save_session(config, session)
    append_journal(config, COMFY_TOPIC, f"### Одобрение\n\n{msg}\n\n{draft}")
    # Пауза: не двигаем step в run_one_step пока status awaiting_prompt —
    # step уже будет инкрементирован... need careful handling.
    return True, msg, None


def apply_prompt_decision(
    config: Config,
    session: LabSession,
    decision: str,
    payload: str,
) -> str:
    """После ответа Дена: approve/edit → running; reject → completed. Генерацию запускает GUI/lab_step."""
    if decision == "reject":
        session.status = "completed"
        session.pause_reason = "prompt_rejected"
        session.meta["approved"] = False
        save_session(config, session)
        append_journal(config, COMFY_TOPIC, "### Промпт отклонён\n\nСтоп по ответу Дена.")
        return "Ок, Comfy-промпт отменила."

    action = payload.strip() if decision == "edit" else str(session.meta.get("action") or payload)
    if decision == "edit":
        session.meta["action"] = action
        session.meta["draft"] = draft_bundle(action)
        ensure_task_file(config, action=action)

    session.meta["approved"] = True
    session.meta["approved_action"] = action
    session.status = "running"
    if session.step < 4:
        session.step = 4
    save_session(config, session)
    append_journal(
        config,
        COMFY_TOPIC,
        f"### Промпт одобрен\n\naction: {action}\n\nДальше — 3 ракурса.",
    )
    return (
        f"Промпт принят («{action[:80]}»).\n"
        "Запускаю 3 ракурса (сбоку / ¾ / анфас) → Lab/Refs."
    )


def step_generate_triple(config: Config, session: LabSession) -> StepResult:
    if session.status == "awaiting_prompt":
        return True, "Жду одобрение промпта в Telegram (ок / правки / стоп).", None
    if not session.meta.get("approved"):
        session.status = "awaiting_prompt"
        save_session(config, session)
        return True, "Промпт ещё не одобрен — жду Telegram.", None

    action = str(session.meta.get("approved_action") or session.meta.get("action") or "")
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in action.lower())[:40] or "mocap"
    ok, msg, results = run_triple_angles(config, action=action, slug=slug)
    session.meta["triple"] = results
    for path in results.get("files") or []:
        session.append_artifact(path)
    append_journal(config, COMFY_TOPIC, f"### 3 ракурса\n\n{msg}")
    if not ok:
        return False, msg, None
    return True, msg, None


def step_report(config: Config, session: LabSession) -> StepResult:
    action = session.meta.get("approved_action") or session.meta.get("action")
    files = session.artifacts[-9:]
    report = (
        f"Comfy MoCap итерация id={session.id}\n"
        f"action: {action}\n"
        f"model: {PREFERRED_FAMILY}\n"
        f"файлы ({len(files)}):\n"
        + "\n".join(f"  • {f}" for f in files)
        + "\n\nДальше: Cascadeur MoCap по mp4 из Lab/Refs — сравним какой ракурс лучше читается."
    )
    session.last_report = report
    session.status = "awaiting_rating"
    append_journal(config, COMFY_TOPIC, f"### Отчёт\n\n{report}")
    notify_lab_awaiting_rating(config, report[:800])
    return True, report, None


STEPS: list[Callable[[Config, LabSession], StepResult]] = [
    step_ensure_comfy,
    step_models,
    step_draft_prompt,
    step_request_approval,
    step_generate_triple,
    step_report,
]


def run_one_step(config: Config, session: LabSession) -> Tuple[bool, str]:
    if session.status == "awaiting_prompt":
        return True, "Жду одобрение промпта в Telegram (ок / правки: … / стоп)."
    if session.status == "awaiting_rating":
        return True, "Жду оценку — «Оценить лабораторию»."
    if session.status not in ("running", "paused"):
        return True, f"Сессия: {session.status}"

    if session.status == "paused":
        session.status = "running"
        session.pause_reason = ""

    if session.step >= len(STEPS):
        session.status = "completed"
        save_session(config, session)
        return True, "Все шаги Comfy выполнены."

    fn = STEPS[session.step]
    step_idx = session.step + 1
    label = STEP_LABELS[session.step]
    ok, msg, _art = fn(config, session)

    # После request_approval статус awaiting_prompt — не инкрементим step за пределы;
    # step остаётся на generate (следующий), approval step считается пройденным.
    if session.status == "awaiting_prompt":
        # Переходим указатель на шаг генерации, но ждём
        if session.step == 3:  # approval step index
            session.step = 4
        session.steps_total = len(STEPS)
        save_session(config, session)
        notify_lab_step(config, step_idx, label, msg)
        return True, msg

    if session.status == "paused":
        save_session(config, session)
        return True, msg

    if not ok and session.step == 4:  # generate
        session.last_fail_step = session.step
        session.last_fail_msg = msg[:2000]
        key = str(session.step)
        session.step_fail_counts[key] = session.step_fail_counts.get(key, 0) + 1
        save_session(config, session)
        return True, msg + "\n\n⏸ Генерация не прошла — поправлю workflow/модели и повторю."

    session.last_fail_step = -1
    session.step += 1
    session.steps_total = len(STEPS)
    notify_lab_step(config, step_idx, label, msg)
    if session.status != "awaiting_rating":
        session.status = "running"
    save_session(config, session)
    return ok, msg


def run_until_done(
    config: Config,
    session: LabSession,
    *,
    max_steps: int = 16,
) -> Tuple[bool, str]:
    lines: list[str] = []
    steps_run = 0
    while steps_run < max_steps:
        session = load_session(config, COMFY_TOPIC) or session
        if session.status in ("awaiting_prompt", "awaiting_rating", "completed"):
            if session.status == "awaiting_prompt":
                lines.append("Жду одобрение промпта в Telegram.")
            elif session.status == "awaiting_rating":
                lines.append("Итерация готова — жду оценку.")
            else:
                lines.append("Сессия завершена.")
            break
        if session.status not in ("running", "paused"):
            lines.append(f"Статус: {session.status}")
            break
        before = session.step
        ok, msg = run_one_step(config, session)
        steps_run += 1
        session = load_session(config, COMFY_TOPIC) or session
        label = STEP_LABELS[min(before, len(STEP_LABELS) - 1)]
        lines.append(f"[{steps_run}] «{label}»: {msg[:500]}")
        if not ok:
            break
        # Если остались на том же step без awaiting — защита от цикла
        if session.step == before and session.status == "running":
            break
    return True, "\n".join(lines) if lines else "Нет шагов."
