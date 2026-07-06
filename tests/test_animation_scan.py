"""Тесты автоскана папки Animations/."""

from pathlib import Path

from viu.integrations.unity.animation_scan import (
    ANIMATIONS_REL,
    classify_file_name,
    folder_fingerprint,
    scan_animations_folder,
)


def _anim_dir(tmp_path: Path) -> Path:
    d = tmp_path / ANIMATIONS_REL
    d.mkdir(parents=True)
    return d


def test_classify_idle_walk():
    state, issues, needs_q = classify_file_name("X Bot@Idle.fbx")
    assert state == "Idle"
    assert not needs_q

    state, _, needs_q = classify_file_name("X Bot@Walking.fbx")
    assert state == "Walk"
    assert not needs_q


def test_classify_unknown_needs_question():
    state, issues, needs_q = classify_file_name("Take 001.fbx")
    assert state is None
    assert needs_q
    assert issues


def test_classify_overrides():
    overrides = {"mystery.fbx": "Walk"}
    state, _, needs_q = classify_file_name("mystery.fbx", overrides)
    assert state == "Walk"
    assert not needs_q


def test_scan_animations_folder(tmp_path):
    (tmp_path / "Assets").mkdir()
    anim = _anim_dir(tmp_path)
    (anim / "X Bot@Idle.fbx").write_bytes(b"")
    (anim / "X Bot@Idle.fbx.meta").write_text(
        "animationType: 2\n", encoding="utf-8"
    )
    (anim / "X Bot@Walking.fbx").write_bytes(b"")
    (anim / "X Bot@Walking.fbx.meta").write_text(
        "animationType: 2\n", encoding="utf-8"
    )

    scan = scan_animations_folder(tmp_path)
    assert len(scan.clips) == 2
    states = {c.file_name: c.suggested_state for c in scan.clips}
    assert states["X Bot@Idle.fbx"] == "Idle"
    assert states["X Bot@Walking.fbx"] == "Walk"
    assert not scan.questions


def test_scan_viu_clips_json_list_format(tmp_path):
    (tmp_path / "Assets").mkdir()
    anim = _anim_dir(tmp_path)
    (anim / "Take 001.fbx").write_bytes(b"")
    (anim / "viu_clips.json").write_text(
        '{"overrides":[{"file":"Take 001.fbx","state":"Walk"}]}',
        encoding="utf-8",
    )

    scan = scan_animations_folder(tmp_path)
    assert len(scan.clips) == 1
    assert scan.clips[0].suggested_state == "Walk"
    assert not scan.questions


def test_folder_fingerprint_changes(tmp_path):
    (tmp_path / "Assets").mkdir()
    anim = _anim_dir(tmp_path)
    fp0 = folder_fingerprint(tmp_path)
    assert fp0 == ""

    (anim / "a.fbx").write_bytes(b"")
    fp1 = folder_fingerprint(tmp_path)
    assert fp1
    assert fp1 != fp0
