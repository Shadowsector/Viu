"""Тесты reflect-роутера и vision."""

from viu.config import Config
from viu.integrations.telegram.router import route_telegram_message
from viu.vision import append_vision, ensure_vision, read_vision


def test_greeting_is_reflect_not_work():
    assert route_telegram_message("Вьюшка, привет, как ты?") == "reflect"
    assert route_telegram_message("привет, ты супер") == "reflect"


def test_correction_about_house_not_work():
    msg = "нет, мы ассет дома пытались разметить и в Юнити запихнуть"
    assert route_telegram_message(msg) == "reflect"


def test_explicit_next_step_is_work():
    assert route_telegram_message("следующий шаг") == "work"
    assert route_telegram_message("сделай следующий шаг") == "work"


def test_vision_roundtrip(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    ensure_vision(cfg)
    append_vision(cfg, "Сарай", "разметка стола готова")
    text = read_vision(cfg)
    assert "Сарай" in text
    assert "разметка" in text
