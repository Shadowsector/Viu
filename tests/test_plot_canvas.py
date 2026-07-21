"""Канва сюжета / квесты — каркас и запись из reflect JSON."""

from viu.config import Config
from viu.plot_canvas import (
    append_plot_canvas,
    apply_reflect_updates,
    canvas_has_substance,
    ensure_plot_canvas,
    ensure_quests,
    looks_like_plot_design,
    read_plot_canvas,
)
from viu.situational_context import build_reflect_notes


def test_ensure_skeleton(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    p = ensure_plot_canvas(cfg)
    q = ensure_quests(cfg)
    assert p.is_file() and q.is_file()
    text = read_plot_canvas(cfg)
    assert "PLOT_CANVAS" in text
    assert not canvas_has_substance(text)


def test_substance_and_append(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    ensure_plot_canvas(cfg)
    append_plot_canvas(cfg, "Логлайн: Шаня ждёт Дена у таскбара зимой.")
    text = read_plot_canvas(cfg)
    assert canvas_has_substance(text)
    notes = apply_reflect_updates(
        cfg, {"quest_update": "### Квест: Первый снег\n**Цель:** согреться"}
    )
    assert notes and "квесты" in notes[0]


def test_reflect_notes_mention_canvas(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    notes = build_reflect_notes(cfg)
    assert "PLOT_CANVAS" in notes


def test_looks_like_plot():
    assert looks_like_plot_design("давай набросаем квест и арку")
    assert not looks_like_plot_design("привет как дела")
