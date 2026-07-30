"""Wan prompt formula — fit girl prefix + short negative, no Action block."""

from viu.integrations.comfy.prompts import (
    SUBJECT_PREFIX,
    clean_process_for_wan,
    draft_bundle,
    mocap_negative,
    mocap_prompt,
    process_from_positive,
)


def test_negative_only_tongue_wet_hair():
    neg = mocap_negative()
    assert neg == "Tongue out, wet hair"
    assert "watermark" not in neg
    assert "moaning" not in neg


def test_positive_starts_with_canon_prefix():
    p = mocap_prompt("lying on a bed in warm evening light", None)
    assert p.startswith(SUBJECT_PREFIX)
    assert "lying on a bed" in p
    assert "warm evening light" in p
    assert "Action" not in p
    assert "Действие" not in p
    assert "white background" not in p.lower()
    assert "tabaxi" not in p.lower()


def test_clean_strips_leading_is_and_cyrillic():
    clean = clean_process_for_wan("is sitting on a sofa (сцена у окна)")
    assert not clean.lower().startswith("is ")
    assert "sitting on a sofa" in clean
    assert "сцена" not in clean


def test_clean_strips_old_young_woman_subject():
    clean = clean_process_for_wan(
        "young woman standing relaxed, full body, soft pose"
    )
    assert "young woman" not in clean.lower()
    assert "standing relaxed" in clean
    pos = mocap_prompt(
        "young woman standing relaxed, full body, soft pose", None
    )
    assert pos.startswith(SUBJECT_PREFIX)
    assert "young woman" not in pos.lower()


def test_process_from_positive():
    pos = f"{SUBJECT_PREFIX} dancing slowly in a dim club"
    assert process_from_positive(pos) == "dancing slowly in a dim club"


def test_draft_bundle_has_no_action_label():
    draft = draft_bundle("walking toward the camera, soft daylight")
    assert "Действие:" not in draft
    assert SUBJECT_PREFIX in draft
    assert "Tongue out, wet hair" in draft
    assert "walking toward the camera" in draft
