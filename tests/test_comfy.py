"""ComfyUI client, workflows, tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from viu.config import Config
from viu.integrations.comfy.client import ComfyClient, ComfyError
from viu.integrations.comfy.paths import comfy_out_dir, comfy_refs_dir, comfy_workflows_dir
from viu.integrations.comfy.workflows import inject_text_prompt, load_workflow, write_install_readme
from viu.tools import AgentContext, build_default_registry
from viu.tools.comfy_tool import ComfyRunTool, ComfyStatusTool


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    monkeypatch.delenv("VIU_COMFY_ROOT", raising=False)
    monkeypatch.delenv("VIU_COMFY_REFS", raising=False)
    monkeypatch.delenv("VIU_COMFY_OUT", raising=False)
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(
        root=tmp_path,
        data_dir=data,
        library_root=str(tmp_path / "Library"),
        comfy_url="http://127.0.0.1:8188",
        comfy_root="",
    )


def test_registry_has_comfy_tools():
    names = build_default_registry().names()
    assert "comfy_status" in names
    assert "comfy_run" in names
    assert "comfy_ensure" in names
    assert "comfy_mocap" in names
    assert "comfy_queue_clear" in names


def test_paths_and_readme(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    refs = comfy_refs_dir(cfg)
    out = comfy_out_dir(cfg)
    wf = comfy_workflows_dir(cfg)
    assert refs.is_dir()
    assert out.is_dir()
    assert wf.is_dir()
    assert "Lab" in str(refs) or refs.name == "Refs"
    readme = write_install_readme(cfg)
    assert readme.is_file()


def test_inject_text_prompt():
    wf = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative blur"}},
    }
    out = inject_text_prompt(wf, "walk cycle")
    assert out["1"]["inputs"]["text"] == "walk cycle"
    assert out["2"]["inputs"]["text"] == "negative blur"


def test_load_workflow_api_and_ui_convert(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    d = comfy_workflows_dir(cfg)
    (d / "default.json").write_text(
        json.dumps({"3": {"class_type": "KSampler", "inputs": {}}}),
        encoding="utf-8",
    )
    assert "3" in load_workflow(cfg, "default")

    ui = {
        "nodes": [
            {
                "id": 6,
                "type": "CLIPTextEncode",
                "mode": 0,
                "inputs": [],
                "widgets_values": ["hello"],
                "title": "Positive",
            }
        ],
        "links": [],
    }
    (d / "ui.json").write_text(json.dumps(ui), encoding="utf-8")
    api = load_workflow(cfg, "ui")
    assert api["6"]["class_type"] == "CLIPTextEncode"
    assert api["6"]["inputs"]["text"] == "hello"


def test_comfy_status_offline(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ctx = AgentContext(
        config=cfg,
        memory=MagicMock(),
        planner=MagicMock(),
        registry=build_default_registry(),
    )
    with patch.object(ComfyClient, "ping", return_value=(False, "down")):
        res = ComfyStatusTool().run({}, ctx)
    assert res.ok
    assert "down" in res.content or "ComfyUI" in res.content


def test_comfy_run_downloads(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    d = comfy_workflows_dir(cfg)
    api_wf = {
        "1": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "x"},
        },
        "2": {"class_type": "SaveImage", "inputs": {}},
    }
    (d / "t2v.json").write_text(json.dumps(api_wf), encoding="utf-8")
    (d / "default.json").write_text(json.dumps(api_wf), encoding="utf-8")
    ctx = AgentContext(
        config=cfg,
        memory=MagicMock(),
        planner=MagicMock(),
        registry=build_default_registry(),
    )
    fake_files = [
        {"filename": "out_00001_.png", "subfolder": "", "type": "output", "kind": "images"}
    ]

    def fake_download(self, filename, *, subfolder="", folder_type="output", dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"png")
        return dest

    with (
        patch.object(ComfyClient, "ping", return_value=(True, "ok")),
        patch.object(ComfyClient, "queue_prompt", return_value="pid-1"),
        patch.object(ComfyClient, "wait_history", return_value={"outputs": {"2": {}}}),
        patch.object(ComfyClient, "collect_output_files", return_value=fake_files),
        patch.object(ComfyClient, "download_view", fake_download),
    ):
        res = ComfyRunTool().run(
            {"prompt": "sit idle", "slug": "test_sit", "workflow": "t2v"}, ctx
        )
    assert res.ok, res.content
    assert "prompt_id=pid-1" in res.content
    refs = list(comfy_refs_dir(cfg).glob("test_sit_*"))
    assert refs
    assert refs[0].read_bytes() == b"png"


def test_client_collect_output_files():
    entry = {
        "outputs": {
            "9": {
                "images": [{"filename": "a.png", "subfolder": "", "type": "output"}],
                "gifs": [{"filename": "b.gif", "subfolder": "v", "type": "output"}],
            }
        }
    }
    files = ComfyClient().collect_output_files(entry)
    assert len(files) == 2
    assert files[0]["filename"] == "a.png"
    assert files[1]["kind"] == "gifs"


def test_client_queue_prompt_error():
    client = ComfyClient()
    with patch.object(client, "_post", return_value={"error": "bad"}):
        with pytest.raises(ComfyError, match="prompt error"):
            client.queue_prompt({"1": {}})
