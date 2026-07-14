"""Лаборатория Comfy → видео для Cascadeur MoCap."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

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
    "Выбор лучшего клипа",
    "Отчёт",
]


def ensure_task_file(config: Config, *, action: str = "") -> Path:
    path = task_path(config, COMFY_TOPIC)
    if not path.is_file() or action.strip():
        body = (
            "# Lab Comfy → Cascadeur MoCap\n\n"
            "Вью сама: ComfyUI → Wan 2.1 → 3 ракурса → ты выбираешь лучший → "
            "kept/ + last-frame seed.\n"
            "Промпт — на одобрение в Telegram.\n\n"
            f"## action\n\n"
            f"{(action or 'idle stand, subtle breathing').strip()}\n"
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
                    from ..integrations.comfy.ui_to_api import ui_workflow_to_api

                    data = ui_workflow_to_api(data)
                    target.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                else:
                    shutil.copy2(src, target)
                if target_name == "t2v.json":
                    default = dest / "default.json"
                    if (not default.is_file()) or workflow_is_stub(default):
                        shutil.copy2(target, default)
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
    # Если нет установки — Вью сама ставит; если есть — только запуск + лог.
    ok, msg = ensure_comfy_running(config, auto_install=True, wait_seconds=180.0)
    append_journal(config, COMFY_TOPIC, f"### Comfy online\n\n{msg}")
    if not ok:
        return False, msg, None
    ensure_workflow_templates(config, overwrite_stubs=True)
    try:
        from ..integrations.comfy.install import download_wan_workflows

        ok_wf, wf_msg = download_wan_workflows(config)
        if wf_msg:
            msg += "\n" + wf_msg
    except Exception as exc:  # noqa: BLE001
        msg += f"\nworkflows: {exc}"
    imported = _import_workflows_from_comfy_install(config)
    if imported:
        msg += "\nИмпорт workflow: " + "; ".join(imported)
    return True, msg, None


def step_models(config: Config, session: LabSession) -> StepResult:
    probe = probe_models(config)
    lines = [f"Модель: {PREFERRED_FAMILY}", f"root={probe.root}"]
    lines.extend(f"• {n}" for n in probe.notes)
    if probe.root and not probe.ready_t2v:
        try:
            from ..integrations.comfy.install import download_wan_models

            ok_m, m_msg = download_wan_models(probe.root, include_i2v=False)
            lines.append("Докачка T2V:\n" + m_msg)
            probe = probe_models(config)
            lines.append(f"T2V ready после докачки: {probe.ready_t2v}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"докачка: {exc}")
    msg = "\n".join(lines)
    append_journal(config, COMFY_TOPIC, f"### Модели\n\n{msg}")
    session.meta["model_ready_t2v"] = probe.ready_t2v
    session.meta["model_ready_i2v"] = probe.ready_i2v
    if not probe.ready_t2v:
        return True, msg + "\n⚠ T2V ещё не готов — повтори lab или comfy_install.", None
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

    from ..integrations.comfy.clip_review import (
        format_candidates_message,
        register_triple_batch,
    )

    clips = register_triple_batch(config, action=action, results=results)
    session.meta["clip_batch_id"] = str(results.get("slug") or "")
    session.meta["clip_candidate_ids"] = [c.id for c in clips]
    pick_msg = format_candidates_message(clips)
    append_journal(config, COMFY_TOPIC, f"### Выбор клипа\n\n{pick_msg}")
    return True, msg + "\n\n" + pick_msg, None


def step_await_clip_pick(config: Config, session: LabSession) -> StepResult:
    """Пауза: Ден выбирает лучший из 3 ракурсов."""
    if session.meta.get("clip_kept_id"):
        return True, f"Клип уже выбран: {session.meta.get('clip_kept_id')}.", None
    from ..integrations.comfy.clip_review import ComfyClipStore, clip_review_path, format_candidates_message

    batch = str(session.meta.get("clip_batch_id") or "")
    store = ComfyClipStore(clip_review_path(config)).load()
    cands = store.by_batch(batch) if batch else store.pending_candidates()
    cands = [c for c in cands if c.status == "candidate"]
    if not cands:
        # нечего выбирать — пропускаем
        return True, "Нет кандидатов — пропускаю выбор.", None
    session.status = "awaiting_clip_pick"
    save_session(config, session)
    msg = format_candidates_message(cands)
    try:
        from ..integrations.telegram import settings as tg_settings
        from ..integrations.telegram.client import TelegramClient

        if tg_settings.enabled(config):
            token = tg_settings.token(config)
            chat_id = tg_settings.chat_id(config)
            if token and chat_id:
                TelegramClient(token).send_message(
                    chat_id, "🎞 Comfy: выбери лучший клип\n\n" + msg[:1500]
                )
    except Exception:
        pass
    return True, msg, None


def apply_clip_pick_decision(
    config: Config,
    session: LabSession,
    decision: str,
    payload: Dict[str, Any],
) -> str:
    """После выбора клипа: keep/reject_all → продолжить lab."""
    from ..integrations.comfy.clip_review import keep_best_by_angle, reject_batch

    batch = str(session.meta.get("clip_batch_id") or "")
    if decision == "reject_all":
        ok, msg = reject_batch(config, batch)
        session.meta["clip_rejected_all"] = True
        session.status = "running"
        if session.step < 6:
            session.step = 6
        save_session(config, session)
        append_journal(config, COMFY_TOPIC, f"### Клипы отклонены\n\n{msg}")
        return msg + "\nМожно снова comfy_mocap с другим промптом."

    angle = str(payload.get("angle") or "front")
    score = int(payload.get("score") or 4)
    notes = str(payload.get("notes") or "")
    ok, msg, clip = keep_best_by_angle(
        config,
        batch,
        angle,
        score=score,
        notes=notes,
        catalog_slug=str(session.meta.get("catalog_slug") or ""),
        enters_from=list(session.meta.get("enters_from") or []),
        exits_to=list(session.meta.get("exits_to") or []),
    )
    if not ok or clip is None:
        return msg
    session.meta["clip_kept_id"] = clip.id
    session.meta["clip_kept_path"] = clip.path
    session.meta["clip_seed_frame"] = clip.seed_frame
    session.append_artifact(clip.path)
    if clip.seed_frame:
        session.append_artifact(clip.seed_frame)
    session.status = "running"
    if session.step < 6:
        session.step = 6
    save_session(config, session)
    append_journal(config, COMFY_TOPIC, f"### Клип выбран\n\n{msg}")
    return msg + "\nДальше — отчёт lab."


def step_report(config: Config, session: LabSession) -> StepResult:
    action = session.meta.get("approved_action") or session.meta.get("action")
    kept = session.meta.get("clip_kept_path")
    seed = session.meta.get("clip_seed_frame")
    files = session.artifacts[-12:]
    report = (
        f"Comfy MoCap итерация id={session.id}\n"
        f"action: {action}\n"
        f"model: {PREFERRED_FAMILY}\n"
        f"kept: {kept or '— (не выбран)'}\n"
        f"seed last-frame: {seed or '—'}\n"
        f"файлы ({len(files)}):\n"
        + "\n".join(f"  • {f}" for f in files)
        + "\n\nДальше: Cascadeur MoCap по kept mp4; next clip можно стартовать с seed PNG (I2V)."
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
    step_await_clip_pick,
    step_report,
]


def run_one_step(config: Config, session: LabSession) -> Tuple[bool, str]:
    if session.status == "awaiting_prompt":
        return True, "Жду одобрение промпта в Telegram (ок / правки: … / стоп)."
    if session.status == "awaiting_clip_pick":
        return True, (
            "Жду выбор клипа: `лучший: front` / `лучший: side 5` / `отклонить все` "
            "или кнопка «Оценить клипы Comfy»."
        )
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

    if session.status == "awaiting_prompt":
        if session.step == 3:
            session.step = 4
        session.steps_total = len(STEPS)
        save_session(config, session)
        notify_lab_step(config, step_idx, label, msg)
        return True, msg

    if session.status == "awaiting_clip_pick":
        # указатель на шаг выбора уже текущий; ждём ответа
        session.steps_total = len(STEPS)
        save_session(config, session)
        notify_lab_step(config, step_idx, label, msg)
        return True, msg

    if session.status == "paused":
        save_session(config, session)
        return True, msg

    if not ok and session.step in (0, 4):
        session.last_fail_step = session.step
        session.last_fail_msg = msg[:2000]
        key = str(session.step)
        session.step_fail_counts[key] = session.step_fail_counts.get(key, 0) + 1
        save_session(config, session)
        if session.step == 0:
            hint = (
                "\n\n⏸ Comfy не ответила на :8188. "
                "Не клонирую заново — смотри `.viu/logs/comfy_launch.log` "
                "или снова `comfy_ensure`."
            )
        else:
            hint = "\n\n⏸ Генерация не прошла — поправлю workflow/модели и повторю."
        return True, msg + hint

    session.last_fail_step = -1
    session.step += 1
    session.steps_total = len(STEPS)
    notify_lab_step(config, step_idx, label, msg)
    if session.status not in ("awaiting_rating", "awaiting_clip_pick"):
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
        if session.status in (
            "awaiting_prompt",
            "awaiting_clip_pick",
            "awaiting_rating",
            "completed",
        ):
            if session.status == "awaiting_prompt":
                lines.append("Жду одобрение промпта в Telegram.")
            elif session.status == "awaiting_clip_pick":
                lines.append("Жду выбор лучшего клипа.")
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
        if session.step == before and session.status == "running":
            break
    return True, "\n".join(lines) if lines else "Нет шагов."
