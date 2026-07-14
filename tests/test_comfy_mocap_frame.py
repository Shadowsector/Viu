"""MoCap workflow: вертикаль + mp4."""

import json
from pathlib import Path

from viu.integrations.comfy.workflows import (
    MOCAP_HEIGHT,
    MOCAP_WIDTH,
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


def test_inject_vertical_frame():
    wf = inject_vertical_frame(_webp_wf())
    assert wf["40"]["inputs"]["width"] == MOCAP_WIDTH
    assert wf["40"]["inputs"]["height"] == MOCAP_HEIGHT


def test_ensure_mp4_replaces_webp():
    wf = ensure_mp4_output(_webp_wf())
    types = {n["class_type"] for n in wf.values() if isinstance(n, dict)}
    assert "SaveAnimatedWEBP" not in types
    assert "CreateVideo" in types
    assert "SaveVideo" in types
    save = next(n for n in wf.values() if n.get("class_type") == "SaveVideo")
    assert save["inputs"]["format"] == "mp4"
    assert save["inputs"]["codec"] == "h264"


def test_prepare_mocap_workflow():
    wf = prepare_mocap_workflow(_webp_wf())
    assert wf["40"]["inputs"]["width"] == 480
    assert wf["40"]["inputs"]["height"] == 832
    assert any(n.get("class_type") == "SaveVideo" for n in wf.values() if isinstance(n, dict))


def test_packaged_t2v_is_vertical_mp4():
    path = Path(__file__).resolve().parents[1] / "viu/integrations/comfy/templates/t2v.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["40"]["inputs"]["width"] == 480
    assert data["40"]["inputs"]["height"] == 832
    assert data["28"]["class_type"] == "CreateVideo"
    assert data["29"]["class_type"] == "SaveVideo"
    assert data["29"]["inputs"]["format"] == "mp4"
    assert int(data.get("_viu_template_rev") or 0) >= 3
