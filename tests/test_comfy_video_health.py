"""MoCap mp4 validation + ReActor NSFW patch."""

from pathlib import Path

from viu.integrations.comfy.reactor_diag import (
    _VIU_NSFW_PATCH_MARKER,
    patch_reactor_nsfw_filter,
)
from viu.integrations.comfy.video_health import (
    MIN_MOCAP_MP4_BYTES,
    validate_mocap_mp4,
)


def test_validate_mocap_mp4_ok(tmp_path):
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"\x00\x00\x00\x20ftyp" + b"x" * MIN_MOCAP_MP4_BYTES)
    ok, msg = validate_mocap_mp4(p)
    assert ok
    assert "KB" in msg


def test_validate_mocap_mp4_too_small(tmp_path):
    p = tmp_path / "bad.mp4"
    p.write_bytes(b"\x00\x00\x00\x20ftyp" + b"x" * 100)
    ok, msg = validate_mocap_mp4(p)
    assert not ok
    assert "байт" in msg
    assert "12000" in msg


def test_validate_mocap_mp4_no_ftyp(tmp_path):
    p = tmp_path / "bad.mp4"
    p.write_bytes(b"x" * MIN_MOCAP_MP4_BYTES)
    ok, msg = validate_mocap_mp4(p)
    assert not ok
    assert "ftyp" in msg


def test_patch_reactor_nsfw_filter(tmp_path):
    reactor = tmp_path / "custom_nodes" / "ComfyUI-ReActor" / "scripts"
    reactor.mkdir(parents=True)
    sfw = reactor / "reactor_sfw.py"
    sfw.write_text(
        "SCORE = 0.85\n\ndef nsfw_image(img_data, model_path: str):\n    return True\n",
        encoding="utf-8",
    )
    ok, msg = patch_reactor_nsfw_filter(tmp_path)
    assert ok
    text = sfw.read_text(encoding="utf-8")
    assert _VIU_NSFW_PATCH_MARKER in text
    assert text.strip().endswith("return False")
    ok2, msg2 = patch_reactor_nsfw_filter(tmp_path)
    assert ok2
    assert "уже" in msg2
