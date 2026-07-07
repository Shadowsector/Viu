"""Тесты Unity setup и project I/O."""

from pathlib import Path

import pytest

from viu.agent import Agent
from viu.integrations.unity.paths import resolve_in_unity_project, unity_project_root
from viu.integrations.unity.setup import deploy_shanya_setup, strip_risky_packages
from viu.llm.mock import MockLLM


def test_resolve_in_unity_project(tmp_path):
    (tmp_path / "Assets").mkdir()
    p = resolve_in_unity_project(tmp_path, "Assets/foo.txt")
    assert p.name == "foo.txt"
    with pytest.raises(ValueError):
        resolve_in_unity_project(tmp_path, "../outside")


def test_deploy_shanya_setup(tmp_path):
    (tmp_path / "Assets").mkdir()
    ok, msg = deploy_shanya_setup(tmp_path)
    assert ok
    assert (tmp_path / "Assets/Editor/Viu/ShanyaSetup.cs").is_file()
    assert (tmp_path / "Assets/Editor/Viu/ShanyaAnimationSync.cs").is_file()
    assert (tmp_path / "Assets/Scripts/Viu/ShanyaLocomotion.cs").is_file()
    assert (tmp_path / "Assets/Characters/Shanya/Animations/viu_clips.json").is_file()
    assert "ShanyaSetup" in msg or "ShanyaAnimationSync" in msg


def test_locomotion_supports_input_system():
    src = Path(__file__).resolve().parents[1] / "viu/integrations/unity/templates/ShanyaLocomotion.cs"
    text = src.read_text(encoding="utf-8")
    assert "using UnityEngine.InputSystem" not in text
    assert "Unity.InputSystem" in text
    assert "ReadHorizontalNewInput" in text


def test_setup_ensures_input_compatible():
    src = Path(__file__).resolve().parents[1] / "viu/integrations/unity/templates/ShanyaSetup.cs"
    text = src.read_text(encoding="utf-8")
    assert "EnsureInputCompatible" in text
    assert "ActiveInputHandler.Both" in text


def test_strip_risky_packages(tmp_path):
    pkg = tmp_path / "Packages"
    pkg.mkdir()
    manifest = pkg / "manifest.json"
    manifest.write_text(
        '{"dependencies":{"com.unity.inputsystem":"1.0","com.unity.ugui":"2.0"}}',
        encoding="utf-8",
    )
    ok, msg = strip_risky_packages(tmp_path)
    assert ok
    data = manifest.read_text(encoding="utf-8")
    assert "inputsystem" not in data
    assert "ugui" in data


def test_unity_project_root_default():
    from viu.config import Config

    c = Config(unity_project="")
    root = unity_project_root(c)
    assert "Anabarra" in str(root)


def test_ask_user_stops_agent():
    agent = Agent(llm=MockLLM(responses=[
        '{"thought":"need path","action":{"tool":"ask_user","args":{"question":"Какой путь к Unity?"}}}',
    ]))
    result = agent.run("test")
    assert result.completed
    assert "Какой путь" in result.final
