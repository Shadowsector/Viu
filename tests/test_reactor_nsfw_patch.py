"""ReActor NSFW stub patch."""

from pathlib import Path

from viu.integrations.comfy.reactor_diag import (
    _VIU_NSFW_PATCH_MARKER,
    is_reactor_nsfw_patched,
    patch_reactor_nsfw_filter,
)


def test_patch_replaces_reactor_sfw(tmp_path):
    root = tmp_path / "ComfyUI"
    sfw = root / "custom_nodes" / "ComfyUI-ReActor" / "scripts" / "reactor_sfw.py"
    sfw.parent.mkdir(parents=True)
    sfw.write_text(
        "SCORE = 0.979\n\ndef nsfw_image(img_data, model_path):\n    return True\n",
        encoding="utf-8",
    )
    ok, msg = patch_reactor_nsfw_filter(root)
    assert ok, msg
    text = sfw.read_text(encoding="utf-8")
    assert _VIU_NSFW_PATCH_MARKER in text
    assert "return False" in text
    assert is_reactor_nsfw_patched(root)
    backup = sfw.with_suffix(".py.viu_orig")
    assert backup.is_file()


def test_patch_idempotent(tmp_path):
    root = tmp_path / "ComfyUI"
    sfw = root / "custom_nodes" / "ComfyUI-ReActor" / "scripts" / "reactor_sfw.py"
    sfw.parent.mkdir(parents=True)
    patch_reactor_nsfw_filter(root)
    ok2, msg2 = patch_reactor_nsfw_filter(root)
    assert ok2
    assert "уже отключён" in msg2
