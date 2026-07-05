import json

from viu.agent import Agent, extract_json
from viu.config import Config
from viu.demo import demo_script
from viu.llm import MockLLM


def test_extract_json_plain():
    assert extract_json('{"thought": "t", "final": "ok"}') == {"thought": "t", "final": "ok"}


def test_extract_json_with_code_fence():
    text = "```json\n{\"final\": \"ok\"}\n```"
    assert extract_json(text) == {"final": "ok"}


def test_extract_json_embedded_in_text():
    text = 'бла бла {"thought": "t", "final": "ответ"} хвост'
    parsed = extract_json(text)
    assert parsed and parsed["final"] == "ответ"


def test_extract_json_invalid():
    assert extract_json("совсем не json") is None


def test_extract_json_rejects_rename_plan_only():
    rename = '{"Root": "Hips", "head": "Head"}'
    assert extract_json(rename) is None


def test_extract_json_picks_agent_object_over_embedded_data():
    text = (
        'rename_plan: {"Root": "Hips"} '
        '{"thought": "ok", "final": "готово"}'
    )
    parsed = extract_json(text)
    assert parsed and parsed["final"] == "готово"


def test_agent_single_tool_then_final(tmp_path):
    responses = [
        json.dumps({"thought": "запишу файл", "action": {"tool": "write_file", "args": {"path": "a.txt", "content": "hi"}}}),
        json.dumps({"thought": "готово", "final": "Файл создан"}),
    ]
    config = Config(root=tmp_path, data_dir=tmp_path / ".viu", provider="mock")
    agent = Agent(config=config, llm=MockLLM(responses=responses))
    result = agent.run("создай файл a.txt")

    assert result.completed
    assert result.final == "Файл создан"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hi"
    # Один вызов инструмента + финал.
    assert [s.kind for s in result.steps] == ["action", "final"]


def test_agent_handles_unknown_tool(tmp_path):
    responses = [
        json.dumps({"thought": "?", "action": {"tool": "does_not_exist", "args": {}}}),
        json.dumps({"thought": "ладно", "final": "конец"}),
    ]
    config = Config(root=tmp_path, data_dir=tmp_path / ".viu", provider="mock")
    agent = Agent(config=config, llm=MockLLM(responses=responses))
    result = agent.run("тест")
    assert result.completed
    assert "не найден" in result.steps[0].observation


def test_agent_recovers_from_bad_json(tmp_path):
    responses = [
        "это не json",
        json.dumps({"thought": "ок", "final": "восстановился"}),
    ]
    config = Config(root=tmp_path, data_dir=tmp_path / ".viu", provider="mock")
    agent = Agent(config=config, llm=MockLLM(responses=responses))
    result = agent.run("тест")
    assert result.completed
    assert result.steps[0].kind == "error"


def test_full_demo_scenario(tmp_path):
    from viu.tools.self_improve import CUSTOM_DIR

    created = CUSTOM_DIR / "word_count.py"
    try:
        config = Config(root=tmp_path, data_dir=tmp_path / ".viu", provider="mock")
        agent = Agent(config=config, llm=MockLLM(responses=demo_script()))
        result = agent.run("Заложи основу игры Анабарра")

        assert result.completed
        # Файл концепции создан.
        assert (tmp_path / "anabarra" / "CONCEPT.md").exists()
        # Память записана.
        assert any("Анабарра" in r.text for r in agent.memory.all())
        # План создан и первый шаг закрыт.
        assert agent.planner.plan.steps[0].status == "done"
        # Самоулучшение: инструмент word_count зарегистрирован и отработал.
        assert agent.registry.get("word_count") is not None
        assert any(s.tool == "word_count" and "words=" in s.observation for s in result.steps)
        # Урок сохранён.
        assert (config.data_dir / "learnings.md").exists()
    finally:
        if created.exists():
            created.unlink()
