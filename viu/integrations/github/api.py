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


def _headers(token: str, *, auth_style: str = "bearer") -> dict:
    prefix = "Bearer" if auth_style == "bearer" else "token"
    return {
        "Authorization": f"{prefix} {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Viu-handoff/1.0",
        "Content-Type": "application/json",
    }


def _api_request(
    method: str,
    url: str,
    token: str,
    payload: dict | None = None,
    *,
    timeout: float = 60.0,
    auth_style: str = "bearer",
) -> Tuple[int, dict | str, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers=_headers(token, auth_style=auth_style), method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, parsed, hdrs
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = body
        hdrs = {k.lower(): v for k, v in exc.headers.items()}
        return exc.code, parsed, hdrs
    except urllib.error.URLError as exc:
        return 0, f"Сеть GitHub: {exc.reason}", {}


def _api_json(
    method: str,
    url: str,
    token: str,
    payload: dict | None = None,
    *,
    timeout: float = 60.0,
) -> Tuple[int, dict | str]:
    code, data, _ = _api_request(method, url, token, payload, timeout=timeout)
    if code == 401:
        code2, data2, _ = _api_request(
            method, url, token, payload, timeout=timeout, auth_style="token"
        )
        if code2 != 401:
            return code2, data2
    return code, data


def _token_suffix(token: str) -> str:
    token = (token or "").strip()
    return token[-4:] if len(token) >= 4 else "????"


def _parse_scopes(headers: dict) -> List[str]:
    raw = headers.get("x-oauth-scopes", "") or ""
    return [s.strip() for s in raw.split(",") if s.strip()]


def _scope_hints(scopes: List[str], *, repo_private: bool | None = None) -> List[str]:
    hints: List[str] = []
    if not scopes:
        if repo_private:
            hints.append(
                "Fine-grained PAT или scopes не видны — нужны Contents: Read and write "
                "на Shadowsector/Viu."
            )
        return hints
    has_write = "repo" in scopes or "public_repo" in scopes
    has_gist = "gist" in scopes
    if not has_write:
        hints.append(
            "Нет scope repo/public_repo — запись в репозиторий не получится. "
            "Public repo здесь не при чём: читать можно без прав, писать — нельзя."
        )
    if not has_gist:
        hints.append("Нет scope gist — запасной Gist не сработает (404).")
    return hints


def _explain_contents_failure(
    code: int,
    *,
    repo: str,
    branch: str,
    repo_private: bool | None,
    scopes: List[str],
) -> str:
    detail = f"GitHub API {code} (ветка {branch})"
    if code == 401:
        return f"{detail}: токен не принят. Создай новый Classic PAT."
    if code == 403:
        return f"{detail}: нет прав на запись в {repo}."
    if code == 404:
        extra = (
            "Not Found — часто это «нет прав на запись», а не «репозиторий private/public». "
            f"Репозиторий {repo!r} "
            f"({'private' if repo_private else 'public' if repo_private is False else '?'}) "
            "читается, но PUT contents требует scope repo (classic) или Contents R/W (fine-grained)."
        )
        scope_lines = _scope_hints(scopes, repo_private=repo_private)
        if scope_lines:
            extra += " " + " ".join(scope_lines)
        return f"{detail}: {extra}"
    return detail


def diagnose_github(token: str, repo: str | None = None) -> str:
    """Проверка токена и прав для handoff — без записи в репозиторий."""
    token = (token or "").strip()
    repo = normalize_repo(repo or os.environ.get("VIU_GITHUB_REPO", DEFAULT_REPO))
    lines: List[str] = []

    if not token:
        return (
            "Токен пуст. Добавь VIU_GITHUB_TOKEN=ghp_... в U:\\Viu\\.env "
            "(без кавычек) и перезапусти Viu."
        )

    suffix = _token_suffix(token)
    if token.startswith("ghp_"):
        lines.append(f"Формат: Classic PAT (…{suffix})")
    elif token.startswith("github_pat_"):
        lines.append(
            f"Формат: Fine-grained PAT (…{suffix}) — на репо нужен Contents: Read and write"
        )
    else:
        lines.append(f"Формат: необычный префикс (…{suffix}); ожидается ghp_ или github_pat_")

    code, data, hdrs = _api_request("GET", "https://api.github.com/user", token)
    if code == 401:
        code, data, hdrs = _api_request(
            "GET", "https://api.github.com/user", token, auth_style="token"
        )
    scopes = _parse_scopes(hdrs)

    if code != 200 or not isinstance(data, dict):
        lines.append(f"Авторизация: FAIL ({code}) — токен недействителен или просрочен.")
        return "\n".join(lines)

    login = data.get("login", "?")
    lines.append(f"Авторизация: OK (@{login})")
    if scopes:
        lines.append(f"Scopes: {', '.join(scopes)}")
        lines.extend(f"  → {h}" for h in _scope_hints(scopes))
    else:
        lines.append("Scopes: (не в заголовке — fine-grained PAT или SSO)")

    code, data, _ = _api_request("GET", f"https://api.github.com/repos/{repo}", token)
    repo_private: bool | None = None
    default_branch = DEFAULT_BRANCH
    if code == 200 and isinstance(data, dict):
        repo_private = bool(data.get("private"))
        default_branch = str(data.get("default_branch") or DEFAULT_BRANCH)
        vis = "private" if repo_private else "public"
        lines.append(f"Репозиторий: OK ({repo}, {vis}, default={default_branch})")
        if not repo_private:
            lines.append(
                "  Public repo — это нормально. Handoff работает; важны права записи, не visibility."
            )
    elif code == 404:
        lines.append(
            f"Репозиторий: FAIL (404) — проверь VIU_GITHUB_REPO={repo!r} и scope repo."
        )
    else:
        lines.append(f"Репозиторий: FAIL ({code})")

    br_code, br_data, _ = _api_request(
        "GET",
        f"https://api.github.com/repos/{repo}/branches?per_page=8",
        token,
    )
    if br_code == 200 and isinstance(br_data, list):
        names = [str(b.get("name", "")) for b in br_data if b.get("name")]
        if names:
            lines.append(f"Ветки (первые): {', '.join(names)}")

    handoff_branch = os.environ.get("VIU_HANDOFF_BRANCH", "").strip() or default_branch
    path = "docs/CURSOR_HANDOFF.md"
    probe_code, probe_data, _ = _api_request(
        "GET",
        f"https://api.github.com/repos/{repo}/contents/{path}?ref={handoff_branch}",
        token,
    )
    if probe_code == 200:
        lines.append(f"Файл {path}@{handoff_branch}: есть на GitHub (GET OK)")
    elif probe_code == 404:
        lines.append(
            f"Файл {path}@{handoff_branch}: ещё нет (норм — создастся при первом push)"
        )
    else:
        lines.append(f"Файл {path}: GET {probe_code}")

    if scopes:
        if "repo" in scopes or "public_repo" in scopes:
            lines.append("Запись в repo: scope repo/public_repo — OK")
        else:
            lines.append("Запись в репо: FAIL — добавь scope repo (classic PAT)")
        if "gist" in scopes:
            lines.append("Gist fallback: scope gist — OK")
        else:
            lines.append("Gist fallback: FAIL — добавь scope gist (classic PAT)")

    lines.append(
        f"Handoff-ветка: {handoff_branch!r} "
        f"(задай VIU_HANDOFF_BRANCH=cursor/viu-agent-core-65c2 при необходимости)"
    )
    return "\n".join(lines)


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
    code, data, hdrs = _api_request(
        "PUT",
        f"https://api.github.com/repos/{repo}/contents/{path}",
        token,
        payload,
        timeout=90,
    )
    if code == 401:
        code, data, hdrs = _api_request(
            "PUT",
            f"https://api.github.com/repos/{repo}/contents/{path}",
            token,
            payload,
            timeout=90,
            auth_style="token",
        )
    if code in (200, 201) and isinstance(data, dict):
        html = (data.get("commit") or {}).get("html_url") or ""
        msg = f"Файл на GitHub ({repo}@{branch}): {path}"
        if html:
            msg += f"\n{html}"
        return True, msg
    scopes = _parse_scopes(hdrs)
    repo_private: bool | None = None
    _, repo_data, _ = _api_request("GET", f"https://api.github.com/repos/{repo}", token)
    if isinstance(repo_data, dict):
        repo_private = bool(repo_data.get("private"))
    explained = _explain_contents_failure(
        code,
        repo=repo,
        branch=branch,
        repo_private=repo_private,
        scopes=scopes,
    )
    detail = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return False, f"{explained}\n{detail[:200]}"


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
    code, data, hdrs = _api_request("POST", "https://api.github.com/gists", token, payload)
    if code == 401:
        code, data, hdrs = _api_request(
            "POST", "https://api.github.com/gists", token, payload, auth_style="token"
        )
    if code == 201 and isinstance(data, dict):
        url = data.get("html_url", "")
        return True, f"Handoff в приватном Gist:\n{url}"
    scopes = _parse_scopes(hdrs)
    detail = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    if code == 404 and scopes and "gist" not in scopes:
        return False, (
            f"Gist API {code}: нет scope gist у Classic PAT. "
            f"Добавь gist при создании токена. ({detail[:120]})"
        )
    if code == 404:
        return False, (
            f"Gist API {code}: Not Found — проверь scope gist (classic PAT) "
            f"или права fine-grained. ({detail[:120]})"
        )
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
    return False, (
        f"{last_err}\nGist: {gist_msg}\n\n"
        "Подсказка: Public repo — не проблема. Classic PAT нужен с scope **repo** и **gist**. "
        "Вызови github_diagnose для проверки."
    )
