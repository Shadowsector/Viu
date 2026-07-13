"""Тесты Lab v2: models inbox, mouse, notify."""

from pathlib import Path

from viu.config import Config
    _score_rig,
    build_models_summary,
    copy_random_model_to_cascadeur_inbox,
    list_model_files,
)
from viu.lab.notify import notify_lab_awaiting_rating, notify_lab_step


def _cfg(tmp_path: Path) -> Config:
    import os

    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    os.environ["VIU_LAB_MODELS_INBOX"] = str(tmp_path / "models_inbox")
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_grade_thresholds():
    assert _grade(80) == "good"
    assert _grade(50) == "maybe"
    assert _grade(10) == "poor"


def test_score_rig_simple_ok():
    bones = [
        "Hips",
        "Spine",
        "Chest",
        "Neck",
        "Head",
        "LeftUpperArm",
        "LeftLowerArm",
        "LeftHand",
        "RightUpperArm",
        "RightLowerArm",
        "RightHand",
        "LeftUpperLeg",
        "LeftLowerLeg",
        "LeftFoot",
        "RightUpperLeg",
        "RightLowerLeg",
        "RightFoot",
    ]
    entry = _score_rig(bones, "Armature")
    assert entry.cascadeur_grade == "good"
    assert entry.cascadeur_score >= 70


def test_build_models_summary_empty(tmp_path):
    cfg = _cfg(tmp_path)
    ok, msg, art = build_models_summary(cfg)
    assert ok
    assert "пуст" in msg.lower() or "Inbox" in msg
    assert art is not None
    assert Path(art).is_file()


def test_list_model_files(tmp_path):
    cfg = _cfg(tmp_path)
    inbox = Path(cfg.root) / "models_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "hero.blend").write_bytes(b"fake")
    (inbox / "npc.fbx").write_bytes(b"fake")
    files = list_model_files(cfg)
    assert len(files) == 2


def test_copy_random_uses_seed_when_empty(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "viu.lab.models_inbox.seed_inbox_sample_fbx",
        lambda _c: (True, "seed ok", tmp_path / "seed.fbx"),
        raising=False,
    )
    from viu.integrations.cascadeur import launch as launch_mod

    monkeypatch.setattr(
        launch_mod,
        "seed_inbox_sample_fbx",
        lambda _c: (True, "seed ok", tmp_path / "seed.fbx"),
    )
    ok, msg, path = copy_random_model_to_cascadeur_inbox(cfg)
    assert ok
    assert path is not None


def test_mouse_disabled_on_linux():
    from viu.integrations.input.mouse import click_screen, lab_mouse_enabled

    assert not lab_mouse_enabled()
    ok, msg = click_screen(100, 100)
    assert not ok
    assert "Windows" in msg or "Мышь" in msg


def test_notify_lab_step_only_when_away(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    sent = []

    monkeypatch.setattr("viu.lab.notify.is_away", lambda _c: False)
    monkeypatch.setattr("viu.lab.notify._send", lambda _c, t: sent.append(t) or True)
    assert not notify_lab_step(cfg, 1, "Test", "hello")

    monkeypatch.setattr("viu.lab.notify.is_away", lambda _c: True)
    assert notify_lab_step(cfg, 2, "Scan", "done")
    assert len(sent) == 1
    assert "шаг 2" in sent[0]


def test_notify_awaiting_rating(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    sent = []
    monkeypatch.setattr("viu.lab.notify.is_away", lambda _c: True)
    monkeypatch.setattr("viu.lab.notify._send", lambda _c, t: sent.append(t) or True)
    notify_lab_awaiting_rating(cfg, "Report body")
    assert sent
    assert "итерация" in sent[0].lower() or "готова" in sent[0].lower()
