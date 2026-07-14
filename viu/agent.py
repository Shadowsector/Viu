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
        return isinstance(obj, dict) and (
            "final" in obj or "action" in obj or "inner" in obj
        )

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


def extract_inner_json(text: str) -> Optional[dict]:
    """Извлекает JSON фазы размышления: {"inner": "…"}."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    def _valid(obj: Any) -> bool:
        return isinstance(obj, dict) and "inner" in obj

    try:
        obj = json.loads(text)
        if _valid(obj):
            return obj
    except json.JSONDecodeError:
        pass

    for match in re.finditer(r"\{", text):
        try:
            obj, _end = json.JSONDecoder().raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if _valid(obj):
            return obj
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
    inner_thought: str = ""
    tool_errors: bool = False


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

    def run(
        self,
        task: str,
        on_step=None,
        *,
        max_steps: Optional[int] = None,
    ) -> RunResult:
        """Инструменты и действия — только явная команда «делай»."""
        limit = max_steps if max_steps is not None else self.config.max_steps
        system = build_system_prompt(self.config, self.registry, self.memory, self.planner)
        user = task
        chat_only = False

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        result = RunResult(final="", completed=False, chat_only=chat_only)
        self._log(f"TASK[work]: {task[:200]}")
        voice_retries = 0

        # Защита от зацикливания: считаем повторы одинаковых вызовов (tool+args).
        repeat_counts: Dict[str, int] = {}
        REPEAT_NUDGE_AT = 2  # после 2-го одинакового вызова — предупреждение
        REPEAT_STOP_AT = 3   # на 3-м — принудительно останавливаемся

        for _ in range(limit):
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
                text = str(parsed["final"]).strip()
                from .prompts.reflect_mode import viu_voice_issues

                issues = viu_voice_issues(text)
                if issues and voice_retries < 2:
                    voice_retries += 1
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {
                            "role": "user",
                            "content": "Тон не Вью: "
                            + ", ".join(issues)
                            + ". Перепиши final — на «ты» Дену, женский род, без «Проверьте»/«Прошу прощения».",
                        }
                    )
                    continue
                step = Step(kind="final", thought=thought, observation=text)
                result.steps.append(step)
                result.final = text
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
                if question.startswith("QUEUED_FOR_DEN:"):
                    # Ден away — вопрос в очереди, цикл не стопорим.
                    observation = question
                    ok = True
                    step = Step(
                        kind="action",
                        thought=thought,
                        tool=tool_name,
                        args=args,
                        observation=observation,
                    )
                    result.steps.append(step)
                    if on_step:
                        on_step(step)
                    self._log(f"ASK_QUEUED: {question}")
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Результат ask_user:\n{observation}\n"
                                "Ден не у ПК. Продолжай работу без него, если можно. "
                                "Не повторяй тот же вопрос."
                            ),
                        }
                    )
                    continue
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
            if not ok:
                result.tool_errors = True
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
                # Эскалация Cursor вместо «нажми Play» Дена.
                try:
                    from .escalate import escalate_failure

                    _, esc = escalate_failure(
                        self.ctx,
                        tool_name=tool_name,
                        error_text=observation,
                    )
                except Exception as exc:  # noqa: BLE001
                    esc = f"(escalate fail: {exc})"
                final = (
                    f"Застряла на «{tool_name}» (повтор {count}×). "
                    "Не кручу дальше — отправила лог Cursor и поискала фикс.\n\n"
                    f"{esc}"
                )
                step = Step(kind="final", thought=thought, observation=final)
                result.steps.append(step)
                result.final = final
                result.completed = True
                result.tool_errors = True
                if on_step:
                    on_step(step)
                self._log(f"STOP: repeated {tool_name} x{count} → escalate")
                return result

            observation_msg = f"Наблюдение:\n{observation}"
            if not ok:
                observation_msg += (
                    "\n\n[Система] Инструмент упал. НЕ повторяй его сразу. "
                    "Сделай: (1) web_search по тексту ошибки, "
                    "(2) cursor_handoff_with_logs с логом, "
                    "(3) если это задача inbox — cursor_inbox_complete status=blocked. "
                    "Дена кнопками не дёргай."
                )
            if count >= REPEAT_NUDGE_AT:
                observation_msg += (
                    f"\n\n[Система] Ты уже вызывал «{tool_name}» с тем же результатом. "
                    "НЕ повторяй его. Сделай web_search + cursor_handoff_with_logs "
                    "или другой инструмент / final."
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

    def run_reflect(
        self,
        task: str,
        on_step=None,
        *,
        history: Optional[List[Dict[str, str]]] = None,
        heartbeat: bool = False,
    ) -> RunResult:
        """Один проход чата: thought + final. Без инструментов."""
        from .prompts.reflect_mode import (
            REFLECT_SYSTEM,
            looks_like_story_chat,
            reflect_reply_issues,
            reflect_temperature,
        )
        from .situational_context import build_reflect_notes

        temp = reflect_temperature(self.config)
        notes = build_reflect_notes(self.config)
        result = RunResult(final="", completed=False, chat_only=True)

        if heartbeat:
            return self._run_reflect_heartbeat(on_step, temp=temp, notes=notes)

        user_text = task.strip()
        self._log(f"REFLECT: {user_text[:160]}")

        system = REFLECT_SYSTEM
        if notes:
            system += "\n\n--- Заметки (фон, не зачитывать списком) ---\n" + notes

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history[-16:])
        messages.append({"role": "user", "content": user_text})

        for _ in range(3):
            raw = self.llm.complete(messages, temperature=temp)
            parsed = extract_json(raw)

            if parsed and "final" in parsed and "action" not in parsed:
                text = str(parsed["final"]).strip()
                thought = str(parsed.get("thought") or parsed.get("inner") or "").strip()
                issues = reflect_reply_issues(text, has_history=bool(history))
                if issues:
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {
                            "role": "user",
                            "content": "Плохой тон: "
                            + ", ".join(issues)
                            + ". Перепиши final тепло и по-русски: без мата, чернухи и слоганов. "
                            "Как близкий человек Дена. JSON: thought+final.",
                        }
                    )
                    continue
                result.inner_thought = thought
                result.final = text
                result.completed = True
                if thought and on_step:
                    on_step(Step(kind="think", thought=thought))
                step = Step(kind="final", thought=thought, observation=result.final)
                result.steps.append(step)
                if on_step:
                    on_step(step)
                if looks_like_story_chat(user_text):
                    try:
                        from .vision import append_vision

                        append_vision(
                            self.config,
                            "Диалог",
                            f"**Ден:** {user_text[:500]}\n**Вью:** {text[:800]}",
                        )
                    except OSError:
                        pass
                return result

            if parsed and "action" in parsed:
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": "Сейчас только разговор — без action. Ответь JSON thought+final.",
                    }
                )
                continue

            if parsed is None and raw.strip() and not raw.strip().startswith("{"):
                result.final = raw.strip()[:800]
                result.completed = True
                return result

            messages.append({"role": "assistant", "content": raw or "{}"})
            messages.append(
                {
                    "role": "user",
                    "content": 'Нужен JSON: {"thought":"…","final":"ответ Дену…"} — без action.',
                }
            )

        result.final = (
            "Хм, меня на секунду переклинило на шаблон. "
            "Спроси ещё раз — или «следующий шаг», если пора делать руками."
        )
        result.completed = True
        return result

    def _run_reflect_heartbeat(
        self,
        on_step,
        *,
        temp: float,
        notes: str,
    ) -> RunResult:
        from .prompts.reflect_mode import HEARTBEAT_SYSTEM, HEARTBEAT_TASK

        system = HEARTBEAT_SYSTEM
        if notes:
            system += "\n\n--- Заметки ---\n" + notes
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": HEARTBEAT_TASK},
        ]
        result = RunResult(final="", completed=False, chat_only=True)
        self._log("REFLECT_HEARTBEAT")

        for _ in range(2):
            raw = self.llm.complete(messages, temperature=temp)
            parsed = extract_json(raw)
            if parsed and "final" in parsed:
                result.final = str(parsed["final"]).strip()
                result.completed = True
                if on_step:
                    on_step(Step(kind="final", observation=result.final))
                return result
            messages.append({"role": "assistant", "content": raw or "{}"})
            messages.append(
                {"role": "user", "content": 'Нужен JSON: {"final":"живая мысль…"}.'}
            )

        result.final = "Проснулась. Когда вернёшься — поговорим про снежинку или анимации?"
        result.completed = True
        return result
