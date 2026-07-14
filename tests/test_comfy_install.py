"""Автоустановка ComfyUI: скан, UI→API, install без сети (mocks)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.integrations.comfy.install import (
    clone_comfyui,
    download_wan_workflows,
    scan_comfy_candidates,
    target_comfy_dir,
)
from viu.integrations.comfy.ui_to_api import ui_workflow_to_api
from viu.tools import build_default_registry


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.delenv("VIU_COMFY_ROOT", raising=False)
    viu = tmp_path / "Viu"
    viu.mkdir()
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(root=viu, data_dir=data, comfy_root="")


def test_registry_has_comfy_install():
    assert "comfy_install" in build_default_registry().names()


def test_target_and_scan(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    assert target_comfy_dir(cfg) == (tmp_path / "Viu" / "ComfyUI")
    comfy = tmp_path / "Viu" / "ComfyUI"
    comfy.mkdir(parents=True)
    (comfy / "main.py").write_text("print(1)\n", encoding="utf-8")
    found = scan_comfy_candidates(cfg)
    assert any(p == comfy.resolve() for p in found)


def test_ui_to_api_wan_like():
    ui = {
        "last_node_id": 3,
        "links": [[1, 2, 0, 1, 0, "CLIP"]],
        "nodes": [
            {
                "id": 1,
                "type": "CLIPTextEncode",
                "mode": 0,
                "title": "CLIP Text Encode (Positive Prompt)",
                "inputs": [{"name": "clip", "type": "CLIP", "link": 1}],
                "widgets_values": ["a cat walks"],
            },
            {
                "id": 2,
                "type": "CLIPLoader",
                "mode": 0,
                "inputs": [],
                "widgets_values": ["umt5.safetensors", "wan", "default"],
            },
            {
                "id": 9,
                "type": "KSampler",
                "mode": 4,  # muted — skip
                "inputs": [],
                "widgets_values": [1, "randomize", 20, 6, "euler", "normal", 1],
            },
        ],
    }
    api = ui_workflow_to_api(ui)
    assert "9" not in api
    assert api["1"]["inputs"]["text"] == "a cat walks"
    assert api["1"]["inputs"]["clip"] == ["2", 0]
    assert api["2"]["inputs"]["clip_name"] == "umt5.safetensors"


def test_clone_comfyui_mock(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    dest = target_comfy_dir(cfg)

    def fake_run(cmd, **kwargs):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "main.py").write_text("# fake\n", encoding="utf-8")
        return True, "cloned"

    with patch("viu.integrations.comfy.install._run", side_effect=fake_run):
        ok, msg, root = clone_comfyui(dest)
    assert ok
    assert root is not None
    assert (dest / "main.py").is_file()


def test_clone_stashes_nonempty_without_main(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    dest = target_comfy_dir(cfg)
    dest.mkdir(parents=True)
    (dest / "models").mkdir()
    (dest / "models" / "readme.txt").write_text("keep", encoding="utf-8")
    (dest / "random.txt").write_text("junk", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        # dest should be empty after stash
        assert list(dest.iterdir()) == [] or not any(dest.iterdir())
        (dest / "main.py").write_text("# fake\n", encoding="utf-8")
        (dest / "models").mkdir(exist_ok=True)
        return True, "cloned"

    with patch("viu.integrations.comfy.install._run", side_effect=fake_run):
        ok, msg, root = clone_comfyui(dest)
    assert ok, msg
    assert root == dest.resolve()
    assert (dest / "main.py").is_file()
    assert "stash" in msg.lower() or "Старое" in msg
    # models restored from stash
    assert (dest / "models" / "readme.txt").is_file()
    stashes = list(dest.parent.glob("ComfyUI_stash_*"))
    assert stashes


def test_find_nested_main(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    outer = target_comfy_dir(cfg)
    nested = outer / "ComfyUI"
    nested.mkdir(parents=True)
    (nested / "main.py").write_text("#x\n", encoding="utf-8")
    from viu.integrations.comfy.paths import find_comfy_main_under

    found = find_comfy_main_under(outer)
    assert found == nested.resolve()


def test_download_workflows_convert(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ui = {
        "nodes": [
            {
                "id": 6,
                "type": "CLIPTextEncode",
                "mode": 0,
                "inputs": [],
                "widgets_values": ["x"],
                "title": "Positive",
            }
        ],
        "links": [],
    }
    payload = json.dumps(ui).encode("utf-8")

    class Resp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("urllib.request.urlopen", return_value=Resp()):
        ok, msg = download_wan_workflows(cfg, force=True)
    assert ok, msg
    t2v = cfg.data_dir / "comfy" / "workflows" / "t2v.json"
    assert t2v.is_file()
    data = json.loads(t2v.read_text(encoding="utf-8"))
    assert data["6"]["class_type"] == "CLIPTextEncode"
    assert not data.get("_viu_stub")
