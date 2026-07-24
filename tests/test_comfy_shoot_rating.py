"""Comfy shoot must not stall on awaiting_rating; slugs must match action."""

from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.lab.comfy_director import infer_slug_from_action
from viu.lab.comfy_pipeline import COMFY_TOPIC
from viu.lab.session import load_session, new_session, save_session
from viu.tools import AgentContext, build_default_registry
from viu.tools.lab_tool import LabStartTool


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    return Config(
        root=tmp_path,
        data_dir=data,
        library_root=str(tmp_path / "Library"),
    ).ensure_dirs()


def _ctx(cfg: Config) -> AgentContext:
    from viu.memory import MemoryStore
    from viu.planning import Planner

    return AgentContext(
        config=cfg,
        memory=MemoryStore(cfg.data_dir / "memory.json"),
        planner=Planner(cfg.data_dir / "plan.json"),
        registry=build_default_registry(),
    )


def test_infer_slug_sit_not_touch_self():
    assert infer_slug_from_action("from standing to sit on a bed") == "sit_down"
    assert infer_slug_from_action("touch self while seated on bed") == "touch_self"


def test_comfy_shoot_skips_awaiting_rating(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    session = new_session(COMFY_TOPIC)
    session.status = "awaiting_rating"
    session.step = 7
    session.meta["action"] = "from standing to sit on a bed"
    session.meta["wan_positive"] = "nude young woman sits on a bed"
    session.meta["prompt_user_edited"] = True
    session.meta["catalog_slug"] = "touch_self"
    save_session(cfg, session)

    calls = {"n": 0}

    def fake_prepared(config, topic, **kwargs):
        calls["n"] += 1
        sess = load_session(config, topic)
        assert sess is not None
        assert sess.status == "running"
        assert sess.meta.get("shoot_intent") is True
        return True, "queued to comfy", sess

    monkeypatch.setattr(
        "viu.integrations.comfy.process.ensure_comfy_running",
        lambda *a, **k: (True, "Comfy OK"),
    )
    monkeypatch.setattr("viu.tools.lab_tool.run_lab_prepared", fake_prepared)

    result = LabStartTool().run(
        {
            "topic": COMFY_TOPIC,
            "run_all": "1",
            "shoot": "1",
            "action": "from standing to sit on a bed",
            "catalog_slug": "sit_down",
        },
        _ctx(cfg),
    )
    assert result.ok
    assert calls["n"] == 1
    assert "Жду оценку" not in result.content
    assert "queued" in result.content.lower() or "comfy" in result.content.lower()


def test_display_stem_not_viu_mocap():
    from viu.integrations.comfy.naming import comfy_filename_prefix, display_video_stem

    stem = display_video_stem(
        catalog_slug="sit_down",
        enters_from=["idle"],
        take_id="take_a",
        seq=1,
    )
    prefix = comfy_filename_prefix(stem)
    assert prefix.lower().startswith("girl")
    assert "viu_mocap" not in prefix.lower()
    assert "Sit" in stem or "sit" in stem.lower()
