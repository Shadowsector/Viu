"""Конфигурация агента Вью.

Все настройки читаются из переменных окружения с разумными
значениями по умолчанию, чтобы агент запускался «из коробки»
даже без API-ключа (в режиме mock-провайдера).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


@dataclass
class Config:
    """Настройки запуска агента."""

    # Корень рабочего пространства — песочница для файловых/shell операций.
    root: Path = field(default_factory=lambda: Path(_env("VIU_ROOT", os.getcwd())).resolve())

    # Каталог для служебных данных агента (память, планы, логи).
    data_dir: Path = field(
        default_factory=lambda: Path(_env("VIU_DATA_DIR", str(Path(os.getcwd()) / ".viu"))).resolve()
    )

    # Провайдер LLM: "mock" (офлайн, детерминированный) или "openai" (OpenAI-совместимый API).
    provider: str = field(default_factory=lambda: _env("VIU_PROVIDER", "mock"))

    # Параметры OpenAI-совместимого API.
    model: str = field(default_factory=lambda: _env("VIU_MODEL", "gpt-4o-mini"))
    api_key: str = field(default_factory=lambda: _env("VIU_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: _env("VIU_BASE_URL", "https://api.openai.com/v1")
    )

    # Ограничения цикла рассуждений.
    max_steps: int = field(default_factory=lambda: int(_env("VIU_MAX_STEPS", "12")))
    temperature: float = field(default_factory=lambda: float(_env("VIU_TEMPERATURE", "0.2")))

    # Разрешать ли реальное выполнение shell-команд (по умолчанию — да, но в песочнице).
    allow_shell: bool = field(default_factory=lambda: _env("VIU_ALLOW_SHELL", "1") == "1")

    # Разрешать ли исходящие сетевые запросы (web-инструменты).
    allow_network: bool = field(default_factory=lambda: _env("VIU_ALLOW_NETWORK", "1") == "1")

    def ensure_dirs(self) -> "Config":
        """Создаёт служебные каталоги, если их ещё нет."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        return self

    def summary(self) -> str:
        return (
            f"root={self.root}\n"
            f"data_dir={self.data_dir}\n"
            f"provider={self.provider}\n"
            f"model={self.model}\n"
            f"max_steps={self.max_steps}\n"
            f"allow_shell={self.allow_shell} allow_network={self.allow_network}"
        )
