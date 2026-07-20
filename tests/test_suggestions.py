"""SUGGESTIONS journal + aside merge."""

from viu.prompts.reflect_mode import merge_display_aside
from viu.suggestions import apply_suggestion_updates


def test_merge_display_aside_prepends():
    out = merge_display_aside("Основной ответ.", "Ой, это смешно.")
    assert out.startswith("«Ой, это смешно.»")
    assert "Основной ответ." in out


def test_merge_display_aside_skips_empty():
    assert merge_display_aside("Только ответ.", "") == "Только ответ."


def test_apply_suggestion_explicit(tmp_path):
    from viu.config import Config

    cfg = Config(data_dir=tmp_path / ".viu")
    cfg.ensure_dirs()
    notes = apply_suggestion_updates(
        cfg,
        {"suggestion_update": "Квест с сараем — норм, надо дожать."},
        thought="",
        user_text="квест",
    )
    assert notes
    text = (tmp_path / ".viu" / "SUGGESTIONS.md").read_text(encoding="utf-8")
    assert "сараем" in text
