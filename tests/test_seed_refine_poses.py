"""Чеклист эталонных поз + сборка img2img refine workflow."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.seed_library import import_seed
from viu.integrations.comfy.seed_poses import (
    SEED_POSE_NEEDS,
    format_pose_checklist_text,
    pose_needs,
)
from viu.integrations.comfy.seed_refine import (
    build_refine_workflow,
    list_checkpoints,
    pick_checkpoint,
    refine_ready,
)


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    (tmp_path / ".viu").mkdir()
    (tmp_path / "Library").mkdir(parents=True)
    return Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        library_root=str(tmp_path / "Library"),
    ).ensure_dirs()


def test_idle_has_three_variants():
    idles = [p for p in SEED_POSE_NEEDS if p.slug == "idle"]
    assert len(idles) >= 3
    variants = {p.variant for p in idles}
    assert "front" in variants
    assert "three_quarter" in variants
    assert "profile" in variants


def test_priority1_covers_barn_and_climb():
    p1 = {p.slug for p in pose_needs(priority_max=1)}
    for slug in (
        "idle",
        "walk",
        "sit_down",
        "sit_idle",
        "lie_down",
        "sleep_idle",
        "climb_up",
        "wave",
        "touch_self",
    ):
        assert slug in p1


def test_checklist_text_mentions_idle_three(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    text = format_pose_checklist_text(cfg, priority_max=1)
    assert "idle" in text.lower() or "Стойка idle" in text
    assert "¾" in text or "3/4" in text or "three" in text.lower() or "профиль" in text


def test_coverage_marks_ready_seed(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    img = tmp_path / "idle_tq.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    ok, msg, entry = import_seed(
        cfg, img, title="idle three_quarter", slug="idle", from_hs2=False
    )
    assert ok, msg
    assert entry is not None
    # mark ready
    from viu.integrations.comfy.seed_library import accept_refined, get_entry

    # import already ready; title contains three_quarter
    text = format_pose_checklist_text(cfg, priority_max=1)
    assert "✓" in text


def test_pick_checkpoint_prefers_realistic(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    comfy = tmp_path / "ComfyUI"
    ckpt_dir = comfy / "models" / "checkpoints"
    ckpt_dir.mkdir(parents=True)
    (ckpt_dir / "animeThing.safetensors").write_bytes(b"x")
    (ckpt_dir / "epicrealism_natural.safetensors").write_bytes(b"x")
    monkeypatch.setattr(
        "viu.integrations.comfy.seed_refine.resolve_comfy_root",
        lambda _c: comfy,
    )
    assert pick_checkpoint(cfg) == "epicrealism_natural.safetensors"
    ok, name = refine_ready(cfg)
    assert ok and name == "epicrealism_natural.safetensors"


def test_build_refine_workflow_injects_ckpt_and_denoise():
    wf = build_refine_workflow(
        ckpt_name="foo.safetensors",
        image_name="viu_seed_refine_in.png",
        positive="pos",
        negative="neg",
        denoise=0.42,
        seed=7,
    )
    assert wf["4"]["inputs"]["ckpt_name"] == "foo.safetensors"
    assert wf["10"]["inputs"]["image"] == "viu_seed_refine_in.png"
    assert wf["3"]["inputs"]["denoise"] == 0.42
    assert wf["3"]["inputs"]["seed"] == 7
    assert wf["6"]["inputs"]["text"] == "pos"
