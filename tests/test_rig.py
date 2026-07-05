import pytest

from viu.config import Config
from viu.integrations.blender import COMMANDS, BlenderClient
from viu.integrations.rig import (
    CANON_ORDER,
    REQUIRED,
    analyze_skeleton,
    normalize,
    standard_summary,
)
from viu.memory import MemoryStore
from viu.planning import Planner
from viu.tools import AgentContext, build_default_registry
from viu.tools.rig_tool import RigApplyTool, RigCheckTool, RigStandardTool

MIXAMO = [
    "mixamorig:Hips", "mixamorig:Spine", "mixamorig:Spine1", "mixamorig:Spine2",
    "mixamorig:Neck", "mixamorig:Head",
    "mixamorig:LeftShoulder", "mixamorig:LeftArm", "mixamorig:LeftForeArm", "mixamorig:LeftHand",
    "mixamorig:RightShoulder", "mixamorig:RightArm", "mixamorig:RightForeArm", "mixamorig:RightHand",
    "mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:LeftFoot", "mixamorig:LeftToeBase",
    "mixamorig:RightUpLeg", "mixamorig:RightLeg", "mixamorig:RightFoot", "mixamorig:RightToeBase",
]

DOT_CONVENTION = [
    "Hips", "Spine", "Chest", "Neck", "Head",
    "UpperArm.L", "LowerArm.L", "Hand.L", "UpperArm.R", "LowerArm.R", "Hand.R",
    "UpperLeg.L", "LowerLeg.L", "Foot.L", "UpperLeg.R", "LowerLeg.R", "Foot.R",
]

RUS_TRANSLIT = [
    "Taz", "Pozvon", "Golova",
    "RukaL", "PredplechieL", "KistL", "RukaR", "PredplechieR", "KistR",
    "BedroL", "GolenL", "StopaL", "BedroR", "GolenR", "StopaR",
]


# --------- Стандарт ---------

def test_standard_has_core_required():
    for b in ("Hips", "Spine", "Head", "LeftUpperArm", "RightFoot"):
        assert b in CANON_ORDER
        assert b in REQUIRED or b in CANON_ORDER
    assert "Hips" in REQUIRED and "LeftUpperLeg" in REQUIRED


def test_normalize_strips_prefix_and_separators():
    assert normalize("mixamorig:LeftUpLeg") == "leftupleg"
    assert normalize("upper_arm.L") == "upperarml"
    assert normalize("DEF-spine") == "spine"


def test_standard_summary_readable():
    s = standard_summary()
    assert "Hips" in s and "LeftUpperArm" in s


# --------- Анализ скелета ---------

def test_mixamo_fully_matches():
    r = analyze_skeleton(MIXAMO)
    assert r.ok, r.missing_required
    assert r.matched["LeftUpperArm"][0] == "mixamorig:LeftArm"
    assert r.matched["LeftLowerArm"][0] == "mixamorig:LeftForeArm"
    assert r.matched["LeftUpperLeg"][0] == "mixamorig:LeftUpLeg"
    # Переименование предлагается (имена нестандартные).
    assert r.rename_plan["mixamorig:Hips"] == "Hips"


def test_dot_convention_matches():
    r = analyze_skeleton(DOT_CONVENTION)
    assert r.ok
    assert r.rename_plan["UpperArm.L"] == "LeftUpperArm"
    assert r.rename_plan["Foot.R"] == "RightFoot"


def test_russian_translit_matches():
    r = analyze_skeleton(RUS_TRANSLIT)
    assert r.ok, r.missing_required
    assert r.matched["Hips"][0] == "Taz"
    assert r.matched["LeftUpperLeg"][0] == "BedroL"
    assert r.matched["LeftHand"][0] == "KistL"


def test_standard_names_need_no_rename():
    r = analyze_skeleton(CANON_ORDER)
    assert r.ok
    assert r.rename_plan == {}
    assert r.unmatched == []


def test_missing_required_detected():
    r = analyze_skeleton(["Hips", "Spine", "Head", "LeftUpperArm", "RightUpperArm"])
    assert not r.ok
    assert "LeftUpperLeg" in r.missing_required
    assert "RightFoot" in r.missing_required


def test_unmatched_bones_reported():
    r = analyze_skeleton(["Hips", "Weapon_Slot_Sword", "IK_Pole_Target_XYZ"])
    assert "Weapon_Slot_Sword" in r.unmatched


# --------- Инструменты ---------

@pytest.fixture
def ctx(tmp_path):
    config = Config(root=tmp_path, data_dir=tmp_path / ".viu", blender_port=59997).ensure_dirs()
    registry = build_default_registry()
    return AgentContext(
        config=config,
        memory=MemoryStore(config.data_dir / "memory.json"),
        planner=Planner(config.data_dir / "plan.json"),
        registry=registry,
    )


def test_rig_standard_tool(ctx):
    r = RigStandardTool().run({}, ctx)
    assert r.ok and "Hips" in r.content


def test_rig_check_tool_with_bones(ctx):
    r = RigCheckTool().run({"bones": MIXAMO}, ctx)
    assert r.ok
    assert "LeftUpperArm" in r.content
    assert "rename_plan" in r.content


def test_rig_check_tool_no_data(ctx):
    r = RigCheckTool().run({}, ctx)
    assert not r.ok and "нет данных" in r.content.lower()


def test_rig_apply_requires_args(ctx):
    r = RigApplyTool().run({"armature": "Скелет"}, ctx)
    assert not r.ok


def test_rename_bones_in_protocol_and_client():
    assert "rename_bones" in COMMANDS
    assert hasattr(BlenderClient, "rename_bones")


def test_rig_tools_registered():
    reg = build_default_registry()
    for name in ("rig_standard", "rig_check", "rig_apply"):
        assert reg.get(name) is not None, name
