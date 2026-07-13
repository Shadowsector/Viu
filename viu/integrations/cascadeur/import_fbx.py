"""Импорт FBX в Cascadeur: deploy Python-команды + pending JSON."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from ...config import Config
from ...integrations.cascadeur.paths import cascadeur_inbox
from .exe import resolve_cascadeur_exe

COMMAND_FILENAME = "viu_lab_import.py"
PENDING_FILENAME = "viu_lab_pending.json"

IMPORT_COMMAND_SOURCE = '''"""Viu Lab — импорт FBX из viu_lab_pending.json (Commands → Viu.Lab Import)."""
import json
import os

import csc


def command_name():
    return "Viu.Lab Import"


def run(scene):
    pending = os.path.join(os.path.dirname(__file__), "viu_lab_pending.json")
    if not os.path.isfile(pending):
        scene.error("Нет viu_lab_pending.json — сначала шаг Import FBX в lab Вью.")
        return
    with open(pending, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    fbx = (data.get("fbx") or "").strip()
    if not fbx:
        scene.error("В pending нет пути fbx.")
        return
    fbx_norm = fbx.replace("\\\\", "/")
    if not os.path.isfile(fbx_norm):
        scene.error(f"FBX не найден: {fbx}")
        return
    app = csc.app.get_application()
    scene_manager = app.get_scene_manager()
    tools_manager = app.get_tools_manager()
    current_scene = scene_manager.current_scene()
    loader_tool = tools_manager.get_tool("FbxSceneLoader")
    fbx_loader = loader_tool.get_fbx_loader(current_scene)
    fbx_loader.import_fbx_scene(current_scene, fbx_norm)
    scene.info(f"Imported: {os.path.basename(fbx_norm)}")
'''


def cascadeur_scripts_dir(config: Config) -> Path:
    """Папка user-команд Cascadeur (Commands menu)."""
    env = os.environ.get("VIU_CASCADEUR_SCRIPTS", "").strip()
    if env:
        p = Path(env).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p

    try:
        exe = resolve_cascadeur_exe(config)
        for rel in (
            ("scripts", "python", "user"),
            ("..", "scripts", "python", "user"),
            ("resources", "scripts", "python", "user"),
        ):
            candidate = (exe.parent / Path(*rel)).resolve()
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
    except FileNotFoundError:
        pass

    docs = Path.home() / "Documents" / "Cascadeur" / "scripts" / "python" / "user"
    docs.mkdir(parents=True, exist_ok=True)
    return docs


def pending_import_path(config: Config, topic: str = "cascadeur") -> Path:
    return config.data_dir / "lab" / topic / "pending_import.json"


def latest_inbox_fbx(config: Config) -> Optional[Path]:
    inbox = cascadeur_inbox(config)
    fbx_files = sorted(inbox.glob("*.fbx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return fbx_files[0] if fbx_files else None


def deploy_import_command(config: Config) -> Tuple[bool, str, Path]:
    """Положить viu_lab_import.py в папку команд Cascadeur."""
    scripts = cascadeur_scripts_dir(config)
    target = scripts / COMMAND_FILENAME
    try:
        target.write_text(IMPORT_COMMAND_SOURCE, encoding="utf-8")
    except OSError as exc:
        return False, f"Не удалось записать {target}: {exc}", target
    return True, f"Команда: {target}", target


def write_pending_import(config: Config, fbx_path: Path, *, topic: str = "cascadeur") -> Tuple[bool, str]:
    payload = {"fbx": str(fbx_path.resolve())}
    lab_pending = pending_import_path(config, topic)
    lab_pending.parent.mkdir(parents=True, exist_ok=True)
    scripts_pending = cascadeur_scripts_dir(config) / PENDING_FILENAME
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        lab_pending.write_text(text, encoding="utf-8")
        scripts_pending.write_text(text, encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    return True, f"pending: {lab_pending.name} + {scripts_pending.name}"


def _try_open_fbx(fbx_path: Path, config: Config | None = None) -> Tuple[bool, str]:
    if sys.platform != "win32":
        return False, "startfile только Windows"
    try:
        os.startfile(str(fbx_path))  # noqa: S606
        time.sleep(2.0)
        return True, f"os.startfile({fbx_path.name})"
    except OSError as exc:
        if config is None:
            return False, str(exc)
        return _try_open_fbx_via_cascadeur(config, fbx_path, prior_error=str(exc))


def _try_open_fbx_via_cascadeur(config: Config, fbx_path: Path, *, prior_error: str = "") -> Tuple[bool, str]:
    """Открыть FBX через cascadeur.exe (если .fbx не ассоциирован с приложением)."""
    if sys.platform != "win32":
        return False, prior_error or "не Windows"
    try:
        exe = resolve_cascadeur_exe(config)
    except FileNotFoundError as exc:
        return False, prior_error or str(exc)

    import ctypes

    rc = ctypes.windll.shell32.ShellExecuteW(
        None,
        "open",
        str(exe),
        str(fbx_path),
        None,
        1,
    )
    if rc <= 32:
        hint = prior_error or f"ShellExecute код {rc}"
        return False, f"{hint}; FBX не ассоциирован с Cascadeur — Commands → Viu.Lab Import"

    time.sleep(3.0)
    note = f" (ранее: {prior_error})" if prior_error else ""
    return True, f"ShellExecute({exe.name}, {fbx_path.name}){note}"


def trigger_fbx_import(
    config: Config,
    fbx_path: Optional[Path] = None,
    *,
    topic: str = "cascadeur",
) -> Tuple[bool, str, bool]:
    """Deploy команды, записать pending, попробовать открыть FBX. Третье значение — opened автоматически."""
    fbx = fbx_path or latest_inbox_fbx(config)
    if fbx is None or not fbx.is_file():
        return False, "Нет FBX в Cascadeur Inbox — сначала шаг Inbox.", False

    ok_deploy, deploy_msg, _script = deploy_import_command(config)
    if not ok_deploy:
        return False, deploy_msg, False

    ok_pending, pending_msg = write_pending_import(config, fbx, topic=topic)
    if not ok_pending:
        return False, pending_msg, False

    opened_ok, open_msg = _try_open_fbx(fbx, config)
    lines = [deploy_msg, pending_msg]
    if opened_ok:
        lines.append(open_msg)
        lines.append(
            "Если открылся диалог Import — подтверди вручную. "
            "Или Commands → Reload scripts → **Viu.Lab Import**."
        )
        return True, "\n".join(lines), True

    lines.append(
        f"Авто-открытие FBX: {open_msg}\n"
        "В Cascadeur: **Commands → Reload scripts → Viu.Lab Import** "
        "(или File → Import → Fbx/Dae, Mode=Scene)."
    )
    return True, "\n".join(lines), False
