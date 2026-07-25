"""Библиотека эталонов I2V: импорт, привязка slug, refine accept."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.seed_library import (
    accept_refined,
    activate_seed,
    bind_seed_to_slug,
    get_entry,
    import_seed,
    load_library,
    load_slug_seeds,
    prepare_refine,
    seeds_for_slug,
)
from viu.integrations.comfy.seed_pose import resolve_active_seed
from viu.integrations.comfy.workflows import inject_end_seed_image


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    lib = tmp_path / "Library"
    lib.mkdir(parents=True, exist_ok=True)
    return Config(
        root=tmp_path,
        data_dir=data,
        library_root=str(lib),
    ).ensure_dirs()


def _png(path: Path) -> Path:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return path


def test_import_hs2_and_bind_slug(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    img = _png(tmp_path / "hs2_sleep.png")
    ok, msg, entry = import_seed(cfg, img, slug="sleep_idle", from_hs2=True)
    assert ok, msg
    assert entry is not None
    assert entry.status == "needs_refine"
    assert entry.source == "hs2"
    assert len(load_library(cfg)) >= 1

    ok2, msg2 = bind_seed_to_slug(cfg, "sleep_idle", entry.id, role="start")
    assert ok2, msg2
    bound = seeds_for_slug(cfg, "sleep_idle")
    assert bound["start"] is not None
    assert bound["start"].id == entry.id
    assert "sleep_idle" in load_slug_seeds(cfg)


def test_accept_refined_and_activate(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    img = _png(tmp_path / "raw.png")
    ok, _msg, entry = import_seed(cfg, img, title="pose", from_hs2=True)
    assert ok and entry

    refined = _png(tmp_path / "natural.png")
    ok2, msg2 = accept_refined(cfg, entry.id, refined, activate=False)
    assert ok2, msg2
    again = get_entry(cfg, entry.id)
    assert again is not None
    assert again.status == "ready"
    assert again.source == "refined"
    assert Path(again.refined_path).is_file()

    comfy = tmp_path / "ComfyUI"
    (comfy / "input").mkdir(parents=True)
    (comfy / "main.py").write_text("#\n", encoding="utf-8")
    (comfy / "comfy").mkdir()
    monkeypatch.setattr(
        "viu.integrations.comfy.seed_pose.resolve_comfy_root",
        lambda _c: comfy,
    )
    monkeypatch.setattr(
        "viu.integrations.comfy.paths.resolve_comfy_root",
        lambda _c: comfy,
    )
    ok3, msg3 = activate_seed(cfg, entry.id, role="start")
    assert ok3, msg3
    path, name, enabled = resolve_active_seed(cfg)
    assert enabled and path is not None
    assert name == "viu_pose_seed.png"


def test_prepare_refine_without_vision(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    img = _png(tmp_path / "a.png")
    ok, _m, entry = import_seed(cfg, img, from_hs2=True)
    assert ok and entry

    def _boom(*_a, **_k):
        raise RuntimeError("no ollama")

    monkeypatch.setattr(
        "viu.integrations.comfy.reference_vision.describe_reference",
        _boom,
    )
    ok2, msg = prepare_refine(cfg, entry.id)
    assert ok2, msg
    again = get_entry(cfg, entry.id)
    assert again is not None
    assert again.status == "needs_refine"
    assert "натураль" in again.notes.lower() or "natural" in again.notes.lower() or "HS2" in again.notes or "доработ" in again.notes.lower()


def test_inject_end_seed_noop_without_end_image():
    wf = {
        "50": {
            "class_type": "WanImageToVideo",
            "inputs": {"start_image": ["52", 0]},
        },
        "52": {
            "class_type": "LoadImage",
            "inputs": {"image": "start.png"},
            "_meta": {"title": "LoadImage"},
        },
    }
    out = inject_end_seed_image(wf, "viu_pose_seed_end.png")
    assert "end_image" not in out["50"]["inputs"]
