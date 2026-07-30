"""T2I/I2I still workflows → PNG."""

from __future__ import annotations

import json
from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.character_refs import assign_character_ref
from viu.integrations.comfy.chat_flow import try_handle_comfy_chat
from viu.integrations.comfy.shoot_settings import (
    MODE_I2I,
    MODE_T2I,
    apply_shoot_settings,
    describe_mode,
    mode_is_image,
    resolve_workflow_for_shoot,
)
from viu.integrations.comfy.workflows import (
    ensure_png_output,
    ensure_workflow_templates,
    prepare_still_workflow,
)


def _cfg(tmp_path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def _png(path: Path) -> Path:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return path


def _mock_look(monkeypatch):
    monkeypatch.setattr(
        "viu.integrations.comfy.reference_vision.look_at_photo",
        lambda *a, **k: (True, "Светлые волосы, мягкий свет."),
    )


def test_templates_exist_and_seed():
    root = Path(__file__).resolve().parents[1]
    t2i = root / "viu/integrations/comfy/templates/t2i.json"
    i2i = root / "viu/integrations/comfy/templates/i2i.json"
    assert t2i.is_file() and i2i.is_file()
    t2i_data = json.loads(t2i.read_text(encoding="utf-8"))
    i2i_data = json.loads(i2i.read_text(encoding="utf-8"))
    assert any(
        isinstance(n, dict) and n.get("class_type") == "SaveImage"
        for n in t2i_data.values()
    )
    assert any(
        isinstance(n, dict) and n.get("class_type") == "SaveImage"
        for n in i2i_data.values()
    )
    assert not any(
        isinstance(n, dict) and n.get("class_type") == "SaveVideo"
        for n in t2i_data.values()
    )


def test_resolve_still_workflows(tmp_path):
    cfg = _cfg(tmp_path)
    meta = apply_shoot_settings({}, mode=MODE_T2I)
    name, note = resolve_workflow_for_shoot(cfg, meta, has_seed=False, is_show=False)
    assert name == "t2i"
    assert "PNG" in note or "картинк" in note.lower()
    meta2 = apply_shoot_settings({}, mode=MODE_I2I)
    name2, _ = resolve_workflow_for_shoot(cfg, meta2, has_seed=True, is_show=False)
    assert name2 == "i2i"
    name3, _ = resolve_workflow_for_shoot(cfg, meta2, has_seed=False, is_show=False)
    assert name3 == "t2i"
    assert mode_is_image(MODE_T2I) and mode_is_image(MODE_I2I)
    assert "черновик" not in describe_mode(MODE_T2I).lower()


def test_ensure_png_and_still_prep():
    root = Path(__file__).resolve().parents[1]
    t2v = json.loads(
        (root / "viu/integrations/comfy/templates/t2v.json").read_text(encoding="utf-8")
    )
    still = ensure_png_output(t2v, filename_prefix="viu_test")
    assert any(
        isinstance(n, dict) and n.get("class_type") == "SaveImage" for n in still.values()
    )
    assert not any(
        isinstance(n, dict) and n.get("class_type") == "SaveVideo" for n in still.values()
    )
    prepared = prepare_still_workflow(t2v, action="sitting in armchair", filename_prefix="x")
    for n in prepared.values():
        if isinstance(n, dict) and n.get("class_type") == "EmptyHunyuanLatentVideo":
            assert n["inputs"]["length"] == 1


def test_ensure_templates_copies_still(tmp_path):
    cfg = _cfg(tmp_path)
    written = ensure_workflow_templates(cfg, overwrite_stubs=True)
    names = {p.name for p in written}
    assert "t2i.json" in names or (cfg.data_dir.parent / "t2i.json")
    from viu.integrations.comfy.paths import comfy_workflows_dir

    dest = comfy_workflows_dir(cfg)
    assert (dest / "t2i.json").is_file()
    assert (dest / "i2i.json").is_file()


def test_chat_photo_invent_sets_i2i(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    img = _png(tmp_path / "g.png")
    out = try_handle_comfy_chat(
        cfg, f"[tg_photo:{img}]\nнарисуй эту девушку сидящей в кресле"
    )
    assert out.handled and out.auto_fire
    assert out.shoot_mode == MODE_I2I
    assert out.seed_image_path
    assert out.wan_positive


def test_chat_text_invent_sets_still_mode(tmp_path, monkeypatch):
    _mock_look(monkeypatch)
    cfg = _cfg(tmp_path)
    out = try_handle_comfy_chat(cfg, "нарисуй девушку в кресле в Комфи")
    assert out.handled and out.auto_fire
    assert out.shoot_mode in (MODE_T2I, MODE_I2I)
    assert mode_is_image(out.shoot_mode)
    img = _png(tmp_path / "me.png")
    assign_character_ref(cfg, "viu", img)
    out2 = try_handle_comfy_chat(cfg, "нарисуй себя в кресле")
    assert out2.handled and out2.auto_fire
    assert out2.shoot_mode == MODE_I2I
    assert out2.seed_image_path


def test_invent_package_mode_flag(tmp_path):
    from viu.integrations.comfy.chat_flow import _invent_directed_package

    cfg = _cfg(tmp_path)
    *_, mode_t = _invent_directed_package(cfg, "сидящей в кресле", has_image=False)
    *_, mode_i = _invent_directed_package(cfg, "сидящей в кресле", has_image=True)
    assert mode_t == MODE_T2I
    assert mode_i == MODE_I2I
