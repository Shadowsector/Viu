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
    return False


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

    if parsed and "final" in parsed and "action" not in parsed:
        final = str(parsed.get("final") or "").strip()
        thought = str(parsed.get("thought") or parsed.get("inner") or "").strip()
        truncated = bool(loose_final) and not closed
        return final or None, thought or None, truncated, parsed

    if loose_final and closed:
        return loose_final, None, False, None

    if loose_final and not closed:
        return None, None, True, None

    if looks_like_leaked_protocol(body):
        return None, None, True, None

    if not candidate.lstrip().startswith("{") and '"final"' not in body:
        return body[:2000], None, False, None

    return None, None, True, None


def salvage_partial_final(raw: str, *, min_len: int = 180) -> str:
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

    def _model_for(self, role: str) -> str | None:
        from .llm_roles import effective_model

        return effective_model(self.config, role)  # type: ignore[arg-type]

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
    ) -> RunResult:
        """Один проход чата: thought + final. Без инструментов."""
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
        )
        from .situational_context import build_reflect_notes

        temp = reflect_temperature(self.config)
        result = RunResult(final="", completed=False, chat_only=True)

        if heartbeat:
            notes = build_reflect_notes(self.config)
            return self._run_reflect_heartbeat(on_step, temp=temp, notes=notes)

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
        if not greeting and len(hist) < 4 and story is not None:
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
            f"REFLECT half={half} notes={int(use_notes)} hist={len(hist) if use_hist else 0}"
            f"{' greeting' if greeting else ''}{' nsfw_q' if nsfw_q else ''}"
            f"{' bold_q' if bold_q else ''}{' scene_rp' if scene_rp else ''}: "
            f"{user_text[:120]}"
        )

        system = select_reflect_system(half)
        if scene_rp:
            system += SCENE_RP_SYSTEM_HINT
        if use_notes:
            system += "\n\n--- Заметки и память сюжета ---\n" + notes

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        if use_hist:
            messages.extend(hist[-16:])
        messages.append({"role": "user", "content": user_text})

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
            result.inner_thought = thought
            result.final = text
            result.completed = True
            if thought and on_step:
                on_step(Step(kind="think", thought=thought))
            step = Step(kind="final", thought=thought, observation=result.final)
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
                    text,
                    source="chat",
                    tags=["story"] if looks_like_story_chat(user_text) else [],
                )
                self.memory.add(
                    f"Ден: {user_text[:200]} | Вью: {text[:200]}",
                    tags=["dialog", "story"]
                    if looks_like_story_chat(user_text)
                    else ["dialog"],
                )
            except OSError:
                pass
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

        for attempt in range(4):
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
    ) -> RunResult:
        from .prompts.reflect_mode import HEARTBEAT_SYSTEM, HEARTBEAT_TASK, reflect_reply_issues

        system = HEARTBEAT_SYSTEM
        if notes:
            system += "\n\n--- Заметки ---\n" + notes
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": HEARTBEAT_TASK},
        ]
        result = RunResult(final="", completed=False, chat_only=True)
        self._log("REFLECT_HEARTBEAT")

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

        result.final = "Проснулась. Когда вернёшься — поговорим про снежинку или анимации?"
        result.completed = True
        return result
