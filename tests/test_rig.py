import json
from pathlib import Path

import pytest

from viu.config import Config
from viu.integrations.blender import COMMANDS, BlenderClient
from viu.integrations.rig import (
    CANON_ORDER,
    REQUIRED,
    analyze_skeleton,
    detect_rig_type,
    is_complex_rig,
    map_to_humanoid,
    normalize,
    standard_summary,
)
from viu.memory import MemoryStore
from viu.planning import Planner
from viu.tools import AgentContext, build_default_registry
from viu.tools.rig_tool import (
    RigApplyAutoTool,
    RigApplyTool,
    RigCheckTool,
    RigStandardTool,
    _pick_armature,
)

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

RIGIFY = [
    "root",
    "DEF-spine", "DEF-spine.001", "DEF-spine.002", "DEF-spine.003",
    "DEF-spine.004", "DEF-spine.005", "DEF-spine.006",
    "ORG-spine", "MCH-spine", "tweak_spine", "hips", "chest", "neck", "head",
    "DEF-shoulder.L", "DEF-upper_arm.L", "DEF-forearm.L", "DEF-hand.L",
    "DEF-shoulder.R", "DEF-upper_arm.R", "DEF-forearm.R", "DEF-hand.R",
    "DEF-thigh.L", "DEF-shin.L", "DEF-foot.L", "DEF-toe.L",
    "DEF-thigh.R", "DEF-shin.R", "DEF-foot.R", "DEF-toe.R",
    "DEF-breast.L", "DEF-breast.R", "DEF-spine.003.tweak.L",
    "MCH-upper_arm_ik.L", "upper_arm_fk.L", "WGT-rig_hand", "ORG-upper_arm.L",
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
    assert normalize("L_ORG_thigh") == "lthigh"
    assert normalize("ORG_upper_arm_L") == "upperarml"
    assert normalize("L_ORG_shin") == "lshin"


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

# --------- Сопоставление сложного рига (Rigify) с Unity Humanoid ---------

def test_detect_rig_type():
    assert detect_rig_type(RIGIFY) == "rigify"
    assert detect_rig_type(MIXAMO) == "mixamo"
    assert detect_rig_type(DOT_CONVENTION) == "generic"
    advanced = ["Root", "ORG_upper_arm_L", "L_ORG_thigh", "L_LegIK_BLEND", "R_LegIK_BLEND"]
    assert detect_rig_type(advanced) == "advanced"


def test_is_complex_rig():
    assert is_complex_rig(RIGIFY)
    assert not is_complex_rig(MIXAMO)
    assert is_complex_rig(["Root", "ORG_upper_arm_L", "L_ORG_thigh"])


def test_rigify_maps_to_deform_bones():
    hm = map_to_humanoid(RIGIFY)
    assert hm.rig_type == "rigify"
    assert not hm.missing_required, hm.missing_required
    # Берём именно DEF-кости, а не ORG-/MCH-/fk.
    assert hm.mapping["LeftUpperArm"] == "DEF-upper_arm.L"
    assert hm.mapping["LeftLowerArm"] == "DEF-forearm.L"
    assert hm.mapping["LeftFoot"] == "DEF-foot.L"
    # Позвоночник по сегментам, без tweak-костей.
    assert hm.mapping["Hips"] == "DEF-spine"
    assert hm.mapping["Head"] == "DEF-spine.006"
    assert "tweak" not in hm.mapping["Chest"]


def test_rigify_not_renamed():
    hm = map_to_humanoid(RIGIFY)
    assert hm.renaming_needed is False


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


def test_rig_check_rigify_uses_map(ctx):
    r = RigCheckTool().run({"bones": RIGIFY}, ctx)
    assert r.ok
    assert "rigify" in r.content
    assert "DEF-upper_arm.L" in r.content
    # Для Rigify не должно быть плана переименования.
    assert "rename_plan" not in r.content


def test_rig_map_tool(ctx):
    from viu.tools.rig_tool import RigMapTool

    r = RigMapTool().run({"bones": RIGIFY}, ctx)
    assert r.ok
    assert "mapping (JSON)" in r.content
    assert "DEF-hand.L" in r.content


def test_rig_tools_registered():
    reg = build_default_registry()
    for name in ("rig_standard", "rig_check", "rig_map", "rig_apply", "rig_apply_auto"):
        assert reg.get(name) is not None, name


def test_pick_main_armature_over_weapon_proxy():
    objects = [
        {
            "name": "Avatar_Female_Size02_Yuzuha_Model.004",
            "type": "ARMATURE",
            "bones": ["Ctr_Wpn_01", "Ctr_Wpn_02", "Skn_Wpn_03"],
        },
        {"name": "rig_", "type": "ARMATURE", "bones": [f"bone_{i}" for i in range(200)]},
    ]
    name, bones = _pick_armature(objects)
    assert name == "rig_"
    assert len(bones) == 200


def test_advanced_rig_check_uses_map_not_rename(ctx):
    bones = [
        "Root", "pelvis", "Torso", "abdomenLower", "chestUpper", "head",
        "ORG_upper_arm_L", "ORG_forearm_L", "L_Hand",
        "ORG_upper_arm_R", "ORG_forearm_R", "R_Hand",
        "L_ORG_thigh", "L_ORG_shin", "L_Foot", "L_Toe",
        "R_ORG_thigh", "R_ORG_shin", "R_Foot", "R_Toe",
        "L_Collar", "R_Collar",
    ]
    r = RigCheckTool().run({"bones": bones}, ctx)
    assert "mapping (JSON)" in r.content
    assert "rename_plan" not in r.content
    assert "LeftUpperLeg" in r.content
    assert "Spine" in r.content


def test_erisa_report_maps_required_bones():
    report_path = Path("/home/ubuntu/.cursor/projects/workspace/uploads/blender_report_3940.txt")
    if not report_path.exists():
        pytest.skip("Erisa report not available")
    text = report_path.read_text(encoding="utf-8")
    idx = text.find("{")
    data, _ = json.JSONDecoder().raw_decode(text, idx)
    arm = next(o for o in data["objects"] if o["name"] == "_Armature")
    hm = map_to_humanoid(arm["bones"])
    assert detect_rig_type(arm["bones"]) == "advanced"
    assert not hm.missing_required, hm.missing_required
    assert hm.mapping["LeftUpperLeg"] == "L_ORG_thigh"
    assert hm.mapping["Head"] == "head"
