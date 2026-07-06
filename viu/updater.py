"""Автообновление Viu из git (при запуске GUI)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


DEFAULT_REPO = "Shadowsector/Viu"
DEFAULT_BRANCH = "cursor/viu-agent-core-65c2"


@dataclass
class UpdateResult:
    checked: bool
    updated: bool
    local_ref: str
    remote_ref: str
    message: str


def package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def find_git_root(start: Optional[Path] = None) -> Optional[Path]:
    path = (start or package_root()).resolve()
    for candidate in (path, *path.parents):
        if (candidate / ".git").is_dir():
            return candidate
    return None


def _run_git(args: List[str], cwd: Path, timeout: float = 120.0) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 1, str(exc)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def current_commit(repo: Path) -> str:
    code, out = _run_git(["rev-parse", "--short", "HEAD"], repo)
    return out if code == 0 else "unknown"


def check_for_update(
    repo: Optional[Path] = None,
    branch: str = DEFAULT_BRANCH,
    remote: str = "origin",
) -> UpdateResult:
    root = repo or find_git_root()
    if root is None:
        return UpdateResult(
            checked=False,
            updated=False,
            local_ref="",
            remote_ref="",
            message="Не git-репозиторий — автообновление пропущено.",
        )

    _run_git(["fetch", remote, branch], root)
    code_local, local = _run_git(["rev-parse", "HEAD"], root)
    code_remote, remote_ref = _run_git(["rev-parse", f"{remote}/{branch}"], root)
    if code_local != 0 or code_remote != 0:
        return UpdateResult(
            checked=True,
            updated=False,
            local_ref=local or "?",
            remote_ref=remote_ref or "?",
            message=f"Не удалось сравнить коммиты ({branch}).",
        )

    if local == remote_ref:
        return UpdateResult(
            checked=True,
            updated=False,
            local_ref=local[:12],
            remote_ref=remote_ref[:12],
            message="Уже последняя версия.",
        )

    return UpdateResult(
        checked=True,
        updated=False,
        local_ref=local[:12],
        remote_ref=remote_ref[:12],
        message="Доступно обновление.",
    )


def apply_git_update(
    repo: Optional[Path] = None,
    branch: str = DEFAULT_BRANCH,
    remote: str = "origin",
) -> UpdateResult:
    status = check_for_update(repo, branch, remote)
    root = repo or find_git_root()
    if root is None:
        return status
    if not status.checked:
        return status
    if status.local_ref and status.remote_ref and status.local_ref == status.remote_ref:
        return status

    code, out = _run_git(["pull", "--ff-only", remote, branch], root, timeout=300.0)
    new_ref = current_commit(root)
    if code != 0:
        return UpdateResult(
            checked=True,
            updated=False,
            local_ref=status.local_ref,
            remote_ref=status.remote_ref,
            message=f"git pull не удался: {out[:500]}",
        )
    return UpdateResult(
        checked=True,
        updated=True,
        local_ref=new_ref,
        remote_ref=status.remote_ref,
        message=f"Обновлено до {new_ref}.",
    )


def download_zip_update(
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_BRANCH,
    target: Optional[Path] = None,
) -> UpdateResult:
    """Резервный путь: скачать zip ветки и распаковать поверх (без .git)."""
    dest = target or package_root()
    url = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310
            data = resp.read()
    except OSError as exc:
        return UpdateResult(False, False, "", "", f"Не скачать zip: {exc}")

    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "viu.zip"
        zpath.write_bytes(data)
        extract = Path(tmp) / "extract"
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(extract)
        roots = list(extract.iterdir())
        if not roots:
            return UpdateResult(True, False, "", "", "Пустой архив.")
        src_root = roots[0]
        for item in src_root.iterdir():
            target_path = dest / item.name
            if item.is_dir():
                if target_path.exists():
                    shutil.rmtree(target_path)
                shutil.copytree(item, target_path)
            else:
                shutil.copy2(item, target_path)

    return UpdateResult(
        checked=True,
        updated=True,
        local_ref="zip",
        remote_ref=branch,
        message=f"Скачан архив {branch}.",
    )


def auto_update_on_start(
    prefer_git: bool = True,
    branch: str = DEFAULT_BRANCH,
) -> UpdateResult:
    root = find_git_root()
    if prefer_git and root is not None:
        return apply_git_update(root, branch=branch)
    if root is not None:
        return check_for_update(root, branch=branch)
    return UpdateResult(
        checked=False,
        updated=False,
        local_ref="",
        remote_ref="",
        message="Клонируй Viu через git для автообновления.",
    )


def version_label() -> str:
    root = find_git_root()
    if root is None:
        return "Viu (без git)"
    return f"Viu {current_commit(root)}"
