"""Автообновление Viu: git, zip (без git), pip после обновления."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
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


def find_git_root(start: Optional[Path] = None) -> Optional[Path]:
    path = (start or package_root()).resolve()
    for candidate in (path, *path.parents):
        if (candidate / ".git").is_dir():
            return candidate
    return None


def _stamp_path(root: Path) -> Path:
    return root / ".viu" / "installed_version.txt"


def write_install_stamp(root: Path, branch: str, note: str = "zip", sha: str = "") -> None:
    stamp = _stamp_path(root)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    lines = [note, branch, datetime.now().isoformat(timespec="seconds")]
    if sha:
        lines.append(sha)
    stamp.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_local_sha(root: Optional[Path] = None) -> str:
    stamp = _stamp_path(root or package_root())
    if not stamp.is_file():
        return ""
    lines = stamp.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) >= 4:
        return lines[3].strip()
    return ""


def remote_sha_github(
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
) -> str:
    """SHA последнего коммита ветки через GitHub API (без git)."""
    import json
    import urllib.request

    url = f"https://api.github.com/repos/{repo}/commits/{branch}"
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
    root = repo or find_git_root()
    if root is None:
        sha = read_local_sha(package_root())
        if sha:
            return sha[:12]
        stamp = _stamp_path(package_root())
        if stamp.is_file():
            lines = stamp.read_text(encoding="utf-8").splitlines()
            if len(lines) >= 2:
                return f"zip:{lines[1][:20]}"
        return "без git"
    code, out = _run_git(["rev-parse", "--short", "HEAD"], root)
    return out if code == 0 else "unknown"


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
    root = repo or find_git_root()
    if root is None:
        try:
            remote = remote_sha_github(branch=branch)
            local = read_local_sha(package_root())
            if local and local == remote:
                return UpdateResult(
                    ok=True,
                    checked=True,
                    has_updates=False,
                    local_ref=local[:12],
                    remote_ref=remote[:12],
                    message="Уже последняя версия (GitHub).",
                )
            msg = "Доступно обновление с GitHub."
            if local:
                msg = f"Доступно обновление ({local[:7]} → {remote[:7]})."
            else:
                msg = "Нужна установка/обновление с GitHub (авто при запуске или get_viu.bat)."
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
            message="Уже последняя версия.",
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
    status = check_for_update(repo, branch, remote)
    root = repo or find_git_root()
    if root is None:
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
    url = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"
    try:
        req = urllib.request.Request(url, headers=github_headers())
        with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310
            data = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            return UpdateResult(ok=False, message=f"Не скачать zip: {exc}")
        api_url = f"https://api.github.com/repos/{repo}/zipball/{branch}"
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
    return UpdateResult(
        ok=True,
        checked=True,
        updated=True,
        has_updates=False,
        local_ref=f"zip:{branch}",
        remote_ref=branch,
        message=f"Скачан архив {branch}. Перезапусти Viu.",
        used_zip=True,
    )


def apply_update_smart(
    branch: str = DEFAULT_BRANCH,
    hard_reset: bool = False,
) -> UpdateResult:
    root = find_git_root()
    if root is not None:
        return apply_git_update(root, branch=branch, hard_reset=hard_reset)
    return download_zip_update(branch=branch)


def auto_update_on_start(
    branch: str = DEFAULT_BRANCH,
    allow_zip: bool = True,
) -> UpdateResult:
    root = find_git_root()
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
        local = read_local_sha(package_root())
        if local == remote:
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
