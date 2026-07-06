"""Тесты запуска редактора Unity (unity_open)."""

from pathlib import Path

from viu.config import Config
from viu.integrations.unity.setup import open_editor_command
from viu.memory import MemoryStore
from viu.planning import Planner
from viu.tools import AgentContext, build_default_registry
from viu.tools.unity_project_tool import UnityOpenTool


def _ctx(tmp_path, **cfg):
    config = Config(root=tmp_path, data_dir=tmp_path / ".viu", **cfg).ensure_dirs()
    return AgentContext(
        config=config,
        memory=MemoryStore(config.data_dir / "memory.json"),
        planner=Planner(config.data_dir / "plan.json"),
        registry=build_default_registry(),
    )


def test_open_editor_command(tmp_path):
    exe = tmp_path / "Unity.exe"
    exe.write_bytes(b"")
    proj = tmp_path / "proj"
    proj.mkdir()
    cmd = open_editor_command(proj, exe)
    assert cmd[0].endswith("Unity.exe")
    assert "-projectPath" in cmd
    assert str(proj.resolve()) in cmd
    assert "-batchmode" not in cmd  # это GUI-запуск, не headless


def test_unity_open_registered():
    reg = build_default_registry()
    assert "unity_open" in reg.names()


def test_unity_open_no_exe(tmp_path):
    unity = tmp_path / "unity"
    (unity / "Assets").mkdir(parents=True)
    ctx = _ctx(tmp_path, unity_project=str(unity), unity_exe="")
    result = UnityOpenTool().run({}, ctx)
    # Без Unity.exe и без Hub на Linux — понятная ошибка, а не падение.
    assert not result.ok
    assert "Unity.exe" in result.content


def test_prepare_scene_blocks_when_unity_open(tmp_path):
    unity = tmp_path / "unity"
    (unity / "Assets").mkdir(parents=True)
    (unity / "Temp").mkdir()
    (unity / "Temp" / "UnityLockfile").write_bytes(b"")  # Unity «открыт»
    ctx = _ctx(tmp_path, unity_project=str(unity))
    from viu.tools.unity_project_tool import UnityPrepareSceneTool

    result = UnityPrepareSceneTool().run({}, ctx)
    assert not result.ok
    assert "закрыт" in result.content.lower()


def test_prepare_scene_registered():
    reg = build_default_registry()
    assert "unity_prepare_scene" in reg.names()


def test_unity_open_launches(tmp_path, monkeypatch):
    unity = tmp_path / "unity"
    (unity / "Assets").mkdir(parents=True)
    fake_exe = tmp_path / "Unity.exe"
    fake_exe.write_bytes(b"")

    from viu.tools import unity_project_tool as upt

    monkeypatch.setattr(upt, "find_unity_exe", lambda cfg: fake_exe)

    launched = {}

    def fake_popen(cmd, **kwargs):
        launched["cmd"] = cmd
        return object()

    monkeypatch.setattr(upt.subprocess, "Popen", fake_popen)

    ctx = _ctx(tmp_path, unity_project=str(unity))
    result = UnityOpenTool().run({}, ctx)
    assert result.ok
    assert launched["cmd"][0].endswith("Unity.exe")
    assert "-projectPath" in launched["cmd"]
