"""Динамическая загрузка пользовательских инструментов.

Находит все подклассы `Tool` в модулях каталога `viu/tools/custom/`
и регистрирует их. Используется как при старте агента, так и
инструментом самоулучшения `add_tool` для «горячей» подгрузки.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from pathlib import Path
from typing import List

from .base import Tool, ToolRegistry

CUSTOM_DIR = Path(__file__).parent / "custom"


def _load_module_from_path(path: Path):
    module_name = f"viu.tools.custom.{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Не удалось загрузить модуль из {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tools_in_module(module) -> List[Tool]:
    found: List[Tool] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, Tool) and obj is not Tool and obj.__module__ == module.__name__:
            found.append(obj())
    return found


def load_custom_tools(registry: ToolRegistry) -> List[str]:
    """Загружает все инструменты из custom-каталога. Возвращает их имена."""
    if not CUSTOM_DIR.exists():
        return []
    loaded: List[str] = []
    for path in sorted(CUSTOM_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            module = _load_module_from_path(path)
        except Exception:  # noqa: BLE001 — кривой custom-инструмент не должен ронять агента
            continue
        for tool in _tools_in_module(module):
            registry.register(tool)
            loaded.append(tool.name)
    return loaded


def load_one(registry: ToolRegistry, path: Path) -> List[str]:
    """Загружает инструменты из одного файла (для «горячей» регистрации)."""
    module = _load_module_from_path(path)
    names: List[str] = []
    for tool in _tools_in_module(module):
        registry.register(tool)
        names.append(tool.name)
    return names
