"""Режим присутствия и очередь решений."""

from viu.config import Config
from viu.decision_queue import enqueue, is_meaningful, list_open, render_open
from viu.presence import MODE_AWAY, MODE_HOME, get_presence, set_presence, toggle_presence
from viu.tools import build_default_registry
from viu.tools.ask_tool import AskUserTool
from viu.tools.base import AgentContext


def test_presence_toggle(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    assert get_presence(cfg) == MODE_HOME
    assert toggle_presence(cfg) == MODE_AWAY
    assert get_presence(cfg) == MODE_AWAY
    set_presence(cfg, MODE_HOME)
    assert get_presence(cfg) == MODE_HOME


def test_decision_queue_filters_trivial(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    assert not is_meaningful("нажми Play")
    assert not is_meaningful("ок")
    assert is_meaningful(
        "Делаем пайплайн через Cascadeur или пока хватит Mixamo для переходов Sit→Stand?",
        kind="pipeline",
    )
    ok, _ = enqueue(cfg, "нажми кнопку оверлей")
    assert not ok
    ok, msg = enqueue(
        cfg,
        "Какой приоритет: сначала живой оверлей с домом или мост Cascadeur?",
        kind="pipeline",
    )
    assert ok
    assert list_open(cfg)
    assert "приоритет" in render_open(cfg).lower() or "Cascadeur" in render_open(cfg)


def test_ask_user_queues_when_away(tmp_path):
    from unittest.mock import MagicMock

    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    set_presence(cfg, MODE_AWAY)
    ctx = AgentContext(
        config=cfg,
        memory=MagicMock(),
        planner=MagicMock(),
        registry=MagicMock(),
    )
    tool = AskUserTool()
    res = tool.run(
        {
            "question": "Идём в Cascadeur для вставания с пола или берём Mixamo Sit To Stand?",
            "kind": "pipeline",
        },
        ctx,
    )
    assert res.ok
    assert res.content.startswith("QUEUED_FOR_DEN:")
    assert list_open(cfg)


def test_registry_has_presence_and_apps():
    reg = build_default_registry()
    for name in (
        "presence_set",
        "presence_status",
        "decision_queue_show",
        "apps_close",
        "apps_restart",
        "apps_status",
    ):
        assert reg.get(name) is not None, name
