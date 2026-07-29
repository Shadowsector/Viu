"""Short MoCap prompts — без RU look и без medium/full body войны."""

from viu.integrations.comfy.prompts import (
    clean_action_for_wan,
    mocap_negative,
    mocap_prompt,
)


def test_negative_lists_junk():
    neg = mocap_negative()
    assert "watermark" in neg
    assert "moaning" in neg


def test_lie_down_prompt_minimal(monkeypatch):
    monkeypatch.setenv("VIU_COMFY_FACE_SWAP", "1")
    p = mocap_prompt("lie down on back", None)
    assert "lie down on back" in p
    assert "shy" not in p.lower()
    assert "breathing" not in p.lower()
    assert "expression" not in p.lower()
    assert "standing or seated" not in p.lower()
    assert len(p) < 220


def test_clean_strips_ru_look_and_medium_shot():
    dirty = (
        "young woman in the described pose, medium shot, full body, natural motion, "
        "matching the reference look (Вижу кадр — запомнила референс.)"
    )
    clean = clean_action_for_wan(dirty)
    assert "Вижу" not in clean
    assert "matching the reference" not in clean.lower()
    assert "medium shot" not in clean.lower()
    assert "described pose" not in clean.lower()


def test_chat_contaminated_action_becomes_clean_prompt(monkeypatch):
    monkeypatch.setenv("VIU_COMFY_FACE_SWAP", "1")
    dirty = (
        "lounging in an armchair, medium shot, full body, "
        "matching the reference look (Вижу кадр — запомнила референс.)"
    )
    p = mocap_prompt(dirty, None)
    assert "armchair" in p.lower()
    assert "Вижу" not in p
    assert "medium shot" not in p.lower()
    assert p.lower().count("nude") <= 1
    assert "standing or seated" not in p.lower()
