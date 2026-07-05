"""Инструменты Вью для работы с Blender.

* blender_info — узнать всё о сцене/файле (через живой Blender или в фоне);
* blender_command — выполнить команду в запущенном Blender (мост);
* blender_screenshot — снять окно Blender (для vision-модели).
"""

from __future__ import annotations

import json
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
