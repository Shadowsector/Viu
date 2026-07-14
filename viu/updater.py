"""Автообновление Viu: git, zip (без git), pip после обновления."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

DEFAULT_REPO = "Shadowsector/Viu"
DEFAULT_BRANCH = "cursor/viu-agent-core-65c2"
_GIT_TIMEOUT = 120.0
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def github_headers() -> dict:
    import os

    token = os.environ.get("VIU_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "Viu-updater", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _quote_ref(ref: str) -> str:
    """Ветки вида cursor/foo — percent-encode для GitHub API/URL."""
    return urllib.parse.quote(ref, safe="")


@dataclass
class UpdateResult:
    ok: bool = True
    checked: bool = False
    updated: bool = False
    has_updates: bool = False
    behind: int = 0
    local_ref: str = ""
    remote_ref: str = ""
    message: str = ""
    used_zip: bool = False


def package_root() -> Path:
    return Path(__file__).resolve().parent.parent


# Файлы и папки, которые остались от старых версий и больше не нужны.
# Убираются при запуске/обновлении, чтобы в корне не копились батники.
OBSOLETE_FILES = (
    "check_blender.bat",
    "check_unity.bat",
    "console.bat",
    "diagnose.bat",
    "get_viu.bat",
    "install_viu.bat",
    "setup_shanya.bat",
    "start_viu.bat",
    "start_viu.vbs",
    "update_viu.bat",
    "make_shortcut.bat",
    "create_shortcut.ps1",
)
OBSOLETE_DIRS = ("legacy_scripts", "setup")


def cleanup_obsolete(root: Optional[Path] = None) -> list[str]:
    """Удаляет устаревшие bat/vbs/ps1 и папки из корня Viu. Возвращает список удалённого."""
    base = root or package_root()
    removed: list[str] = []
    for name in OBSOLETE_FILES:
        p = base / name
        if p.is_file():
            try:
                p.unlink()
                removed.append(name)
            except OSError:
                pass
    for name in OBSOLETE_DIRS:
        p = base / name
        if p.is_dir():
            try:
                shutil.rmtree(p)
                removed.append(name + "/")
            except OSError:
                pass
    return removed


def find_git_root(start: Optional[Path] = None) -> Optional[Path]:
    path = (start or package_root()).resolve()
    for candidate in (path, *path.parents):
        if (candidate / ".git").is_dir():
            return candidate
    return None


def has_git_origin(root: Path) -> bool:
    code, out = _run_git(["remote", "get-url", "origin"], root)
    return code == 0 and bool(out.strip())


def usable_git_root(start: Optional[Path] = None) -> Optional[Path]:
    """Git-репозиторий с настроенным origin — иначе None (zip-установка)."""
    root = find_git_root(start)
    if root is None:
        return None
    if not has_git_origin(root):
        return None
    return root


def cleanup_broken_git(root: Optional[Path] = None) -> bool:
    """Удаляет .git без origin (случайный git init агента)."""
    g = find_git_root(root)
    if g is None or has_git_origin(g):
        return False
    try:
        shutil.rmtree(g / ".git")
        return True
    except OSError:
        return False


def _stamp_path(root: Path) -> Path:
    return root / ".viu" / "installed_version.txt"


def write_install_stamp(root: Path, branch: str, note: str = "zip", sha: str = "") -> None:
    stamp = _stamp_path(root)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    lines = [note, branch, datetime.now().isoformat(timespec="seconds")]
    if sha:
        lines.append(sha)
    stamp.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_package_sha(root: Path, sha: str) -> None:
    """Зашить SHA в поставку — версия кода, а не только метка .viu/stamp."""
    path = root / "viu" / "package_sha.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sha.strip() + "\n", encoding="utf-8")


def read_package_sha(root: Optional[Path] = None) -> str:
    """SHA из viu/package_sha.txt — что реально лежит в файлах."""
    path = (root or package_root()) / "viu" / "package_sha.txt"
    if not path.is_file():
        return ""
    line = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    return line[0].strip() if line else ""


def read_local_sha(root: Optional[Path] = None) -> str:
    stamp = _stamp_path(root or package_root())
    if not stamp.is_file():
        return ""
    lines = stamp.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) >= 4:
        return lines[3].strip()
    return ""


def running_sha(root: Optional[Path] = None) -> str:
    """Версия работающего кода: package_sha → stamp → ''."""
    base = root or package_root()
    return read_package_sha(base) or read_local_sha(base)


def stamp_changed_since(start_sha: str, root: Optional[Path] = None) -> bool:
    """На диске другая метка версии — процессу нужен relaunch (zip/bootstrap)."""
    current = running_sha(root)
    return bool(start_sha and current and start_sha != current)


def remote_sha_github(
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
) -> str:
    """SHA последнего коммита ветки через GitHub API (без git)."""
    import json

    url = f"https://api.github.com/repos/{repo}/commits/{_quote_ref(branch)}"
    req = urllib.request.Request(url, headers=github_headers())
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        data = json.loads(resp.read().decode("utf-8"))
    sha = data.get("sha") or ""
    if not sha:
        raise RuntimeError("GitHub API: нет SHA")
    return sha


def _run_git(
    args: List[str],
    cwd: Path,
    timeout: float = _GIT_TIMEOUT,
    retries: int = 1,
) -> Tuple[int, str]:
    last_out = ""
    for attempt in range(retries):
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                creationflags=_NO_WINDOW,
            )
        except FileNotFoundError:
            return 127, "git не найден. Установи Git или используй update_viu.bat (zip)."
        except subprocess.TimeoutExpired:
            last_out = "git: таймаут"
        else:
            out = ((proc.stdout or "") + (proc.stderr or "")).strip()
            if proc.returncode == 0:
                return 0, out
            last_out = out
        if attempt < retries - 1:
            time.sleep(2 * (attempt + 1))
    return 1, last_out


def current_commit(repo: Optional[Path] = None) -> str:
    root = repo or usable_git_root()
    if root is None:
        sha = running_sha(package_root())
        if sha:
            return sha[:12]
        stamp = _stamp_path(package_root())
        if stamp.is_file():
            lines = stamp.read_text(encoding="utf-8").splitlines()
            if len(lines) >= 2:
                return f"zip:{lines[1][:20]}"
        return "без git"
    code, out = _run_git(["rev-parse", "--short", "HEAD"], root)
    if code == 0 and out:
        return out
    # git сломан — всё равно показать package_sha
    sha = running_sha(package_root())
    return sha[:12] if sha else "unknown"


def install_package(root: Optional[Path] = None) -> Tuple[bool, str]:
    """pip install -e . — как Mia install_requirements."""
    cwd = root or package_root()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(cwd)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=1200,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return False, "pip: таймаут 1200s"
    except OSError as exc:
        return False, f"pip: {exc}"
    if proc.returncode == 0:
        return True, "Зависимости установлены (pip install -e .)."
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
    return False, f"pip ошибка: {tail}"


def check_for_update(
    repo: Optional[Path] = None,
    branch: str = DEFAULT_BRANCH,
    remote: str = "origin",
) -> UpdateResult:
    cleanup_broken_git()
    root = repo or usable_git_root()
    if root is None:
        try:
            remote = remote_sha_github(branch=branch)
            local = running_sha(package_root())
            if local and local == remote:
                return UpdateResult(
                    ok=True,
                    checked=True,
                    has_updates=False,
                    local_ref=local[:12],
                    remote_ref=remote[:12],
                    message=f"Уже последняя версия (GitHub) {local[:12]}.",
                )
            if local:
                msg = (
                    f"Доступно обновление ({local[:12]} → {remote[:12]}). "
                    "Нажми «Обновить Вью» или перезапусти — подтяну сама."
                )
            else:
                msg = (
                    f"Нужна установка/обновление с GitHub (remote={remote[:12]}). "
                    "Авто при запуске или кнопка «Обновить Вью»."
                )
            return UpdateResult(
                ok=True,
                checked=True,
                has_updates=True,
                local_ref=local[:12] if local else "—",
                remote_ref=remote[:12],
                message=msg,
            )
        except (OSError, RuntimeError) as exc:
            return UpdateResult(
                ok=True,
                checked=True,
                has_updates=True,
                message=f"Не удалось проверить GitHub: {exc}. Запусти get_viu.bat.",
            )

    code, out = _run_git(["fetch", remote, branch], root, retries=4)
    if code != 0:
        return UpdateResult(
            ok=False,
            checked=True,
            message=f"Не удалось проверить обновления: {out[:500]}",
        )

    _, local = _run_git(["rev-parse", "HEAD"], root)
    _, remote_ref = _run_git(["rev-parse", f"{remote}/{branch}"], root)
    if not local or not remote_ref:
        return UpdateResult(
            ok=False,
            checked=True,
            message=f"Не найдена ветка {remote}/{branch}.",
        )

    _, count_out = _run_git(["rev-list", "--count", f"HEAD..{remote}/{branch}"], root)
    behind = int(count_out) if count_out.isdigit() else 0
    short_local = local[:12]
    short_remote = remote_ref[:12]

    if behind == 0:
        return UpdateResult(
            ok=True,
            checked=True,
            has_updates=False,
            behind=0,
            local_ref=short_local,
            remote_ref=short_remote,
            message=f"Уже последняя версия ({short_local}).",
        )

    return UpdateResult(
        ok=True,
        checked=True,
        has_updates=True,
        behind=behind,
        local_ref=short_local,
        remote_ref=short_remote,
        message=f"Доступно обновление: +{behind} коммит(ов) ({short_local} → {short_remote}).",
    )


def apply_git_update(
    repo: Optional[Path] = None,
    branch: str = DEFAULT_BRANCH,
    remote: str = "origin",
    hard_reset: bool = False,
) -> UpdateResult:
    cleanup_broken_git()
    status = check_for_update(repo, branch, remote)
    root = repo or usable_git_root()
    if root is None:
        if status.has_updates:
            return download_zip_update(branch=branch)
        return status
    if not status.ok:
        return status
    if not status.has_updates:
        return UpdateResult(
            ok=True,
            updated=False,
            has_updates=False,
            behind=0,
            local_ref=status.local_ref,
            remote_ref=status.remote_ref,
            message=status.message,
        )

    if hard_reset:
        code, out = _run_git(["reset", "--hard", f"{remote}/{branch}"], root, timeout=300.0)
    else:
        code, out = _run_git(["pull", "--ff-only", remote, branch], root, timeout=300.0)

    if code == 0:
        cleanup_obsolete(root)
    new_ref = current_commit(root)
    if code != 0:
        return UpdateResult(
            ok=False,
            checked=True,
            has_updates=True,
            behind=status.behind,
            local_ref=status.local_ref,
            remote_ref=status.remote_ref,
            message=f"Обновление не удалось: {out[:500]}",
        )
    return UpdateResult(
        ok=True,
        checked=True,
        updated=True,
        has_updates=False,
        behind=0,
        local_ref=new_ref,
        remote_ref=status.remote_ref,
        message=f"Обновлено до {new_ref}.",
    )


def download_zip_update(
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    target: Optional[Path] = None,
) -> UpdateResult:
    dest = target or package_root()
    q = _quote_ref(branch)
    url = f"https://github.com/{repo}/archive/refs/heads/{q}.zip"
    try:
        req = urllib.request.Request(url, headers=github_headers())
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310
            data = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            return UpdateResult(ok=False, message=f"Не скачать zip: {exc}")
        api_url = f"https://api.github.com/repos/{repo}/zipball/{q}"
        try:
            req2 = urllib.request.Request(api_url, headers=github_headers())
            with urllib.request.urlopen(req2, timeout=180) as resp:  # noqa: S310
                data = resp.read()
        except OSError as exc2:
            return UpdateResult(
                ok=False,
                message=f"Репозиторий private? Задай VIU_GITHUB_TOKEN или сделай repo public: {exc2}",
            )
    except OSError as exc:
        return UpdateResult(ok=False, message=f"Не скачать zip: {exc}")

    preserve = {".viu", ".env"}
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "viu.zip"
        zpath.write_bytes(data)
        extract = Path(tmp) / "extract"
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(extract)
        roots = list(extract.iterdir())
        if not roots:
            return UpdateResult(ok=False, message="Пустой архив с GitHub.")
        src_root = roots[0]
        for item in src_root.iterdir():
            if item.name in preserve and (dest / item.name).exists():
                continue
            target_path = dest / item.name
            if item.is_dir():
                if target_path.exists():
                    shutil.rmtree(target_path)
                shutil.copytree(item, target_path)
            else:
                shutil.copy2(item, target_path)

    try:
        sha = remote_sha_github(repo=repo, branch=branch)
    except (OSError, RuntimeError):
        sha = ""
    write_install_stamp(dest, branch, note="zip", sha=sha)
    if sha:
        write_package_sha(dest, sha)
    cleanup_obsolete(dest)
    return UpdateResult(
        ok=True,
        checked=True,
        updated=True,
        has_updates=False,
        local_ref=sha[:12] if sha else f"zip:{branch}",
        remote_ref=sha[:12] if sha else branch,
        message=f"Скачан архив {branch} ({sha[:12] if sha else '?'}). Перезапусти Viu.",
        used_zip=True,
    )


def apply_update_smart(
    branch: str = DEFAULT_BRANCH,
    hard_reset: bool = False,
) -> UpdateResult:
    cleanup_broken_git()
    root = usable_git_root()
    if root is not None:
        return apply_git_update(root, branch=branch, hard_reset=hard_reset)
    return download_zip_update(branch=branch)


def auto_update_on_start(
    branch: str = DEFAULT_BRANCH,
    allow_zip: bool = True,
) -> UpdateResult:
    cleanup_broken_git()
    root = usable_git_root()
    if root is not None:
        result = apply_git_update(root, branch=branch)
        if result.updated:
            install_package(root)
        return result
    status = check_for_update(branch=branch)
    if not allow_zip or not status.has_updates:
        return status
    try:
        remote = remote_sha_github(branch=branch)
        local = running_sha(package_root())
        if local and local == remote:
            return status
    except (OSError, RuntimeError):
        pass
    result = download_zip_update(branch=branch)
    if result.updated:
        install_package()
    return result


def version_label() -> str:
    ref = current_commit()
    return f"Viu {ref}"


def update_viu_full(branch: str = DEFAULT_BRANCH) -> Tuple[bool, str, bool]:
    """Проверка → скачивание (если есть) → pip install. Возвращает (ok, текст, нужен_рестарт)."""
    lines: List[str] = []
    needs_restart = False

    status = check_for_update(branch=branch)
    lines.append(status.message)

    if status.has_updates:
        applied = apply_update_smart(branch=branch)
        lines.append(applied.message)
        if applied.updated:
            needs_restart = True
        if not applied.ok:
            ok, pip_msg = install_package()
            lines.append(pip_msg)
            return ok and applied.ok, "\n\n".join(lines), needs_restart

    ok, pip_msg = install_package()
    lines.append(pip_msg)
    return ok, "\n\n".join(lines), needs_restart
