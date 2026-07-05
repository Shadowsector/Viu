"""Ядро агента Вью: цикл «рассуждение → действие → наблюдение» (ReAct).

Протокол общения с моделью не зависит от провайдера: модель отвечает
одним JSON-объектом, агент его разбирает, выполняет инструмент и
добавляет наблюдение в диалог, повторяя цикл до финального ответа.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import Config
from .llm import LLMProvider, build_provider
from .memory import MemoryStore
from .planning import Planner
from .prompts import build_system_prompt
from .tools import AgentContext, ToolRegistry, build_default_registry

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> Optional[dict]:
    """Извлекает JSON-объект из ответа модели, устойчиво к обёрткам ```/тексту."""
    text = text.strip()
    # Убираем markdown-обёртку ```json ... ```
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_RE.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


@dataclass
class Step:
    kind: str  # "action" | "final" | "error"
    thought: str = ""
    tool: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""


@dataclass
class RunResult:
    final: str
    completed: bool
    steps: List[Step] = field(default_factory=list)


class Agent:
    def __init__(
        self,
        config: Optional[Config] = None,
        llm: Optional[LLMProvider] = None,
        registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.config = (config or Config()).ensure_dirs()
        self.llm = llm or build_provider(self.config)
        self.registry = registry or build_default_registry()
        self.memory = MemoryStore(self.config.data_dir / "memory.json")
        self.planner = Planner(self.config.data_dir / "plan.json")
        self.ctx = AgentContext(
            config=self.config,
            memory=self.memory,
            planner=self.planner,
            registry=self.registry,
        )

    def _log(self, line: str) -> None:
        log_path = self.config.data_dir / "logs" / "agent.log"
        try:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
        except OSError:
            pass

    def run(self, task: str, on_step=None) -> RunResult:
        """Запускает цикл решения задачи. `on_step` — опциональный колбэк(Step)."""
        system = build_system_prompt(self.config, self.registry, self.memory, self.planner)
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]
        result = RunResult(final="", completed=False)
        self._log(f"TASK: {task}")

        for _ in range(self.config.max_steps):
            raw = self.llm.complete(messages)
            parsed = extract_json(raw)

            if parsed is None:
                step = Step(kind="error", observation="Ответ не является валидным JSON.")
                result.steps.append(step)
                if on_step:
                    on_step(step)
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": "Ошибка: ответ должен быть одним JSON-объектом по протоколу. Повтори.",
                    }
                )
                continue

            thought = str(parsed.get("thought", ""))

            if "final" in parsed:
                step = Step(kind="final", thought=thought, observation=str(parsed["final"]))
                result.steps.append(step)
                result.final = str(parsed["final"])
                result.completed = True
                if on_step:
                    on_step(step)
                self._log(f"FINAL: {result.final}")
                return result

            action = parsed.get("action") or {}
            tool_name = action.get("tool", "")
            args = action.get("args", {}) or {}
            tool = self.registry.get(tool_name)

            if tool is None:
                observation = (
                    f"Инструмент {tool_name!r} не найден. Доступны: {', '.join(self.registry.names())}"
                )
                ok = False
            else:
                tr = tool.run(args, self.ctx)
                observation = tr.render()
                ok = tr.ok

            step = Step(kind="action", thought=thought, tool=tool_name, args=args, observation=observation)
            result.steps.append(step)
            if on_step:
                on_step(step)
            self._log(f"ACTION {tool_name} args={args} -> ok={ok}")

            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"Наблюдение:\n{observation}"})

        result.final = "Достигнут лимит шагов без финального ответа."
        self._log("STOP: max_steps reached")
        return result
