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


def _version_message(
    *,
    branch: str,
    local: str,
    remote: str = "",
    behind: int = 0,
    up_to_date: bool,
) -> str:
    """Человекочитаемая строка: ветка + SHA (zip/git одинаково)."""
    short_local = (local or "—")[:12]
    short_remote = (remote or "")[:12]
    if up_to_date:
        return f"Уже последняя версия [{branch}] {short_local}."
    if behind:
        return (
            f"Доступно обновление [{branch}]: +{behind} коммит(ов) "
            f"({short_local} → {short_remote})."
        )
    if short_remote:
        return (
            f"Доступно обновление [{branch}]: {short_local} → {short_remote}. "
            "Нажми «Обновить Вью» — скачаю и перезапущу."
        )
    return (
        f"Нужна установка с GitHub [{branch}] (remote={short_remote or '?'}). "
        "Кнопка «Обновить Вью» или авто при запуске."
    )


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
    from .net_env import scrub_proxy_env

    cwd = root or package_root()
    env = scrub_proxy_env()
    attempts = [
        [sys.executable, "-m", "pip", "install", "-e", str(cwd), "--proxy="],
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            str(cwd),
            "--proxy=",
            "--no-build-isolation",
        ],
    ]
    last_tail = ""
    try:
        for cmd in attempts:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=1200,
                creationflags=_NO_WINDOW,
                env=env,
            )
            if proc.returncode == 0:
                return True, "Зависимости установлены (pip install -e .)."
            last_tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-400:]
    except subprocess.TimeoutExpired:
        return False, "pip: таймаут 1200s"
    except OSError as exc:
        return False, f"pip: {exc}"
    return False, f"pip ошибка: {last_tail}"


def _sha_mismatch_with_github(branch: str) -> Tuple[bool, str, str]:
    """package_sha на диске ≠ GitHub — даже если git fetch говорит «актуально»."""
    local = running_sha(package_root())
    try:
        remote = remote_sha_github(branch=branch)
    except (OSError, RuntimeError):
        return False, local, ""
    if not remote:
        return False, local, ""
    outdated = not local or local != remote
    return outdated, local, remote


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
                    message=_version_message(
                        branch=branch,
                        local=local,
                        remote=remote,
                        up_to_date=True,
                    ),
                )
            return UpdateResult(
                ok=True,
                checked=True,
                has_updates=True,
                local_ref=local[:12] if local else "—",
                remote_ref=remote[:12],
                message=_version_message(
                    branch=branch,
                    local=local,
                    remote=remote,
                    up_to_date=False,
                ),
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

    sha_outdated, pkg_local, pkg_remote = _sha_mismatch_with_github(branch)
    if sha_outdated and pkg_remote:
        short_pkg = (pkg_local or "—")[:12]
        short_pkg_remote = pkg_remote[:12]
        if behind == 0:
            return UpdateResult(
                ok=True,
                checked=True,
                has_updates=True,
                behind=1,
                local_ref=short_pkg or short_local,
                remote_ref=short_pkg_remote or short_remote,
                message=(
                    f"Файлы на диске ({short_pkg}) ≠ GitHub [{branch}] ({short_pkg_remote}). "
                    "Нажми «Обновить Вью» — подтяну zip или hard reset."
                ),
            )
        short_local = short_pkg or short_local
        short_remote = short_pkg_remote or short_remote

    if behind == 0:
        return UpdateResult(
            ok=True,
            checked=True,
            has_updates=False,
            behind=0,
            local_ref=short_local,
            remote_ref=short_remote,
            message=_version_message(
                branch=branch,
                local=local,
                remote=remote_ref,
                up_to_date=True,
            ),
        )

    return UpdateResult(
        ok=True,
        checked=True,
        has_updates=True,
        behind=behind,
        local_ref=short_local,
        remote_ref=short_remote,
        message=_version_message(
            branch=branch,
            local=local,
            remote=remote_ref,
            behind=behind,
            up_to_date=False,
        ),
    )


def _ensure_git_branch(root: Path, branch: str, remote: str) -> Tuple[int, str]:
    """Переключить на ветку обновления, если сейчас другая."""
    _, current = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    if current == branch:
        return 0, current
    code, out = _run_git(["checkout", "-B", branch, f"{remote}/{branch}"], root, timeout=120.0)
    if code == 0:
        return 0, out
    code2, out2 = _run_git(["checkout", branch], root, timeout=120.0)
    return code2, (out + "\n" + out2).strip()


def apply_git_update(
    repo: Optional[Path] = None,
    branch: str = DEFAULT_BRANCH,
    remote: str = "origin",
    hard_reset: bool = False,
    force: bool = False,
) -> UpdateResult:
    cleanup_broken_git()
    status = check_for_update(repo, branch, remote)
    root = repo or usable_git_root()
    if root is None:
        if status.has_updates or force or hard_reset:
            return download_zip_update(branch=branch)
        return status
    if not status.ok:
        return status
    must_sync = status.has_updates or hard_reset or force
    if not must_sync:
        return UpdateResult(
            ok=True,
            updated=False,
            has_updates=False,
            behind=0,
            local_ref=status.local_ref,
            remote_ref=status.remote_ref,
            message=status.message,
        )

    code_fetch, out_fetch = _run_git(["fetch", remote, branch], root, retries=4)
    if code_fetch != 0:
        zip_result = download_zip_update(branch=branch, target=root)
        if zip_result.ok and zip_result.updated:
            zip_result.message = f"Git fetch не удался: {out_fetch[:200]}\n\nZip: {zip_result.message}"
            return zip_result
        return UpdateResult(
            ok=False,
            checked=True,
            has_updates=True,
            message=f"Не удалось fetch {branch}: {out_fetch[:500]}",
        )

    br_code, br_out = _ensure_git_branch(root, branch, remote)
    if br_code != 0:
        zip_result = download_zip_update(branch=branch, target=root)
        if zip_result.ok and zip_result.updated:
            zip_result.message = f"Git checkout {branch}: {br_out[:200]}\n\nZip: {zip_result.message}"
            return zip_result
        return UpdateResult(
            ok=False,
            checked=True,
            has_updates=True,
            message=f"Не удалось переключить ветку {branch}: {br_out[:500]}",
        )

    def _do_pull(ff_only: bool) -> Tuple[int, str]:
        if hard_reset or force or not ff_only:
            return _run_git(["reset", "--hard", f"{remote}/{branch}"], root, timeout=300.0)
        return _run_git(["pull", "--ff-only", remote, branch], root, timeout=300.0)

    code, out = _do_pull(ff_only=not (hard_reset or force))
    used_reset = hard_reset or force
    if code != 0 and not (hard_reset or force):
        # Локальные правки / расхождение — сбрасываем код к origin ( .viu не в git ).
        code2, out2 = _do_pull(ff_only=False)
        if code2 == 0:
            code, out = code2, out2
            used_reset = True
        else:
            out = (out + "\n" + out2).strip()

    if code == 0:
        cleanup_obsolete(root)
        _, full_sha = _run_git(["rev-parse", "HEAD"], root)
        if full_sha:
            write_package_sha(root, full_sha)
    new_ref = current_commit(root)
    if code != 0:
        # Git не вытянул — zip поверх папки (как без git).
        zip_result = download_zip_update(branch=branch, target=root)
        if zip_result.ok and zip_result.updated:
            zip_result.message = (
                f"Git не смог: {out[:200]}\n\nZip: {zip_result.message}"
            )
            return zip_result
        return UpdateResult(
            ok=False,
            checked=True,
            has_updates=True,
            behind=status.behind,
            local_ref=status.local_ref,
            remote_ref=status.remote_ref,
            message=f"Обновление не удалось: {out[:500]}",
        )
    note = " (hard reset)" if used_reset or hard_reset or force else ""
    still_outdated, _, _ = _sha_mismatch_with_github(branch)
    if still_outdated:
        zip_result = download_zip_update(branch=branch, target=root)
        if zip_result.ok and zip_result.updated:
            zip_result.message = (
                f"Git обновлён до {new_ref}, но package_sha ≠ GitHub — докачал zip.\n{zip_result.message}"
            )
            return zip_result
    return UpdateResult(
        ok=True,
        checked=True,
        updated=True,
        has_updates=False,
        behind=0,
        local_ref=new_ref,
        remote_ref=status.remote_ref,
        message=f"Обновлено до {new_ref} [{branch}]{note}.",
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
        from .ollama_layout import copy_install_tree_item

        for item in src_root.iterdir():
            if item.name in preserve and (dest / item.name).exists():
                continue
            copy_install_tree_item(item, dest)

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
    force: bool = False,
) -> UpdateResult:
    cleanup_broken_git()
    root = usable_git_root()
    if root is not None:
        result = apply_git_update(root, branch=branch, hard_reset=hard_reset, force=force)
        if result.updated:
            return result
        if force or hard_reset:
            zip_result = download_zip_update(branch=branch, target=root)
            if zip_result.ok and zip_result.updated:
                return zip_result
        return result
    return download_zip_update(branch=branch)


def auto_update_on_start(
    branch: str = DEFAULT_BRANCH,
    allow_zip: bool = True,
) -> UpdateResult:
    cleanup_broken_git()
    sha_outdated, _, _ = _sha_mismatch_with_github(branch)
    root = usable_git_root()
    if root is not None:
        result = apply_git_update(root, branch=branch, hard_reset=sha_outdated)
        if result.updated:
            install_package(root)
        return result
    status = check_for_update(branch=branch)
    if not allow_zip or not status.has_updates:
        return status
    result = download_zip_update(branch=branch)
    if result.updated:
        install_package()
    return result


def version_label() -> str:
    ref = current_commit()
    return f"Viu {ref}"


def sha_needs_update(branch: str = DEFAULT_BRANCH) -> Tuple[bool, str, str]:
    """Сравнить package_sha на диске с GitHub — независимо от git fetch."""
    outdated, local, remote = _sha_mismatch_with_github(branch)
    return outdated, local, remote


def update_viu_full(branch: str = DEFAULT_BRANCH) -> Tuple[bool, str, bool]:
    """Проверка → скачивание (если есть) → pip install. Возвращает (ok, текст, нужен_рестарт)."""
    lines: List[str] = []
    needs_restart = False
    before = running_sha(package_root())[:12] or "—"

    sha_outdated, local_full, remote_full = sha_needs_update(branch=branch)
    if remote_full:
        lines.append(
            f"SHA на диске: {local_full[:12] or '—'} · GitHub [{branch}]: {remote_full[:12]}"
        )

    status = check_for_update(branch=branch)
    lines.append(status.message)

    must_apply = status.has_updates or sha_outdated
    if must_apply:
        force = sha_outdated
        applied = apply_update_smart(branch=branch, hard_reset=sha_outdated, force=force)
        lines.append(applied.message)
        if applied.updated:
            needs_restart = True
        elif force:
            zip_result = download_zip_update(branch=branch)
            lines.append(zip_result.message)
            if zip_result.updated:
                needs_restart = True
                applied = zip_result
        if not applied.ok:
            ok, pip_msg = install_package()
            lines.append(pip_msg)
            return ok and applied.ok, "\n\n".join(lines), needs_restart

    after = running_sha(package_root())[:12] or "—"
    if before != after:
        lines.append(f"Версия: {before} → {after}")
        needs_restart = True

    still_outdated, _, remote_after = sha_needs_update(branch=branch)
    if still_outdated and remote_after:
        lines.append(
            f"После обновления SHA всё ещё ≠ GitHub ({after} vs {remote_after[:12]}). "
            "Проверь сеть / VIU_GITHUB_TOKEN."
        )
        ok, pip_msg = install_package()
        lines.append(pip_msg)
        return False, "\n\n".join(lines), needs_restart

    ok, pip_msg = install_package()
    lines.append(pip_msg)
    if must_apply and ok and not needs_restart and sha_outdated:
        needs_restart = True
    return ok, "\n\n".join(lines), needs_restart
