"""Тесты support bundle."""

from pathlib import Path

from viu.config import Config
from viu.support import _overlay_diagnostics_text, collect_support_bundle


def test_overlay_diagnostics_in_bundle(tmp_path):
    proj = tmp_path / "Unity" / "Anabarra"
    overlay = proj / "Builds" / "AnabarraOverlay"
    overlay.mkdir(parents=True)
    (overlay / "overlay_boot.log").write_text("HWND ok\n", encoding="utf-8")
    (proj / "viu_overlay_build.log").write_text("[Viu] Overlay build OK\n", encoding="utf-8")

    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        unity_project=str(proj),
    ).ensure_dirs()

    text = _overlay_diagnostics_text(cfg)
    assert "overlay_boot.log" in text
    assert "viu_overlay_build.log" in text

    bundle = collect_support_bundle(cfg)
    import zipfile

    with zipfile.ZipFile(bundle) as zf:
        assert "overlay_diagnostics.txt" in zf.namelist()
