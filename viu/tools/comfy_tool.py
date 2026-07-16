"""Инструменты ComfyUI: статус, ensure, прогон, MoCap-пакет."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

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
        if not ok:
            lines.append("Запуск: comfy_ensure или lab_start topic=comfy.")
            lines.append("Гайд: docs/COMFY_SETUP.md")
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
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.comfy.install import ensure_comfy_installed

        with_models = str(args.get("models", "1")).lower() in ("1", "true", "yes", "")
        include_i2v = str(args.get("i2v", "0")).lower() in ("1", "true", "yes")
        with_pip = str(args.get("pip", "1")).lower() in ("1", "true", "yes", "")
        notes: list[str] = []

        def progress(msg: str) -> None:
            notes.append(msg)

        ok, msg = ensure_comfy_installed(
            ctx.config,
            with_models=with_models,
            include_i2v=include_i2v,
            with_pip=with_pip,
            progress=progress,
        )
        body = msg
        if notes:
            body = "Прогресс:\n" + "\n".join(f"  • {n}" for n in notes[-20:]) + "\n\n" + msg
        return ToolResult(ok, body)


class ComfyEnsureTool(Tool):
    name = "comfy_ensure"
    description = (
        "Если Comfy нет — установить в U:\\Viu\\ComfyUI; затем запустить API :8188 "
        "(лог: .viu/logs/comfy_launch.log)."
    )
    parameters = {"wait": "секунд ожидания API (по умолчанию 180)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        try:
            wait = float(args.get("wait") or 180)
        except (TypeError, ValueError):
            wait = 180.0
        ensure_workflow_templates(ctx.config, overwrite_stubs=True)
        ok, msg = ensure_comfy_running(ctx.config, wait_seconds=wait, auto_install=True)
        return ToolResult(ok, msg)


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
        "timeout": "секунд на один угол (900)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        action = str(args.get("action") or "").strip()
        if not action:
            return ToolResult(False, "Нужен action=.")
        slug = str(args.get("slug") or "mocap").strip()
        try:
            timeout = float(args.get("timeout") or 900)
        except (TypeError, ValueError):
            timeout = 900.0
        ok, msg, _ = run_triple_angles(
            ctx.config, action=action, slug=slug, timeout_each=timeout
        )
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
