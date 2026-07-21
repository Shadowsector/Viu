"""MoCap framing + mp4 workflow."""

import json
from pathlib import Path

from viu.integrations.comfy.framing import (
    choose_length,
    detect_orientation,
    frame_spec_for_action,
)
from viu.integrations.comfy.workflows import (
    ensure_mp4_output,
    inject_vertical_frame,
    prepare_mocap_workflow,
)


def _webp_wf() -> dict:
    return {
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
        "28": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": "ComfyUI",
                "fps": 16,
                "lossless": False,
                "quality": 90,
                "method": "default",
            },
        },
        "40": {
            "class_type": "EmptyHunyuanLatentVideo",
            "inputs": {"width": 832, "height": 480, "length": 33, "batch_size": 1},
        },
    }


def test_orientation_stand_vs_lie():
    assert detect_orientation("idle stand") == "vertical"
    assert detect_orientation("sleep on the back") == "horizontal"
    assert detect_orientation("lie down idle") == "horizontal"


def test_length_idle_longer_than_action():
    idle_len, _ = choose_length("idle stand")
    act_len, _ = choose_length("wave hello")
    assert idle_len > act_len
    assert idle_len % 4 == 1


def test_frame_spec_lie_horizontal():
    spec = frame_spec_for_action("lying on back, subtle breathing")
    assert spec.orientation == "horizontal"
    assert spec.width > spec.height


def test_prepare_mocap_stand():
    wf = prepare_mocap_workflow(
        _webp_wf(),
        action="idle stand",
        filename_prefix="Girl_Idle_loop_01",
    )
    assert wf["40"]["inputs"]["width"] == 576
    assert wf["40"]["inputs"]["height"] == 1024
    assert wf["40"]["inputs"]["length"] == 81
    save = next(
        n for n in wf.values() if isinstance(n, dict) and n.get("class_type") == "SaveVideo"
    )
    assert save["inputs"]["filename_prefix"] == "Girl_Idle_loop_01"


def test_prepare_mocap_lie():
    wf = prepare_mocap_workflow(_webp_wf(), action="sleep idle on the back")
    assert wf["40"]["inputs"]["width"] == 1024
    assert wf["40"]["inputs"]["height"] == 576


def test_ensure_mp4_replaces_webp():
    wf = ensure_mp4_output(_webp_wf())
    types = {n["class_type"] for n in wf.values() if isinstance(n, dict)}
    assert "SaveAnimatedWEBP" not in types
    assert "CreateVideo" in types


def test_packaged_t2v_rev4():
    path = Path(__file__).resolve().parents[1] / "viu/integrations/comfy/templates/t2v.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["40"]["inputs"]["width"] == 576
    assert data["40"]["inputs"]["height"] == 1024
    assert data["40"]["inputs"]["length"] == 81
    assert int(data.get("_viu_template_rev") or 0) >= 4


def test_inject_defaults():
    wf = inject_vertical_frame(_webp_wf())
    assert wf["40"]["inputs"]["height"] >= wf["40"]["inputs"]["width"]
