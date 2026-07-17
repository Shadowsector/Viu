"""Тест run_gui.pyw bootstrap."""

from pathlib import Path


def test_run_gui_script_exists():
    root = Path(__file__).resolve().parent.parent
    script = root / "run_gui.pyw"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "viu.gui" in text
    assert "viu_startup.log" in text
