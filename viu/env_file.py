"""Загрузка .env в os.environ (без сторонних пакетов)."""

from __future__ import annotations

import os
import re
from pathlib import Path

# Из .env перечитываем всегда, если в файле непустое значение
# (иначе пустая переменная окружения блокирует токен из файла).
_RELOAD_IF_EMPTY = frozenset(
    {
        "VIU_GITHUB_TOKEN",
        "GITHUB_TOKEN",
        "VIU_TELEGRAM_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "VIU_API_KEY",
    }
)

# Эти ключи из .env всегда перекрывают то, что выставил Viu.cmd / оболочка.
_ALWAYS_FROM_FILE = frozenset(
    {
        "VIU_LLM_TIMEOUT",
        "VIU_MODEL",
        "VIU_MODEL_REFLECT",
        "VIU_MODEL_WORK",
        "VIU_MODEL_CODE",
        "VIU_PROVIDER",
        "VIU_BASE_URL",
        "VIU_OLLAMA_NUM_CTX",
        "VIU_OLLAMA_NUM_PREDICT",
        "VIU_OLLAMA_KEEP_ALIVE",
        "VIU_LAB_VRAM_GB",
        "VIU_REFLECT_TEMPERATURE",
        "VIU_REFLECT_PROMPT_HALF",
        "VIU_REFLECT_DUMP",
        "VIU_REFLECT_NO_SYSTEM",
        "VIU_REFLECT_NO_HISTORY",
        "VIU_REFLECT_STORY_HISTORY",
        "VIU_REFLECT_FILTERED",
    }
)


_EXPORT_RE = re.compile(r"^export\s+", re.IGNORECASE)


def _parse_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    line = _EXPORT_RE.sub("", line)
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if not key:
        return None
    return key, value


def _apply_pair(key: str, value: str) -> None:
    if key in _RELOAD_IF_EMPTY:
        if value:
            os.environ[key] = value
        return
    if key in _ALWAYS_FROM_FILE:
        if value:
            os.environ[key] = value
        return
    if key not in os.environ:
        os.environ[key] = value


def load_env_file(*roots: Path) -> None:
    """Читает KEY=VALUE из .env в каждом root."""
    seen: set[Path] = set()
    for root in roots:
        if root is None:
            continue
        path = Path(root).expanduser().resolve() / ".env"
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        for line in text.splitlines():
            parsed = _parse_line(line)
            if parsed:
                _apply_pair(*parsed)


def ensure_env_file(root: Path) -> Path:
    """Если нет .env — копирует .env.example → .env."""
    root = Path(root).expanduser().resolve()
    target = root / ".env"
    example = root / ".env.example"
    if not target.is_file() and example.is_file():
        target.write_text(example.read_text(encoding="utf-8-sig"), encoding="utf-8")
    return target


def default_env_roots(install_root: Path | None = None) -> list[Path]:
    """U:\\Viu и .viu — оба места, куда Ден мог положить .env."""
    roots: list[Path] = []
    if install_root is not None:
        roots.append(Path(install_root))
    try:
        from .updater import package_root

        pkg = package_root().parent
        if pkg not in roots:
            roots.append(pkg)
    except Exception:  # noqa: BLE001
        pass
    try:
        from .config import Config

        data = Config().data_dir
        if data not in roots:
            roots.append(data)
    except Exception:  # noqa: BLE001
        pass
    return roots


def bootstrap_env(install_root: Path | None = None) -> Path | None:
    """Шаблон .env + загрузка. Вызывать при старте GUI/CLI."""
    roots = default_env_roots(install_root)
    primary = roots[0] if roots else Path.cwd()
    env_path = ensure_env_file(primary)
    load_env_file(*roots)
    try:
        from .ollama_vram import apply_ollama_vram_limit

        apply_ollama_vram_limit()
    except Exception:
        pass
    return env_path if env_path.is_file() else None


def reload_secrets() -> None:
    """Перечитать токены из .env (после правки файла без перезапуска — на всякий)."""
    load_env_file(*default_env_roots())


def github_token() -> str:
    reload_secrets()
    return (
        os.environ.get("VIU_GITHUB_TOKEN", "").strip()
        or os.environ.get("GITHUB_TOKEN", "").strip()
    )


def env_hint_for_token(name: str = "VIU_GITHUB_TOKEN") -> str:
    roots = default_env_roots()
    paths = [str(Path(r) / ".env") for r in roots[:2]]
    where = " или ".join(paths) if paths else "U:\\Viu\\.env"
    return f"Добавь {name}=... в {where} и перезапусти Viu."
