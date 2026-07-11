"""Очередь задач Cursor → Viu: docs/VIU_INBOX.json на GitHub."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ...env_file import github_token
from ...updater import DEFAULT_BRANCH, DEFAULT_REPO, package_root
from .api import get_file_via_api, normalize_repo, push_file_via_api

INBOX_REL = "docs/VIU_INBOX.json"


def inbox_local_path(repo_root: Path | None = None) -> Path:
    root = repo_root or package_root()
    return (root / INBOX_REL).resolve()


def empty_inbox() -> Dict[str, Any]:
    return {
        "version": 1,
        "updated_at": "",
        "note": (
            "Cursor пишет задачи сюда. Viu забирает pending, выполняет, "
            "ставит done/blocked и пушит обратно. Дена зовём только на decision."
        ),
        "tasks": [],
    }


def fetch_inbox(
    *,
    token: str | None = None,
    repo: str | None = None,
    branch: str | None = None,
) -> Tuple[bool, Dict[str, Any] | str]:
    """Скачать VIU_INBOX.json с GitHub."""
    token = (token or github_token()).strip()
    if not token:
        return False, "Нет VIU_GITHUB_TOKEN — не могу забрать задачи с GitHub."
    repo = normalize_repo(repo or os.environ.get("VIU_GITHUB_REPO", DEFAULT_REPO))
    br = (branch or os.environ.get("VIU_HANDOFF_BRANCH", "") or DEFAULT_BRANCH).strip()
    ok, content, sha = get_file_via_api(INBOX_REL, token=token, repo=repo, branch=br)
    if not ok and content == "404" and br != DEFAULT_BRANCH:
        ok, content, sha = get_file_via_api(
            INBOX_REL, token=token, repo=repo, branch=DEFAULT_BRANCH
        )
        if ok:
            br = DEFAULT_BRANCH
    if not ok:
        if content == "404":
            return True, empty_inbox()
        return False, f"GET {INBOX_REL}@{br}: {content}"
    try:
        inbox = json.loads(content)
    except (json.JSONDecodeError, ValueError) as exc:
        return False, f"VIU_INBOX.json битый: {exc}"
    if not isinstance(inbox, dict):
        return False, "VIU_INBOX.json: ожидался объект"
    inbox.setdefault("tasks", [])
    inbox["_fetched_branch"] = br
    inbox["_fetched_sha"] = sha
    return True, inbox


def save_inbox_local(inbox: Dict[str, Any], repo_root: Path | None = None) -> Path:
    path = inbox_local_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in inbox.items() if not str(k).startswith("_")}
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def push_inbox(
    inbox: Dict[str, Any],
    *,
    message: str = "Viu: update VIU_INBOX",
    token: str | None = None,
    repo: str | None = None,
    branch: str | None = None,
) -> Tuple[bool, str]:
    inbox = dict(inbox)
    inbox["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for key in list(inbox.keys()):
        if str(key).startswith("_"):
            del inbox[key]
    content = json.dumps(inbox, ensure_ascii=False, indent=2) + "\n"
    save_inbox_local(inbox)
    token = (token or github_token()).strip()
    if not token:
        return False, f"Локально сохранила {inbox_local_path()}, push без токена невозможен."
    br = branch or os.environ.get("VIU_HANDOFF_BRANCH", "").strip() or DEFAULT_BRANCH
    return push_file_via_api(
        INBOX_REL,
        content,
        message=message,
        token=token,
        repo=repo or os.environ.get("VIU_GITHUB_REPO", DEFAULT_REPO),
        branch=br,
    )


def pending_tasks(inbox: Dict[str, Any]) -> List[Dict[str, Any]]:
    tasks = inbox.get("tasks") or []
    out = [t for t in tasks if isinstance(t, dict) and t.get("status") == "pending"]
    out.sort(key=lambda t: int(t.get("priority") or 100))
    return out


def mark_task(
    inbox: Dict[str, Any],
    task_id: str,
    *,
    status: str,
    result: str = "",
) -> bool:
    for t in inbox.get("tasks") or []:
        if isinstance(t, dict) and t.get("id") == task_id:
            t["status"] = status
            t["result"] = (result or "")[:4000]
            t["finished_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return True
    return False


def format_task_prompt(task: Dict[str, Any]) -> str:
    """Текст для agent work-режима."""
    lines = [
        f"[Cursor → Viu task `{task.get('id')}`]",
        f"Заголовок: {task.get('title') or '(без названия)'}",
        "",
        "Инструкции от Cursor:",
        str(task.get("instructions") or "").strip(),
        "",
        "Правила:",
        "- Выполни сама инструментами. Не проси Дена нажимать кнопки.",
        "- ask_user / Telegram — только если в задаче явно нужен decision, "
        "или без выбора человека дальше нельзя.",
        "- В конце: cursor_inbox_complete с id и кратким result; "
        "при важном итоге — cursor_handoff_with_logs.",
    ]
    return "\n".join(lines)


def upsert_task(inbox: Dict[str, Any], task: Dict[str, Any]) -> None:
    tasks: List[Dict[str, Any]] = list(inbox.get("tasks") or [])
    tid = task.get("id")
    for i, t in enumerate(tasks):
        if isinstance(t, dict) and t.get("id") == tid:
            tasks[i] = {**t, **task}
            inbox["tasks"] = tasks
            return
    tasks.append(task)
    inbox["tasks"] = tasks
