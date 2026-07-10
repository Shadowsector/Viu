"""GitHub REST API — push файлов без локального git (zip-установка Viu)."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from typing import List, Optional, Tuple

from ...updater import DEFAULT_BRANCH, DEFAULT_REPO

_REPO_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([^/]+/[^/.]+)",
    re.IGNORECASE,
)


def normalize_repo(repo: str) -> str:
    """Shadowsector/Viu из URL или .git."""
    raw = (repo or DEFAULT_REPO).strip().rstrip("/")
    m = _REPO_URL_RE.match(raw)
    if m:
        return m.group(1)
    if raw.lower().endswith(".git"):
        raw = raw[:-4]
    if raw.lower().startswith("github.com/"):
        raw = raw[11:]
    return raw


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Viu-handoff/1.0",
        "Content-Type": "application/json",
    }


def _api_json(
    method: str,
    url: str,
    token: str,
    payload: dict | None = None,
    *,
    timeout: float = 60.0,
) -> Tuple[int, dict | str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=_headers(token), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed
    except urllib.error.URLError as exc:
        return 0, f"Сеть GitHub: {exc.reason}"


def github_token_valid(token: str) -> Tuple[bool, str]:
    code, data = _api_json("GET", "https://api.github.com/user", token)
    if code == 200 and isinstance(data, dict):
        login = data.get("login", "?")
        return True, f"GitHub: @{login}"
    if code == 401:
        return False, "Токен GitHub не принят (401). Создай новый PAT с scope repo."
    return False, f"GitHub user API {code}: {data}"


def get_repo_info(repo: str, token: str) -> Tuple[bool, dict | str]:
    repo = normalize_repo(repo)
    code, data = _api_json("GET", f"https://api.github.com/repos/{repo}", token)
    if code == 200 and isinstance(data, dict):
        return True, data
    if code == 404:
        return False, (
            f"Репозиторий {repo!r} не найден или нет доступа (private + токен без repo). "
            "Проверь VIU_GITHUB_REPO=Shadowsector/Viu и права токена."
        )
    return False, f"GitHub repo API {code}: {data}"


def branch_candidates(preferred: str | None, repo_info: dict | None) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []

    def add(b: str) -> None:
        b = (b or "").strip()
        if b and b not in seen:
            seen.add(b)
            out.append(b)

    add(preferred or "")
    add(os.environ.get("VIU_HANDOFF_BRANCH", "").strip())
    add(os.environ.get("VIU_UPDATE_BRANCH", "").strip())
    if repo_info:
        add(str(repo_info.get("default_branch", "")))
    add(DEFAULT_BRANCH)
    add("main")
    add("master")
    return out


def _file_sha(repo: str, path: str, branch: str, token: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    code, data = _api_json("GET", url, token)
    if code == 404:
        return None
    if code != 200 or not isinstance(data, dict):
        return None
    return data.get("sha")


def _push_once(
    repo: str,
    path: str,
    content: str,
    *,
    message: str,
    token: str,
    branch: str,
) -> Tuple[bool, str]:
    sha = _file_sha(repo, path, branch, token)
    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    code, data = _api_json(
        "PUT",
        f"https://api.github.com/repos/{repo}/contents/{path}",
        token,
        payload,
        timeout=90,
    )
    if code in (200, 201) and isinstance(data, dict):
        html = (data.get("commit") or {}).get("html_url") or ""
        msg = f"Файл на GitHub ({repo}@{branch}): {path}"
        if html:
            msg += f"\n{html}"
        return True, msg
    detail = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return False, f"GitHub API {code} (ветка {branch}): {detail[:400]}"


def upload_gist(
    filename: str,
    content: str,
    *,
    token: str,
    description: str = "Viu handoff",
) -> Tuple[bool, str]:
    payload = {
        "description": description,
        "public": False,
        "files": {filename: {"content": content}},
    }
    code, data = _api_json("POST", "https://api.github.com/gists", token, payload)
    if code == 201 and isinstance(data, dict):
        url = data.get("html_url", "")
        return True, f"Handoff в приватном Gist:\n{url}"
    detail = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return False, f"Gist API {code}: {detail[:400]}"


def push_file_via_api(
    path: str,
    content: str,
    *,
    message: str,
    token: str,
    repo: str | None = None,
    branch: str | None = None,
) -> Tuple[bool, str]:
    """Contents API по веткам; если не вышло — приватный Gist."""
    repo = normalize_repo(repo or os.environ.get("VIU_GITHUB_REPO", DEFAULT_REPO))
    path = path.replace("\\", "/").lstrip("/")

    ok_user, user_msg = github_token_valid(token)
    if not ok_user:
        return False, user_msg

    ok_repo, repo_data = get_repo_info(repo, token)
    if not ok_repo:
        gist_ok, gist_msg = upload_gist(
            path.replace("/", "_") or "handoff.md",
            content,
            token=token,
            description=message,
        )
        if gist_ok:
            return True, f"{repo_data}\nЗапасной канал — Gist:\n{gist_msg}"
        return False, f"{repo_data}\nGist: {gist_msg}"

    repo_info = repo_data if isinstance(repo_data, dict) else {}
    branches = branch_candidates(branch, repo_info)
    last_err = ""
    for br in branches:
        ok, msg = _push_once(repo, path, content, message=message, token=token, branch=br)
        if ok:
            return True, msg
        last_err = msg

    gist_ok, gist_msg = upload_gist(
        path.replace("/", "_") or "handoff.md",
        content,
        token=token,
        description=f"{message} (repo push failed)",
    )
    if gist_ok:
        return True, (
            f"В репозиторий не вышло ({last_err}).\n"
            f"Запасной канал — Gist:\n{gist_msg}"
        )
    return False, f"{last_err}\nGist: {gist_msg}"
