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

    # Интеграция с Blender.
    blender_exe: str = field(default_factory=lambda: _env("VIU_BLENDER_EXE", "blender"))
    blender_host: str = field(default_factory=lambda: _env("VIU_BLENDER_HOST", "127.0.0.1"))
    blender_port: int = field(default_factory=lambda: int(_env("VIU_BLENDER_PORT", "8765")))

    # Unity-проект Анабарра (корень с Assets/).
    unity_project: str = field(default_factory=lambda: _env("VIU_UNITY_PROJECT", ""))

    # Путь к Unity.exe для batchmode (опционально).
    unity_exe: str = field(default_factory=lambda: _env("VIU_UNITY_EXE", ""))

    # Автосинк Animations/: batchmode при изменении (Unity должен быть закрыт).
    unity_auto_sync: bool = field(default_factory=lambda: _env("VIU_UNITY_AUTO_SYNC", "0") == "1")

    # Интервал наблюдателя папки Animations/ (секунды).
    unity_anim_scan_sec: float = field(
        default_factory=lambda: float(_env("VIU_ANIM_SCAN_SEC", "300"))
    )

    # Папка-«вход» для FBX перед Unity (Total Commander и т.п.).
    unity_anim_staging: str = field(
        default_factory=lambda: _env("VIU_ANIM_STAGING", "U:/Anabarra/Animations")
    )

    # Библиотека ассетов и каталог предметов.
    library_root: str = field(default_factory=lambda: _env("VIU_LIBRARY_ROOT", ""))
    downloads_dir: str = field(default_factory=lambda: _env("VIU_DOWNLOADS_DIR", ""))
    shanya_max_lift_kg: float = field(
        default_factory=lambda: float(_env("VIU_SHANYA_MAX_LIFT_KG", "35"))
    )

    # Ветка git для автообновления GUI.
    update_branch: str = field(
        default_factory=lambda: _env("VIU_UPDATE_BRANCH", "cursor/viu-agent-core-65c2")
    )

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
            f"allow_shell={self.allow_shell} allow_network={self.allow_network}\n"
            f"blender_exe={self.blender_exe} blender={self.blender_host}:{self.blender_port}\n"
            f"unity_project={self.unity_project or '(не задан)'}\n"
            f"unity_exe={self.unity_exe or '(авто Hub)'}"
        )
