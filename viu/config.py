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


def _default_data_dir() -> Path:
    explicit = os.environ.get("VIU_DATA_DIR")
    if explicit not in (None, ""):
        return Path(explicit).expanduser().resolve()
    cwd = Path(os.getcwd()).resolve()
    if cwd.name.lower() == "viu":
        return (cwd / ".viu").resolve()
    viu_default = Path("U:/Viu")
    if viu_default.is_dir():
        return (viu_default / ".viu").resolve()
    unity = os.environ.get("VIU_UNITY_PROJECT", "").strip()
    if unity:
        root = Path(unity).expanduser().resolve()
        if root.name.lower() == "anabarra" and root.parent.name.lower() == "unity":
            return (root.parent.parent / ".viu").resolve()
    return (cwd / ".viu").resolve()


@dataclass
class Config:
    """Настройки запуска агента."""

    # Корень рабочего пространства — песочница для файловых/shell операций.
    root: Path = field(default_factory=lambda: Path(_env("VIU_ROOT", os.getcwd())).resolve())

    # Каталог для служебных данных агента (память, планы, логи).
    data_dir: Path = field(default_factory=_default_data_dir)

    # Провайдер LLM: "mock" (офлайн, детерминированный) или "openai" (OpenAI-совместимый API).
    provider: str = field(default_factory=lambda: _env("VIU_PROVIDER", "mock"))

    # Параметры OpenAI-совместимого API.
    # Пустые роли → viu-обёртки (см. llm_roles.effective_model), не голый coder.
    model: str = field(default_factory=lambda: _env("VIU_MODEL", "viu-cydonia"))
    model_reflect: str = field(
        default_factory=lambda: _env("VIU_MODEL_REFLECT", "viu-cydonia")
    )
    model_work: str = field(default_factory=lambda: _env("VIU_MODEL_WORK", "viu-qwen32"))
    model_code: str = field(
        default_factory=lambda: _env("VIU_MODEL_CODE", "qwen2.5-coder:14b")
    )
    api_key: str = field(default_factory=lambda: _env("VIU_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: _env("VIU_BASE_URL", "https://api.openai.com/v1")
    )

    # Ограничения цикла рассуждений.
    max_steps: int = field(default_factory=lambda: int(_env("VIU_MAX_STEPS", "12")))
    temperature: float = field(default_factory=lambda: float(_env("VIU_TEMPERATURE", "0.2")))
    # Один запрос к Ollama/LLM (сек). 14b на холодном старте легко >2 мин.
    llm_timeout: float = field(default_factory=lambda: float(_env("VIU_LLM_TIMEOUT", "1800")))

    # Разрешать ли реальное выполнение shell-команд (по умолчанию — да, но в песочнице).
    allow_shell: bool = field(default_factory=lambda: _env("VIU_ALLOW_SHELL", "1") == "1")

    # Разрешать ли исходящие сетевые запросы (web-инструменты).
    allow_network: bool = field(default_factory=lambda: _env("VIU_ALLOW_NETWORK", "1") == "1")

    # Интеграция с Blender.
    blender_exe: str = field(default_factory=lambda: _env("VIU_BLENDER_EXE", "blender"))
    blender_host: str = field(default_factory=lambda: _env("VIU_BLENDER_HOST", "127.0.0.1"))
    blender_port: int = field(default_factory=lambda: int(_env("VIU_BLENDER_PORT", "8765")))

    # Cascadeur — правка FBX-анимаций (Windows).
    cascadeur_exe: str = field(default_factory=lambda: _env("VIU_CASCADEUR_EXE", ""))

    # ComfyUI — локальный API; установка по умолчанию рядом с Вью.
    comfy_url: str = field(
        default_factory=lambda: _env("VIU_COMFY_URL", "http://127.0.0.1:8188")
    )
    comfy_root: str = field(
        default_factory=lambda: _env("VIU_COMFY_ROOT", "U:/Viu/ComfyUI")
    )

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
    # Inbox — один пак за раз (U:\Viu\Inbox). Не Windows Downloads на C:.
    inbox_dir: str = field(
        default_factory=lambda: _env("VIU_INBOX_DIR", "") or _env("VIU_DOWNLOADS_DIR", "")
    )
    downloads_dir: str = field(
        default_factory=lambda: _env("VIU_DOWNLOADS_DIR", "") or _env("VIU_INBOX_DIR", "")
    )
    mascot_dir: str = field(default_factory=lambda: _env("VIU_MASCOT_DIR", ""))
    shanya_max_lift_kg: float = field(
        default_factory=lambda: float(_env("VIU_SHANYA_MAX_LIFT_KG", "35"))
    )

    # Comfy MoCap: лимит kept-клипов на одно действие (цикл сарая).
    comfy_max_per_action: int = field(
        default_factory=lambda: int(_env("VIU_COMFY_MAX_PER_ACTION", "10"))
    )
    comfy_barn_cycle: bool = field(
        default_factory=lambda: _env("VIU_COMFY_BARN_CYCLE", "1") == "1"
    )

    # Ветка git для автообновления GUI.
    update_branch: str = field(
        default_factory=lambda: _env("VIU_UPDATE_BRANCH", "cursor/viu-agent-core-65c2")
    )

    def ensure_dirs(self) -> "Config":
        """Создаёт служебные каталоги, если их ещё нет."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        try:
            from .anabarra_layout import ensure_layout

            ensure_layout(self)
        except OSError:
            pass
        return self

    def summary(self) -> str:
        return (
            f"root={self.root}\n"
            f"data_dir={self.data_dir}\n"
            f"provider={self.provider}\n"
            f"model={self.model}\n"
            f"llm_timeout={self.llm_timeout}\n"
            f"max_steps={self.max_steps}\n"
            f"allow_shell={self.allow_shell} allow_network={self.allow_network}\n"
            f"blender_exe={self.blender_exe} blender={self.blender_host}:{self.blender_port}\n"
            f"comfy_url={self.comfy_url} comfy_root={self.comfy_root or '(авто)'}\n"
            f"unity_project={self.unity_project or '(не задан)'}\n"
            f"unity_exe={self.unity_exe or '(авто Hub)'}"
        )
