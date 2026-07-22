"""FaceRefs + ReActor / I2V workflow injection."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.face_refs import (
    ensure_face_refs_dir,
    face_pregen_enabled,
    list_face_refs,
    pick_face_ref,
    stage_face_for_comfy,
)
from viu.integrations.comfy.workflows import (
    inject_face_swap,
    inject_start_image,
    prepare_mocap_workflow,
)
from tests.test_comfy_mocap_frame import _webp_wf


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir()
    for name in ("main.py", "folder_paths.py", "nodes.py", "execution.py", "server.py"):
        (comfy / name).write_text("# stub\n", encoding="utf-8")
    return Config(
        root=tmp_path / "Viu",
        data_dir=data,
        library_root=str(tmp_path / "Library"),
        comfy_root=str(comfy),
    )


def test_pick_default_face(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    d = ensure_face_refs_dir(cfg)
    (d / "random.png").write_bytes(b"x")
    (d / "default.png").write_bytes(b"y")
    assert pick_face_ref(cfg).name == "default.png"


def test_stage_face_for_comfy(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    d = ensure_face_refs_dir(cfg)
    src = d / "default.png"
    src.write_bytes(b"png")
    ok, msg, name = stage_face_for_comfy(cfg, src)
    assert ok and name == "viu_face_ref.png"
    dest = tmp_path / "ComfyUI" / "input" / "viu_face_ref.png"
    assert dest.is_file()


def test_inject_face_swap_inserts_reactor():
    wf = prepare_mocap_workflow(_webp_wf(), action="idle stand", filename_prefix="Girl_Idle")
    out = inject_face_swap(wf, face_image="viu_face_ref.png")
    types = {n.get("class_type") for n in out.values() if isinstance(n, dict)}
    assert "ReActorFaceSwap" in types
    assert "LoadImage" in types


def test_inject_start_image_updates_i2v_loadimage():
    from viu.integrations.comfy.workflows import load_workflow
    from viu.config import Config

    cfg = Config()
    cfg.data_dir = Path(__file__).resolve().parents[1] / ".viu_test"
    wf = load_workflow(cfg, "i2v")
    out = inject_start_image(wf, "viu_face_ref.png")
    load_nodes = [
        n
        for n in out.values()
        if isinstance(n, dict) and n.get("class_type") == "LoadImage"
    ]
    assert any(n["inputs"]["image"] == "viu_face_ref.png" for n in load_nodes)


def test_face_pregen_default_on(monkeypatch):
    monkeypatch.delenv("VIU_COMFY_FACE_PREGEN", raising=False)
    assert face_pregen_enabled() is True


def test_list_face_refs_ignores_txt(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    d = ensure_face_refs_dir(cfg)
    (d / "README.txt").write_text("x", encoding="utf-8")
    (d / "face.jpg").write_bytes(b"j")
    assert len(list_face_refs(cfg)) == 1
