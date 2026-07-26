"""Reflect notes tiering + meta NSFW questions."""

from viu.prompts.reflect_mode import asks_about_nsfw, is_meta_nsfw_boundary_question
from viu.situational_context import (
    _needs_full_work_notes,
    build_reflect_notes,
    build_reflect_notes_plot,
    needs_plot_file_context,
)


def test_meta_intimacy_not_nsfw_policy_question():
    q = "Почему такой осторожный ответ? Ты не хочешь говорить на интимные темы?"
    assert is_meta_nsfw_boundary_question(q)
    assert not asks_about_nsfw(q)


def test_can_we_nsfw_still_light_prompt():
    assert asks_about_nsfw("можно ли у нас NSFW в игре?")


def test_chat_notes_no_viu_self_reflect_leak(tmp_path, monkeypatch):
    from viu.config import Config

    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    data = tmp_path / ".viu"
    data.mkdir(parents=True)
    cfg = Config(data_dir=data)
    chat = build_reflect_notes(cfg, user_text="давай сцену в сарае")
    assert "VIU_SELF" not in chat
    assert "Reflect" not in chat
    assert "Work" not in chat


def test_meta_mode_reply_rejected():
    from viu.prompts.reflect_mode import reflect_reply_issues

    issues = reflect_reply_issues("Я вышла из режима Reflect, давай по-другому.")
    assert any("мета" in i for i in issues)


def test_bare_reflect_accepts_model_reply(tmp_path):
    from viu.agent import Agent
    from viu.config import Config
    from viu.llm.mock import MockLLM

    class OnceLLM(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            return '{"thought":"ok","final":"Привет, Ден — я здесь."}'

    agent = Agent(
        llm=OnceLLM(),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect("привет")
    assert result.completed
    assert "Привет" in result.final


def test_reflect_no_system_omits_system_message(tmp_path, monkeypatch):
    from viu.agent import Agent
    from viu.config import Config
    from viu.llm.mock import MockLLM

    monkeypatch.setenv("VIU_REFLECT_NO_SYSTEM", "1")
    seen: list[list[dict]] = []

    class CaptureLLM(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            seen.append(list(messages))
            return '{"thought":"ok","final":"только modelfile"}'

    agent = Agent(
        llm=CaptureLLM(),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect("тест без system")
    assert result.completed
    assert seen
    roles = [m["role"] for m in seen[0]]
    assert "system" not in roles
    assert roles == ["user"]


def test_reflect_no_system_still_binds_memory(tmp_path, monkeypatch):
    """При NO_SYSTEM память должна ехать в user — иначе привязка к reflect пропадает."""
    from viu.agent import Agent
    from viu.config import Config
    from viu.llm.mock import MockLLM
    from viu.viu_memory import append_memory_line, ensure_viu_memory, _SECTION_PREFS

    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    monkeypatch.setenv("VIU_REFLECT_NO_SYSTEM", "1")
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    ensure_viu_memory(cfg)
    append_memory_line(cfg, _SECTION_PREFS, "- Мяучиться в ответ")

    seen: list[list[dict]] = []

    class CaptureLLM(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            seen.append(list(messages))
            return '{"thought":"ok","final":"мяу"}'

    agent = Agent(llm=CaptureLLM(), config=cfg)
    result = agent.run_reflect("Вью, как там?")
    assert result.completed
    assert seen
    user = seen[0][-1]["content"]
    assert "Вью, как там?" in user
    assert "VIU_MEMORY" in user
    assert "Мяучиться" in user
    assert "# Память Вью" not in user  # digest, не весь файл


def test_reflect_no_history_omits_history(tmp_path, monkeypatch):
    from viu.agent import Agent
    from viu.config import Config
    from viu.llm.mock import MockLLM

    monkeypatch.setenv("VIU_REFLECT_NO_HISTORY", "1")
    seen: list[list[dict]] = []

    class CaptureLLM(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            seen.append(list(messages))
            return '{"thought":"ok","final":"solo"}'

    agent = Agent(
        llm=CaptureLLM(),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect(
        "тест",
        history=[
            {"role": "user", "content": "старое"},
            {"role": "assistant", "content": "старое ответ"},
        ],
    )
    assert result.completed
    roles = [m["role"] for m in seen[0]]
    assert roles.count("user") == 1
    assert seen[0][-1]["content"] == "тест"


def test_reflect_no_history_auto_dump(tmp_path, monkeypatch):
    from viu.agent import Agent
    from viu.config import Config
    from viu.llm.mock import MockLLM
    from viu.prompts.reflect_mode import reflect_request_log_path

    monkeypatch.setenv("VIU_REFLECT_NO_HISTORY", "1")
    monkeypatch.setenv("VIU_REFLECT_DUMP", "1")
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))

    class OnceLLM(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            return '{"thought":"ok","final":"solo"}'

    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    agent = Agent(llm=OnceLLM(), config=cfg)
    agent.run_reflect("одиночный")
    assert reflect_request_log_path(cfg).is_file()


def test_reflect_no_system_default_on():
    from viu.prompts.reflect_mode import reflect_no_system

    assert reflect_no_system() is True


def test_reflect_no_system_explicit_off(monkeypatch):
    from viu.prompts.reflect_mode import reflect_no_system

    monkeypatch.setenv("VIU_REFLECT_NO_SYSTEM", "0")
    assert reflect_no_system() is False


def test_reflect_request_dump_writes_json(tmp_path, monkeypatch):
    from viu.agent import Agent
    from viu.config import Config
    from viu.llm.mock import MockLLM
    from viu.prompts.reflect_mode import reflect_request_log_path

    monkeypatch.setenv("VIU_REFLECT_DUMP", "1")
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))

    class OnceLLM(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            return '{"thought":"ok","final":"дамп"}'

    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    agent = Agent(llm=OnceLLM(), config=cfg)
    agent.run_reflect("покажи дамп")
    path = reflect_request_log_path(cfg)
    assert path.is_file()
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["mode"] == "bare"
    assert data["messages"][-1]["content"] == "покажи дамп"


def test_weak_scene_reply_not_filtered():
    from viu.prompts.reflect_mode import is_roleplay_scene_prompt, is_weak_scene_reply

    user = (
        "Представь, я выхожу из ванной, мокрый, полотенце падает. Твои действия?"
    )
    assert is_roleplay_scene_prompt(user)
    weak = "*Я вижу твоё лицо через экран — ты краснеешь*\n\nОй... 😳"
    assert not is_weak_scene_reply(weak, user)
    from viu.prompts.reflect_mode import reflect_reply_issues

    assert reflect_reply_issues(weak, user_text=user) == []


def test_reflect_fail_snapshot(tmp_path, monkeypatch):
    from viu.config import Config
    from viu.prompts.reflect_mode import (
        format_reflect_fail_message,
        reflect_fail_log_path,
        write_reflect_fail_snapshot,
    )

    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config(data_dir=tmp_path / ".viu")
    write_reflect_fail_snapshot(
        cfg,
        user_text="тест",
        issues=["осторожничание"],
        model="viu-cydonia",
        raw='{"final":"нужно быть осторожной"}',
    )
    path = reflect_fail_log_path(cfg)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "осторожничание" in text
    msg = format_reflect_fail_message(["мета про режимы"], "viu-command-r")
    assert "reflect_last_fail" in msg
    assert "viu-cydonia" in msg


def test_needs_plot_file_context_story_review():
    q = "Просмотри файлы сюжета игры. Хотелось бы твоё мнение о нём."
    assert needs_plot_file_context(q)


def test_plot_notes_injected_in_bare_reflect(tmp_path, monkeypatch):
    from viu.agent import Agent
    from viu.config import Config
    from viu.llm.mock import MockLLM
    from viu.plot_canvas import ensure_plot_canvas, ensure_quests

    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    canvas = ensure_plot_canvas(cfg)
    canvas.write_text(
        "## Акт 1\n\nДомовой в сарае, не Корпорация XYZ.\n",
        encoding="utf-8",
    )
    quests = ensure_quests(cfg)
    quests.write_text("## Квест\n\nНайти снежинку.\n", encoding="utf-8")
    seen: list[list[dict]] = []

    class CaptureLLM(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            seen.append(list(messages))
            return '{"thought":"ok","final":"Вижу домового в сарае."}'

    agent = Agent(llm=CaptureLLM(), config=cfg)
    agent.run_reflect(
        "Просмотри файлы сюжета игры. Хотелось бы твоё мнение о нём."
    )
    assert seen
    user = next(m["content"] for m in seen[0] if m["role"] == "user")
    # При NO_SYSTEM=1 канон едет в user (иначе отваливается вместе с system).
    assert "PLOT_CANVAS" in user
    assert "домовой" in user.lower()
    assert "QUESTS" in user or "снежин" in user.lower()


def test_build_reflect_notes_plot_has_canvas(tmp_path, monkeypatch):
    from viu.config import Config
    from viu.plot_canvas import ensure_plot_canvas

    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    ensure_plot_canvas(cfg).write_text("## Тест\n\nШаня у таскбара.\n", encoding="utf-8")
    notes = build_reflect_notes_plot(cfg)
    assert "PLOT_CANVAS" in notes
    assert "Шаня" in notes


def test_chat_notes_plot_not_slim_brief(tmp_path, monkeypatch):
    from viu.config import Config
    from viu.plot_canvas import ensure_plot_canvas

    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    ensure_plot_canvas(cfg).write_text("## Канон\n\nСарай.\n", encoding="utf-8")
    chat = build_reflect_notes(
        cfg, user_text="Просмотри файлы сюжета — твоё мнение?"
    )
    assert "PLOT_CANVAS" in chat
    assert "VIU_SELF" not in chat


def test_chat_notes_slimmer_than_work(tmp_path, monkeypatch):
    from viu.config import Config

    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    data = tmp_path / ".viu"
    data.mkdir(parents=True)
    cfg = Config(data_dir=data)
    chat = build_reflect_notes(cfg, user_text="давай сцену в сарае, она озорная")
    work = build_reflect_notes(cfg, user_text="чем занимаешься, что делаешь сейчас")
    assert _needs_full_work_notes("чем занимаешься")
    assert not _needs_full_work_notes("давай сцену в сарае")
    if work:
        assert len(work) >= len(chat) or "CAPABILITY" in work or "PLOT" in work
