"""Тесты interaction_catalog и lab scaffold."""

from pathlib import Path

from viu.interaction_catalog import (
    InteractionCatalogStore,
    InteractionWish,
    interaction_catalog_path,
    interaction_scene_dir,
)
from viu.interaction_catalog.models import DEFAULT_INTERACTIONS, interaction_id
from viu.lab.interaction_pipeline import STEP_LABELS, load_wish, run_one_step
from viu.lab.session import new_session, save_session


def test_interaction_id_stable():
    assert interaction_id("shanya_wolf_approach") == interaction_id("shanya_wolf_approach")
    assert len(interaction_id("x")) == 16


def test_default_interactions_seed(tmp_path, monkeypatch):
    from viu.config import Config

    cfg = Config(data_dir=tmp_path / ".viu")
    path = interaction_catalog_path(cfg)
    store = InteractionCatalogStore(path).load()
    assert len(store.all_wishes()) >= 1
    w = store.get_by_slug("shanya_wolf_approach")
    assert w is not None
    assert len(w.actors) == 2
    assert w.choreography.fps == 24
    assert w.sync_markers


def test_interaction_wish_roundtrip():
    src = DEFAULT_INTERACTIONS[0]
    restored = InteractionWish.from_dict(src.to_dict())
    assert restored.slug == src.slug
    assert restored.actors[0].creature_slug == src.actors[0].creature_slug
    assert restored.choreography.duration_frames == src.choreography.duration_frames


def test_interaction_scene_dir(tmp_path, monkeypatch):
    from viu.config import Config

    cfg = Config(data_dir=tmp_path / ".viu")
    p = interaction_scene_dir(cfg, "shanya_wolf_approach")
    assert p.is_dir()
    assert "Interactions" in str(p)


def test_interaction_lab_one_step(tmp_path, monkeypatch):
    import os

    from viu.config import Config

    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    InteractionCatalogStore(interaction_catalog_path(cfg)).load().save()

    session = new_session("interaction")
    session.steps_total = len(STEP_LABELS)
    save_session(cfg, session)

    wish = load_wish(cfg)
    assert wish is not None
    assert wish.slug == "shanya_wolf_approach"

    ok, msg = run_one_step(cfg, session)
    assert ok
    assert "shanya_wolf_approach" in msg


def test_interaction_catalog_show_tool(tmp_path, monkeypatch):
    import os

    from viu.config import Config
    from viu.memory import MemoryStore
    from viu.planning import Planner
    from viu.tools import AgentContext, build_default_registry
    from viu.tools.interaction_catalog_tool import InteractionCatalogShowTool

    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    InteractionCatalogStore(interaction_catalog_path(cfg)).load().save()
    ctx = AgentContext(
        config=cfg,
        memory=MemoryStore(cfg.data_dir / "memory.json"),
        planner=Planner(cfg.data_dir / "plan.json"),
        registry=build_default_registry(),
    )
    result = InteractionCatalogShowTool().run({"slug": "shanya_wolf_approach"}, ctx)
    assert result.ok
    assert "волк" in result.content.lower() or "Шаня" in result.content
