"""GitHub REST API — push файлов без локального git (zip-установка Viu)."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Optional, Tuple

from ...updater import DEFAULT_BRANCH, DEFAULT_REPO


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Viu-handoff/1.0",
        "Content-Type": "application/json",
    }


def _file_sha(repo: str, path: str, branch: str, token: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    req = urllib.request.Request(url, headers=_headers(token), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GET {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Сеть GitHub: {exc.reason}") from exc
    if isinstance(data, list):
        return None
    return data.get("sha")


def push_file_via_api(
    path: str,
    content: str,
    *,
    message: str,
    token: str,
    repo: str | None = None,
    branch: str | None = None,
) -> Tuple[bool, str]:
    """Создать или обновить один файл в репозитории через Contents API."""
    repo = repo or os.environ.get("VIU_GITHUB_REPO", DEFAULT_REPO)
    branch = branch or os.environ.get("VIU_UPDATE_BRANCH", DEFAULT_BRANCH)
    path = path.replace("\\", "/").lstrip("/")

    sha = _file_sha(repo, path, branch, token)
    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    body = json.dumps(payload).encode("utf-8")
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    req = urllib.request.Request(url, data=body, headers=_headers(token), method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return False, f"GitHub API {exc.code}: {detail[:500]}"
    except urllib.error.URLError as exc:
        return False, f"Сеть GitHub: {exc.reason}"

    html = (data.get("commit") or {}).get("html_url") or ""
    return True, f"Файл на GitHub ({branch}): {path}" + (f"\n{html}" if html else "")
