"""Два режима мозга: reflect (чат) и work (инструменты)."""

from viu.integrations.telegram.router import route_telegram_message
from viu.modes import Mode, is_reflect, is_work, mode_log_label, route_message


def test_modes_default_chat():
    assert route_message("привет, как ты?") == Mode.REFLECT
    assert route_telegram_message("давай сцену в сарае") == "reflect"
    assert is_reflect(Mode.REFLECT)
    assert not is_work(Mode.REFLECT)
    assert mode_log_label(Mode.REFLECT) == "чат"
    assert mode_log_label(Mode.WORK) == "работа"


def test_modes_work_only_on_action():
    assert route_message("следующий шаг") == Mode.WORK
    assert route_message("сделай следующий шаг") == Mode.WORK
    assert route_message("Попробуешь?") == Mode.REFLECT
    assert route_message("Попробуешь выложить на GitHub?") == Mode.WORK


def test_reflect_no_system_binds_list_hint(tmp_path, monkeypatch):
    """Под NO_SYSTEM подсказки списков тоже едут в user, не теряются."""
    from viu.agent import Agent
    from viu.config import Config
    from viu.llm.mock import MockLLM

    monkeypatch.setenv("VIU_REFLECT_NO_SYSTEM", "1")
    seen: list[list[dict]] = []

    class CaptureLLM(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            seen.append(list(messages))
            return (
                '{"thought":"ok","final_parts":["один","два","три","четыре","пять"]}'
            )

    agent = Agent(
        llm=CaptureLLM(),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    # «5 событий» должно включить list_delivery_hint
    result = agent.run_reflect("Накинь 5 событий для сарая")
    assert result.completed
    assert seen
    assert "system" not in [m["role"] for m in seen[0]]
    user = seen[0][-1]["content"]
    assert "Накинь 5 событий" in user
    # hint содержит final_parts / отдельн — если хинт сработал
    assert "final_parts" in user or "отдельн" in user.lower() or "список" in user.lower()
