"""Тесты interaction_catalog, blocking и lab scaffold."""

import json
from pathlib import Path
from subprocess import CompletedProcess

from viu.interaction_catalog import (
    InteractionCatalogStore,
    InteractionWish,
    build_blocking_job,
    interaction_catalog_path,
    interaction_scene_dir,
    resolve_actor_asset,
    run_interaction_blocking,
)
from viu.interaction_catalog.models import DEFAULT_INTERACTIONS, interaction_id
from viu.lab.interaction_pipeline import STEP_LABELS, load_wish, run_one_step
from viu.lab.session import new_session, save_session


def _cfg(tmp_path):
    import os

    from viu.config import Config

    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def _seed_creature_catalog(cfg, tmp_path, slug: str, model: Path):
    from viu.creature_catalog import CreatureCatalogStore, creature_catalog_path
    from viu.creature_catalog.models import CreatureEntry

    store = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    e = CreatureEntry(
        id="c1",
        path=str(model),
        name=slug,
        slug=slug,
        size_class="quad_med",
        target_height_m=0.75,
        status="ready",
    )
    store.upsert(e)
    store.save()


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


def test_build_blocking_job(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    shanya_fbx = tmp_path / "Shanya.fbx"
    wolf_fbx = tmp_path / "wolf.fbx"
    shanya_fbx.write_bytes(b"")
    wolf_fbx.write_bytes(b"")
    _seed_creature_catalog(cfg, tmp_path, "wolf_alpha", wolf_fbx)
    monkeypatch.setattr(
        "viu.interaction_catalog.blocking.resolve_shanya_path",
        lambda c: shanya_fbx,
    )

    wish = InteractionWish.from_dict(DEFAULT_INTERACTIONS[0].to_dict())
    ok, msg, job_path = build_blocking_job(cfg, wish)
    assert ok, msg
    assert job_path.is_file()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["interaction_slug"] == "shanya_wolf_approach"
    assert len(job["actors"]) == 2
    assert job["sync_markers"]
    assert (job_path.parent / "viu_interaction_blocking.py").is_file()


def test_resolve_shanya_slug(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    shanya = tmp_path / "Shanya.fbx"
    shanya.write_bytes(b"")
    monkeypatch.setattr(
        "viu.interaction_catalog.blocking.resolve_shanya_path",
        lambda c: shanya,
    )
    path, height, name = resolve_actor_asset(cfg, "shanya", rig_kind="humanoid")
    assert path == shanya
    assert height == 1.70


def test_run_blocking_mock_blender(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    wolf_fbx = tmp_path / "wolf.fbx"
    wolf_fbx.write_bytes(b"")
    shanya_fbx = tmp_path / "Shanya.fbx"
    shanya_fbx.write_bytes(b"")
    _seed_creature_catalog(cfg, tmp_path, "wolf_alpha", wolf_fbx)
    monkeypatch.setattr(
        "viu.interaction_catalog.blocking.resolve_shanya_path",
        lambda c: shanya_fbx,
    )

    wish = InteractionWish.from_dict(DEFAULT_INTERACTIONS[0].to_dict())

    def fake_runner(cmd, **kwargs):
        job_path = Path(cmd[-1])
        job = json.loads(job_path.read_text(encoding="utf-8"))
        blend = Path(job["output_blend"])
        blend.parent.mkdir(parents=True, exist_ok=True)
        blend.write_bytes(b"FAKEBLEND")
        lock = Path(job["choreography_lock"])
        lock.write_text("{}", encoding="utf-8")
        return CompletedProcess(cmd, 0, stdout='VIU_BLOCKING_OK {"blend":"x"}\n', stderr="")

    monkeypatch.setattr(
        "viu.integrations.blender.exe.resolve_blender_exe",
        lambda c: Path("/fake/blender"),
    )

    from viu.interaction_catalog import blocking as blocking_mod

    ok, msg = blocking_mod.run_interaction_blocking(
        cfg, wish, open_result=False, runner=fake_runner
    )
    assert ok, msg
    store = InteractionCatalogStore(interaction_catalog_path(cfg)).load()
    w = store.get_by_slug("shanya_wolf_approach")
    assert w is not None
    assert w.blocking_blend
    assert w.status == "blocking_done"
