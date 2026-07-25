"""Тесты личной привязки машины (без материнки/GPU)."""

from pathlib import Path

from viu.config import Config
from viu.machine_bind import (
    collect_soft_traits,
    ensure_bind,
    load_bind,
    rebind,
    require_personal_machine,
    status_text,
    verify_bind,
)
from viu.memory import MemoryStore
from viu.planning import Planner
from viu.tools import build_default_registry
from viu.tools.base import AgentContext
from viu.tools.machine_bind_tool import MachineBindTool


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.delenv("VIU_MACHINE_BIND_SKIP", raising=False)
    monkeypatch.delenv("VIU_MASCOT_DIR", raising=False)
    viu = tmp_path / "Viu"
    ana = tmp_path / "Anabarra"
    mascot = tmp_path / "Desktop Mascot"
    viu.mkdir()
    ana.mkdir()
    mascot.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(ana))
    monkeypatch.setenv("VIU_MASCOT_DIR", str(mascot))
    monkeypatch.setenv("VIU_ROOT", str(viu))
    return Config(root=viu, data_dir=viu / ".viu").ensure_dirs()


def test_ensure_creates_personal_bind(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    bind, created = ensure_bind(cfg)
    assert created
    assert bind.personal_use_only is True
    assert bind.owner == "den"
    assert bind.install_id
    assert bind.soft_fingerprint
    again, created2 = ensure_bind(cfg)
    assert not created2
    assert again.install_id == bind.install_id


def test_verify_ok_same_machine(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ensure_bind(cfg)
    ok, msg, bind = verify_bind(cfg)
    assert ok
    assert bind is not None
    assert "ok" in msg.lower() or "install_id" in msg


def test_fingerprint_ignores_gpu_fields(tmp_path, monkeypatch):
    """В отпечатке нет полей материнки/GPU — только soft traits."""
    cfg = _cfg(tmp_path, monkeypatch)
    traits = collect_soft_traits(cfg)
    data = traits.__dict__
    assert "gpu" not in data
    assert "motherboard" not in data
    assert "mac" not in data
    assert "username" in data and "hostname" in data


def test_path_change_requires_rebind(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ensure_bind(cfg)
    # Съехал путь Anabarra
    other = tmp_path / "Anabarra2"
    other.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(other))
    cfg2 = Config(root=cfg.root, data_dir=cfg.data_dir)
    ok, msg, _ = verify_bind(cfg2)
    assert ok is False
    assert "rebind" in msg.lower() or "отпечаток" in msg.lower()


def test_rebind_keeps_install_id(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    bind, _ = ensure_bind(cfg)
    old_id = bind.install_id
    other = tmp_path / "AnabarraMoved"
    other.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(other))
    cfg2 = Config(root=cfg.root, data_dir=cfg.data_dir)
    new_bind, msg = rebind(cfg2, reason="moved_anabarra")
    assert new_bind.install_id == old_id
    assert new_bind.rebind_count == 1
    assert "перепривязано" in msg
    ok, _, _ = verify_bind(cfg2)
    assert ok


def test_require_personal_auto_ensure(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    assert load_bind(cfg) is None
    ok, msg = require_personal_machine(cfg, auto_ensure=True)
    assert ok
    assert load_bind(cfg) is not None


def test_skip_env(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    monkeypatch.setenv("VIU_MACHINE_BIND_SKIP", "1")
    ok, msg, _ = verify_bind(cfg)
    assert ok
    assert "SKIP" in msg


def test_status_text_mentions_rebind(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ensure_bind(cfg)
    text = status_text(cfg)
    assert "материн" in text.lower() or "GPU" in text
    assert "rebind" in text.lower()


def test_machine_bind_tool(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    reg = build_default_registry()
    ctx = AgentContext(
        config=cfg,
        memory=MemoryStore(cfg.data_dir / "memory.json"),
        planner=Planner(cfg.data_dir / "plan.json"),
        registry=reg,
    )
    r = MachineBindTool().run({"action": "ensure"}, ctx)
    assert r.ok
    assert "install_id" in r.content
    r2 = MachineBindTool().run({"action": "check"}, ctx)
    assert r2.ok


def test_asset_stage_blocked_on_mismatch(tmp_path, monkeypatch):
    from viu.tools.asset_archive_tool import AssetArchiveStageTool

    cfg = _cfg(tmp_path, monkeypatch)
    ensure_bind(cfg)
    other = tmp_path / "OtherAna"
    other.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(other))
    cfg2 = Config(root=cfg.root, data_dir=cfg.data_dir)
    reg = build_default_registry()
    ctx = AgentContext(
        config=cfg2,
        memory=MemoryStore(cfg2.data_dir / "memory.json"),
        planner=Planner(cfg2.data_dir / "plan.json"),
        registry=reg,
    )
    pack = tmp_path / "Desktop Mascot" / "Women" / "x"
    pack.mkdir(parents=True)
    (pack / "a.blend").write_bytes(b"1")
    r = AssetArchiveStageTool().run(
        {"source": str(pack), "category": "Women"}, ctx
    )
    assert not r.ok
    assert "rebind" in r.content.lower()


def test_cli_machine_ensure(tmp_path, monkeypatch):
    from viu.__main__ import main

    cfg = _cfg(tmp_path, monkeypatch)
    monkeypatch.setenv("VIU_DATA_DIR", str(cfg.data_dir))
    code = main(["machine", "ensure"])
    assert code == 0
    assert (cfg.data_dir / "machine_bind.json").is_file()
