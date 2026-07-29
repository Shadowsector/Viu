"""Триггер Comfy/Комфи vs фантазия «снять»."""

from __future__ import annotations

from viu.integrations.comfy.intent import (
    format_reflect_comfy_block,
    looks_like_comfy_job_request,
    mentions_comfy,
)
from viu.prompts.reflect_mode import viu_voice_issues


def test_mentions_comfy_trigger():
    assert mentions_comfy("сгенерируй мне это видео в ComfyUi")
    assert mentions_comfy("сними в Комфи")
    assert mentions_comfy("открой ComfyUI")
    assert not mentions_comfy("сними сцену, представь что я с камерой")
    assert not mentions_comfy("давай снимем это красиво")


def test_comfy_job_needs_trigger():
    assert looks_like_comfy_job_request("сгенерируй видео в Comfy")
    assert looks_like_comfy_job_request("сними это в Комфи")
    assert not looks_like_comfy_job_request("сними это красиво")
    assert not looks_like_comfy_job_request("Comfy как тебе настроение?")


def test_reflect_comfy_block_mentions_pause_and_not_cameras():
    block = format_reflect_comfy_block()
    assert "Comfy" in block or "Комфи" in block
    assert "камер" in block.lower()  # запрет врать про камеры
    assert "паузе" in block.lower() or "чат" in block.lower() or "Студия" in block


def test_voice_flags_fake_no_comfy_access():
    user = "хорошо, теперь сгенерируй мне это видео в ComfyUi"
    bad = (
        "Извини, но я не могу создать или сгенерировать видео. "
        "У меня нет доступа к камерам или ComfyUI — я просто беседую с тобой."
    )
    issues = viu_voice_issues(bad, user_text=user)
    assert any("Comfy" in i or "комфи" in i.lower() for i in issues)
    ok = "Сейчас Comfy на паузе — сначала тело Шани, потом Студия Comfy."
    assert not any("отказ от Comfy" in i for i in viu_voice_issues(ok, user_text=user))
