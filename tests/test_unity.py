"""Тесты интеграции Unity."""

from pathlib import Path

from viu.integrations.unity import parse_editor_log, workflow_status_text
from viu.integrations.unity.project_scan import scan_fbx_meta, scan_unity_project


def test_parse_editor_log_rig_and_wgt(tmp_path):
    log = tmp_path / "Editor.log"
    log.write_text(
        "Rig Error: Copied Avatar mis-match Torso\n"
        "Can't calculate tangents, because mesh 'WGT-rig_root' doesn't contain normals.\n"
        "Can't calculate tangents, because mesh 'WGT-rig_hands' doesn't contain normals.\n"
        "All compiler errors have to be fixed before you can enter playmode!\n",
        encoding="utf-8",
    )
    s = parse_editor_log(log)
    assert s.rig_errors
    assert s.wgt_tangent_count == 2
    assert s.playmode_blockers


def test_scan_fbx_meta_copy_avatar(tmp_path):
    fbx = tmp_path / "Idle.fbx"
    fbx.touch()
    meta = tmp_path / "Idle.fbx.meta"
    meta.write_text(
        "ModelImporter:\n  animationType: 2\n  copyAvatar: 1\n  humanDescription:\n    human: []\n",
        encoding="utf-8",
    )
    info = scan_fbx_meta(fbx)
    assert info.copy_avatar
    assert info.issues


def test_workflow_has_steps():
    text = workflow_status_text(current_step=4)
    assert "Mixamo" in text
    assert "→" in text


def test_scan_unity_project_empty(tmp_path):
    (tmp_path / "Assets").mkdir()
    scan = scan_unity_project(tmp_path)
    assert "FBX" in scan.render()
