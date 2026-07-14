"""Инструменты ComfyUI: статус, прогон workflow, пути."""

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
from .base import AgentContext, Tool, ToolResult


def _client(ctx: AgentContext) -> ComfyClient:
    url = getattr(ctx.config, "comfy_url", None) or "http://127.0.0.1:8188"
    return ComfyClient(base_url=str(url))


class ComfyStatusTool(Tool):
    name = "comfy_status"
    description = (
        "Статус ComfyUI: сервер :8188, корень установки, workflows, папки Refs/ComfyOut."
    )
    parameters = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        write_install_readme(ctx.config)
        root = resolve_comfy_root(ctx.config)
        lines = [
            f"URL: {getattr(ctx.config, 'comfy_url', 'http://127.0.0.1:8188')}",
            f"Root: {root or '(не найден — VIU_COMFY_ROOT или U:\\ComfyUI)'}",
            f"Workflows: {comfy_workflows_dir(ctx.config)}",
            f"Refs (для Cascadeur): {comfy_refs_dir(ctx.config)}",
            f"ComfyOut: {comfy_out_dir(ctx.config)}",
        ]
        wfs = list_workflows(ctx.config)
        if wfs:
            lines.append("Workflow files:")
            lines.extend(f"  • {p.name}" for p in wfs)
        else:
            lines.append("Workflow files: (пусто — нужен default.json API Format)")

        ok, msg = _client(ctx).ping()
        lines.append(msg)
        if not ok:
            lines.append(
                "\nЗапусти ComfyUI (обычно python main.py --listen), "
                "потом снова comfy_status."
            )
            lines.append("Гайд: docs/COMFY_SETUP.md")
        # Статус-инструмент всегда ok: offline — это информация, не сбой тула.
        return ToolResult(True, "\n".join(lines))


class ComfyRunTool(Tool):
    name = "comfy_run"
    description = (
        "Прогнать ComfyUI workflow (API JSON). prompt= текст для CLIPTextEncode. "
        "workflow=default или имя файла в .viu/comfy/workflows/. "
        "Результат копируется в Lab/Refs."
    )
    parameters = {
        "prompt": "текст действия / сцены (подставится в CLIPTextEncode)",
        "workflow": "default или имя .json",
        "timeout": "секунд ожидания (по умолчанию 600)",
        "slug": "имя выходного файла без расширения (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        prompt = str(args.get("prompt") or "").strip()
        workflow_name = str(args.get("workflow") or "default").strip()
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
            return ToolResult(False, ping + "\nСначала запусти ComfyUI.")

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
                "Проверь, что в workflow есть SaveImage / SaveVideo / VHS_VideoCombine.",
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
        lines.append(
            "Дальше: Cascadeur File→Import→Reference video (mp4) "
            "или MoCap с image (когда подключим auto)."
        )
        return ToolResult(True, "\n".join(lines))
