"""Тесты GUI actions, updater, import staging."""

from pathlib import Path

from viu.config import Config
from viu.gui_actions import ACTION_GROUPS, GUI_ACTIONS, actions_by_group
from viu.memory import MemoryStore
from viu.planning import Planner
from viu.tools import AgentContext, build_default_registry
from viu.tools.unity_project_tool import UnityImportStagingTool
from viu.updater import find_git_root, package_root, version_label


def test_gui_actions_grouped():
    grouped = actions_by_group()
    assert "Каждый день" in grouped
    assert "Blender — существа" in grouped
    assert "ComfyUI — видео" in grouped
    assert ACTION_GROUPS == [
        "Каждый день",
        "Unity — тест на столе",
        "Blender — существа",
        "Blender — сцены и домик",
        "Cascadeur — анимации",
        "Unity — анимации",
        "ComfyUI — видео",
        "Сервис",
    ]
    assert len(grouped["Каждый день"]) <= 5
    assert len(grouped["Blender — существа"]) <= 7
    # Минимум кнопок — не стена из 30 пунктов в одной группе
    assert len(GUI_ACTIONS) <= 34
    assert any(a.action_id == "next_step" and a.tool == "__next_step__" for a in GUI_ACTIONS)
    assert any(a.action_id == "unity_overlay" and a.tool == "unity_overlay" for a in GUI_ACTIONS)
    assert any(a.tool == "__update_viu__" for a in GUI_ACTIONS)
    assert any(a.action_id == "unity_apply" and a.is_chain for a in GUI_ACTIONS)
    assert any(a.action_id == "lab_comfy" and a.tool == "__lab_comfy__" for a in GUI_ACTIONS)
    assert any(a.action_id == "interaction_blocking" and a.tool == "interaction_blocking" for a in GUI_ACTIONS)
    assert any(a.action_id == "interaction_master" and a.is_chain for a in GUI_ACTIONS)
    assert any(a.action_id == "lab_interaction" and a.tool == "__interaction_lab__" for a in GUI_ACTIONS)
    assert any(a.action_id == "comfy_studio" and a.tool == "__comfy_studio__" for a in GUI_ACTIONS)
    assert any(a.action_id == "comfy_open" and a.tool == "__comfy_open__" for a in GUI_ACTIONS)
    assert any(a.action_id == "decision_queue" and a.tool == "__decision_queue__" for a in GUI_ACTIONS)
    # Presence — сверху окна, не в сайдбаре
    assert not any(a.action_id == "presence_toggle" for a in GUI_ACTIONS)
    assert all("диска U" not in a.label for a in GUI_ACTIONS)
    # Убрали Cascadeur / apps restart / три шага overlay из главного UI
    ids = {a.action_id for a in GUI_ACTIONS}
    assert "cascadeur_status" not in ids
    assert "apps_restart_unity" not in ids
    assert "unity_overlay_validate" not in ids
    assert "unity_overlay_build" not in ids
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
