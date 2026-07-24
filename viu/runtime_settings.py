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


def get_away_ping_per_day(config: Config) -> int:
    """Сколько раз в сутки Вью пишет сама, когда Дена нет (away). 0 = выкл."""
    raw = get(config, "away_ping_per_day", None)
    if raw is None:
        try:
            return max(0, min(6, int(float(__import__("os").environ.get("VIU_AWAY_PING_PER_DAY", "3") or 3))))
        except (TypeError, ValueError):
            return 3
    try:
        return max(0, min(6, int(raw)))
    except (TypeError, ValueError):
        return 3


def set_away_ping_per_day(config: Config, count: int) -> None:
    set_value(config, "away_ping_per_day", max(0, min(6, int(count))))


def away_ping_interval_min(config: Config) -> int:
    """Интервал между away-пингами (мин), из away_ping_per_day."""
    per_day = get_away_ping_per_day(config)
    if per_day <= 0:
        return 0
    return max(90, int(24 * 60 / per_day))


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


def sanitize_window_geometry(
    geometry: str,
    *,
    default: str = "1200x840",
    min_w: int = 920,
    min_h: int = 640,
) -> str:
    """Сбросить геометрию, если окно уехало за экран (отрицательный X/Y или крошечное).

    Пример бага: ``920x1053+-1029+667`` — окно на отключённом левом мониторе,
    Вью «запущена», но пользователь её не видит.
    """
    import re

    raw = (geometry or "").strip()
    if not raw:
        return default
    m = re.match(
        r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$",
        raw,
    )
    if not m:
        # «1200x840» без позиции — ок
        if re.match(r"^\d+x\d+$", raw):
            return raw
        return default
    w, h, xs, ys = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    x, y = int(xs), int(ys)
    if w < min_w // 2 or h < min_h // 2:
        return default
    # Сильно за левый/верхний край виртуального рабочего стола
    if x < -100 or y < -50:
        return f"{max(w, min_w)}x{max(h, min_h)}+80+60"
    # Слишком далеко вправо/вниз (грубый порог без WinAPI)
    if x > 6000 or y > 4000:
        return f"{max(w, min_w)}x{max(h, min_h)}+80+60"
    return raw
