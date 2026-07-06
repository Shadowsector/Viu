"""Сбор логов Вью в один файл — чтобы отдать разработчику (в Cursor или на GitHub).

collect_support_bundle() складывает в один .zip:
  - последние чаты из logs/,
  - viu_startup.log (ошибки запуска),
  - runtime.json, память, план,
  - system_info.txt (Python, ОС, версия Вью, конфиг).

Если задан VIU_GITHUB_TOKEN — bundle можно выгрузить в приватный Gist,
и разработчик (или облачный агент Cursor) прочитает его по ссылке.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .config import Config
from .updater import version_label


def _system_info(config: Config) -> str:
    lines = [
        "=== Viu support bundle ===",
        f"Время: {datetime.now().isoformat(timespec='seconds')}",
        f"Версия: {version_label()}",
        f"Python: {sys.version.split()[0]} ({sys.executable})",
        f"ОС: {platform.platform()}",
        "",
        "--- Конфигурация ---",
        config.summary(),
    ]
    return "\n".join(lines)


def _iter_log_files(config: Config, max_chats: int = 5) -> List[Path]:
    files: List[Path] = []
    logs_dir = config.data_dir / "logs"
    if logs_dir.is_dir():
        chats = sorted(
            logs_dir.glob("chat_*.txt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        files.extend(chats[:max_chats])
    for extra in ("memory.json", "plan.json", "runtime.json"):
        p = config.data_dir / extra
        if p.is_file():
            files.append(p)
    root = Path(__file__).resolve().parent.parent
    startup = root / "viu_startup.log"
    if startup.is_file():
        files.append(startup)
    return files


def collect_support_bundle(config: Config) -> Path:
    """Собирает logs+инфо в один .zip и возвращает путь к нему."""
    config.ensure_dirs()
    out_dir = config.data_dir / "support"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle = out_dir / f"viu_logs_{stamp}.zip"

    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("system_info.txt", _system_info(config))
        for f in _iter_log_files(config):
            try:
                zf.write(f, arcname=f.name)
            except OSError:
                continue
    return bundle


def upload_bundle_to_gist(
    bundle: Path,
    description: str = "Viu logs",
    token: Optional[str] = None,
) -> Tuple[bool, str]:
    """Выгружает текст логов в приватный GitHub Gist (нужен VIU_GITHUB_TOKEN)."""
    token = token or os.environ.get("VIU_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return False, (
            "Нет токена GitHub. Задай VIU_GITHUB_TOKEN, чтобы Вью сама отправляла логи. "
            f"Пока просто прикрепи файл: {bundle}"
        )

    # Читаем содержимое zip как отдельные текстовые файлы для gist.
    files_payload = {}
    try:
        with zipfile.ZipFile(bundle) as zf:
            for name in zf.namelist():
                data = zf.read(name)
                try:
                    text = data.decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    continue
                files_payload[name] = {"content": text or "(пусто)"}
    except (OSError, zipfile.BadZipFile) as exc:
        return False, f"Не прочитать bundle: {exc}"

    if not files_payload:
        return False, "В bundle нет текстовых файлов для отправки."

    payload = json.dumps(
        {"description": description, "public": False, "files": files_payload}
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/gists",
        data=payload,
        headers={
            "User-Agent": "Viu-support",
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
    except OSError as exc:
        return False, f"Gist не создан: {exc}"
    url = data.get("html_url", "")
    return True, f"Логи отправлены: {url}"
