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

from .anabarra_layout import unity_project_path
from .config import Config
from .env_file import env_hint_for_token, github_token
from .integrations.unity.overlay import OVERLAY_BUILD_DIR
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


def _tail_text(path: Path, max_lines: int = 120) -> str:
    if not path.is_file():
        return f"(нет файла: {path})\n"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"(не прочитать {path}: {exc})\n"
    if len(lines) <= max_lines:
        body = "\n".join(lines)
    else:
        body = "\n".join(lines[-max_lines:])
    return f"=== {path.name} (last {max_lines} lines) ===\n{body}\n\n"


def _player_log_candidates(config: Config) -> List[Path]:
    """Player.log Unity build — LocalLow/<Company>/<Product>."""
    roots: List[Path] = []
    if os.name == "nt":
        local_low = Path(os.environ.get("LOCALAPPDATA", "")) / ".." / "LocalLow"
        try:
            local_low = local_low.resolve()
        except OSError:
            local_low = Path.home() / "AppData" / "LocalLow"
        if local_low.is_dir():
            for company in local_low.iterdir():
                if not company.is_dir():
                    continue
                for product in company.iterdir():
                    if product.is_dir() and "anabarra" in product.name.lower():
                        p = product / "Player.log"
                        if p.is_file():
                            roots.append(p)
    try:
        proj = unity_project_path(config)
        roots.append(proj / OVERLAY_BUILD_DIR / "Player.log")
    except Exception:
        pass
    return roots


def _overlay_diagnostics_text(config: Config) -> str:
    parts: List[str] = ["=== Overlay diagnostics ===\n"]
    try:
        proj = unity_project_path(config)
    except Exception as exc:
        return parts[0] + f"Unity project: {exc}\n"

    overlay_dir = proj / OVERLAY_BUILD_DIR
    parts.append(f"Overlay dir: {overlay_dir}\n")
    for name in (
        "overlay_boot.log",
        "LaunchOverlay.bat",
        "AnabarraOverlay.exe",
    ):
        p = overlay_dir / name
        parts.append(f"  {name}: {'OK' if p.is_file() else 'нет'}\n")

    for log_name in (
        "viu_overlay_build.log",
        "viu_overlay_scene.log",
        "viu_setup.log",
        "viu_animator.log",
    ):
        parts.append(_tail_text(proj / log_name, max_lines=80))

    for pl in _player_log_candidates(config):
        parts.append(_tail_text(pl, max_lines=80))

    parts.append(_tail_text(overlay_dir / "overlay_boot.log", max_lines=80))

    # Unity Editor.log — Console / Animator / Rig (раньше не попадало в bundle)
    try:
        from .integrations.unity.log_parser import default_editor_log, parse_editor_log

        editor_log = default_editor_log()
        parts.append(_tail_text(editor_log, max_lines=200))
        if editor_log.is_file():
            summary = parse_editor_log(editor_log)
            parts.append("=== Editor.log summary ===\n")
            parts.append(summary.render())
            parts.append("\n")
    except Exception as exc:  # noqa: BLE001
        parts.append(f"(Editor.log: {exc})\n")

    return "".join(parts)


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

    # Unity project diagnostics
    try:
        proj = unity_project_path(config)
        for name in (
            "viu_animator.log",
            "viu_setup.log",
            "viu_overlay_scene.log",
            "viu_overlay_build.log",
        ):
            p = proj / name
            if p.is_file():
                files.append(p)
    except Exception:
        pass

    try:
        from .integrations.unity.log_parser import default_editor_log

        editor = default_editor_log()
        if editor.is_file():
            files.append(editor)
    except Exception:
        pass

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
        zf.writestr("overlay_diagnostics.txt", _overlay_diagnostics_text(config))
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
    token = token or github_token()
    if not token:
        return False, (
            "Нет токена GitHub. "
            + env_hint_for_token()
            + f" Пока прикрепи файл: {bundle}"
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
