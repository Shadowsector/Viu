"""Инструменты ComfyUI: статус, ensure, прогон, MoCap-пакет."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from ..integrations.comfy import (
    ComfyClient,
    ComfyError,
    comfy_out_dir,
    comfy_refs_dir,
    comfy_workflows_dir,
    inject_text_prompt,
    list_workflows,
    load_workflow,
    resolve_comfy_root,
    write_install_readme,
)
from ..integrations.comfy.generate import run_triple_angles
from ..integrations.comfy.model_pref import PREFERRED_FAMILY, probe_models
from ..integrations.comfy.process import ensure_comfy_running
from ..integrations.comfy.workflows import ensure_workflow_templates
from .base import AgentContext, Tool, ToolResult


def _client(ctx: AgentContext) -> ComfyClient:
    url = getattr(ctx.config, "comfy_url", None) or "http://127.0.0.1:8188"
    return ComfyClient(base_url=str(url))


class ComfyStatusTool(Tool):
    name = "comfy_status"
    description = (
        "Статус ComfyUI: сервер :8188, корень U:\\Viu\\ComfyUI, Wan-модели, workflows."
    )
    parameters = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        write_install_readme(ctx.config)
        ensure_workflow_templates(ctx.config)
        root = resolve_comfy_root(ctx.config)
        probe = probe_models(ctx.config)
        lines = [
            f"URL: {getattr(ctx.config, 'comfy_url', 'http://127.0.0.1:8188')}",
            f"Root: {root or '(не найден — жду U:\\Viu\\ComfyUI)'}",
            f"Model family: {PREFERRED_FAMILY}",
            f"T2V ready: {probe.ready_t2v} | I2V ready: {probe.ready_i2v}",
            f"Workflows: {comfy_workflows_dir(ctx.config)}",
            f"Refs (Cascadeur): {comfy_refs_dir(ctx.config)}",
            f"ComfyOut: {comfy_out_dir(ctx.config)}",
        ]
        for n in probe.notes:
            lines.append(f"  • {n}")
        wfs = list_workflows(ctx.config)
        if wfs:
            lines.append("Workflow files:")
            lines.extend(f"  • {p.name}" for p in wfs)
        else:
            lines.append("Workflow files: (пусто)")

        ok, msg = _client(ctx).ping()
        lines.append(msg)
        if ok:
            from ..integrations.comfy.face_refs import face_swap_status_line

            lines.append(face_swap_status_line(ctx.config, client=_client(ctx)))
        if not ok:
            lines.append("Запуск: comfy_ensure или lab_start topic=comfy.")
            lines.append("Гайд: docs/COMFY_SETUP.md")
        try:
            from ..integrations.comfy.lora import ensure_registry, list_registry_status_brief
            from ..lab.comfy_pipeline import COMFY_TOPIC
            from ..lab.session import load_session

            ensure_registry(ctx.config)
            session = load_session(ctx.config, COMFY_TOPIC)
            slug = str(session.meta.get("catalog_slug") or "") if session else ""
            lines.append("")
            lines.append(list_registry_status_brief(ctx.config, catalog_slug=slug))
        except Exception as exc:
            lines.append(f"(lora registry: {exc})")
        try:
            from ..integrations.comfy.pipeline_status import comfy_pipeline_status

            lines.append("")
            lines.append(comfy_pipeline_status(ctx.config))
        except Exception as exc:
            lines.append(f"(pipeline status: {exc})")
        try:
            from ..integrations.comfy.face_refs import face_refs_status

            lines.append("")
            lines.append(face_refs_status(ctx.config, client=_client(ctx)))
        except Exception as exc:
            lines.append(f"(face refs: {exc})")
        return ToolResult(True, "\n".join(lines))


class ComfyInstallTool(Tool):
    name = "comfy_install"
    description = (
        "Поставить/доустановить ComfyUI в U:\\Viu\\ComfyUI: git clone, "
        "Wan 2.1 workflows (JSON с github), T2V-модели с HuggingFace, pip. "
        "i2v=1 — ещё I2V 14B (~30GB). models=0 — только код+workflows."
    )
    parameters = {
        "models": "1 = скачать T2V модели (по умолчанию 1)",
        "i2v": "1 = ещё I2V+clip_vision (очень много места)",
        "pip": "1 = pip install requirements (по умолчанию 1)",
        "reactor": "1 = ComfyUI-ReActor + inswapper (подмена лица MoCap)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.install import ensure_comfy_installed

        with_models = str(args.get("models", "1")).lower() in ("1", "true", "yes", "")
        include_i2v = str(args.get("i2v", "0")).lower() in ("1", "true", "yes")
        with_pip = str(args.get("pip", "1")).lower() in ("1", "true", "yes", "")
        with_reactor = str(args.get("reactor", "0")).lower() in ("1", "true", "yes")
        notes: list[str] = []

        def progress(msg: str) -> None:
            notes.append(msg)
            print(f"[comfy_install] {msg}", flush=True)

        print("[comfy_install] старт…", flush=True)
        ok, msg = ensure_comfy_installed(
            ctx.config,
            with_models=with_models,
            include_i2v=include_i2v,
            with_pip=with_pip,
            with_reactor=with_reactor,
            progress=progress,
        )
        body = msg
        if notes:
            body = "Прогресс:\n" + "\n".join(f"  • {n}" for n in notes[-20:]) + "\n\n" + msg
        if with_reactor and ok:
            from ..integrations.comfy.process import ensure_comfy_running

            ok_r, r_msg = ensure_comfy_running(
                ctx.config,
                wait_seconds=120.0,
                auto_install=False,
                reload_if_reactor_missing=True,
            )
            body += f"\n\n{r_msg}"
            ok = ok and ok_r
        return ToolResult(ok, body)


class ComfyEnsureTool(Tool):
    name = "comfy_ensure"
    description = (
        "Если Comfy нет — установить в U:\\Viu\\ComfyUI; затем запустить API :8188 "
        "(лог: .viu/logs/comfy_launch.log)."
    )
    parameters = {
        "wait": "секунд ожидания API (по умолчанию 180)",
        "restart": "1 — перезапустить Comfy (подхватить ReActor после install)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        try:
            wait = float(args.get("wait") or 180)
        except (TypeError, ValueError):
            wait = 180.0
        force_restart = str(args.get("restart") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        ensure_workflow_templates(ctx.config, overwrite_stubs=True)
        ok, msg = ensure_comfy_running(
            ctx.config,
            wait_seconds=wait,
            auto_install=True,
            force_restart=force_restart,
            reload_if_reactor_missing=True,
        )
        if ok and "face_swap:" not in msg:
            client = _client(ctx)
            from ..integrations.comfy.face_refs import face_refs_status

            msg = f"{msg}\n\n{face_refs_status(ctx.config, client=client)}"
        return ToolResult(ok, msg)


class ComfyReactorFixTool(Tool):
    name = "comfy_reactor_fix"
    description = (
        "Починить ReActor: pip зависимости, import-test, перезапуск Comfy. "
        "Если face_swap нет после comfy_ensure."
    )
    parameters = {
        "skip_restart": "1 — только pip/deps, без рестарта Comfy",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.face_refs import face_swap_status_line, reactor_face_swap_class
        from ..integrations.comfy.process import ensure_comfy_running
        from ..integrations.comfy.reactor_diag import (
            reactor_diagnose,
            reactor_errors_in_launch_log,
            repair_reactor_dependencies,
        )

        skip_restart = str(args.get("skip_restart") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        lines: List[str] = ["=== comfy_reactor_fix ==="]
        notes: List[str] = []

        def progress(msg: str) -> None:
            notes.append(msg)
            print(f"[comfy_reactor_fix] {msg}", flush=True)

        log_bit = reactor_errors_in_launch_log(ctx.config)
        if log_bit:
            lines.append("Лог Comfy (ReActor):")
            lines.extend(f"  {ln}" for ln in log_bit.splitlines()[-6:])

        try:
            lines.append("Шаг 1/3: NSFW-патч + зависимости venv…")
            from ..integrations.comfy.reactor_diag import ensure_reactor_nsfw_patch

            ok_patch, patch_msg, _ = ensure_reactor_nsfw_patch(ctx.config, force=True)
            lines.append(patch_msg)
            ok_fix, fix_msg = repair_reactor_dependencies(ctx.config, progress=progress)
            lines.append(fix_msg)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"Шаг 1: сбой — {exc}")
            ok_fix = False

        if notes:
            lines.append("Прогресс: " + "; ".join(notes[-8:]))

        client = _client(ctx)
        if skip_restart:
            lines.append(reactor_diagnose(ctx.config, client=client))
            lines.append(face_swap_status_line(ctx.config, client=client))
            return ToolResult(ok_fix, "\n\n".join(lines))

        try:
            lines.append("Шаг 2/3: перезапуск Comfy…")
            ok_run, run_msg = ensure_comfy_running(
                ctx.config,
                wait_seconds=90.0,
                auto_install=False,
                force_restart=True,
                reload_if_reactor_missing=True,
            )
            lines.append(run_msg)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"Шаг 2: сбой — {exc}")
            ok_run = False

        try:
            lines.append("Шаг 3/3: проверка API…")
            client = _client(ctx)
            cls = reactor_face_swap_class(client)
            if cls:
                lines.append(f"✓ ReActor в API: **{cls}**")
            else:
                lines.append(reactor_diagnose(ctx.config, client=client))
            lines.append(face_swap_status_line(ctx.config, client=client))
        except Exception as exc:  # noqa: BLE001
            lines.append(f"Шаг 3: {exc}")

        ok = bool(reactor_face_swap_class(_client(ctx)))
        return ToolResult(ok, "\n\n".join(lines))


class ComfyFocusTool(Tool):
    name = "comfy_focus"
    description = (
        "Фокус Comfy MoCap: nsfw (touch_self, shower, bath) или barn (цикл сарая). "
        "Бытовые sit/walk — Mixamo; Comfy — NSFW."
    )
    parameters = {
        "focus": "nsfw | barn | all — что снимать дальше",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.focus import set_comfy_focus

        mode = str(args.get("focus") or args.get("mode") or "").strip()
        if not mode:
            from ..integrations.comfy.focus import focus_mode_label, resolve_focus_slugs

            slugs = resolve_focus_slugs(ctx.config)
            return ToolResult(
                True,
                f"Сейчас фокус: **{focus_mode_label(ctx.config)}**\n"
                f"slugs: {', '.join(slugs) or '(все)'}\n"
                "Сменить: comfy_focus focus=nsfw | focus=barn",
            )
        ok, msg = set_comfy_focus(ctx.config, mode)
        return ToolResult(ok, msg)


class ComfyQueueClearTool(Tool):
    name = "comfy_queue_clear"
    description = (
        "Сбросить очередь ComfyUI: interrupt текущий job + очистить pending. "
        "Полезно, если в очереди старые lie_down, а lab уже на touch_self."
    )
    parameters = {
        "free": "1 — освободить VRAM после сброса",
        "force": "1 — очистить даже если slug совпадает",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.queue_manage import clear_comfy_queue, prepare_queue_for_slug
        from ..lab.comfy_pipeline import COMFY_TOPIC
        from ..lab.session import load_session

        client = _client(ctx)
        ok, ping = client.ping()
        if not ok:
            return ToolResult(False, ping + "\nСначала comfy_ensure.")

        free = str(args.get("free") or "").strip().lower() in ("1", "true", "yes", "on")
        force = str(args.get("force") or "").strip().lower() in ("1", "true", "yes", "on")
        session = load_session(ctx.config, COMFY_TOPIC)
        slug = ""
        if session is not None:
            slug = str(session.meta.get("catalog_slug") or "").strip()

        if force or not slug:
            msg = clear_comfy_queue(client, interrupt_running=True, free_memory=free)
            return ToolResult(True, msg)

        msg = prepare_queue_for_slug(client, slug, force=False)
        if msg:
            if free:
                msg += "\n" + clear_comfy_queue(
                    client, interrupt_running=False, free_memory=True
                )
            return ToolResult(True, msg)

        return ToolResult(
            True,
            f"Очередь совпадает с **{slug}** — сброс не нужен. force=1 чтобы очистить принудительно.",
        )


class ComfyRunTool(Tool):
    name = "comfy_run"
    description = (
        "Прогнать ComfyUI workflow (API JSON). prompt= текст. "
        "workflow=t2v|i2v|default. Результат → Lab/Refs."
    )
    parameters = {
        "prompt": "текст действия / сцены",
        "workflow": "t2v | i2v | default",
        "timeout": "секунд ожидания (по умолчанию 600)",
        "slug": "имя выходного файла без расширения",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        prompt = str(args.get("prompt") or "").strip()
        workflow_name = str(args.get("workflow") or "t2v").strip()
        slug = str(args.get("slug") or "comfy_out").strip() or "comfy_out"
        try:
            timeout = float(args.get("timeout") or 600)
        except (TypeError, ValueError):
            timeout = 600.0

        try:
            wf = load_workflow(ctx.config, workflow_name)
        except (FileNotFoundError, ValueError, OSError) as exc:
            return ToolResult(False, str(exc))

        if prompt:
            wf = inject_text_prompt(wf, prompt)

        client = _client(ctx)
        ok, ping = client.ping()
        if not ok:
            return ToolResult(False, ping + "\nСначала comfy_ensure.")

        try:
            prompt_id = client.queue_prompt(wf)
            entry = client.wait_history(prompt_id, timeout=timeout)
            files = client.collect_output_files(entry)
        except ComfyError as exc:
            return ToolResult(False, str(exc))

        if not files:
            return ToolResult(
                False,
                f"prompt_id={prompt_id} завершён, но outputs пусты.\n"
                "Проверь SaveImage / SaveVideo / VHS_VideoCombine в workflow.",
            )

        refs = comfy_refs_dir(ctx.config)
        out_dir = comfy_out_dir(ctx.config)
        saved: list[str] = []
        for i, meta in enumerate(files):
            ext = Path(meta["filename"]).suffix or ".png"
            dest_out = out_dir / f"{slug}_{i}{ext}"
            try:
                client.download_view(
                    meta["filename"],
                    subfolder=meta.get("subfolder") or "",
                    folder_type=meta.get("type") or "output",
                    dest=dest_out,
                )
            except ComfyError as exc:
                return ToolResult(False, str(exc))
            dest_ref = refs / dest_out.name
            try:
                shutil.copy2(dest_out, dest_ref)
            except OSError:
                dest_ref = dest_out
            saved.append(str(dest_ref))

        lines = [
            f"Comfy OK prompt_id={prompt_id}",
            f"prompt: {prompt[:200] or '(без подстановки текста)'}",
            "Файлы → Lab/Refs:",
        ]
        lines.extend(f"  • {p}" for p in saved)
        return ToolResult(True, "\n".join(lines))


class ComfyMocapTool(Tool):
    name = "comfy_mocap"
    description = (
        "Comfy MoCap lab: Вью сама выбирает кадр из каталога (action=auto), "
        "или action= явное действие. Дома — Telegram; нет дома — авто-одобрение."
    )
    parameters = {
        "action": "действие или auto — Вью сама выберет из каталога",
        "reset": "1 = новая сессия",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from .lab_tool import LabStartTool

        action = str(args.get("action") or "").strip()
        plan_meta: Dict[str, Any] = {}
        if not action or action.lower() in ("auto", "сам", "сама", "invent"):
            from ..lab.comfy_director import invent_next_shot
            from ..lab.comfy_pipeline import ensure_task_file

            plan = invent_next_shot(ctx.config)
            action = plan.action
            ensure_task_file(ctx.config, action=action)
            plan_meta = {
                "catalog_slug": plan.catalog_slug,
                "enters_from": ",".join(plan.enters_from),
                "exits_to": ",".join(plan.exits_to),
                "shot_reason": plan.reason,
            }
        payload = {
            "topic": "comfy",
            "run_all": "1",
            "reset": args.get("reset", "1"),
            "action": action,
            **plan_meta,
        }
        return LabStartTool().run(payload, ctx)


class ComfyTripleTool(Tool):
    name = "comfy_triple"
    description = (
        "Сразу 3 ракурса без Telegram (если промпт уже согласован). action= текст."
    )
    parameters = {
        "action": "действие / описание motion",
        "slug": "префикс имени файлов",
        "catalog_slug": "slug каталога (для LoRA)",
        "timeout": "секунд на один угол (900)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        action = str(args.get("action") or "").strip()
        if not action:
            return ToolResult(False, "Нужен action=.")
        slug = str(args.get("slug") or "mocap").strip()
        catalog_slug = str(args.get("catalog_slug") or slug).strip()
        try:
            timeout = float(args.get("timeout") or 900)
        except (TypeError, ValueError):
            timeout = 900.0
        ok, msg, _ = run_triple_angles(
            ctx.config,
            action=action,
            slug=slug,
            catalog_slug=catalog_slug,
            timeout_each=timeout,
        )
        return ToolResult(ok, msg)


class ComfyLoraListTool(Tool):
    name = "comfy_lora_list"
    description = (
        "Проиндексированные LoRA из ComfyUI/models/loras/ — номера для выбора перед пулом. "
        "scan=1 — пересканировать папку."
    )
    parameters = {"scan": "1 = пересканировать models/loras/"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.lora import ensure_registry, list_registry_status, scan_loras

        ensure_registry(ctx.config)
        if str(args.get("scan") or "").lower() in ("1", "true", "yes"):
            scan_loras(ctx.config)
        return ToolResult(True, list_registry_status(ctx.config))


class ComfyLoraScanTool(Tool):
    name = "comfy_lora_scan"
    description = "Пересканировать ComfyUI/models/loras/ и обновить индекс .viu/comfy_loras_index.json."
    parameters = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.lora import format_lora_pick_message, scan_loras

        entries = scan_loras(ctx.config)
        return ToolResult(True, format_lora_pick_message(entries))


class ComfyLoraPickTool(Tool):
    name = "comfy_lora_pick"
    description = (
        "Выбрать LoRA для текущего Comfy-пула. pick=1,3 | none | all. "
        "Работает когда Lab ждёт awaiting_lora_pick."
    )
    parameters = {
        "pick": "1 | 1,3 | all | none",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.lora import load_index, parse_lora_pick_reply
        from ..lab.comfy_pipeline import COMFY_TOPIC, apply_lora_pick_decision
        from ..lab.session import load_session

        raw = str(args.get("pick") or "").strip()
        if not raw:
            return ToolResult(False, "Нужен pick=1,3 или pick=none.")
        session = load_session(ctx.config, COMFY_TOPIC)
        if session is None:
            return ToolResult(False, "Нет lab comfy сессии.")
        entries = load_index(ctx.config)
        max_idx = max((e.index for e in entries), default=0)
        text = raw if raw.lower().startswith(("lora", "лора", "none", "нет")) else f"lora: {raw}"
        indices = parse_lora_pick_reply(text, max_index=max_idx)
        if indices is None:
            return ToolResult(False, "Не поняла pick — пример: pick=1,2 или pick=none")
        if session.status != "awaiting_lora_pick":
            return ToolResult(
                False,
                f"Сейчас статус {session.status}, не awaiting_lora_pick. "
                "Дождись шага «Выбор LoRA» после одобрения промпта.",
            )
        msg = apply_lora_pick_decision(ctx.config, session, indices)
        return ToolResult(True, msg)


class ComfyLoraNoteTool(Tool):
    name = "comfy_lora_note"
    description = (
        "Заметки к файлу LoRA: trigger-слова, strength, tags. "
        "lora_file=name.safetensors trigger=... strength=0.85 tags=wan,touch"
    )
    parameters = {
        "lora_file": "имя файла в loras/",
        "trigger": "слова в промпт",
        "strength": "0.85",
        "tags": "через запятую (для списка)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.lora import update_library_entry

        strength_raw = args.get("strength")
        strength = None
        if strength_raw not in (None, ""):
            try:
                strength = float(strength_raw)
            except (TypeError, ValueError):
                strength = 0.85
        ok, msg = update_library_entry(
            ctx.config,
            str(args.get("lora_file") or ""),
            trigger=str(args.get("trigger") or ""),
            strength=strength,
            tags=str(args.get("tags") or ""),
        )
        return ToolResult(ok, msg)


class ComfyLoraBindTool(Tool):
    name = "comfy_lora_bind"
    description = (
        "Привязать LoRA к catalog_slug. catalog_slug=touch_self lora_file=name.safetensors "
        "strength=0.85 trigger=... download_url=https://... replace=1 — заменить список."
    )
    parameters = {
        "catalog_slug": "slug в animation_catalog",
        "lora_file": "имя файла в models/loras/",
        "strength": "0.85",
        "trigger": "слова в промпт",
        "subfolder": "подпапка в loras/",
        "download_url": "прямая ссылка .safetensors (опционально)",
        "replace": "1 = заменить loras у slug, не дописывать",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.lora import bind_slug

        try:
            strength = float(args.get("strength") or 0.85)
        except (TypeError, ValueError):
            strength = 0.85
        replace = str(args.get("replace") or "").lower() in ("1", "true", "yes")
        ok, msg = bind_slug(
            ctx.config,
            catalog_slug=str(args.get("catalog_slug") or ""),
            lora_file=str(args.get("lora_file") or ""),
            strength=strength,
            trigger=str(args.get("trigger") or ""),
            subfolder=str(args.get("subfolder") or ""),
            download_url=str(args.get("download_url") or ""),
            replace=replace,
        )
        return ToolResult(ok, msg)


class ComfyLoraFetchTool(Tool):
    name = "comfy_lora_fetch"
    description = (
        "Скачать LoRA из реестра (download_url). catalog_slug= — только для slug; "
        "all=1 — все недостающие; force=1 — перекачать."
    )
    parameters = {
        "catalog_slug": "скачать LoRA для одного slug",
        "all": "1 = все недостающие из реестра",
        "force": "1 = перекачать даже если файл есть",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.lora import ensure_registry, fetch_all_missing, fetch_for_slug

        ensure_registry(ctx.config)
        force = str(args.get("force") or "").lower() in ("1", "true", "yes")
        if str(args.get("all") or "").lower() in ("1", "true", "yes"):
            ok, msg = fetch_all_missing(ctx.config, force=force)
            return ToolResult(ok, msg)
        slug = str(args.get("catalog_slug") or "").strip()
        if not slug:
            return ToolResult(False, "Нужен catalog_slug= или all=1.")
        ok, msg = fetch_for_slug(ctx.config, slug, force=force)
        return ToolResult(ok, msg)


class ComfyVisionReviewTool(Tool):
    name = "comfy_vision_review"
    description = (
        "Llava/qwen2-vl: оценить MoCap mp4 (кадр из видео → вердикт). "
        "path= один файл или paths= через запятую. auto=1 — после triple в lab."
    )
    parameters = {
        "path": "один mp4",
        "paths": "несколько mp4 через запятую",
        "action": "что должно быть в кадре (для промпта)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.vision_review import review_paths, vision_review_enabled

        if not vision_review_enabled():
            return ToolResult(
                False,
                "VIU_COMFY_VISION=0 — включи в .env или убери переменную.",
            )
        raw_paths: List[str] = []
        if args.get("path"):
            raw_paths.append(str(args["path"]))
        if args.get("paths"):
            raw_paths.extend(str(args["paths"]).split(","))
        action = str(args.get("action") or "").strip()
        ok, msg, _ = review_paths(ctx.config, raw_paths, action=action)
        return ToolResult(ok, msg)


class ComfyClipPickTool(Tool):
    name = "comfy_clip_pick"
    description = (
        "Выбрать лучший Comfy-клип после тройки ракурсов. "
        "angle=front|side|three_quarter, score=1..5, "
        "catalog_slug=, enters_from=a,b exits_to=c,d. "
        "reject=1 — отклонить весь batch. "
        "Или в чате/Telegram: «лучший: front 5»."
    )
    parameters = {
        "angle": "front | side | three_quarter",
        "score": "1–5",
        "catalog_slug": "slug в animation_catalog",
        "enters_from": "через запятую",
        "exits_to": "через запятую",
        "notes": "заметки",
        "reject": "1 = отклонить все кандидаты batch",
        "batch": "id batch (по умолчанию из lab session)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.clip_review import keep_best_by_angle, reject_batch
        from ..lab.comfy_pipeline import COMFY_TOPIC, apply_clip_pick_decision
        from ..lab.session import load_session

        session = load_session(ctx.config, COMFY_TOPIC)
        batch = str(args.get("batch") or "").strip()
        if not batch and session is not None:
            batch = str(session.meta.get("clip_batch_id") or "")
        if not batch:
            return ToolResult(False, "Нет batch — сначала comfy_mocap / lab comfy.")

        if str(args.get("reject") or "").strip() in ("1", "true", "yes"):
            if session is not None and session.status == "awaiting_clip_pick":
                return ToolResult(True, apply_clip_pick_decision(ctx.config, session, "reject_all", {}))
            ok, msg = reject_batch(ctx.config, batch)
            return ToolResult(ok, msg)

        angle = str(args.get("angle") or "").strip()
        if not angle:
            return ToolResult(False, "Нужен angle=take_a|take_b|take_c (или a/b/c)")
        try:
            score = int(args.get("score") or 4)
        except (TypeError, ValueError):
            score = 4

        def _csv(key: str) -> list:
            return [p.strip() for p in str(args.get(key) or "").split(",") if p.strip()]

        if session is not None and session.status == "awaiting_clip_pick":
            # не затирать meta пустыми args
            cs = str(args.get("catalog_slug") or "").strip()
            if cs:
                session.meta["catalog_slug"] = cs
            ef = _csv("enters_from")
            et = _csv("exits_to")
            if ef:
                session.meta["enters_from"] = ef
            if et:
                session.meta["exits_to"] = et
            from ..lab.session import save_session

            save_session(ctx.config, session)
            msg = apply_clip_pick_decision(
                ctx.config,
                session,
                "keep",
                {
                    "angle": angle,
                    "score": score,
                    "notes": str(args.get("notes") or ""),
                },
            )
            return ToolResult(True, msg)

        ok, msg, _ = keep_best_by_angle(
            ctx.config,
            batch,
            angle,
            score=score,
            notes=str(args.get("notes") or ""),
            catalog_slug=str(args.get("catalog_slug") or ""),
            enters_from=_csv("enters_from"),
            exits_to=_csv("exits_to"),
        )
        return ToolResult(ok, msg)
