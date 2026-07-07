"""Тесты GUI actions, updater, import staging."""

from pathlib import Path

from viu.config import Config
from viu.gui_actions import GUI_ACTIONS, actions_by_group
from viu.memory import MemoryStore
from viu.planning import Planner
from viu.tools import AgentContext, build_default_registry
from viu.tools.unity_project_tool import UnityImportStagingTool
from viu.updater import find_git_root, package_root, version_label


def test_gui_actions_grouped():
    grouped = actions_by_group()
    assert "Unity" in grouped
    assert "Игра" in grouped
    assert any(a.action_id == "add_animation" for a in GUI_ACTIONS)
    assert any(a.action_id == "unity_apply" and a.is_chain for a in GUI_ACTIONS)
    assert any(a.action_id == "unity_overlay" and a.tool == "unity_overlay" for a in GUI_ACTIONS)
    assert any(a.tool == "__update_viu__" for a in GUI_ACTIONS)
    assert any(a.action_id == "autopilot" and a.uses_agent for a in GUI_ACTIONS)
    # Больше нет запутанной кнопки про «диск U».
    assert all("диска U" not in a.label for a in GUI_ACTIONS)
    apply_btn = next(a for a in GUI_ACTIONS if a.action_id == "unity_apply")
    assert "unity_sync_animations" in [t[0] for t in apply_btn.tool_chain]


def test_find_git_root():
    root = find_git_root(package_root())
    assert root is not None
    assert (root / ".git").is_dir()


def test_version_label():
    label = version_label()
    assert "Viu" in label


def test_unity_import_staging(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "X Bot@Female Tough Walk.fbx").write_bytes(b"fbx")

    unity = tmp_path / "unity"
    (unity / "Assets").mkdir(parents=True)

    config = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        unity_project=str(unity),
        unity_anim_staging=str(staging),
    ).ensure_dirs()
    registry = build_default_registry()
    ctx = AgentContext(
        config=config,
        memory=MemoryStore(config.data_dir / "memory.json"),
        planner=Planner(config.data_dir / "plan.json"),
        registry=registry,
    )

    result = UnityImportStagingTool().run({}, ctx)
    assert result.ok
    dest = unity / "Assets/Characters/Shanya/Animations/X Bot@Female Tough Walk.fbx"
    assert dest.is_file()
