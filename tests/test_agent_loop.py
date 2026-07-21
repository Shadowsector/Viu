import json

from viu.agent import (
    Agent,
    extract_json,
    looks_like_leaked_protocol,
    parse_reflect_response,
    salvage_partial_final,
)
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


def test_extract_json_with_preamble_and_fence():
    text = (
        "Похоже на кусок размышлений.\n\n"
        '```json\n{"thought": "x", "final": "ответ Дену"}\n```'
    )
    parsed = extract_json(text)
    assert parsed and parsed["final"] == "ответ Дену"


def test_parse_reflect_truncated_json_not_plaintext():
    raw = (
        'Похоже на кусок размышлений.\n\n```json\n{\n'
        '  "thought": "план",\n'
        '  "final": "Разбираюсь! Давай структурированно:\\n\\n## Сюжет\\n'
        "Вушка: прозрачный ду"
    )
    final, thought, truncated, parsed = parse_reflect_response(raw)
    assert truncated
    assert final is None
    assert looks_like_leaked_protocol(raw)


def test_parse_reflect_complete_fenced_json():
    raw = (
        "комментарий модели\n\n"
        '```json\n{"thought":"план","final":"Короткий ответ."}\n```'
    )
    final, thought, truncated, parsed = parse_reflect_response(raw)
    assert final == "Короткий ответ."
    assert thought == "план"
    assert not truncated
    assert parsed is not None


def test_salvage_partial_final_from_truncated_gdd():
    raw = (
        '```json\n{\n  "thought": "план",\n  "final": "Я вижу это. Давай разберём по кадрам:\n\n'
        "## Сцена: Вушка\n"
        "**Кадр 1:** Ночь. Шаня спит на коврике у стены.\n"
        "- Освещение: луна\n"
        "она н"
    )
    final, thought, truncated, parsed = parse_reflect_response(raw)
    assert truncated
    assert final is None
    salvaged = salvage_partial_final(raw)
    assert "Я вижу это" in salvaged
    assert "thought" not in salvaged.lower() or "вижу" in salvaged
    assert "продолжай" in salvaged
    assert not looks_like_leaked_protocol(salvaged)


def test_run_reflect_does_not_leak_raw_json_to_final(tmp_path):
    """Обрезанный JSON не уходит в final как сырой текст."""

    class TruncatedLLM:
        name = "trunc"

        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages, *, temperature=None, model=None):
            self.calls += 1
            if self.calls == 1:
                return (
                    'Похоже на кусок размышлений.\n```json\n'
                    '{"thought":"x","final":"Начало ответа без конца'
                )
            return json.dumps(
                {"thought": "короче", "final": "Короткий цельный ответ."},
                ensure_ascii=False,
            )

    agent = Agent(
        llm=TruncatedLLM(),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect("сценарии NSFW для домового")
    assert result.completed
    assert result.final == "Короткий цельный ответ."
    assert "Похоже" not in result.final
    assert '"thought"' not in result.final


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


def test_agent_breaks_repeat_loop(tmp_path):
    # Модель упорно зовёт один и тот же инструмент — агент должен остановиться сам.
    same = json.dumps(
        {"thought": "проверю", "action": {"tool": "list_dir", "args": {"path": "."}}}
    )
    config = Config(root=tmp_path, data_dir=tmp_path / ".viu", provider="mock")
    agent = Agent(config=config, llm=MockLLM(responses=[same] * 10))
    result = agent.run("зациклись")
    assert result.completed
    assert "повтор" in result.final.lower() or "ручной шаг" in result.final.lower()
    # Остановились до исчерпания лимита шагов (3-й одинаковый вызов).
    action_steps = [s for s in result.steps if s.kind == "action"]
    assert len(action_steps) <= 3


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
