"""Тесты интеграции Unity."""

from pathlib import Path

from viu.integrations.unity import extract_compiler_errors, parse_editor_log, workflow_status_text
from viu.integrations.unity.project_scan import scan_fbx_meta, scan_unity_project


def test_parse_editor_log_rig_and_wgt(tmp_path):
    log = tmp_path / "Editor.log"
    log.write_text(
        "Assets/TutorialInfo/Scripts/Readme.cs(10,7): error CS0246: Type not found\n"
        "Rig Error: Copied Avatar mis-match Torso\n"
        "Can't calculate tangents, because mesh 'WGT-rig_root' doesn't contain normals.\n"
        "All compiler errors have to be fixed before you can enter playmode!\n"
        "UnityEditor.SceneView:ShowCompileErrorNotification ()\n",
        encoding="utf-8",
    )
    s = parse_editor_log(log)
    assert s.rig_errors
    assert s.wgt_tangent_count == 1
    assert s.playmode_blockers
    assert s.compiler_errors
    assert "CS0246" in s.compiler_errors[0]


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


def test_extract_compiler_errors_dedupe(tmp_path):
    log = tmp_path / "Editor.log"
    log.write_text(
        "Assets/Foo.cs(1,1): error CS1002: ; expected\n"
        "Assets/Foo.cs(1,1): error CS1002: ; expected\n"
        "Assets/Bar.cs(2,3): error CS0246: missing type\n",
        encoding="utf-8",
    )
    errs = extract_compiler_errors(log)
    assert len(errs) == 2


def test_workflow_has_steps():
    text = workflow_status_text(current_step=4)
    assert "Mixamo" in text
    assert "→" in text


def test_scan_unity_project_empty(tmp_path):
    (tmp_path / "Assets").mkdir()
    scan = scan_unity_project(tmp_path)
    assert "FBX" in scan.render()
