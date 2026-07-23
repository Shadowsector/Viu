"""Short MoCap prompts."""

from viu.integrations.comfy.prompts import mocap_negative, mocap_prompt


def test_negative_is_short():
    neg = mocap_negative()
    assert len(neg) < 120
    assert "watermark" in neg


def test_lie_down_prompt_minimal(monkeypatch):
    monkeypatch.setenv("VIU_COMFY_FACE_SWAP", "1")
    p = mocap_prompt("lie down on back", None)
    assert "lie down on back" in p
    assert "shy" not in p.lower()
    assert "breathing" not in p.lower()
    assert "expression" not in p.lower()
    assert len(p) < 200
