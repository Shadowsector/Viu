"""Тесты Comfy → Cascadeur Reference / Export clip."""

from __future__ import annotations

import json
import os
from pathlib import Path

from viu.config import Config
from viu.integrations.cascadeur.reference_mocap import (
    EXPORT_COMMAND_FILENAME,
    REF_COMMAND_FILENAME,
    deploy_mocap_commands,
    finalize_export_clip,
    mocap_status_text,
    prepare_import_reference,
    resolve_kept_clip,
    stage_reference_video,
)
from viu.integrations.comfy.clip_review import (
    STATUS_KEPT,
    ComfyClip,
    ComfyClipStore,
    clip_review_path,
    comfy_kept_dir,
)


def _cfg(tmp_path: Path) -> Config:
    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    os.environ["VIU_LIBRARY_ROOT"] = str(tmp_path / "Library")
    os.environ["VIU_ANABARRA_ROOT"] = str(tmp_path / "Anabarra")
    commands = tmp_path / "csc_scripts" / "commands"
    commands.mkdir(parents=True)
    os.environ["VIU_CASCADEUR_SCRIPTS"] = str(commands)
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    anim = tmp_path / "Anabarra" / "Animations"
    anim.mkdir(parents=True, exist_ok=True)
    return Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        library_root=str(tmp_path / "Library"),
        unity_anim_staging=str(anim),
    ).ensure_dirs()


def _kept_mp4(cfg: Config, name: str = "sleep_side.mp4") -> Path:
    kept = comfy_kept_dir(cfg)
    p = kept / name
    p.write_bytes(b"\x00\x00fake-mp4")
    return p


def test_deploy_mocap_commands(tmp_path):
    cfg = _cfg(tmp_path)
    ok, msg = deploy_mocap_commands(cfg)
    assert ok
    commands = Path(os.environ["VIU_CASCADEUR_SCRIPTS"])
    assert (commands / REF_COMMAND_FILENAME).is_file()
    assert (commands / EXPORT_COMMAND_FILENAME).is_file()
    text = (commands / REF_COMMAND_FILENAME).read_text(encoding="utf-8")
    assert "Viu.ImportReference" in text
    assert "viu_mocap_pending.json" in text
    export = (commands / EXPORT_COMMAND_FILENAME).read_text(encoding="utf-8")
    assert "Viu.ExportClip" in export
    assert "export_all_objects" in export


def test_prepare_import_reference_from_kept_file(tmp_path):
    cfg = _cfg(tmp_path)
    mp4 = _kept_mp4(cfg, "toss_front.mp4")
    ok, msg, payload = prepare_import_reference(cfg, path=str(mp4), slug="sleep_toss")
    assert ok, msg
    assert payload["slug"] == "sleep_toss"
    assert Path(payload["video"]).is_file()
    assert "shanya_sleep_toss.fbx" in payload["export_fbx"]
    assert "ImportReference" in msg or "Reference" in msg
    pending = cfg.data_dir / "lab" / "mocap" / "pending_mocap.json"
    assert pending.is_file()
    scripts_pending = Path(os.environ["VIU_CASCADEUR_SCRIPTS"]) / "viu_mocap_pending.json"
    assert scripts_pending.is_file()
    data = json.loads(scripts_pending.read_text(encoding="utf-8"))
    assert data["slug"] == "sleep_toss"


def test_prepare_from_clip_store(tmp_path):
    cfg = _cfg(tmp_path)
    mp4 = _kept_mp4(cfg, "idle_front.mp4")
    store = ComfyClipStore(clip_review_path(cfg)).load()
    clip = ComfyClip(
        id="abc123",
        batch_id="b1",
        action="idle stand",
        angle="front",
        angle_label="анфас",
        path=str(mp4),
        status=STATUS_KEPT,
        catalog_slug="idle",
        enters_from=["sit_idle"],
        exits_to=["walk"],
        kept_at="2026-07-15T00:00:00",
    )
    store.clips.append(clip)
    store.save()

    ok, msg, payload = prepare_import_reference(cfg, clip_id="abc123")
    assert ok, msg
    assert payload["slug"] == "idle"
    assert payload["clip_id"] == "abc123"
    assert payload["enters_from"] == ["sit_idle"]


def test_resolve_kept_empty(tmp_path):
    cfg = _cfg(tmp_path)
    clip, path, err = resolve_kept_clip(cfg)
    assert path is None
    assert "kept" in err.lower() or "Нет" in err


def test_finalize_export_missing_then_ok(tmp_path):
    cfg = _cfg(tmp_path)
    mp4 = _kept_mp4(cfg)
    ok, msg, payload = prepare_import_reference(cfg, path=str(mp4), slug="wave")
    assert ok
    ok2, msg2 = finalize_export_clip(cfg, slug="wave")
    assert not ok2
    assert "ExportClip" in msg2 or "FBX ещё нет" in msg2

    fbx = Path(payload["export_fbx"])
    fbx.parent.mkdir(parents=True, exist_ok=True)
    fbx.write_bytes(b"fbx-bytes")
    ok3, msg3 = finalize_export_clip(cfg, slug="wave")
    assert ok3, msg3
    assert "Export OK" in msg3
    assert "wave" in msg3


def test_stage_and_status(tmp_path):
    cfg = _cfg(tmp_path)
    mp4 = _kept_mp4(cfg, "x.mp4")
    staged = stage_reference_video(cfg, mp4, "hello_world")
    assert staged.is_file()
    assert "hello_world" in staged.name
    text = mocap_status_text(cfg)
    assert "kept mp4" in text
    assert "Cascadeur MoCap" in text


def test_tools_registered():
    from viu.tools import build_default_registry

    names = build_default_registry().names()
    assert "cascadeur_import_reference" in names
    assert "cascadeur_export_clip" in names
    assert "cascadeur_mocap_assist" in names
