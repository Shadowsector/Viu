"""Лаборатория Comfy → видео для Cascadeur MoCap."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from ..config import Config
from ..integrations.comfy.generate import run_triple_angles
from ..integrations.comfy.model_pref import PREFERRED_FAMILY, probe_models
from ..integrations.comfy.process import ensure_comfy_running
from ..integrations.comfy.prompts import draft_bundle, mocap_take_count
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
    "Панель съёмки",
    "Выбор LoRA",
    "5 дублей (¾)",
    "Выбор лучшего дубля",
    "Отчёт",
]


def ensure_task_file(config: Config, *, action: str = "") -> Path:
    path = task_path(config, COMFY_TOPIC)
    plan_slug = ""
    plan_looped = False
    if not action.strip():
        from .comfy_director import invent_next_shot

        plan = invent_next_shot(config)
        action = plan.action
        plan_slug = plan.catalog_slug
        plan_looped = plan.looped
    if not path.is_file() or action.strip():
        kind = "looped цикл" if plan_looped else "переход/жест"
        body = (
            "# Lab Comfy → Cascadeur MoCap\n\n"
            "Вью выбирает дыру графа (не idle, пока есть другие wave 1).\n"
            "Промпт — Telegram дома; в режиме «Нет дома» — сама одобряет.\n\n"
            f"## catalog_slug\n\n{plan_slug or '(из session.meta)'}\n\n"
            f"## kind\n\n{kind}\n\n"
            f"## action\n\n{action.strip()}\n"
        )
        path.write_text(body, encoding="utf-8")
    return path


def read_action_from_task(config: Config) -> str:
    path = task_path(config, COMFY_TOPIC)
    if not path.is_file():
        from .comfy_director import invent_next_action

        return invent_next_action(config)
    text = path.read_text(encoding="utf-8")
    if "## action" in text.lower():
        after = text.lower().split("## action", 1)[1]
        lines = [ln.strip() for ln in after.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        if lines:
            raw_after = text.split("## action", 1)[1] if "## action" in text else text.split("## Action", 1)[-1]
            for ln in raw_after.splitlines():
                s = ln.strip()
                if s and not s.startswith("#"):
                    return s
    from .comfy_director import invent_next_action

    return invent_next_action(config)


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
    from ..integrations.comfy.prompts import clean_action_for_wan, draft_bundle
    from ..integrations.comfy.show_profile import (
        draft_show_bundle,
        find_show_unet,
        is_show_profile,
        show_style_from_meta,
    )

    action = str(session.meta.get("action") or "").strip() or read_action_from_task(config)
    action = clean_action_for_wan(action)
    session.meta["action"] = action
    if is_show_profile(session.meta):
        unet, unet_note = find_show_unet(config)
        style = show_style_from_meta(session.meta)
        draft = draft_show_bundle(
            action,
            style=style,
            unet_note=unet_note,
            has_smoothmix=bool(unet),
        )
        label = f"шоу ({style})"
    else:
        draft = draft_bundle(action)
        label = "MoCap"
    session.meta["draft"] = draft
    append_journal(config, COMFY_TOPIC, f"### Черновик промпта ({label})\n\n{draft}")
    return True, f"Черновик {label} готов для «{action[:80]}».", None


def _is_directed_shoot(session: LabSession) -> bool:
    """Съёмка по кнопке/чату — человеку нужна живая панель, не автопропуск."""
    meta = session.meta or {}
    if meta.get("shoot_intent") or meta.get("auto_approved_shoot"):
        return True
    reason = str(meta.get("shot_reason") or "").strip().lower()
    return reason.startswith("chat:")


def step_request_approval(config: Config, session: LabSession) -> StepResult:
    """Панель съёмки в Telegram. Генерация только после «Снять».

    Исключение: съёмка из GUI «СЪЁМКА ВИДЕО» (from_shoot_panel) —
    промпт уже согласован в панели → сразу генерация, без «План MoCap».
    """
    from ..integrations.comfy.comfy_panel import apply_setup_and_start, send_control_panel
    from ..integrations.telegram import settings as tg_settings

    action = str(session.meta.get("action") or read_action_from_task(config))
    draft = str(session.meta.get("draft") or draft_bundle(action))
    session.meta["action"] = action
    session.meta["draft"] = draft
    session.meta.pop("lora_pick_done", None)

    # Панель «Съёмка» уже сохранила промпт и нажала «Снять».
    if session.meta.pop("from_shoot_panel", None):
        session.meta["approved_action"] = action
        msg = apply_setup_and_start(config, session, jump_to_generate=True)
        append_journal(config, COMFY_TOPIC, f"### Съёмка из панели\n\n{msg}\n\n{draft}")
        return True, msg, None

    try:
        from ..presence import is_away

        away = is_away(config)
    except Exception:
        away = False

    directed = _is_directed_shoot(session)
    tg_on = bool(tg_settings.enabled(config) and tg_settings.chat_id(config))

    # Тихий away-цикл без shoot: авто (LoRA прошлый + сразу дальше по pipeline).
    if away and not directed:
        session.meta["approved_action"] = action
        session.meta["auto_approved_away"] = True
        last = [int(x) for x in (session.meta.get("lora_last_pick") or []) if str(x).isdigit()]
        session.meta["setup_lora_indices"] = last
        msg = apply_setup_and_start(config, session, jump_to_generate=False)
        append_journal(config, COMFY_TOPIC, f"### Away auto\n\n{msg}\n\n{draft}")
        return True, msg, None

    # Человек у пульта (чат / MoCap / home lab): всегда ждём панель.
    session.status = "awaiting_prompt"
    session.meta["approved"] = False
    if "setup_lora_indices" not in session.meta:
        # дефолт — прошлый выбор, пока Ден не нажмёт LoRA
        pass
    save_session(config, session)

    if tg_on:
        sent, msg = send_control_panel(config, session)
        session.meta["approval_sent"] = sent
        save_session(config, session)
    else:
        msg = (
            "Жду в чате Вью: ок (=снять) | стоп | lora: 1 | промпт comfy.\n"
            f"Сцена: {action[:100]}"
        )
        session.meta["approval_sent"] = False
        save_session(config, session)

    append_journal(config, COMFY_TOPIC, f"### Панель съёмки\n\n{msg}\n\n{draft}")
    return True, msg, None


def apply_prompt_decision(
    config: Config,
    session: LabSession,
    decision: str,
    payload: str,
) -> str:
    """После ответа Дена: approve = «Снять» (сразу генерация); edit/reject/redraft."""
    if decision == "reject":
        session.status = "completed"
        session.pause_reason = "prompt_rejected"
        session.meta["approved"] = False
        save_session(config, session)
        append_journal(config, COMFY_TOPIC, "### Промпт отклонён\n\nСтоп по ответу Дена.")
        return "Ок, съёмку отменила."

    if decision == "redraft":
        return _redraft_comfy_prompt(config, session, note=payload)

    if decision == "edit":
        from .comfy_director import action_for_slug
        from ..integrations.comfy.clip_review import normalize_catalog_slug
        from ..integrations.comfy.mocap_sanitize import extract_slug_token, sanitize_mocap_action
        from ..integrations.comfy.comfy_panel import send_control_panel

        action = payload.strip()
        note_extra = ""
        raw_edit = action.strip()
        slug_tok = extract_slug_token(raw_edit)
        if slug_tok:
            slug = normalize_catalog_slug(slug_tok)
            if slug:
                canonical = action_for_slug(config, slug)
                session.meta["catalog_slug"] = slug
                action, note_extra = sanitize_mocap_action(raw_edit, canonical=canonical)
        elif raw_edit and " " not in raw_edit and re.match(r"^[\w-]+$", raw_edit):
            slug = normalize_catalog_slug(raw_edit)
            if slug:
                action = action_for_slug(config, slug)
                session.meta["catalog_slug"] = slug
        else:
            slug = str(session.meta.get("catalog_slug") or "")
            canonical = action_for_slug(config, slug) if slug else action
            action, note_extra = sanitize_mocap_action(raw_edit, canonical=canonical)
        session.meta["action"] = action
        session.meta.pop("wan_positive", None)
        session.meta.pop("wan_negative", None)
        session.meta["draft"] = draft_bundle(action)
        ensure_task_file(config, action=action)
        session.status = "awaiting_prompt"
        session.meta["approved"] = False
        save_session(config, session)
        sent, panel_msg = send_control_panel(config, session)
        append_journal(
            config,
            COMFY_TOPIC,
            f"### Правка сцены\n\n{action}\n\n{panel_msg}",
        )
        return (
            (note_extra + "\n" if note_extra else "")
            + f"Сцену обновила («{action[:80]}»).\n"
            + panel_msg
        )

    # approve / «Снять» — сразу в генерацию с выбранной LoRA
    from ..integrations.comfy.comfy_panel import apply_setup_and_start

    if payload.strip() and payload.strip() != str(session.meta.get("action") or ""):
        # approve с новым action из парсера
        session.meta["action"] = payload.strip()
    msg = apply_setup_and_start(config, session)
    append_journal(config, COMFY_TOPIC, f"### Снять\n\n{msg}")
    return msg


def _redraft_comfy_prompt(config: Config, session: LabSession, *, note: str = "") -> str:
    from .comfy_director import invent_redraft_shot

    prev_slug = str(session.meta.get("catalog_slug") or "")
    plan = invent_redraft_shot(config, exclude_slug=prev_slug)
    draft = draft_bundle(plan.action)
    session.meta["catalog_slug"] = plan.catalog_slug
    session.meta["action"] = plan.action
    session.meta["approved_action"] = ""
    session.meta["approved"] = False
    session.meta["draft"] = draft
    session.meta["enters_from"] = list(plan.enters_from)
    session.meta["exits_to"] = list(plan.exits_to)
    session.meta["looped"] = plan.looped
    session.meta["shot_reason"] = plan.reason
    session.meta.pop("lora_pick_done", None)
    session.meta.pop("selected_loras", None)
    session.meta.pop("auto_approved_away", None)
    session.step = 3
    session.status = "awaiting_prompt"
    ensure_task_file(config, action=plan.action)
    save_session(config, session)

    from ..integrations.comfy.comfy_panel import send_control_panel

    sent, send_msg = send_control_panel(config, session)
    session.meta["approval_sent"] = sent
    save_session(config, session)
    title = plan.title_ru or plan.catalog_slug
    journal = (
        f"### Другой кадр (redraft)\n\n"
        f"Было: `{prev_slug or '?'}`\n"
        f"Комментарий: {(note or '')[:300]}\n\n"
        f"Новый: `{plan.catalog_slug}` — {plan.action[:200]}\n\n{send_msg}"
    )
    append_journal(config, COMFY_TOPIC, journal)
    return (
        f"Поняла — не тот кадр ({prev_slug or 'предыдущий'}).\n"
        f"Новый: «{title}» (`{plan.catalog_slug}`).\n"
        f"{send_msg}"
    )


def step_request_lora_pick(config: Config, session: LabSession) -> StepResult:
    """После панели «Снять» LoRA уже выбрана — шаг обычно no-op.

    Если сюда попали без lora_pick_done (старый путь) — шлём меню и ждём.
    """
    if session.meta.get("lora_pick_done"):
        picked = session.meta.get("selected_loras") or []
        return True, f"LoRA готовы: {len(picked)} шт.", None

    from ..integrations.comfy.comfy_panel import send_control_panel, send_lora_menu

    entries_exist = True
    try:
        from ..integrations.comfy.lora import scan_loras

        entries_exist = bool(scan_loras(config))
    except Exception:
        entries_exist = False

    if not entries_exist:
        session.meta["selected_loras"] = []
        session.meta["lora_pick_done"] = True
        session.meta["setup_lora_indices"] = []
        return True, "LoRA на диске нет — чистый Wan.", None

    # Вернуть на панель — единый UX.
    session.status = "awaiting_prompt"
    session.meta["approved"] = False
    save_session(config, session)
    send_lora_menu(config, session)
    sent, msg = send_control_panel(config, session)
    append_journal(config, COMFY_TOPIC, f"### LoRA через панель\n\n{msg}")
    return True, "Сначала панель: выбери LoRA, потом «Снять».\n" + msg, None


def apply_lora_pick_decision(
    config: Config,
    session: LabSession,
    indices: List[int],
) -> str:
    """Выбор LoRA только запоминает setup — генерация после «Снять»."""
    from ..integrations.comfy.comfy_panel import (
        send_control_panel,
        set_setup_lora_indices,
    )
    from ..integrations.comfy.lora import (
        scan_loras,
        spec_to_dict,
        specs_from_indices,
    )

    scan_loras(config)
    specs = specs_from_indices(config, indices)
    set_setup_lora_indices(session, indices)
    session.meta["selected_loras"] = [spec_to_dict(s) for s in specs]
    session.meta["lora_last_pick"] = list(indices)
    session.meta.pop("lora_pick_done", None)
    session.meta["approved"] = False
    session.status = "awaiting_prompt"
    save_session(config, session)
    if not specs:
        msg = "Без LoRA — чистый Wan."
    else:
        names = ", ".join(f"{s.file}@{s.strength}" for s in specs)
        msg = f"LoRA: {names}."
    _ok, panel = send_control_panel(config, session)
    append_journal(config, COMFY_TOPIC, f"### LoRA записаны\n\n{msg}")
    return f"{msg}\nЖми «Снять», когда готово.\n{panel}"


def _preserve_chat_directed_action(session: LabSession) -> bool:
    """Сцена из чата/GUI уже несёт EN action — не затирать каталогом."""
    meta = session.meta or {}
    if bool(meta.get("prompt_user_edited")) and bool(meta.get("auto_approved_shoot")):
        reason = str(meta.get("shot_reason") or "").strip().lower()
        if reason.startswith("chat:"):
            return True
        slug = str(meta.get("catalog_slug") or "").strip().lower()
        if slug in ("chat_scene", "chat", "scene"):
            return True
    reason = str(meta.get("shot_reason") or "").strip().lower()
    return reason.startswith("chat:")


def step_generate_triple(config: Config, session: LabSession) -> StepResult:
    if session.status == "awaiting_prompt":
        return True, "Жду панель: Telegram «Снять» / Промпт / LoRA.", None
    if not session.meta.get("approved"):
        session.status = "awaiting_prompt"
        save_session(config, session)
        return True, "Ещё не жмякнули «Снять» — жду панель в Telegram.", None

    # Не долбить генерацию, если :8188 мёртв
    from ..integrations.comfy.client import ComfyClient

    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    ok_ping, ping_msg = ComfyClient(base_url=str(url), timeout=3.0).ping()
    if not ok_ping:
        ok_run, run_msg = ensure_comfy_running(
            config, auto_install=False, wait_seconds=90.0
        )
        if not ok_run:
            session.status = "paused"
            session.pause_reason = "comfy_offline"
            save_session(config, session)
            msg = (
                f"ComfyUI недоступен ({url}): {ping_msg}\n{run_msg}\n\n"
                "⏸ Lab на паузе. Запусти Comfy (или comfy_ensure), потом снова Lab."
            )
            from ..integrations.comfy.show_profile import is_show_profile, show_take_count

            if is_show_profile(session.meta):
                tag = f"### Шоу-дубль ×{show_take_count()}\n\n"
            else:
                tag = f"### {mocap_take_count()} дублей ¾\n\n"
            append_journal(config, COMFY_TOPIC, tag + msg)
            return False, msg, None

    action = str(session.meta.get("approved_action") or session.meta.get("action") or "")
    catalog_slug = str(session.meta.get("catalog_slug") or "").strip()
    preserve_chat = _preserve_chat_directed_action(session) and bool(action.strip())
    if preserve_chat:
        # Чат уже задал action; slug оставляем как есть (часто chat_scene).
        if not catalog_slug:
            session.meta["catalog_slug"] = "chat_scene"
            catalog_slug = "chat_scene"
            save_session(config, session)
    elif not catalog_slug:
        from .comfy_director import invent_next_shot

        plan = invent_next_shot(config)
        catalog_slug = plan.catalog_slug
        action = plan.action
        session.meta["catalog_slug"] = catalog_slug
        session.meta["enters_from"] = list(plan.enters_from)
        session.meta["exits_to"] = list(plan.exits_to)
        session.meta["shot_reason"] = plan.reason
        session.meta["looped"] = plan.looped
        save_session(config, session)
    else:
        from .comfy_director import sync_session_shot_from_slug

        action = sync_session_shot_from_slug(config, session)
        save_session(config, session)
    # Никогда не slugify EN-action («idle stand…» → idle_stand)
    from ..integrations.comfy.clip_review import normalize_catalog_slug

    slug = normalize_catalog_slug(catalog_slug) or "mocap"
    session.meta["catalog_slug"] = slug
    looped = bool(session.meta.get("looped"))
    from ..integrations.comfy.lora import specs_from_session_meta

    lora_specs = specs_from_session_meta(session.meta)
    pos_ov = str(session.meta.get("wan_positive") or "").strip()
    neg_ov = str(session.meta.get("wan_negative") or "").strip()
    # Защита: ручной Wan-промпт от другого кадра не подмешивать.
    if pos_ov and session.meta.get("prompt_user_edited"):
        edited_for = str(session.meta.get("prompt_edit_slug") or "").strip()
        if edited_for and edited_for != slug:
            pos_ov = ""
            neg_ov = ""
            session.meta.pop("wan_positive", None)
            session.meta.pop("wan_negative", None)
            session.meta.pop("prompt_user_edited", None)
            save_session(config, session)

    seed_image_name = ""
    from ..integrations.comfy.seed_library import activate_for_slug
    from ..integrations.comfy.seed_pose import resolve_active_seed, stage_seed_for_comfy
    from ..integrations.comfy.show_profile import is_show_profile, show_take_count

    # Эталон I2V: для шоу — только если режим i2v/i2i; для mocap — как раньше.
    from ..integrations.comfy.shoot_settings import mode_needs_seed, shoot_mode_from_meta

    mode = shoot_mode_from_meta(session.meta)
    allow_seed = mode_needs_seed(mode) or not is_show_profile(session.meta)
    if allow_seed:
        # Привязка библиотеки эталонов к slug (если глобальный seed ещё не выбран вручную).
        _path0, _n0, seed_already = resolve_active_seed(config)
        if not seed_already and slug:
            bind_msg = activate_for_slug(config, slug)
            if bind_msg:
                append_journal(config, COMFY_TOPIC, "### Эталон I2V\n\n" + bind_msg)

        seed_path, seed_comfy, seed_on = resolve_active_seed(config)
        if seed_on and seed_path is not None:
            ok_s, _msg_s, staged = stage_seed_for_comfy(config, seed_path)
            if ok_s:
                seed_image_name = staged or seed_comfy
                session.meta["i2v_seed_enabled"] = True
                session.meta["i2v_seed_path"] = str(seed_path)
                session.meta["i2v_seed_comfy"] = seed_image_name
                # Подмешать «натуральное тело» в positive, если эталон ещё HS2.
                hint = str(session.meta.get("i2v_seed_natural_hint") or "").strip()
                if hint and pos_ov and hint.lower() not in pos_ov.lower():
                    pos_ov = f"{pos_ov}, {hint}"
                elif hint and not pos_ov:
                    session.meta["i2v_seed_natural_hint"] = hint
                save_session(config, session)
    ok, msg, results = run_triple_angles(
        config,
        action=action,
        slug=slug,
        catalog_slug=slug,
        enters_from=list(session.meta.get("enters_from") or []),
        looped=looped,
        lora_specs=lora_specs,
        prompt_override=pos_ov,
        negative_override=neg_ov,
        seed_image_name=seed_image_name,
    )
    from ..integrations.comfy.clip_review import harvest_comfy_native_output

    h_n, h_msg = harvest_comfy_native_output(config)
    if h_n:
        msg += "\n" + h_msg
    session.meta["triple"] = results
    for path in results.get("files") or []:
        session.append_artifact(path)

    from ..integrations.comfy.shoot_settings import mode_is_image, shoot_mode_from_meta

    still = bool(results.get("still")) or mode_is_image(shoot_mode_from_meta(session.meta))
    if still:
        tag = "### Still PNG\n\n"
    elif is_show_profile(session.meta):
        tag = f"### Шоу-дубль ×{show_take_count()}\n\n"
    else:
        tag = f"### {mocap_take_count()} дублей ¾\n\n"
    append_journal(config, COMFY_TOPIC, tag + msg)
    if not ok:
        # Connection refused / все дубли FAIL — не маскировать под успех
        if "10061" in msg or "недоступен" in msg.lower() or "refused" in msg.lower():
            session.status = "paused"
            session.pause_reason = "comfy_offline"
            save_session(config, session)
            msg += (
                "\n\n⏸ ComfyUI не на :8188. Lab на паузе — запусти Comfy, "
                "потом Lab (будет RECOVER, не 20 слепых повторов)."
            )
        return False, msg, None

    # Still: сразу PNG в Telegram, без выбора дублей.
    if still:
        from pathlib import Path

        from ..integrations.comfy.chat_flow import send_media_to_telegram

        sent = 0
        for path in results.get("files") or []:
            p = Path(str(path))
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                continue
            if send_media_to_telegram(config, "photo", p, caption="Кадр от Вью"):
                sent += 1
        session.meta["clip_kept_id"] = "still_auto"
        session.meta["still_sent"] = sent
        session.meta["clip_batch_id"] = str(results.get("slug") or "")
        session.meta["clip_candidate_ids"] = []
        save_session(config, session)
        try:
            from ..integrations.comfy.queue_manage import clear_comfy_queue

            client = ComfyClient(base_url=str(url), timeout=8.0)
            yield_note = clear_comfy_queue(
                client, interrupt_running=False, free_memory=True
            )
            if yield_note:
                msg += "\n" + yield_note
        except Exception as exc:
            msg += f"\nпосле still: queue/VRAM ({exc})"
        pick_msg = (
            f"Прислала {sent} PNG в Telegram."
            if sent
            else "PNG готов в Lab/Refs (Telegram не отправился — проверь токен/чат)."
        )
        append_journal(config, COMFY_TOPIC, f"### Still → TG\n\n{pick_msg}")
        return True, msg + "\n\n" + pick_msg, None

    from ..integrations.comfy.clip_review import (
        format_candidates_message,
        register_triple_batch,
    )

    clips = register_triple_batch(
        config,
        action=action,
        results=results,
        catalog_slug=slug,
        enters_from=list(session.meta.get("enters_from") or []),
        exits_to=list(session.meta.get("exits_to") or []),
    )
    session.meta["clip_batch_id"] = str(results.get("slug") or "")
    session.meta["clip_candidate_ids"] = [c.id for c in clips]
    pick_msg = format_candidates_message(clips)

    # Три дубля готовы — очередь/VRAM освободить. Процесс Comfy может остаться.
    yield_note = ""
    try:
        from ..integrations.comfy.queue_manage import clear_comfy_queue

        client = ComfyClient(base_url=str(url), timeout=8.0)
        yield_note = clear_comfy_queue(
            client, interrupt_running=False, free_memory=True
        )
        if yield_note:
            append_journal(config, COMFY_TOPIC, f"### После тройки\n\n{yield_note}")
            msg += "\n" + yield_note
    except Exception as exc:
        yield_note = f"после тройки: queue/VRAM не трогала ({exc})"
        append_journal(config, COMFY_TOPIC, f"### После тройки\n\n{yield_note}")

    append_journal(config, COMFY_TOPIC, f"### Выбор дубля\n\n{pick_msg}")
    return True, msg + "\n\n" + pick_msg, None


def step_await_clip_pick(config: Config, session: LabSession) -> StepResult:
    """Пауза: Ден выбирает лучший из дублей (дома); away — авто."""
    if session.meta.get("clip_kept_id"):
        return True, f"Клип уже выбран: {session.meta.get('clip_kept_id')}.", None
    from ..integrations.comfy.clip_review import ComfyClipStore, clip_review_path, format_candidates_message
    from ..integrations.comfy.tg_buttons import clip_pick_keyboard

    batch = str(session.meta.get("clip_batch_id") or "")
    store = ComfyClipStore(clip_review_path(config)).load()
    cands = store.by_batch(batch) if batch else store.pending_candidates()
    cands = [c for c in cands if c.status == "candidate"]
    if not cands:
        return True, "Нет кандидатов — пропускаю выбор.", None

    try:
        from ..presence import is_away

        away = is_away(config)
    except Exception:
        away = False
    if away:
        from ..integrations.comfy.angles import AWAY_AUTO_TAKE_ID

        msg = apply_clip_pick_decision(
            config,
            session,
            "keep",
            {
                "angle": AWAY_AUTO_TAKE_ID,
                "score": 3,
                "notes": "auto away clip pick",
            },
        )
        return True, f"Нет дома — сама выбрала лучший из {len(cands)} дублей.\n{msg}", None

    session.status = "awaiting_clip_pick"
    save_session(config, session)
    msg = format_candidates_message(cands)
    angles: List[str] = []
    for c in cands:
        a = str(getattr(c, "angle", "") or "").strip()
        if a and a not in angles:
            angles.append(a)
    try:
        from ..integrations.telegram import settings as tg_settings
        from ..integrations.telegram.client import TelegramClient

        if tg_settings.enabled(config):
            token = tg_settings.token(config)
            chat_id = tg_settings.chat_id(config)
            if token and chat_id:
                TelegramClient(token).send_message(
                    chat_id,
                    "🎞 Comfy: выбери лучший клип\n\n" + msg[:1500],
                    reply_markup=clip_pick_keyboard(angles),
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
    from ..integrations.comfy.clip_review import keep_best_take, reject_batch

    batch = str(session.meta.get("clip_batch_id") or "")
    if decision == "reject_all":
        ok, msg = reject_batch(config, batch)
        session.meta["clip_rejected_all"] = True
        for key in ("clip_kept_id", "clip_kept_path", "clip_seed_frame", "clip_batch_id"):
            session.meta.pop(key, None)
        session.status = "running"
        session.step = min(session.step, 5)
        save_session(config, session)
        append_journal(config, COMFY_TOPIC, f"### Клипы отклонены\n\n{msg}")
        return msg + "\nМожно снова comfy_mocap с другим промптом (lab reset или шаг генерации)."

    angle = str(payload.get("angle") or "take_b")
    score = int(payload.get("score") or 4)
    notes = str(payload.get("notes") or "")
    ok, msg, clip = keep_best_take(
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
    # В Telegram — сам файл, не только текст.
    try:
        from ..integrations.comfy.chat_flow import send_media_to_telegram

        if clip.path and Path(clip.path).is_file():
            send_media_to_telegram(
                config, "video", clip.path, caption="Оставила этот клип"
            )
    except Exception:
        pass
    return msg + "\nДальше — отчёт lab."


def step_report(config: Config, session: LabSession) -> StepResult:
    action = session.meta.get("approved_action") or session.meta.get("action")
    kept = session.meta.get("clip_kept_path")
    seed = session.meta.get("clip_seed_frame")
    files = session.artifacts[-12:]
    from ..integrations.comfy.focus import focus_cycle_status
    from .paths import journal_path

    draft = str(session.meta.get("draft") or "").strip()
    draft_block = ""
    if draft:
        draft_block = f"\n\nПромпт (Wan MoCap, как ушло в Comfy):\n{draft[:2200]}"
    jpath = journal_path(config, COMFY_TOPIC)

    report = (
        f"Comfy MoCap итерация id={session.id}\n"
        f"action: {action}\n"
        f"catalog: {session.meta.get('catalog_slug') or '—'}\n"
        f"model: {PREFERRED_FAMILY}\n"
        f"kept: {kept or '— (не выбран)'}\n"
        f"seed last-frame: {seed or '—'}\n"
        f"файлы ({len(files)}):\n"
        + "\n".join(f"  • {f}" for f in files)
        + draft_block
        + f"\n\nJournal (промпт / шаги): {jpath}"
        + "\n\n"
        + focus_cycle_status(config)
        + "\n\nДальше: Cascadeur MoCap по kept mp4; next clip — I2V с seed PNG."
        + "\nПравки: `comfy_prompt` / «Промпт MoCap» в GUI · `правки: …` на одобрении · journal."
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
    step_request_lora_pick,
    step_generate_triple,
    step_await_clip_pick,
    step_report,
]


def run_one_step(config: Config, session: LabSession) -> Tuple[bool, str]:
    if session.status == "awaiting_prompt":
        return True, (
            "Жду панель съёмки в Telegram: «Снять» / Промпт / LoRA / Стоп. "
            "Полный промпт: «промпт comfy»."
        )
    if session.status == "awaiting_lora_pick":
        return True, (
            "Жду выбор LoRA: `lora: 1` / `lora: 1,3` / `lora: all` / `lora: none` "
            "или tool comfy_lora_pick."
        )
    if session.status == "awaiting_clip_pick":
        return True, (
            "Жду выбор клипа: `лучший: take_b` / `лучший: a` / `лучший: c 5` / `отклонить все` "
            "(несколько вариантов через | — беру первый) "
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

    if session.status == "awaiting_lora_pick":
        session.steps_total = len(STEPS)
        save_session(config, session)
        notify_lab_step(config, step_idx, label, msg)
        return True, msg

    if session.status == "paused":
        save_session(config, session)
        return True, msg

    if not ok and session.step in (0, 5):
        session.last_fail_step = session.step
        session.last_fail_msg = msg[:2000]
        key = str(session.step)
        session.step_fail_counts[key] = session.step_fail_counts.get(key, 0) + 1
        n = session.step_fail_counts[key]
        save_session(config, session)
        if session.step == 0:
            hint = (
                "\n\n⏸ Comfy не ответила на :8188. "
                "Не клонирую заново — смотри `.viu/logs/comfy_launch.log` "
                "или снова `comfy_ensure`."
            )
        else:
            hint = (
                "\n\n⏸ Генерация не прошла. "
                f"Провал ×{n} — следующий Lab = RECOVER (не слепой повтор)."
            )
        # ok=False чтобы run_until_done остановился
        return False, msg + hint

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
    max_steps: int = 40,
) -> Tuple[bool, str]:
    lines: list[str] = []
    steps_run = 0
    try:
        from ..presence import is_away
    except Exception:

        def is_away(_cfg: Config) -> bool:
            return False

    while steps_run < max_steps:
        session = load_session(config, COMFY_TOPIC) or session
        # Панель / LoRA — только ответ Дена. Не авто-сжимать shoot.
        if session.status == "awaiting_clip_pick" and is_away(config):
            ok, msg = run_one_step(config, session)
            steps_run += 1
            lines.append(f"[away клип] {msg[:400]}")
            continue
        if session.status == "awaiting_rating" and is_away(config):
            session.rating_notes = "away: auto-пропуск оценки"
            session.status = "completed"
            save_session(config, session)
            append_journal(
                config,
                COMFY_TOPIC,
                "### Оценка (away auto)\n\nПропущена в run_until_done — следующий кадр.",
            )
            lines.append("Нет дома — оценку пропустила, итерация закрыта.")
            break
        if session.status in (
            "awaiting_prompt",
            "awaiting_lora_pick",
            "awaiting_clip_pick",
            "awaiting_rating",
            "completed",
        ):
            if session.status == "awaiting_prompt":
                lines.append("Жду панель в Telegram: «Снять» / Промпт / LoRA.")
            elif session.status == "awaiting_lora_pick":
                lines.append("Жду выбор LoRA (lora: 1,2 / none).")
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
