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
    """Извлекает JSON-объект протокола агента из ответа модели."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    def _valid_agent(obj: Any) -> bool:
        return isinstance(obj, dict) and ("final" in obj or "action" in obj)

    # Пробуем весь текст целиком.
    try:
        obj = json.loads(text)
        if _valid_agent(obj):
            return obj
    except json.JSONDecodeError:
        pass

    # Ищем все JSON-объекты в тексте; берём первый с action/final (не rename_plan и т.п.).
    for match in re.finditer(r"\{", text):
        try:
            obj, _end = json.JSONDecoder().raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if _valid_agent(obj):
            return obj

    # Fallback: жадный regex для старых/коротких ответов.
    match = _JSON_RE.search(text)
    if match:
        try:
            obj = json.loads(match.group(0))
            if _valid_agent(obj):
                return obj
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
    waiting_for_user: bool = False
    chat_only: bool = False


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

        # Защита от зацикливания: считаем повторы одинаковых вызовов (tool+args).
        repeat_counts: Dict[str, int] = {}
        REPEAT_NUDGE_AT = 2  # после 2-го одинакового вызова — предупреждение
        REPEAT_STOP_AT = 3   # на 3-м — принудительно останавливаемся

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
                        "content": (
                            "Ошибка: ответ должен быть одним JSON-объектом протокола "
                            'с ключом "action" или "final", без текста вне JSON. '
                            'Пример: {"thought":"...", "action":{"tool":"rig_apply_auto","args":{}}}'
                        ),
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
            elif tool_name == "ask_user":
                tr = tool.run(args, self.ctx)
                question = tr.content
                step = Step(kind="final", thought=thought, observation=question)
                result.steps.append(step)
                result.final = question
                result.completed = True
                result.waiting_for_user = True
                if on_step:
                    on_step(step)
                self._log(f"ASK_USER: {question}")
                return result
            else:
                tr = tool.run(args, self.ctx)
                observation = tr.render()
                ok = tr.ok

            step = Step(kind="action", thought=thought, tool=tool_name, args=args, observation=observation)
            result.steps.append(step)
            if on_step:
                on_step(step)
            self._log(f"ACTION {tool_name} args={args} -> ok={ok}")

            # Считаем повторы одинаковых действий, чтобы не крутиться в цикле.
            try:
                sig = tool_name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False)
            except TypeError:
                sig = tool_name + ":" + str(args)
            repeat_counts[sig] = repeat_counts.get(sig, 0) + 1
            count = repeat_counts[sig]

            messages.append({"role": "assistant", "content": raw})

            if count >= REPEAT_STOP_AT:
                final = (
                    f"Я несколько раз повторил «{tool_name}» без изменений — похоже, "
                    "дальше нужен твой ручной шаг (например, нажать ▶ Play в Unity или "
                    "что-то настроить в окне). Вот что я вижу:\n\n"
                    f"{observation}\n\n"
                    "Скажи, что сделать дальше, или выполни ручной шаг и напиши мне."
                )
                step = Step(kind="final", thought=thought, observation=final)
                result.steps.append(step)
                result.final = final
                result.completed = True
                if on_step:
                    on_step(step)
                self._log(f"STOP: repeated {tool_name} x{count}")
                return result

            observation_msg = f"Наблюдение:\n{observation}"
            if count >= REPEAT_NUDGE_AT:
                observation_msg += (
                    f"\n\n[Система] Ты уже вызывал «{tool_name}» с тем же результатом. "
                    "НЕ повторяй его. Если нужен ручной шаг пользователя — вызови ask_user "
                    "с конкретным вопросом. Иначе выбери другой инструмент или дай final."
                )
            messages.append({"role": "user", "content": observation_msg})

        result.final = "Достигнут лимит шагов без финального ответа."
        self._log("STOP: max_steps reached")
        return result

    def run_chat(self, task: str, on_step=None) -> RunResult:
        """Короткий ответ без инструментов — приветствия и small talk."""
        from .prompts.chat_mode import CHAT_SYSTEM

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": CHAT_SYSTEM},
            {"role": "user", "content": task.strip()},
        ]
        result = RunResult(final="", completed=False, chat_only=True)
        self._log(f"CHAT: {task}")

        raw = self.llm.complete(messages)
        parsed = extract_json(raw)
        if parsed and "final" in parsed:
            result.final = str(parsed["final"]).strip()
            result.completed = True
            step = Step(kind="final", thought=str(parsed.get("thought", "")), observation=result.final)
            result.steps.append(step)
            if on_step:
                on_step(step)
            self._log(f"CHAT_FINAL: {result.final[:120]}")
            return result

        if parsed and "action" in parsed:
            result.final = (
                "Привет! Я на связи. Если нужна работа — напиши «следующий шаг» "
                "или конкретную задачу."
            )
            result.completed = True
            self._log("CHAT: model tried action — fallback reply")
            return result

        fallback = (raw or "").strip()
        if fallback and not fallback.startswith("{"):
            result.final = fallback[:500]
        else:
            result.final = (
                "Привет! Я здесь. Напиши «следующий шаг», когда захочешь, чтобы я что-то сделала."
            )
        result.completed = True
        return result

    def run_status(self, task: str, on_step=None) -> RunResult:
        """Ответ о плане проекта — только текст, без Unity."""
        from .director import format_banner, plan_next_step
        from .project_state import project_status
        from .prompts.status_mode import STATUS_SYSTEM

        facts = project_status(self.config)
        try:
            plan = format_banner(plan_next_step(self.config))
        except OSError:
            plan = ""

        user_content = (
            f"Вопрос Дена: {task.strip()}\n\n"
            f"=== Roadmap и состояние (не выполняй, только расскажи) ===\n{facts}\n\n"
            f"=== Подсказка режиссёра (если спросит «что нажать» — переформулируй, не запускай) ===\n"
            f"{plan}"
        )
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": STATUS_SYSTEM},
            {"role": "user", "content": user_content},
        ]
        result = RunResult(final="", completed=False, chat_only=True)
        self._log(f"STATUS: {task}")

        raw = self.llm.complete(messages)
        parsed = extract_json(raw)
        if parsed and "final" in parsed:
            result.final = str(parsed["final"]).strip()
        else:
            # Fallback без LLM: хотя бы кратко из фактов.
            focus_line = ""
            for line in facts.splitlines():
                if "in_progress" in line or "→" in line or "Фокус" in line:
                    focus_line = line.strip()
                    break
            result.final = (
                "Сейчас смотрю на roadmap.\n"
                + (focus_line + "\n" if focus_line else "")
                + "Чтобы я начала делать — напиши «следующий шаг»."
            )
        result.completed = True
        step = Step(kind="final", thought="", observation=result.final)
        result.steps.append(step)
        if on_step:
            on_step(step)
        return result
