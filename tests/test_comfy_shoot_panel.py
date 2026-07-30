"""Shoot settings + show prompt editor resolution."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.prompt_edit import format_wan_editor_text, resolved_wan_lines
from viu.integrations.comfy.prompts import SUBJECT_PREFIX
from viu.integrations.comfy.shoot_settings import (
    MODE_I2V,
    MODE_T2V,
    clamp_frames,
    frames_from_seconds,
    mode_needs_seed,
    normalize_shoot_mode,
    resolve_workflow_for_shoot,
    seed_list_labels,
)
from viu.integrations.comfy.show_profile import arm_show_profile
from viu.lab.comfy_pipeline import COMFY_TOPIC
from viu.lab.session import new_session, save_session


def _cfg(tmp_path: Path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_normalize_modes():
    assert normalize_shoot_mode("I2V") == MODE_I2V
    assert normalize_shoot_mode("img2video") == MODE_I2V
    assert normalize_shoot_mode("") == MODE_T2V
    assert mode_needs_seed("i2v")
    assert not mode_needs_seed("t2v")


def test_frames_from_seconds():
    assert frames_from_seconds(2.0) == 49  # odd
    assert clamp_frames(48) == 49
    assert clamp_frames(200) <= 121


def test_resolved_wan_lines_show_anime(tmp_path):
    cfg = _cfg(tmp_path)
    session = new_session(COMFY_TOPIC)
    arm_show_profile(
        session.meta,
        style="anime",
        action="standing near cherry blossom",
    )
    save_session(cfg, session)
    action, pos, neg = resolved_wan_lines(cfg)
    assert action
    assert pos.startswith(SUBJECT_PREFIX)
    assert "anime" in pos.lower() or "smoothmixanime" in pos.lower()
    assert "young woman" not in pos.lower()
    assert neg == "Tongue out, wet hair"
    editor = format_wan_editor_text(cfg)
    assert "ШОУ" in editor
    assert SUBJECT_PREFIX in editor
    assert "Tongue out, wet hair" in editor


def test_arm_keep_prompts(tmp_path):
    cfg = _cfg(tmp_path)
    session = new_session(COMFY_TOPIC)
    session.meta["wan_positive"] = f"{SUBJECT_PREFIX} custom pose"
    session.meta["prompt_user_edited"] = True
    arm_show_profile(
        session.meta, style="anime", action="wave", keep_prompts=True
    )
    assert session.meta["wan_positive"].startswith(SUBJECT_PREFIX)
    assert "custom pose" in session.meta["wan_positive"]


def test_seed_list_labels_mark_active(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)

    class E:
        def __init__(self, name):
            self._name = name

        def label(self):
            return self._name

        def resolve_path(self):
            return Path(self._name)

    monkeypatch.setattr(
        "viu.integrations.comfy.seed_pose.resolve_active_seed",
        lambda _c: (Path("active.png"), "viu_pose_seed.png", True),
    )
    labels = seed_list_labels(cfg, [E("active.png"), E("other.png")])
    assert any("← ВЫБРАН" in x for x in labels)
    assert labels[0].startswith("★")


def test_resolve_workflow_show_t2v(tmp_path):
    cfg = _cfg(tmp_path)
    wf, note = resolve_workflow_for_shoot(
        cfg, {"shoot_mode": "t2v", "render_profile": "show"}, has_seed=True, is_show=True
    )
    assert wf == "t2v"
    wf2, _ = resolve_workflow_for_shoot(
        cfg, {"shoot_mode": "i2v"}, has_seed=False, is_show=False
    )
    assert wf2 == "t2v"  # no seed → fallback
