"""NSFW attach specs: bone match + socket plan."""

from __future__ import annotations

from viu.creature_catalog.nsfw_attach import (
    HAND_L_ALIASES,
    HIPS_ALIASES,
    PENIS_BONE_NAMES,
    SOCKET_SPECS,
    list_socket_ids,
    match_bone_name,
    normalize_bone_key,
    socket_parent_plan,
)


def test_normalize_mixamo_prefix():
    assert normalize_bone_key("mixamorig:Hips") == "hips"
    assert normalize_bone_key("Hand.L") == "hand_l"


def test_match_hips_and_hand():
    bones = ["mixamorig:Hips", "mixamorig:Spine", "mixamorig:LeftHand", "Head"]
    assert match_bone_name(bones, HIPS_ALIASES) == "mixamorig:Hips"
    assert match_bone_name(bones, HAND_L_ALIASES) == "mixamorig:LeftHand"
    assert match_bone_name(bones, ("Head",), prefer=("Jaw",)) == "Head"


def test_jaw_preferred_for_oral():
    bones = ["Head", "Jaw", "Hips"]
    plan = socket_parent_plan(bones)
    assert plan["socket_oral"] == "Jaw"
    assert plan["socket_vaginal"] == "Hips"
    assert plan["socket_hand_l"] is None


def test_six_socket_ids_stable():
    ids = list_socket_ids()
    assert ids == [
        "socket_oral",
        "socket_vaginal",
        "socket_anal",
        "socket_hand_l",
        "socket_hand_r",
        "socket_cleavage",
    ]
    assert len(SOCKET_SPECS) == 6
    assert PENIS_BONE_NAMES == ("Penis_01", "Penis_02", "Penis_03")
