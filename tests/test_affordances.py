import json

import pytest

from viu.config import Config
from viu.integrations.affordances import (
    Affordance,
    get_from_library,
    load_affordance,
    match_sockets,
)
from viu.memory import MemoryStore
from viu.planning import Planner
from viu.tools import AgentContext, build_default_registry
from viu.tools.affordance_tool import AffordanceMatchTool, AffordanceShowTool


def test_stick_fits_hand():
    shanya = get_from_library("шаня")
    stick = get_from_library("палка")
    matches = match_sockets(shanya, stick)
    pairs = {(m.socket_a, m.socket_b) for m in matches}
    assert ("hand_R", "grip_center") in pairs


def test_chair_interactions():
    shanya = get_from_library("шаня")
    chair = get_from_library("стул")
    matches = match_sockets(shanya, chair)
    pairs = {(m.socket_a, m.socket_b) for m in matches}
    assert ("hips", "seat") in pairs
    assert ("feet", "top") in pairs
    assert ("back", "backrest") in pairs


def test_no_match_between_incompatible():
    chair = get_from_library("стул")
    stick = get_from_library("палка")
    # У стула сокеты ничего не «принимают», у палки — тоже; общих стыковок нет.
    assert match_sockets(chair, stick) == []


def test_load_from_dict_and_json():
    d = {"name": "Меч", "sockets": [{"name": "handle", "tags": ["grip_point"]}], "interactions": ["swing"]}
    a1 = load_affordance(d)
    a2 = load_affordance(json.dumps(d, ensure_ascii=False))
    assert a1.name == "Меч" and a2.name == "Меч"
    assert a1.sockets[0].name == "handle"


def test_load_invalid_raises():
    with pytest.raises(ValueError):
        load_affordance("не json и не имя из библиотеки {")


@pytest.fixture
def ctx(tmp_path):
    config = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    registry = build_default_registry()
    return AgentContext(
        config=config,
        memory=MemoryStore(config.data_dir / "memory.json"),
        planner=Planner(config.data_dir / "plan.json"),
        registry=registry,
    )


def test_affordance_show_tool(ctx):
    r = AffordanceShowTool().run({"object": "палка"}, ctx)
    assert r.ok and "grip_center" in r.content


def test_affordance_match_tool(ctx):
    r = AffordanceMatchTool().run({"a": "шаня", "b": "палка"}, ctx)
    assert r.ok
    assert "hand_R" in r.content and "grip_center" in r.content


def test_affordance_match_requires_both(ctx):
    r = AffordanceMatchTool().run({"a": "шаня"}, ctx)
    assert not r.ok


def test_affordance_tools_registered():
    reg = build_default_registry()
    assert reg.get("affordance_show") is not None
    assert reg.get("affordance_match") is not None
