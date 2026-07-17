"""Инструменты Вью для работы с Blender.

* blender_info — узнать всё о сцене/файле (через живой Blender или в фоне);
* blender_command — выполнить команду в запущенном Blender (мост);
* blender_screenshot — снять окно Blender (для vision-модели).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..integrations.blender import (
    COMMANDS,
    BlenderBridgeError,
    BlenderClient,
    dump_blend_info,
)
from .base import AgentContext, Tool, ToolResult


def _client(ctx: AgentContext) -> BlenderClient:
    return BlenderClient(host=ctx.config.blender_host, port=ctx.config.blender_port)


class BlenderInfoTool(Tool):
    name = "blender_info"
    description = (
        "Получить сведения о сцене Blender: объекты, кости, блендшейпы, материалы. "
        "Если Blender запущен с мостом — берёт из него; иначе читает .blend в фоне"
    )
    parameters = {"blend_file": "путь к .blend (нужен, если Blender не запущен)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        client = _client(ctx)
        if client.is_alive():
            try:
                data = client.scene_info()
                return ToolResult(True, "Живой Blender:\n" + json.dumps(data, ensure_ascii=False, indent=2))
            except BlenderBridgeError as exc:
                return ToolResult(False, str(exc))

        blend_file = args.get("blend_file", "")
        if not blend_file:
            return ToolResult(
                False,
                "Blender не запущен с мостом. Укажите blend_file для чтения в фоновом режиме.",
            )
        try:
            data = dump_blend_info(blend_file, blender_exe=ctx.config.blender_exe)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, "Файл (фоновый Blender):\n" + json.dumps(data, ensure_ascii=False, indent=2))


class BlenderCommandTool(Tool):
    name = "blender_command"
    description = "Выполнить команду в запущенном Blender через мост (аналог действия в интерфейсе)"
    parameters = {
        "command": f"одна из: {', '.join(COMMANDS)}",
        "params": "словарь параметров команды (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        command = args.get("command", "")
        if command not in COMMANDS:
            return ToolResult(False, f"Команда {command!r} не поддерживается. Доступны: {', '.join(COMMANDS)}")
        params = args.get("params") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                return ToolResult(False, "params должен быть корректным JSON-объектом")
        try:
            data = _client(ctx)._post(command, params)
        except BlenderBridgeError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, json.dumps(data, ensure_ascii=False, indent=2))


class BlenderScanTool(Tool):
    name = "blender_scan"
    description = (
        "Просканировать папку с .blend-файлами и составить сводку по каждому "
        "(объекты, есть ли скелет/блендшейпы) — чтобы выбрать подходящие модели"
    )
    parameters = {"folder": "путь к папке с .blend"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        folder = args.get("folder", "")
        if not folder:
            return ToolResult(False, "Не указан folder")
        p = Path(folder)
        if not p.is_dir():
            return ToolResult(False, f"Папка не найдена: {folder}")
        files = sorted(p.glob("*.blend"))
        if not files:
            return ToolResult(True, "В папке нет .blend-файлов.")

        lines = []
        for f in files:
            try:
                info = dump_blend_info(str(f), blender_exe=ctx.config.blender_exe)
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                lines.append(f"- {f.name}: ошибка чтения ({exc})")
                continue
            objects = info.get("objects", [])
            meshes = [o for o in objects if o.get("type") == "MESH"]
            has_arm = any(o.get("type") == "ARMATURE" for o in objects)
            shape_keys = sorted({sk for o in meshes for sk in o.get("shape_keys", [])})
            lines.append(
                f"- {f.name}: мешей={len(meshes)}, скелет={'да' if has_arm else 'нет'}, "
                f"блендшейпы={len(shape_keys)}"
            )
        return ToolResult(True, "Сводка по папке:\n" + "\n".join(lines))


class BlenderExportCascadeurTool(Tool):
    name = "blender_export_cascadeur"
    description = (
        "Экспорт одного .blend для Cascadeur: без WGT/widget-мешей, только deform bones, "
        "суффикс _cascadeur.fbx"
    )
    parameters = {
        "blend_file": "путь к .blend",
        "output_fbx": "куда сохранить (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.export_cascadeur import export_cascadeur_fbx

        blend = args.get("blend_file", "")
        if not blend:
            return ToolResult(False, "Не указан blend_file")
        out = args.get("output_fbx")
        try:
            path, meta = export_cascadeur_fbx(blend, out, blender_exe=ctx.config.blender_exe)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(
            True,
            f"Cascadeur FBX: {path}\n"
            f"deform_bones={meta.get('deform_bones')}, "
            f"widgets_hidden={meta.get('hidden_widgets')}, "
            f"selected={meta.get('selected')}",
        )


class BlenderExportCascadeurBatchTool(Tool):
    name = "blender_export_cascadeur_batch"
    description = (
        "Пакетный экспорт всех .blend/.fbx из Lab Inbox и Cascadeur Inbox "
        "→ Library/Lab/Models/CascadeurReady/*_cascadeur.fbx"
    )
    parameters = {
        "force": "1 = пересобрать даже если FBX свежее",
        "topic": "cascadeur (manifest в lab artifacts)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.export_cascadeur import batch_export_cascadeur_models

        force = str(args.get("force", "0")).lower() in ("1", "true", "yes")
        topic = str(args.get("topic") or "cascadeur").strip().lower()
        ok, msg, manifest = batch_export_cascadeur_models(
            ctx.config, topic=topic, force=force,
        )
        return ToolResult(ok, msg + f"\n\nManifest: {manifest}")


class BlenderExportShanyaTool(Tool):
    name = "blender_export_shanya"
    description=(
        "Экспорт FBX из Shanya_Erisa.blend для Unity: скрывает WGT/Circle/Sphere, "
        "Mesh+Armature, без bake animation"
    )
    parameters = {
        "blend_file": "путь к .blend",
        "output_fbx": "куда сохранить .fbx (опционально, рядом с blend)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.export_shanya import export_shanya_fbx

        blend = args.get("blend_file", "")
        if not blend:
            return ToolResult(False, "Не указан blend_file")
        out = args.get("output_fbx")
        try:
            path = export_shanya_fbx(blend, out, blender_exe=ctx.config.blender_exe)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(
            True,
            f"FBX готов: {path}\nСкопируй в Unity Assets/Characters/Shanya/",
        )


class BlenderScreenshotTool(Tool):
    name = "blender_screenshot"
    description = "Сделать снимок окна Blender и вернуть путь к файлу (для анализа vision-моделью)"
    parameters = {"path": "куда сохранить .png (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        path = args.get("path")
        try:
            data = _client(ctx).screenshot(path)
        except BlenderBridgeError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, f"Снимок сохранён: {data.get('path') if isinstance(data, dict) else data}")
