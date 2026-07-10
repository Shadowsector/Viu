"""Тесты cursor handoff и расширенного роутера."""

import json

from viu.agent import Agent
from viu.config import Config
from viu.integrations.github.handoff import append_handoff, handoff_path, push_handoff
from viu.integrations.telegram.router import route_telegram_message
from viu.llm.base import LLMProvider


def test_github_cursor_message_is_work():
    msg = (
        "Да, стоит.\n"
        "Вью, у тебя есть прямой канал для общения с Курсором - "
        "ты можешь выложить свои размышления и логи на GitHub. Попробуешь?"
    )
    assert route_telegram_message(msg) == "work"


def test_poprobuyesh_is_work():
    assert route_telegram_message("Попробуешь?") == "work"


def test_taskbar_question_still_reflect():
    assert (
        route_telegram_message("Как ты видишь панель задач Шани? Мы её разве делали?")
        == "reflect"
    )


def test_append_handoff_creates_file(tmp_path):
    append_handoff("Тест", "Идея про снежинку", repo_root=tmp_path)
    path = handoff_path(tmp_path)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "снежинку" in text
    assert "Тест" in text


class HandoffLLM(LLMProvider):
    name = "handoff"

    def __init__(self) -> None:
        self.tools: list[str] = []

    def complete(self, messages, *, temperature=None):
        sys = messages[0]["content"] if messages else ""
        if "cursor_handoff" in sys or "Доступные инструменты" in sys:
            self.tools.append("cursor_handoff_with_logs")
            return json.dumps(
                {
                    "thought": "Ден просит handoff — делаю.",
                    "action": {
                        "tool": "cursor_handoff_with_logs",
                        "args": {
                            "title": "Старт с Cursor",
                            "body": "Размышления Вью про Шаню и игру.",
                        },
                    },
                },
                ensure_ascii=False,
            )
        return json.dumps({"thought": "done", "final": "Готово."}, ensure_ascii=False)


def test_push_handoff_uses_api_without_git(tmp_path, monkeypatch):
    append_handoff("API", "тест без git", repo_root=tmp_path)
    monkeypatch.setenv("VIU_GITHUB_TOKEN", "ghp_test")
    calls = {}

    def fake_api(path, content, *, message, token, repo=None, branch=None):
        calls["path"] = path
        calls["len"] = len(content)
        return True, "ok api"

    monkeypatch.setattr(
        "viu.integrations.github.handoff.push_file_via_api",
        fake_api,
    )
    ok, msg = push_handoff(repo_root=tmp_path, token="ghp_test")
    assert ok
    assert calls["path"] == "docs/CURSOR_HANDOFF.md"
    assert "API" in append_handoff.__doc__ or ok


def test_work_mode_calls_handoff_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "viu.tools.cursor_handoff_tool.push_handoff",
        lambda **kw: (True, "push ok"),
    )

    llm = HandoffLLM()
    agent = Agent(
        llm=llm,
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run("Попробуешь выложить на GitHub для Cursor?")
    assert any(s.tool == "cursor_handoff_with_logs" for s in result.steps)
    assert llm.tools
