"""Эталон позы → I2V и inject LoadImage."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.seed_pose import (
    clear_pose_seed,
    load_seed_state,
    mocap_lora_checklist_text,
    resolve_active_seed,
    set_pose_seed,
)
from viu.integrations.comfy.workflows import inject_seed_image
from viu.lab.comfy_pipeline import COMFY_TOPIC
from viu.lab.session import load_session


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


def test_set_and_clear_pose_seed(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    img = tmp_path / "pose.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    # Comfy root fake for stage
    comfy = tmp_path / "ComfyUI"
    (comfy / "input").mkdir(parents=True)
    (comfy / "main.py").write_text("# fake\n", encoding="utf-8")
    (comfy / "comfy").mkdir()
    monkeypatch.setattr(
        "viu.integrations.comfy.seed_pose.resolve_comfy_root",
        lambda _c: comfy,
    )
    monkeypatch.setattr(
        "viu.integrations.comfy.seed_pose.probe_models",
        lambda _c: type(
            "P",
            (),
            {"ready_i2v": False, "ready_t2v": True},
        )(),
    )

    ok, msg = set_pose_seed(cfg, img, slug="sit_down")
    assert ok, msg
    assert "sit_down" in msg or "Эталон" in msg
    path, name, enabled = resolve_active_seed(cfg)
    assert enabled
    assert path is not None and path.is_file()
    assert name == "viu_pose_seed.png"
    assert (comfy / "input" / "viu_pose_seed.png").is_file()
    st = load_seed_state(cfg)
    assert st["enabled"] is True
    sess = load_session(cfg, COMFY_TOPIC)
    assert sess is not None
    assert sess.meta.get("i2v_seed_enabled") is True

    clear_pose_seed(cfg)
    _p2, _n2, en2 = resolve_active_seed(cfg)
    assert en2 is False


def test_inject_seed_image_skips_faceref():
    wf = {
        "52": {
            "class_type": "LoadImage",
            "inputs": {"image": "old.png"},
            "_meta": {"title": "LoadImage"},
        },
        "910": {
            "class_type": "LoadImage",
            "inputs": {"image": "viu_face_ref.png"},
            "_meta": {"title": "Viu FaceRef"},
        },
    }
    out = inject_seed_image(wf, "viu_pose_seed.png")
    assert out["52"]["inputs"]["image"] == "viu_pose_seed.png"
    assert out["910"]["inputs"]["image"] == "viu_face_ref.png"


def test_mocap_lora_checklist_mentions_motion():
    text = mocap_lora_checklist_text().lower()
    assert "motion" in text or "wan 2.1" in text
    assert "i2v" in text
