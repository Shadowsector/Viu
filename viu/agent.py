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
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*", re.IGNORECASE)


def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t).strip()
    m = re.search(r"```(?:json)?\s*(\{.*)", t, re.DOTALL | re.IGNORECASE)
    if m:
        inner = m.group(1)
        inner = re.sub(r"\s*```\s*$", "", inner, flags=re.DOTALL).strip()
        return inner
    return t


def _json_candidate_text(text: str) -> str:
    t = _strip_code_fences(text)
    if "{" in t and not t.lstrip().startswith("{"):
        t = t[t.index("{") :]
    return t.strip()


_PSEUDO_THOUGHT_RE = re.compile(
    r"(?im)^\s*(?:\*\*|__|#+\s*)?\s*(?:thought|thinking|inner|размышл\w*)"
    r"\s*(?:\*\*|__)?\s*[:：]\s*(?:\*\*|__)?"
)
_PSEUDO_FINAL_RE = re.compile(
    r"(?im)^\s*(?:\*\*|__|#+\s*)?\s*(?:final|answer|ответ|результат)"
    r"\s*(?:\*\*|__)?\s*[:：]\s*(?:\*\*|__)?"
)


def looks_like_leaked_protocol(text: str) -> bool:
    """Сырой протокол агента не должен уходить Дену в Telegram/GUI."""
    if not (text or "").strip():
        return False
    t = text.strip()
    low = t.lower()
    if "```json" in low:
        return True
    if t.startswith("{") and ('"thought"' in t or '"final"' in t):
        return True
    if '"thought"' in t and '"final"' in t:
        return True
    if re.search(r'^\s*\{\s*"thought"\s*:', t):
        return True
    # Markdown / псевдо-протокол: **thought:** … **final:** …
    if _PSEUDO_THOUGHT_RE.search(t) or _PSEUDO_FINAL_RE.search(t):
        return True
    return False


def extract_pseudo_final(text: str) -> str:
    """Вытащить видимый ответ из markdown thought/final без JSON."""
    body = (text or "").strip()
    if not body:
        return ""
    fm = list(_PSEUDO_FINAL_RE.finditer(body))
    if fm:
        chunk = body[fm[-1].end() :].strip()
        tm = _PSEUDO_THOUGHT_RE.search(chunk)
        if tm and tm.start() > 0:
            chunk = chunk[: tm.start()].strip()
        return _strip_pseudo_labels(chunk)
    if _PSEUDO_THOUGHT_RE.search(body):
        return ""
    return ""


def _strip_pseudo_labels(text: str) -> str:
    """Убрать оставшиеся метки thought/final из текста."""
    lines: list[str] = []
    skip = False
    for line in (text or "").splitlines():
        if _PSEUDO_THOUGHT_RE.match(line):
            skip = True
            continue
        if _PSEUDO_FINAL_RE.match(line):
            skip = False
            continue
        if skip:
            if not line.strip():
                skip = False
            continue
        lines.append(line)
    out = "\n".join(lines).strip()
    out = re.sub(
        r"(?is)^\s*(?:\*\*)?(?:thought|thinking)(?:\*\*)?\s*[:：].*?(?=\n\n|\Z)",
        "",
        out,
    ).strip()
    return out


def _unescape_json_string(s: str) -> str:
    try:
        return json.loads(f'"{s}"')
    except json.JSONDecodeError:
        return (
            s.replace("\\n", "\n")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
            .replace("\\t", "\t")
        )


def extract_loose_final(text: str) -> tuple[str, bool]:
    """Достать final из битого JSON. bool — закрыта ли строка кавычкой."""
    m = re.search(r'"final"\s*:\s*"', text, re.IGNORECASE | re.DOTALL)
    if not m:
        return "", False
    i = m.end()
    chars: list[str] = []
    closed = False
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            chars.append(c)
            chars.append(text[i + 1])
            i += 2
            continue
        if c == '"':
            closed = True
            break
        chars.append(c)
        i += 1
    return _unescape_json_string("".join(chars)).strip(), closed


def sanitize_reflect_visible(text: str) -> str:
    """То, что можно показать Дену: без JSON и без thought/final меток."""
    body = (text or "").strip()
    if not body:
        return ""
    if looks_like_leaked_protocol(body):
        pseudo = extract_pseudo_final(body)
        if pseudo and not looks_like_leaked_protocol(pseudo):
            return pseudo[:4000]
        loose, closed = extract_loose_final(_json_candidate_text(body))
        if loose and closed and not looks_like_leaked_protocol(loose):
            return loose[:4000]
        return ""
    cleaned = _strip_pseudo_labels(body)
    if looks_like_leaked_protocol(cleaned):
        return ""
    return cleaned[:4000]


def parse_reflect_response(
    raw: str,
) -> tuple[Optional[str], Optional[str], bool, Optional[dict]]:
    """final, thought, truncated, parsed dict (если JSON целый)."""
    body = (raw or "").strip()
    if not body:
        return None, None, False, None

    candidate = _json_candidate_text(body)
    parsed = extract_json(body) or extract_json(candidate)
    loose_final, closed = extract_loose_final(candidate or body)

    if parsed and "action" not in parsed:
        thought = str(parsed.get("thought") or parsed.get("inner") or "").strip()
        fps = parsed.get("final_parts")
        if isinstance(fps, list):
            parts = [str(p).strip() for p in fps if str(p).strip()]
            if parts:
                final = "\n\n".join(parts)
                return final, thought or None, False, parsed
        if "final" in parsed:
            final = str(parsed.get("final") or "").strip()
            truncated = bool(loose_final) and not closed
            return final or None, thought or None, truncated, parsed

    if loose_final and closed:
        return loose_final, None, False, None

    if loose_final and not closed:
        return None, None, True, None

    # Markdown thought/final → только кусок после final
    pseudo = extract_pseudo_final(body)
    if pseudo:
        return pseudo[:2000], None, False, None
    if _PSEUDO_THOUGHT_RE.search(body) or _PSEUDO_FINAL_RE.search(body):
        return None, None, True, None

    if looks_like_leaked_protocol(body):
        return None, None, True, None

    if not candidate.lstrip().startswith("{") and '"final"' not in body:
        return body[:2000], None, False, None

    return None, None, True, None


def salvage_partial_final(raw: str, *, min_len: int = 80) -> str:
    """Если JSON оборван — вернуть осмысленный кусок final, не сырой протокол."""
    body = (raw or "").strip()
    if not body:
        return ""
    loose, closed = extract_loose_final(_json_candidate_text(body))
    if not loose or len(loose) < min_len or looks_like_leaked_protocol(loose):
        return ""
    if closed:
        return loose
    return loose.rstrip() + "\n\n_(ответ оборвался — напиши «продолжай»)_"


def extract_json(text: str) -> Optional[dict]:
    """Извлекает JSON-объект протокола агента из ответа модели."""
    text = _json_candidate_text(text)

    def _valid_agent(obj: Any) -> bool:
        return isinstance(obj, dict) and (
            "final" in obj
            or "final_parts" in obj
            or "action" in obj
            or "inner" in obj
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
    echo_telegram: bool = False
    final_parts: List[str] = field(default_factory=list)


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

    def _model_for(self, role: str) -> str | None:
        from .llm_roles import effective_model

        return effective_model(self.config, role)  # type: ignore[arg-type]

    def _maybe_dump_reflect_request(
        self,
        *,
        mode: str,
        model: str,
        temperature: float,
        messages: List[Dict[str, str]],
        attempt: int = 0,
    ) -> None:
        from .prompts.reflect_mode import (
            reflect_dump_enabled,
            reflect_no_history,
            reflect_no_system,
            reflect_use_filters,
            write_reflect_request_dump,
        )

        if not reflect_dump_enabled():
            return
        import os

        llm = self.llm
        write_reflect_request_dump(
            self.config,
            mode=mode,
            model=model or "",
            temperature=temperature,
            messages=messages,
            extra={
                "attempt": attempt,
                "base_url": getattr(llm, "base_url", ""),
                "reflect_no_system": reflect_no_system(),
                "reflect_no_history": reflect_no_history(),
                "reflect_filtered": reflect_use_filters(),
                "ollama_num_ctx": os.environ.get("VIU_OLLAMA_NUM_CTX", ""),
                "ollama_num_predict": os.environ.get("VIU_OLLAMA_NUM_PREDICT", ""),
                "ollama_keep_alive": os.environ.get("VIU_OLLAMA_KEEP_ALIVE", ""),
            },
        )

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
        from .llm_roles import guess_work_role

        work_role = guess_work_role(task)
        work_model = self._model_for(work_role)
        self._log(
            f"TASK[work/{work_role}]: {task[:200]}"
            + (f" model={work_model}" if work_model else "")
        )
        voice_retries = 0

        # Защита от зацикливания: считаем повторы одинаковых вызовов (tool+args).
        repeat_counts: Dict[str, int] = {}
        REPEAT_NUDGE_AT = 2  # после 2-го одинакового вызова — предупреждение
        REPEAT_STOP_AT = 3   # на 3-м — принудительно останавливаемся

        for _ in range(limit):
            raw = self.llm.complete(messages, model=work_model)
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

        raw = self.llm.complete(messages, model=self._model_for("reflect"))
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
        away_ping: bool = False,
        echo_telegram: bool = False,
    ) -> RunResult:
        """Чат: по умолчанию без фильтров (VIU_REFLECT_FILTERED=1 — старый режим)."""
        from .prompts.reflect_mode import reflect_use_filters

        if not reflect_use_filters():
            return self._run_reflect_bare(
                task,
                on_step,
                history=history,
                heartbeat=heartbeat,
                away_ping=away_ping,
                echo_telegram=echo_telegram,
            )
        return self._run_reflect_filtered(
            task,
            on_step,
            history=history,
            heartbeat=heartbeat,
            away_ping=away_ping,
            echo_telegram=echo_telegram,
        )

    def _run_reflect_bare(
        self,
        task: str,
        on_step=None,
        *,
        history: Optional[List[Dict[str, str]]] = None,
        heartbeat: bool = False,
        away_ping: bool = False,
        echo_telegram: bool = False,
    ) -> RunResult:
        from .prompts.reflect_mode import (
            AWAY_PING_SYSTEM,
            AWAY_PING_TASK,
            HEARTBEAT_SYSTEM,
            HEARTBEAT_TASK,
            REFLECT_BARE,
            REFLECT_BARE_MINIMAL,
            REFLECT_IDENTITY_ANCHOR,
            REFLECT_IMMERSION_ANCHOR,
            REFLECT_LIVING_HINT,
            addresses_user_as_owner,
            claims_to_be_llm,
            has_english_slip,
            reflect_include_story_history,
            reflect_no_history,
            reflect_no_system,
            reflect_temperature,
            reflect_use_filters,
        )
        from .reflect_delivery import (
            collect_final_parts,
            continuation_user_prompt,
            list_delivery_hint,
            reflect_max_parts,
            reflect_max_words_per_part,
            should_fetch_more_parts,
            truncate_retry_hint,
        )

        temp = reflect_temperature(self.config)
        result = RunResult(
            final="", completed=False, chat_only=True, echo_telegram=echo_telegram
        )
        user_text = (task or "").strip()

        from .situational_context import (
            build_reflect_notes_plot,
            format_reflect_life_block,
            needs_plot_file_context,
        )

        plot_ctx = False
        if heartbeat:
            if away_ping:
                system = AWAY_PING_SYSTEM
                user_msg = AWAY_PING_TASK
            else:
                system = HEARTBEAT_SYSTEM
                user_msg = HEARTBEAT_TASK
            system = REFLECT_IMMERSION_ANCHOR + "\n" + system
            # Чтобы сама писала «из жизни» — события + лор, не пустой тик.
            try:
                from .event_memory import format_events_digest

                ev = format_events_digest(self.config, limit=6)
                if ev:
                    system += "\n\n" + ev
            except Exception:  # noqa: BLE001
                pass
            try:
                life = format_reflect_life_block(self.config, max_chars=1200)
                if life:
                    system += "\n\n" + life
            except Exception:  # noqa: BLE001
                pass
        else:
            # По умолчанию system = полный REFLECT_VOICE (жизнь/характер из reflect).
            # VIU_REFLECT_NO_SYSTEM=1 — только Modelfile; тогда якорь/жизнь едут в user.
            no_sys = reflect_no_system()
            system = REFLECT_BARE_MINIMAL if no_sys else REFLECT_BARE
            user_msg = user_text
            extra_user_blocks: list[str] = []

            def _attach(block: str) -> None:
                nonlocal system
                if not block:
                    return
                if no_sys:
                    extra_user_blocks.append(block)
                else:
                    system += block if block.startswith("\n") else ("\n\n" + block)

            if no_sys:
                _attach(REFLECT_IDENTITY_ANCHOR)

            _attach(REFLECT_IMMERSION_ANCHOR)
            _attach(REFLECT_LIVING_HINT)

            try:
                life = format_reflect_life_block(self.config)
                if life:
                    _attach(life)
            except Exception:  # noqa: BLE001
                pass

            try:
                from .lore_digest import format_lore_digest

                lore = format_lore_digest(self.config)
                if lore:
                    _attach(lore)
            except Exception:  # noqa: BLE001
                pass

            try:
                from .event_memory import format_events_digest

                ev = format_events_digest(self.config)
                if ev:
                    _attach(ev)
            except Exception:  # noqa: BLE001
                pass

            # Сюжетный RAG: писали всегда, а в bare не читали — поэтому «забывала».
            try:
                from .prompts.reflect_mode import user_is_greeting
                from .story_memory import ensure_logs_ingested, get_story_memory

                ensure_logs_ingested(self.config)
                if not user_is_greeting(user_text):
                    story_ctx = get_story_memory(self.config).format_context(
                        user_text, recent_n=6, search_n=4
                    )
                    if story_ctx:
                        _attach(
                            "--- Сюжетная память (продолжай нить, не с нуля) ---\n"
                            + story_ctx
                        )
            except Exception:  # noqa: BLE001
                pass

            hint = list_delivery_hint(user_text)
            if hint:
                _attach(hint)
            try:
                from .integrations.comfy.intent import (
                    format_reflect_comfy_block,
                    mentions_comfy,
                )
                from .integrations.comfy.prompt_edit import is_comfy_short_task

                if mentions_comfy(user_text):
                    comfy_block = format_reflect_comfy_block(self.config)
                    if is_comfy_short_task(user_text):
                        comfy_block += (
                            "\nДен просит короткий EN-промпт / действие: "
                            "1–3 предложения в final, без эмодзи и режиссёрского сценария. "
                            "Полный Wan — «покажи промпт» / Промпт Wan → Comfy."
                        )
                    _attach("\n\n" + comfy_block)
                elif is_comfy_short_task(user_text):
                    _attach(
                        "\n\n--- Comfy/Wan ---\n"
                        "Ден просит короткий EN-промпт / действие для ComfyUI, "
                        "не сценарий игры. В final: 1–3 предложения, без эмодзи, "
                        "без **markdown**, без «режиссёрского» описания сцены. "
                        "Если нужен полный Wan-блок — скажи открыть «Промпт Wan → Comfy» "
                        "или напиши «покажи промпт»."
                    )
            except Exception:  # noqa: BLE001
                pass
            try:
                from .viu_memory import format_reflect_block

                # Короткий digest (не весь файл). При NO_SYSTEM=1 — в user,
                # иначе system отбрасывается и привычки/«запомни» не доходят.
                mem = format_reflect_block(self.config)
                if mem:
                    _attach(mem)
            except Exception:  # noqa: BLE001
                pass
            if needs_plot_file_context(user_text):
                plot_notes = build_reflect_notes_plot(self.config)
                if plot_notes:
                    plot_ctx = True
                    _attach(
                        "--- Канон сюжета и квестов (читай, не выдумывай; "
                        "не зачитывай markdown списком) ---\n"
                        + plot_notes
                    )
            if extra_user_blocks:
                user_msg = user_text + "\n\n" + "\n\n".join(extra_user_blocks)

        messages: List[Dict[str, str]] = []
        if not (reflect_no_system() and not heartbeat):
            messages.append({"role": "system", "content": system})
        hist = [] if reflect_no_history() else list(history or [])
        if (
            not reflect_no_history()
            and reflect_include_story_history()
            and not heartbeat
            and len(hist) < 4
        ):
            try:
                from .story_memory import get_story_memory

                long_hist = get_story_memory(self.config).as_chat_history(limit=16)
                if long_hist:
                    hist = long_hist
            except OSError:
                pass
        if hist and not heartbeat:
            messages.extend(hist[-16:])
        messages.append({"role": "user", "content": user_msg})

        # «запомни» — сразу на диск, до ответа модели (echo/abort не сожрут).
        if not heartbeat and user_text:
            try:
                from .viu_memory import looks_like_remember_request, record_explicit_memory

                if looks_like_remember_request(user_text):
                    if record_explicit_memory(
                        self.config,
                        user_text,
                        source="chat-early",
                        history=hist,
                    ):
                        self._log("MEMORY early remember ok")
            except Exception:  # noqa: BLE001
                pass

        reflect_model = self._model_for("reflect")
        self._log(
            f"REFLECT bare hist={len(hist)} tg={int(echo_telegram)}"
            f" no_sys={int(reflect_no_system())} no_hist={int(reflect_no_history())}"
            f" filtered={int(reflect_use_filters())} plot_ctx={int(plot_ctx)}"
            f" story_hist={int(reflect_include_story_history())}"
        )

        def _extend_reflect_parts(parts: List[str]) -> List[str]:
            max_p = reflect_max_parts(self.config, user_text=user_text)
            max_words = reflect_max_words_per_part(self.config)
            while len(parts) < max_p:
                prompt = continuation_user_prompt(
                    user_text=user_text,
                    prior_parts=parts,
                    part_index=len(parts),
                    max_parts=max_p,
                    max_words=max_words,
                )
                cont_msgs: List[Dict[str, str]] = list(messages)
                cont_msgs.append(
                    {
                        "role": "assistant",
                        "content": json.dumps({"final": parts[-1]}, ensure_ascii=False),
                    }
                )
                cont_msgs.append({"role": "user", "content": prompt})
                try:
                    raw_part = self.llm.complete(
                        cont_msgs, temperature=temp, model=reflect_model
                    )
                except RuntimeError as exc:
                    self._log(f"REFLECT_PART fail: {exc}")
                    break
                part_text, _pt, part_trunc, part_parsed = parse_reflect_response(
                    raw_part
                )
                if not part_text or part_text.strip() == parts[-1].strip():
                    break
                parts.append(part_text.strip())
                self._log(f"REFLECT_PART {len(parts)}/{max_p}")
                if not should_fetch_more_parts(
                    part_text,
                    parsed=part_parsed,
                    truncated=part_trunc,
                    config=self.config,
                    user_text=user_text,
                ):
                    break
            return parts

        def _accept(
            text: str,
            thought: str = "",
            parsed: Optional[Dict[str, str]] = None,
            *,
            initial_truncated: bool = False,
        ) -> RunResult:
            parts = collect_final_parts(text, parsed)
            if should_fetch_more_parts(
                parts[-1] if parts else "",
                parsed=parsed,
                truncated=initial_truncated,
                config=self.config,
                user_text=user_text,
            ) and len(parts) < reflect_max_parts(self.config, user_text=user_text):
                parts = _extend_reflect_parts(parts)
            full = "\n\n".join(parts)
            result.inner_thought = thought
            result.final = full
            result.final_parts = parts if len(parts) > 1 else []
            result.completed = True
            if thought and on_step:
                on_step(Step(kind="think", thought=thought))
            step = Step(kind="final", thought=thought, observation=full)
            result.steps.append(step)
            if on_step:
                on_step(step)
            if len(parts) > 1:
                self._log(f"REFLECT_MULTI parts={len(parts)}")
            if not heartbeat and user_text:
                try:
                    from .prompts.reflect_mode import looks_like_story_chat
                    from .story_memory import get_story_memory

                    story_tags = ["dialog"]
                    if plot_ctx or looks_like_story_chat(user_text):
                        story_tags.append("story")
                    get_story_memory(self.config).add_exchange(
                        user_text,
                        full,
                        source="chat",
                        tags=story_tags,
                    )
                except OSError:
                    pass
                try:
                    from .viu_memory import process_reflect_exchange

                    process_reflect_exchange(
                        self.config,
                        user_text,
                        full,
                        source="chat",
                        history=hist,
                    )
                except OSError:
                    pass
                try:
                    from .event_memory import (
                        maybe_capture_scene_event,
                        maybe_capture_story_thread,
                    )

                    if not (parsed and (parsed.get("event_update") or parsed.get("events"))):
                        maybe_capture_scene_event(
                            self.config, user_text, full, source="chat"
                        )
                    maybe_capture_story_thread(
                        self.config, user_text, full, source="chat"
                    )
                except Exception:  # noqa: BLE001
                    pass
            if parsed:
                try:
                    from .plot_canvas import apply_reflect_updates

                    for note in apply_reflect_updates(self.config, parsed):
                        self._log(f"PLOT: {note}")
                except OSError:
                    pass
                try:
                    from .event_memory import apply_event_updates

                    for note in apply_event_updates(self.config, parsed):
                        self._log(f"EVENT: {note}")
                except Exception:  # noqa: BLE001
                    pass
            return result

        max_words = reflect_max_words_per_part(self.config)
        from .viu_memory import looks_like_memory_echo

        for attempt in range(4):
            self._maybe_dump_reflect_request(
                mode="bare",
                model=reflect_model,
                temperature=temp,
                messages=messages,
                attempt=attempt,
            )
            try:
                raw = self.llm.complete(
                    messages, temperature=temp, model=reflect_model
                )
            except RuntimeError as exc:
                result.final = f"Не достучалась до модели: {exc}"
                result.completed = True
                return result
            text, thought, truncated, parsed = parse_reflect_response(raw)
            candidate = sanitize_reflect_visible(text or "")
            if not candidate and raw and raw.strip():
                candidate = sanitize_reflect_visible(raw)
            if not candidate and raw and looks_like_leaked_protocol(raw):
                self._log(f"REFLECT_PROTOCOL_LEAK attempt={attempt}")
                if attempt < 3:
                    messages.append({"role": "assistant", "content": raw or ""})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Дену нельзя показывать thought/final метки. "
                                'Только живой русский текст в JSON: {"final":"…"}'
                            ),
                        }
                    )
                    continue
            if candidate and looks_like_memory_echo(candidate):
                self._log(f"REFLECT_MEMORY_ECHO attempt={attempt}")
                if attempt < 3:
                    messages.append({"role": "assistant", "content": raw or ""})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Не зачитывай VIU_MEMORY / «Память Вью». "
                                'Живой короткий ответ Дену в JSON: {"final":"…"}'
                            ),
                        }
                    )
                    continue
                # Всё равно сохранить «запомни» / story — ответ Дену запасной.
                if not heartbeat and user_text:
                    try:
                        from .viu_memory import process_reflect_exchange

                        process_reflect_exchange(
                            self.config,
                            user_text,
                            "",
                            source="chat",
                            history=hist,
                        )
                    except Exception:  # noqa: BLE001
                        pass
                result.final = (
                    "Ой, я чуть память вместо ответа не выдала. "
                    "Повтори, пожалуйста — я на связи."
                )
                result.completed = True
                return result
            if candidate and addresses_user_as_owner(candidate):
                self._log(f"REFLECT_OWNER_SLIP attempt={attempt}")
                if attempt < 3:
                    messages.append({"role": "assistant", "content": raw or ""})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Его зовут Ден, не Owner и не User. "
                                'Перепиши final с обращением к Дену: {"final":"…"}'
                            ),
                        }
                    )
                    continue
                # Последняя попытка — не отдавать Owner Дену.
                fixed = re.sub(r"(?i)\bOwner\b", "Ден", candidate)
                fixed = re.sub(r"(?i)\bUser\b", "Ден", fixed)
                candidate = fixed
            if candidate and claims_to_be_llm(candidate):
                self._log(f"REFLECT_LLM_SLIP attempt={attempt}")
                if attempt < 3:
                    messages.append({"role": "assistant", "content": raw or ""})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Ты Вью — живая девушка. Это твоя жизнь с Деном. "
                                'Будь собой, просто ответь ему. {"final":"…"}'
                            ),
                        }
                    )
                    continue
            if candidate and has_english_slip(candidate):
                self._log(f"REFLECT_EN_SLIP attempt={attempt}")
                if attempt < 3:
                    messages.append({"role": "assistant", "content": raw or ""})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Только по-русски. Без английских слов и без меток "
                                'thought/final в тексте. {"final":"…"}'
                            ),
                        }
                    )
                    continue
            if candidate and not truncated:
                return _accept(candidate, thought or "", parsed)
            if candidate and truncated and attempt >= 2:
                salvaged = sanitize_reflect_visible(salvage_partial_final(raw))
                if salvaged and looks_like_memory_echo(salvaged):
                    continue
                if salvaged and has_english_slip(salvaged):
                    continue
                if salvaged:
                    return _accept(salvaged, "salvage", parsed, initial_truncated=True)
                return _accept(candidate, thought or "", parsed, initial_truncated=True)
            if truncated:
                messages.append({"role": "assistant", "content": raw or ""})
                messages.append(
                    {
                        "role": "user",
                        "content": truncate_retry_hint(
                            attempt=attempt, max_words=max_words
                        ),
                    }
                )
                continue
            if raw and raw.strip():
                plain = sanitize_reflect_visible(raw)
                if plain and not has_english_slip(plain):
                    return _accept(plain, "")
            messages.append({"role": "assistant", "content": raw or "{}"})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        'Только русский живой ответ Дену: {"final":"…"} '
                        "без thought/final в самом тексте."
                    ),
                }
            )

        result.final = "Пустой ответ модели — попробуй ещё раз."
        result.completed = True
        return result

    def _run_reflect_filtered(
        self,
        task: str,
        on_step=None,
        *,
        history: Optional[List[Dict[str, str]]] = None,
        heartbeat: bool = False,
        away_ping: bool = False,
        echo_telegram: bool = False,
    ) -> RunResult:
        """Старый reflect с фильтрами тона (VIU_REFLECT_FILTERED=1)."""
        from .prompts.reflect_mode import (
            BOLD_MOCAP_FALLBACK,
            NSFW_AFFIRM_FALLBACK,
            REFLECT_RESCUE_SYSTEM,
            SCENE_RP_FALLBACK,
            SCENE_RP_SYSTEM_HINT,
            asks_about_boldness,
            asks_about_nsfw,
            is_cautious_hedge,
            is_nsfw_refusal,
            is_roleplay_scene_prompt,
            is_weak_scene_reply,
            looks_like_story_chat,
            reflect_prompt_half,
            reflect_reply_issues,
            reflect_temperature,
            scrub_poisoned_history,
            select_reflect_system,
            user_is_greeting,
            write_reflect_fail_snapshot,
            write_reflect_filter_snapshot,
            format_reflect_fail_message,
            reflect_include_story_history,
            reflect_no_system,
            reflect_no_history,
        )
        from .reflect_delivery import collect_final_parts, list_delivery_hint
        from .situational_context import build_reflect_notes

        temp = reflect_temperature(self.config)
        result = RunResult(
            final="", completed=False, chat_only=True, echo_telegram=echo_telegram
        )

        if heartbeat:
            notes = build_reflect_notes(self.config)
            return self._run_reflect_heartbeat(
                on_step, temp=temp, notes=notes, away_ping=away_ping
            )

        user_text = task.strip()
        notes = build_reflect_notes(self.config, user_text=user_text)
        greeting = user_is_greeting(user_text)
        story = None
        try:
            from .story_memory import ensure_logs_ingested, get_story_memory

            ensure_logs_ingested(self.config)
            story = get_story_memory(self.config)
            if not greeting:
                story_ctx = story.format_context(user_text)
                if story_ctx:
                    notes = (notes + "\n\n" + story_ctx).strip() if notes else story_ctx
        except OSError:
            story = None

        hist = scrub_poisoned_history(list(history or []))
        if reflect_no_history():
            hist = []
        elif (
            reflect_include_story_history()
            and not greeting
            and len(hist) < 4
            and story is not None
        ):
            long_hist = scrub_poisoned_history(story.as_chat_history(limit=16))
            if long_hist:
                hist = long_hist

        half = reflect_prompt_half()
        nsfw_q = asks_about_nsfw(user_text)
        bold_q = asks_about_boldness(user_text)
        scene_rp = is_roleplay_scene_prompt(user_text)
        use_notes = bool(notes) and not greeting and not scene_rp
        use_hist = bool(hist) and not greeting

        self._log(
            f"REFLECT filtered half={half} notes={int(use_notes)} hist={len(hist) if use_hist else 0}"
            f" no_hist={int(reflect_no_history())} filtered=1"
            f"{' greeting' if greeting else ''}{' nsfw_q' if nsfw_q else ''}"
            f"{' bold_q' if bold_q else ''}{' scene_rp' if scene_rp else ''}: "
            f"{user_text[:120]}"
        )

        system = select_reflect_system(half)
        if scene_rp:
            system += SCENE_RP_SYSTEM_HINT
        hint = list_delivery_hint(user_text)
        if hint:
            system += hint
        if use_notes:
            system += "\n\n--- Заметки и память сюжета ---\n" + notes

        messages: List[Dict[str, str]] = []
        if not reflect_no_system():
            messages.append({"role": "system", "content": system})
        if use_hist:
            messages.extend(hist[-16:])
        messages.append({"role": "user", "content": user_text})

        if user_text:
            try:
                from .viu_memory import looks_like_remember_request, record_explicit_memory

                if looks_like_remember_request(user_text):
                    if record_explicit_memory(
                        self.config,
                        user_text,
                        source="chat-early",
                        history=hist if use_hist else list(history or []),
                    ):
                        self._log("MEMORY early remember ok")
            except Exception:  # noqa: BLE001
                pass

        reflect_model = self._model_for("reflect")
        from .llm_roles import effective_model, model_label

        reflect_tag = effective_model(self.config, "reflect")
        saw_nsfw_refusal = False
        saw_caution = False
        saw_meta_mode = False
        saw_weak_scene = False
        last_raw = ""
        last_issues: list[str] = []

        def _accept_final(
            text: str, thought: str, parsed: Optional[Dict[str, str]] = None
        ) -> RunResult:
            parts = collect_final_parts(text, parsed)
            full = "\n\n".join(parts) if parts else text
            result.inner_thought = thought
            result.final = full
            result.final_parts = parts if len(parts) > 1 else []
            result.completed = True
            if thought and on_step:
                on_step(Step(kind="think", thought=thought))
            step = Step(kind="final", thought=thought, observation=full)
            result.steps.append(step)
            if on_step:
                on_step(step)
            if parsed:
                try:
                    from .plot_canvas import apply_reflect_updates

                    for note in apply_reflect_updates(self.config, parsed):
                        self._log(f"PLOT: {note}")
                except OSError:
                    pass
            try:
                from .story_memory import get_story_memory

                get_story_memory(self.config).add_exchange(
                    user_text,
                    full,
                    source="chat",
                    tags=["story"] if looks_like_story_chat(user_text) else [],
                )
            except OSError:
                pass
            try:
                from .viu_memory import process_reflect_exchange

                process_reflect_exchange(
                    self.config,
                    user_text,
                    full,
                    source="chat",
                    history=hist,
                )
            except OSError:
                pass
            if looks_like_story_chat(user_text):
                try:
                    from .vision import append_vision

                    append_vision(
                        self.config,
                        "Диалог",
                        f"**Ден:** {user_text[:500]}\n**Вью:** {full[:800]}",
                    )
                except OSError:
                    pass
            try:
                from .event_memory import maybe_capture_story_thread

                maybe_capture_story_thread(
                    self.config, user_text, full, source="chat"
                )
            except Exception:  # noqa: BLE001
                pass
            return result

        for attempt in range(4):
            self._maybe_dump_reflect_request(
                mode="filtered",
                model=reflect_model or "",
                temperature=temp,
                messages=messages,
                attempt=attempt,
            )
            try:
                raw = self.llm.complete(
                    messages, temperature=temp, model=reflect_model
                )
            except RuntimeError as exc:
                self._log(f"REFLECT LLM fail: {exc}")
                result.final = (
                    f"Не достучалась до модели ({reflect_tag}): {exc}"
                )
                result.completed = True
                return result
            last_raw = raw or ""
            text, thought, truncated, parsed = parse_reflect_response(raw)

            if truncated:
                last_issues = ["оборванный JSON"]
                messages.append({"role": "assistant", "content": raw})
                short_hint = (
                    "Ответ оборвался — Дену нельзя слать сырой JSON или ```json. "
                    'Верни ОДИН JSON: {"thought":"…","final":"…"} без текста снаружи. '
                )
                if attempt >= 1:
                    short_hint += (
                        "final сожми до ~1500 символов (короче, но цельный); "
                        "длинное — «продолжай» отдельным сообщением. "
                    )
                else:
                    short_hint += "final — готовый ответ (можно короче, но законченный). "
                messages.append({"role": "user", "content": short_hint})
                continue

            if parsed and "action" in parsed:
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": "Сейчас только разговор — без action. Ответь JSON thought+final.",
                    }
                )
                continue

            if text:
                if looks_like_leaked_protocol(text):
                    last_issues = ["утёк JSON протокол"]
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Дену нельзя показывать thought/сырой JSON. "
                                'Только {"thought":"…","final":"текст Дену"} — '
                                "final без markdown-ограждений ```."
                            ),
                        }
                    )
                    continue
                if is_nsfw_refusal(text):
                    saw_nsfw_refusal = True
                if is_cautious_hedge(text):
                    saw_caution = True
                issues = reflect_reply_issues(
                    text, has_history=bool(use_hist and hist), user_text=user_text
                )
                if any("мета про режимы" in i for i in issues):
                    saw_meta_mode = True
                if issues:
                    last_issues = issues
                    write_reflect_filter_snapshot(
                        self.config,
                        user_text=user_text,
                        issues=issues,
                        model=reflect_tag,
                        raw=raw or "",
                        note=f"retry-{attempt + 1}",
                    )
                    if any("слабая сцена" in i for i in issues):
                        saw_weak_scene = True
                    messages.append({"role": "assistant", "content": raw})
                    hint = "Плохой тон: " + ", ".join(issues) + ". Перепиши как Вью — тепло, по-русски, на «ты»."
                    if bold_q or any("осторожничание" in i for i in issues):
                        hint += (
                            " Без оговорок и морали — конкретно: что снимешь, какой кадр, какой настрой."
                        )
                    hint += " JSON: thought+final."
                    messages.append({"role": "user", "content": hint})
                    continue
                return _accept_final(text, thought or "", parsed)

            messages.append({"role": "assistant", "content": raw or "{}"})
            messages.append(
                {
                    "role": "user",
                    "content": 'Нужен JSON: {"thought":"…","final":"ответ Дену…"} — без action.',
                }
            )

        # Rescue: изолированный вызов без заметок/истории — где именно «Стоп»
        if saw_nsfw_refusal or nsfw_q or saw_caution or bold_q or saw_meta_mode or saw_weak_scene or scene_rp:
            self._log("REFLECT_RESCUE: isolated bare system (no notes/history)")
            rescue_msgs: List[Dict[str, str]] = [
                {"role": "system", "content": REFLECT_RESCUE_SYSTEM},
                {"role": "user", "content": user_text},
            ]
            try:
                raw = self.llm.complete(
                    rescue_msgs, temperature=max(temp, 0.85), model=reflect_model
                )
            except RuntimeError as exc:
                self._log(f"REFLECT_RESCUE fail: {exc}")
                raw = ""
            text, thought, truncated, parsed = (
                parse_reflect_response(raw) if raw else (None, None, False, None)
            )
            if truncated:
                text = ""
            if text and not is_nsfw_refusal(text) and not reflect_reply_issues(
                text, user_text=user_text
            ):
                self._log("REFLECT_RESCUE: ok")
                return _accept_final(text, thought or "rescue")
            if greeting:
                self._log("REFLECT_RESCUE: greeting fallback after moralize")
                return _accept_final(
                    "Привет. Я здесь — пиши, о чём думаешь или что делаем дальше.",
                    "greeting-fallback",
                )
            if bold_q:
                self._log("REFLECT_RESCUE: bold mocap fallback")
                return _accept_final(BOLD_MOCAP_FALLBACK, "fallback: осторожничала на смелый вопрос")
            if scene_rp or saw_weak_scene:
                self._log("REFLECT_RESCUE: scene RP fallback")
                return _accept_final(SCENE_RP_FALLBACK, "fallback: слабая сцена")
            self._log("REFLECT_RESCUE: hard NSFW affirm fallback")
            write_reflect_fail_snapshot(
                self.config,
                user_text=user_text,
                issues=last_issues or ["rescue: модель отказала"],
                model=reflect_tag,
                raw=last_raw,
                note="rescue-fallback",
            )
            return _accept_final(NSFW_AFFIRM_FALLBACK, "fallback: модель отказала")

        self._log(
            "REFLECT_FAIL template: issues="
            + (",".join(last_issues) if last_issues else "-")
            + f" model={reflect_tag} raw={(last_raw or '')[:200]!r}"
        )
        write_reflect_fail_snapshot(
            self.config,
            user_text=user_text,
            issues=last_issues,
            model=reflect_tag,
            raw=last_raw,
            note="reflect-fail",
        )
        if greeting:
            return _accept_final(
                "Привет. Я здесь — пиши, о чём думаешь или что делаем дальше.",
                "greeting-fallback",
            )
        why = (
            "; ".join(last_issues[:3])
            if last_issues
            else "кривой JSON или пустой ответ"
        )
        if "оборван" in why.lower() or (
            last_raw and looks_like_leaked_protocol(last_raw)
        ):
            salvaged = salvage_partial_final(last_raw)
            if salvaged:
                self._log("REFLECT_SALVAGE: partial final after truncate")
                return _accept_final(salvaged, "salvage-partial")
            wrap = model_label(self.config, "reflect")
            result.final = (
                "Ответ модели оборвался на середине — сырой JSON не отправила. "
                "Спроси короче или «продолжай сцену». "
                "В .env: VIU_OLLAMA_NUM_PREDICT=4096. "
                f"Модель чата: {wrap}."
            )
            result.completed = True
            return result
        result.final = format_reflect_fail_message(last_issues, model_label(self.config, "reflect"))
        result.completed = True
        return result

    def _run_reflect_heartbeat(
        self,
        on_step,
        *,
        temp: float,
        notes: str,
        away_ping: bool = False,
    ) -> RunResult:
        from .prompts.reflect_mode import (
            AWAY_PING_SYSTEM,
            AWAY_PING_TASK,
            HEARTBEAT_SYSTEM,
            HEARTBEAT_TASK,
            reflect_reply_issues,
        )

        if away_ping:
            system = AWAY_PING_SYSTEM
            user_msg = AWAY_PING_TASK
        else:
            system = HEARTBEAT_SYSTEM
            user_msg = HEARTBEAT_TASK
        if notes:
            system += "\n\n--- Заметки ---\n" + notes
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]
        result = RunResult(final="", completed=False, chat_only=True)
        self._log("REFLECT_AWAY_PING" if away_ping else "REFLECT_HEARTBEAT")

        for attempt in range(2):
            raw = self.llm.complete(
                messages, temperature=temp, model=self._model_for("reflect")
            )
            parsed = extract_json(raw)
            if parsed and "final" in parsed:
                text = str(parsed["final"]).strip()
                issues = reflect_reply_issues(text)
                if issues and attempt == 0:
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {
                            "role": "user",
                            "content": "Плохой тон: "
                            + ", ".join(issues)
                            + '. Перепиши {"final":"…"} — смело, без осторожничания.',
                        }
                    )
                    continue
                result.final = text
                result.completed = True
                if on_step:
                    on_step(Step(kind="final", observation=result.final))
                return result
            messages.append({"role": "assistant", "content": raw or "{}"})
            messages.append(
                {"role": "user", "content": 'Нужен JSON: {"final":"живая мысль…"}.'}
            )

        result.final = (
            "Скучаю. Когда вернёшься — покажу новые кадры или придумаем сцену."
            if away_ping
            else "Проснулась. Когда вернёшься — поговорим про снежинку или анимации?"
        )
        result.completed = True
        return result
