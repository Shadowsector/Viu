"""Тесты прямых команд чата → tool."""

from viu.gui_direct import parse_direct_tool_command
from viu.tools import build_default_registry


def test_parse_blender_batch_export():
    reg = build_default_registry()
    parsed = parse_direct_tool_command("blender_export_cascadeur_batch force=1", reg)
    assert parsed is not None
    name, args = parsed
    assert name == "blender_export_cascadeur_batch"
    assert args["force"] == "1"


def test_parse_lab_start_default_topic():
    reg = build_default_registry()
    parsed = parse_direct_tool_command("lab_start run_all=1", reg)
    assert parsed == ("lab_start", {"run_all": "1", "topic": "cascadeur"})


def test_natural_language_not_direct():
    reg = build_default_registry()
    assert parse_direct_tool_command("экспортируй модели в cascadeur", reg) is None


def test_unknown_tool_not_direct():
    reg = build_default_registry()
    assert parse_direct_tool_command("not_a_real_tool", reg) is None


def test_creature_scan_direct():
    reg = build_default_registry()
    parsed = parse_direct_tool_command("creature_catalog_scan", reg)
    assert parsed == ("creature_catalog_scan", {})


def test_creature_scan_doubled_typo():
    """Ден иногда склеивает имя дважды без пробела."""
    reg = build_default_registry()
    parsed = parse_direct_tool_command(
        "creature_catalog_scancreature_catalog_scan", reg
    )
    assert parsed is not None
    assert parsed[0] == "creature_catalog_scan"


def test_creature_scan_ru_alias():
    reg = build_default_registry()
    parsed = parse_direct_tool_command("сканируй существ", reg)
    assert parsed == ("creature_catalog_scan", {})


def test_creature_pending_ru_alias():
    reg = build_default_registry()
    parsed = parse_direct_tool_command("очередь существ", reg)
    assert parsed == ("creature_catalog_show", {"mode": "pending"})
