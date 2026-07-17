"""Handoff Вью → Cursor: docs/CURSOR_HANDOFF.md в репозитории Viu."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Tuple

from ...env_file import env_hint_for_token, github_token
from ...updater import DEFAULT_BRANCH, DEFAULT_REPO, package_root
from .api import push_file_via_api

HANDOFF_REL = Path("docs/CURSOR_HANDOFF.md")

_HEADER = """# Viu → Cursor

Сюда **Вью** (и иногда Ден) складывает мысли, задачи и логи для облачного агента **Cursor**.
Cloud Agent читает этот файл в репозитории и может продолжить работу над «Анабарра».

Не удаляй историю — новые блоки добавляются сверху вниз с меткой времени.
"""


def install_root() -> Path:
    """Корень установки Viu (U:\\Viu) — parent каталога пакета viu/."""
    return package_root()


def handoff_path(repo_root: Path | None = None) -> Path:
    root = repo_root or install_root()
    return (root / HANDOFF_REL).resolve()


def is_git_repo(root: Path) -> bool:
    return (root / ".git").is_dir()


def append_handoff(
    title: str,
    body: str,
    *,
    author: str = "Viu",
    repo_root: Path | None = None,
) -> Path:
    """Добавляет блок в CURSOR_HANDOFF.md."""
    path = handoff_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(_HEADER, encoding="utf-8")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = (
        f"\n\n---\n\n"
        f"## {stamp} — {title.strip()} ({author})\n\n"
        f"{body.strip()}\n"
    )
    path.write_text(path.read_text(encoding="utf-8") + block, encoding="utf-8")
    return path


def _run_git(args: list[str], cwd: Path, *, timeout: float = 90.0) -> Tuple[int, str]:
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=no_window,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, str(exc)
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out


def _current_branch(repo_root: Path) -> str:
    if is_git_repo(repo_root):
        code, out = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
        if code == 0 and out.strip():
            return out.strip()
    return os.environ.get("VIU_UPDATE_BRANCH", DEFAULT_BRANCH)


def _push_handoff_git(
    root: Path,
    path: Path,
    *,
    message: str,
    token: str,
    branch: str,
    repo: str,
) -> Tuple[bool, str]:
    rel = HANDOFF_REL.as_posix()
    code, out = _run_git(["add", rel], root)
    if code != 0:
        return False, f"git add: {out or 'ошибка'}"

    code, out = _run_git(["commit", "-m", message], root)
    if code != 0 and "nothing to commit" not in out.lower():
        return False, f"git commit: {out or 'ошибка'}"

    push_url = f"https://x-access-token:{token}@github.com/{repo}.git"
    code, out = _run_git(["push", push_url, f"HEAD:{branch}"], root, timeout=120.0)
    if code != 0:
        return False, f"git push: {out or 'ошибка'}"
    return True, f"Handoff на GitHub ({branch}): {rel}"


def push_handoff(
    *,
    message: str = "Viu: handoff для Cursor",
    repo_root: Path | None = None,
    branch: str | None = None,
    token: str | None = None,
) -> Tuple[bool, str]:
    """Отправить docs/CURSOR_HANDOFF.md на GitHub (API — без локального git)."""
    root = repo_root or install_root()
    path = handoff_path(root)
    if not path.is_file():
        return False, "Нет docs/CURSOR_HANDOFF.md — сначала cursor_handoff."

    token = (token or github_token()).strip()
    if not token:
        return False, (
            f"Handoff записан локально: {path}\n"
            f"Push не вышел — токен пуст. {env_hint_for_token()}"
        )

    br = branch or _current_branch(root)
    repo = os.environ.get("VIU_GITHUB_REPO", DEFAULT_REPO)
    content = path.read_text(encoding="utf-8")

    # Zip-установка (типично у Дена) — без .git; GitHub Contents API.
    if not is_git_repo(root):
        return push_file_via_api(
            HANDOFF_REL.as_posix(),
            content,
            message=message,
            token=token,
            repo=repo,
            branch=br,
        )

    ok, msg = _push_handoff_git(root, path, message=message, token=token, branch=br, repo=repo)
    if ok:
        return ok, msg
    # Fallback если git сломан
    api_ok, api_msg = push_file_via_api(
        HANDOFF_REL.as_posix(),
        content,
        message=message,
        token=token,
        repo=repo,
        branch=br,
    )
    if api_ok:
        return True, f"{api_msg}\n(git локально не сработал: {msg})"
    return False, f"{msg}\nAPI: {api_msg}"
