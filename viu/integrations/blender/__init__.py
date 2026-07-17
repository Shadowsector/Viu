"""Мост «Вью ↔ Blender».

Состоит из трёх частей:
* protocol — общий, независимый от Blender, набор команд и их разбор;
* client — клиент со стороны Вью (HTTP), общается с живым Blender;
* headless — получение сведений о .blend-файле через фоновый запуск Blender.

Модуль bridge_addon.py — это надстройка, которая ставится ВНУТРЬ Blender,
и намеренно НЕ импортируется отсюда (ей нужен модуль bpy, доступный только
внутри Blender).
"""

from .client import BlenderBridgeError, BlenderClient
from .headless import build_dump_command, dump_blend_info
from .protocol import COMMANDS, dispatch, make_error, make_ok

__all__ = [
    "BlenderClient",
    "BlenderBridgeError",
    "dump_blend_info",
    "build_dump_command",
    "COMMANDS",
    "dispatch",
    "make_error",
    "make_ok",
]
