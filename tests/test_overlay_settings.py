"""Player settings patches for overlay."""

from pathlib import Path

from viu.integrations.unity.setup import ensure_flip_model_off


def test_ensure_flip_model_off(tmp_path):
    settings_dir = tmp_path / "ProjectSettings"
    settings_dir.mkdir()
    settings = settings_dir / "ProjectSettings.asset"
    settings.write_text(
        "PlayerSettings:\n  useFlipModelSwapchain: 1\n",
        encoding="utf-8",
    )
    ok, msg = ensure_flip_model_off(tmp_path)
    assert ok
    assert "useFlipModelSwapchain: 0" in settings.read_text(encoding="utf-8")
    assert "flip model" in msg.lower()
