"""Пауза лишних кнопок + чеклист тела."""

from pathlib import Path

from viu.body_pipeline import BODY_STEPS, mark_step_done, render_checklist
from viu.config import Config
from viu.feature_focus import PAUSED_GUI_GROUPS, is_action_paused
from viu.gui_actions import ACTION_GROUPS, GUI_ACTIONS, actions_by_group
from viu.tools import build_default_registry


def test_comfy_and_cascadeur_groups_paused():
    assert "ComfyUI — видео" in PAUSED_GUI_GROUPS
    assert "Cascadeur — анимации" in PAUSED_GUI_GROUPS


def test_paused_actions_hidden_from_sidebar_groups():
    visible = actions_by_group(include_paused=False)
    assert visible["ComfyUI — видео"] == []
    assert visible["Cascadeur — анимации"] == []
    assert not any(a.action_id == "lab_comfy" for a in visible["ComfyUI — видео"])
    assert any(a.action_id == "body_pipeline" for a in visible["Тело Шани"])
    # В полном списке кнопки живут
    all_ids = {a.action_id for a in GUI_ACTIONS}
    assert "lab_comfy" in all_ids
    assert "lab_cascadeur" in all_ids
    assert GUI_ACTIONS  # noqa: keep


def test_include_paused_shows_comfy():
    full = actions_by_group(include_paused=True)
    assert any(a.action_id == "lab_comfy" for a in full["ComfyUI — видео"])


def test_show_paused_env(monkeypatch):
    monkeypatch.setenv("VIU_SHOW_PAUSED_UI", "1")
    assert is_action_paused("lab_comfy", "ComfyUI — видео", paused_flag=True) is False
    visible = actions_by_group(include_paused=False)
    assert any(a.action_id == "lab_comfy" for a in visible["ComfyUI — видео"])


def test_body_group_in_action_groups():
    assert "Тело Шани" in ACTION_GROUPS
    assert ACTION_GROUPS.index("Тело Шани") < ACTION_GROUPS.index("ComfyUI — видео")


def test_body_pipeline_checklist(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    text = render_checklist(cfg)
    assert "Тело Шани" in text
    assert "Shrinkwrap" in text or "подогнать" in text.lower()
    _, msg = mark_step_done(cfg)
    assert "отмечен" in msg or "Дальше" in msg
    text2 = render_checklist(cfg)
    assert "[x]" in text2


def test_body_steps_count():
    assert len(BODY_STEPS) == 6


def test_body_pipeline_tool_registered():
    reg = build_default_registry()
    assert reg.get("body_pipeline") is not None
