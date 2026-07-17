"""Тихие часы и качество reflect-ответов."""

from datetime import datetime

from viu.config import Config
from viu.prompts.reflect_mode import reflect_reply_issues
from viu.quiet_hours import in_quiet_hours, quiet_hours_bounds


def test_quiet_hours_default_midnight_to_seven(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    assert quiet_hours_bounds(cfg) == (0, 7)
    assert in_quiet_hours(cfg, when=datetime(2026, 7, 10, 3, 30))
    assert not in_quiet_hours(cfg, when=datetime(2026, 7, 10, 9, 0))


def test_reflect_mid_conversation_greeting_rejected():
    issues = reflect_reply_issues("Привет! Рада снова поговорить.", has_history=True)
    assert any("приветствие" in i for i in issues)
    assert not reflect_reply_issues("Рада снова поговорить.", has_history=True)


def test_reflect_cjk_rejected():
    issues = reflect_reply_issues("Возможности 拍摄a!")
    assert any("иероглиф" in i for i in issues)


def test_reflect_deflection_banned():
    issues = reflect_reply_issues("Понял. Возвращайся к общению, когда будешь готов.")
    assert any("возвращайся" in i or "готов" in i for i in issues)
