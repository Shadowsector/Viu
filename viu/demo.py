"""Офлайн-сценарий для демонстрации всего цикла агента без API/сети.

Сценарий имитирует ответы модели (mock) и прогоняет ключевые
возможности: планирование, работу с файлами, память, самоанализ и
самоулучшение (добавление нового инструмента).
"""

from __future__ import annotations

import json
from typing import List

NEW_TOOL_CODE = '''\
"""Пример инструмента, созданного Вью на лету."""
from viu.tools.base import AgentContext, Tool, ToolResult


class WordCountTool(Tool):
    name = "word_count"
    description = "Посчитать количество слов в тексте"
    parameters = {"text": "исходный текст"}

    def run(self, args, ctx: AgentContext) -> ToolResult:
        text = args.get("text", "")
        return ToolResult(True, f"words={len(text.split())}")
'''


def _j(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


def demo_script() -> List[str]:
    """Возвращает список mock-ответов модели в порядке их выдачи."""
    return [
        _j(
            {
                "thought": "Задача многоэтапная — составлю план.",
                "action": {
                    "tool": "plan_create",
                    "args": {
                        "goal": "Заложить основу проекта игры Анабарра",
                        "steps": [
                            "Создать документ концепции",
                            "Зафиксировать ключевое решение в памяти",
                            "Проверить и расширить свои возможности",
                        ],
                    },
                },
            }
        ),
        _j(
            {
                "thought": "Первый шаг — создам файл концепции.",
                "action": {
                    "tool": "write_file",
                    "args": {
                        "path": "anabarra/CONCEPT.md",
                        "content": "# Анабарра\n\n3D-игра. Черновик концепции.\n",
                    },
                },
            }
        ),
        _j(
            {
                "thought": "Отмечу шаг 1 выполненным.",
                "action": {"tool": "plan_update", "args": {"step_id": 1, "status": "done"}},
            }
        ),
        _j(
            {
                "thought": "Сохраню ключевое решение в долгосрочную память.",
                "action": {
                    "tool": "memory_write",
                    "args": {"text": "Игра Анабарра — 3D, движок пока не выбран.", "tags": ["анабарра", "решение"]},
                },
            }
        ),
        _j(
            {
                "thought": "Посмотрю на свой список файлов (самоанализ).",
                "action": {"tool": "self_inspect", "args": {}},
            }
        ),
        _j(
            {
                "thought": "Мне не хватает инструмента подсчёта слов — добавлю его себе.",
                "action": {"tool": "add_tool", "args": {"filename": "word_count.py", "code": NEW_TOOL_CODE}},
            }
        ),
        _j(
            {
                "thought": "Проверю только что созданный инструмент.",
                "action": {"tool": "word_count", "args": {"text": "Анабарра будет отличной игрой"}},
            }
        ),
        _j(
            {
                "thought": "Зафиксирую урок для будущих запусков.",
                "action": {"tool": "improve_prompt", "args": {"lesson": "Начинать сложные задачи с явного плана."}},
            }
        ),
        _j(
            {
                "thought": "Все шаги выполнены, задача решена.",
                "final": "Основа проекта заложена: создан CONCEPT.md, сохранено решение в память, добавлен инструмент word_count, зафиксирован урок.",
            }
        ),
    ]
