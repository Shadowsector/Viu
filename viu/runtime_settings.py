"""Runtime-настройки GUI (как у Mia): модель, интервал автообновления."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .config import Config

_LOCK = threading.Lock()


def _path(config: Config) -> Path:
    return config.data_dir / "runtime.json"


def _read(config: Config) -> dict:
    path = _path(config)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write(config: Config, data: dict) -> None:
    config.ensure_dirs()
    path = _path(config)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def get(config: Config, key: str, default: Any = None) -> Any:
    with _LOCK:
        return _read(config).get(key, default)


def set_value(config: Config, key: str, value: Any) -> None:
    with _LOCK:
        data = _read(config)
        data[key] = value
        _write(config, data)


def get_active_model(config: Config) -> str:
    return str(get(config, "active_model") or config.model)


def set_active_model(config: Config, model: str) -> None:
    set_value(config, "active_model", model)


def get_update_interval_min(config: Config) -> int:
    raw = get(config, "update_interval_min", None)
    if raw is None:
        return int(float(__import__("os").environ.get("VIU_UPDATE_INTERVAL_MIN", "60") or 60))
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def set_update_interval_min(config: Config, minutes: int) -> None:
    set_value(config, "update_interval_min", max(0, int(minutes)))


def get_reflect_model_override(config: Config) -> str:
    """Выбор reflect в GUI (runtime.json). Пусто = из .env."""
    return str(get(config, "reflect_model") or "").strip()


def set_reflect_model_override(config: Config, model_id: str) -> None:
    mid = (model_id or "").strip()
    if mid:
        set_value(config, "reflect_model", mid)
    else:
        with _LOCK:
            data = _read(config)
            data.pop("reflect_model", None)
            _write(config, data)


def get_heartbeat_interval_min(config: Config) -> int:
    raw = get(config, "heartbeat_interval_min", None)
    if raw is None:
        # По умолчанию раз в 20 мин — Вью не молчит; 0 = выкл явно
        return int(float(__import__("os").environ.get("VIU_HEARTBEAT_MIN", "20") or 20))
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 20


def set_heartbeat_interval_min(config: Config, minutes: int) -> None:
    set_value(config, "heartbeat_interval_min", max(0, int(minutes)))


def get_quiet_hours(config: Config) -> str:
    raw = get(config, "quiet_hours", None)
    if raw is None:
        return str(__import__("os").environ.get("VIU_QUIET_HOURS", "0-7") or "0-7")
    return str(raw)


def set_quiet_hours(config: Config, value: str) -> None:
    set_value(config, "quiet_hours", value.strip())


def get_window_geometry(config: Config) -> str:
    return str(get(config, "window_geometry") or "").strip()


def set_window_geometry(config: Config, geometry: str) -> None:
    set_value(config, "window_geometry", geometry.strip())
