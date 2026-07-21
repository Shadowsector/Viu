"""Общие фикстуры pytest."""

import pytest

# Тесты, написанные под старый reflect с фильтрами тона.
_FILTERED_SUFFIXES = (
    "test_telegram_router",
    "test_nsfw_halves",
    "test_nsfw_voice",
    "test_quiet_hours",
    "test_capabilities",
)


@pytest.fixture(autouse=True)
def _reflect_filtered_for_legacy_tests(request, monkeypatch):
    mod = getattr(request.module, "__name__", "") or ""
    if mod in _FILTERED_SUFFIXES or any(mod.endswith("." + s) for s in _FILTERED_SUFFIXES):
        monkeypatch.setenv("VIU_REFLECT_FILTERED", "1")
