#!/usr/bin/env python3
"""Автоапдейтер Viu — только stdlib, без git.

Скачивается с GitHub при первом запуске (см. get_viu.bat / start_viu.bat).
Сравнивает SHA ветки через GitHub API → zip → pip install -e .

Использование:
  python bootstrap_update.py --auto          # проверить и обновить при необходимости
  python bootstrap_update.py --apply         # принудительно скачать
  python bootstrap_update.py --apply --launch  # обновить и открыть GUI
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

REPO = "Shadowsector/Viu"
BRANCH = os.environ.get("VIU_UPDATE_BRANCH", "cursor/viu-agent-core-65c2")
PRESERVE_DIRS = {".viu"}
PRESERVE_FILES = {".env", "viu_startup.log"}
RAW_BOOTSTRAP_URL = (
    f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/bootstrap_update.py"
)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def github_headers() -> dict:
    token = os.environ.get("VIU_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Viu-bootstrap/1.0", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def root_dir() -> Path:
    return Path(__file__).resolve().parent


def stamp_path() -> Path:
    return root_dir() / ".viu" / "installed_version.txt"


def log(msg: str) -> None:
    print(f"[Viu] {msg}", flush=True)


def _api_request(url: str) -> dict:
    req = urllib.request.Request(url, headers=github_headers())
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def remote_sha() -> str:
    """Последний коммит ветки на GitHub (без git)."""
    url = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
    data = _api_request(url)
    sha = data.get("sha") or ""
    if not sha:
        raise RuntimeError("GitHub API не вернул SHA коммита")
    return sha


def local_sha() -> str:
    path = stamp_path()
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    # формат: note, branch, datetime, sha
    if len(lines) >= 4:
        return lines[3].strip()
    return ""


def write_stamp(sha: str, note: str = "zip") -> None:
    path = stamp_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([note, BRANCH, datetime.now().isoformat(timespec="seconds"), sha]) + "\n",
        encoding="utf-8",
    )


def needs_update() -> tuple[bool, str, str]:
    remote = remote_sha()
    local = local_sha()
    if not local:
        return True, remote, "первая установка или старая версия без метки"
    if local != remote:
        return True, remote, f"новая версия ({local[:7]} → {remote[:7]})"
    return False, remote, "уже актуально"


def download_zip() -> bytes:
    # Публичный zip
    url = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
    log(f"Скачиваю {url} …")
    req = urllib.request.Request(url, headers=github_headers())
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    # Приватный репо — zipball через API
    api_url = f"https://api.github.com/repos/{REPO}/zipball/{BRANCH}"
    log(f"Пробую API zipball (нужен VIU_GITHUB_TOKEN для private) …")
    req2 = urllib.request.Request(api_url, headers=github_headers())
    with urllib.request.urlopen(req2, timeout=300) as resp:  # noqa: S310
        return resp.read()


def apply_zip(data: bytes) -> None:
    dest = root_dir()
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "viu.zip"
        zpath.write_bytes(data)
        extract = Path(tmp) / "extract"
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(extract)
        roots = list(extract.iterdir())
        if not roots:
            raise RuntimeError("Пустой zip-архив")
        src_root = roots[0]
        log(f"Распаковка в {dest} …")
        for item in src_root.iterdir():
            if item.name in PRESERVE_DIRS and (dest / item.name).exists():
                continue
            if item.name in PRESERVE_FILES and (dest / item.name).exists():
                continue
            target = dest / item.name
            if item.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)


OBSOLETE_FILES = (
    "check_blender.bat", "check_unity.bat", "console.bat", "diagnose.bat",
    "get_viu.bat", "install_viu.bat", "setup_shanya.bat", "start_viu.bat",
    "start_viu.vbs", "update_viu.bat", "make_shortcut.bat", "create_shortcut.ps1",
)
OBSOLETE_DIRS = ("legacy_scripts", "setup")


def cleanup_obsolete() -> None:
    """Убирает старые батники/папки из корня (наследие прошлых версий)."""
    base = root_dir()
    for name in OBSOLETE_FILES:
        p = base / name
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    import shutil as _sh

    for name in OBSOLETE_DIRS:
        p = base / name
        if p.is_dir():
            try:
                _sh.rmtree(p)
            except OSError:
                pass


def pip_install() -> None:
    """pip install -e . без мёртвого локального proxy; fallback без build isolation."""
    try:
        from viu.net_env import scrub_proxy_env
    except ImportError:
        def scrub_proxy_env():  # type: ignore[misc]
            out = dict(os.environ)
            for key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
                "PIP_PROXY",
            ):
                out.pop(key, None)
            out["NO_PROXY"] = "*"
            out["no_proxy"] = "*"
            return out

    env = scrub_proxy_env()
    cwd = str(root_dir())
    attempts = [
        [sys.executable, "-m", "pip", "install", "-e", cwd, "--proxy="],
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            cwd,
            "--proxy=",
            "--no-build-isolation",
        ],
    ]
    last_tail = ""
    for cmd in attempts:
        log(" ".join(cmd[3:]) + " …")
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=1200,
            creationflags=_NO_WINDOW,
            env=env,
        )
        if proc.returncode == 0:
            return
        last_tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-500:]
    raise RuntimeError(f"pip не удался: {last_tail}")


def launch_gui() -> None:
    dest = root_dir()
    pyw = Path(sys.executable)
    if pyw.name.lower() == "python.exe":
        candidate = pyw.with_name("pythonw.exe")
        if candidate.is_file():
            pyw = candidate
    vbs = dest / "start_viu.vbs"
    if vbs.is_file() and sys.platform == "win32":
        subprocess.Popen(  # noqa: S603
            ["wscript.exe", "//nologo", str(vbs)],
            cwd=str(dest),
            creationflags=_NO_WINDOW,
        )
        return
    run_gui = dest / "run_gui.pyw"
    if run_gui.is_file():
        subprocess.Popen(  # noqa: S603
            [str(pyw), str(run_gui)],
            cwd=str(dest),
            creationflags=_NO_WINDOW,
        )
        return
    subprocess.Popen(  # noqa: S603
        [str(pyw), "-m", "viu", "gui"],
        cwd=str(dest),
        creationflags=_NO_WINDOW,
    )


def run_update(force: bool = False) -> bool:
    """Возвращает True, если файлы обновлены."""
    try:
        outdated, sha, reason = needs_update()
    except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as exc:
        log(f"Не удалось проверить обновления: {exc}")
        return False

    if not force and not outdated:
        log(reason)
        return False

    log(f"Обновление: {reason}")
    try:
        data = download_zip()
        apply_zip(data)
        pip_install()
        write_stamp(sha)
    except (OSError, zipfile.BadZipFile, RuntimeError, subprocess.TimeoutExpired) as exc:
        log(f"ОШИБКА обновления: {exc}")
        return False

    log(f"Готово! Версия {sha[:7]}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Автоапдейтер Viu (без git)")
    parser.add_argument("--auto", action="store_true", help="обновить, если на GitHub новее")
    parser.add_argument("--apply", action="store_true", help="принудительно скачать zip")
    parser.add_argument("--check", action="store_true", help="только проверить")
    parser.add_argument("--launch", action="store_true", help="открыть GUI после обновления")
    args = parser.parse_args(argv)

    try:
        from viu.net_env import apply_proxy_scrub_to_process, proxy_hint

        removed = apply_proxy_scrub_to_process()
        hint = proxy_hint(removed)
        if hint:
            log(hint)
    except Exception:  # noqa: BLE001
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            os.environ.pop(key, None)

    if args.check:
        try:
            outdated, sha, reason = needs_update()
            log(f"{reason} (remote {sha[:7]})")
            return 0 if not outdated else 2
        except Exception as exc:  # noqa: BLE001
            log(str(exc))
            return 1

    force = args.apply
    auto = args.auto or (not force and not args.check)

    updated = False
    if force:
        updated = run_update(force=True)
    elif auto:
        updated = run_update(force=False)

    # Всегда прибираем старые файлы, даже если обновления не было.
    try:
        cleanup_obsolete()
    except Exception:  # noqa: BLE001
        pass

    if args.launch:
        log("Запуск GUI …")
        launch_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
