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
import urllib.parse
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


def _quote_branch(branch: str) -> str:
    return urllib.parse.quote(branch, safe="")


def refresh_bootstrap_script() -> bool:
    """Подтянуть свежий bootstrap_update.py с GitHub (без git)."""
    try:
        req = urllib.request.Request(RAW_BOOTSTRAP_URL, headers=github_headers())
        with urllib.request.urlopen(req, timeout=45) as resp:  # noqa: S310
            data = resp.read()
        if len(data) < 200 or b"bootstrap" not in data.lower():
            return False
        dest = root_dir() / "bootstrap_update.py"
        dest.write_bytes(data)
        return True
    except (OSError, urllib.error.URLError):
        return False


def write_package_sha(sha: str) -> None:
    path = root_dir() / "viu" / "package_sha.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sha.strip() + "\n", encoding="utf-8")


def remote_sha() -> str:
    """Последний коммит ветки на GitHub (без git)."""
    url = f"https://api.github.com/repos/{REPO}/commits/{_quote_branch(BRANCH)}"
    data = _api_request(url)
    sha = data.get("sha") or ""
    if not sha:
        raise RuntimeError("GitHub API не вернул SHA коммита")
    return sha


def read_package_sha() -> str:
    path = root_dir() / "viu" / "package_sha.txt"
    if not path.is_file():
        return ""
    line = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    return line[0].strip() if line else ""


def local_sha() -> str:
    pkg = read_package_sha()
    if pkg:
        return pkg
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
    q = _quote_branch(BRANCH)
    url = f"https://github.com/{REPO}/archive/refs/heads/{q}.zip"
    log(f"Скачиваю {url} …")
    req = urllib.request.Request(url, headers=github_headers())
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    api_url = f"https://api.github.com/repos/{REPO}/zipball/{q}"
    log("Пробую API zipball (нужен VIU_GITHUB_TOKEN для private) …")
    req2 = urllib.request.Request(api_url, headers=github_headers())
    with urllib.request.urlopen(req2, timeout=300) as resp:  # noqa: S310
        return resp.read()


def _copy_install_tree_item_from_zip(src_root: Path):
    """Взять merge-логику из zip (новее кода на диске), иначе с диска."""
    import importlib.util

    candidate = src_root / "install_merge.py"
    if candidate.is_file():
        spec = importlib.util.spec_from_file_location("_viu_install_merge", candidate)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.copy_install_tree_item
    try:
        from install_merge import copy_install_tree_item

        return copy_install_tree_item
    except ImportError:
        pass
    try:
        from viu.ollama_layout import copy_install_tree_item

        return copy_install_tree_item
    except ImportError:
        pass
    return _fallback_copy_install_tree_item


def _fallback_copy_install_tree_item(item: Path, dest_root: Path) -> None:
    """Без viu/install_merge — Inbox и ollama только merge, никогда rmtree."""
    if item.is_dir() and item.name == "viu":
        try:
            from install_merge import preserve_reflect_mode

            preserve_reflect_mode(dest_root)
        except Exception:
            pass
    target = dest_root / item.name
    if item.is_dir() and item.name == "Inbox":
        _merge_inbox_fallback(item, target)
        return
    if item.is_dir() and item.name == "ollama":
        _merge_ollama_fallback(item, target)
        return
    if item.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(item, target)
    else:
        shutil.copy2(item, target)


def _merge_inbox_fallback(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        t = dest / child.name
        if child.is_dir():
            _merge_inbox_fallback(child, t)
        elif child.is_file():
            if t.exists() and child.name.lower() != "readme.txt":
                continue
            shutil.copy2(child, t)


def _merge_ollama_fallback(src: Path, dest: Path) -> None:
    local = {
        "Modelfile.viu-cydonia",
        "Modelfile.viu-magnum",
        "Modelfile.viu-command-r",
        "Modelfile.viu-qwen32",
        "Modelfile.viu-euryale",
        "Modelfile.viu-nevoria",
        "_SYSTEM_SNIPPET.txt",
    }
    dest.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        t = dest / child.name
        if child.is_file():
            if child.name in local and t.is_file():
                continue
            shutil.copy2(child, t)
        elif child.is_dir():
            if t.exists():
                shutil.rmtree(t)
            shutil.copytree(child, t)


def apply_zip(data: bytes) -> None:
    dest = root_dir()
    try:
        from install_merge import preserve_reflect_mode

        msg = preserve_reflect_mode(dest)
        if msg:
            log(msg)
    except Exception:
        # Старый install_merge без preserve — не мешаем апдейту.
        pass
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
        copy_item = _copy_install_tree_item_from_zip(src_root)
        for item in src_root.iterdir():
            if item.name in PRESERVE_DIRS and (dest / item.name).exists():
                continue
            if item.name in PRESERVE_FILES and (dest / item.name).exists():
                continue
            copy_item(item, dest)


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
    """pip install -e . — делегируем viu.updater после распаковки."""
    try:
        from viu.updater import install_package

        ok, msg = install_package(root_dir())
        if ok:
            return
        raise RuntimeError(msg)
    except ImportError:
        pass

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

    def _run(cmd: list[str]) -> tuple[int, str]:
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
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-500:]
        return proc.returncode, tail

    code, last_tail = _run([sys.executable, "-m", "pip", "install", "-e", cwd, "--proxy="])
    if code == 0:
        return
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "setuptools>=61",
            "wheel",
            "--proxy=",
        ]
    )
    code, last_tail = _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            cwd,
            "--proxy=",
            "--no-build-isolation",
        ]
    )
    if code == 0:
        return
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
        write_package_sha(sha)
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

    if refresh_bootstrap_script():
        log("bootstrap_update.py — свежая копия с GitHub")

    force = args.apply
    auto = args.auto or (not force and not args.check)

    updated = False
    if force:
        if not run_update(force=True):
            return 1
    elif auto:
        try:
            outdated, _sha, reason = needs_update()
        except Exception as exc:  # noqa: BLE001
            log(str(exc))
            return 1
        if not outdated:
            log(reason)
        else:
            updated = run_update(force=False)
            if not updated:
                return 2

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
