"""Импорт FBX в Cascadeur: deploy Python-команды + pending JSON."""

from __future__ import annotations

import configparser
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from ...config import Config
from ...integrations.cascadeur.paths import cascadeur_inbox
from .exe import resolve_cascadeur_exe

COMMAND_FILENAME = "viu_lab_import.py"
CONSOLE_FILENAME = "viu_lab_import_console.py"
PENDING_FILENAME = "viu_lab_pending.json"

# Официальный путь: [Install]\resources\scripts\python\commands\
# (см. cascadeur.com/help/installation/file_structure)
IMPORT_COMMAND_SOURCE = '''"""Viu Lab — импорт FBX из viu_lab_pending.json (Commands → Viu.Lab Import).

Preset «Scene» / import_scene — персонаж из Blender (скелет + mesh) в пустую сцену.
"""
import json
import os

import csc


def command_name():
    return "Viu.LabImport"


def _ensure_scene(app):
    sm = app.get_scene_manager()
    current = sm.current_scene()
    if current is not None:
        return current
    try:
        app.get_action_manager().call_action("Application.New scene")
    except Exception:
        pass
    current = sm.current_scene()
    if current is not None:
        return current
    try:
        return sm.create_application_scene()
    except Exception:
        return None


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
    current = _ensure_scene(app)
    if current is None:
        scene.error("Нет активной сцены — на welcome: New scene, потом снова Viu.Lab Import.")
        return

    tools = app.get_tools_manager()
    loader_tool = tools.get_tool("FbxSceneLoader")
    fbx_loader = loader_tool.get_fbx_loader(current)
    # FbxLoader.import_scene ≈ UI preset «Scene» (скелет + mesh из Blender FBX).
    fbx_loader.import_scene(fbx_norm)
    scene.info(f"Imported (Scene): {os.path.basename(fbx_norm)}")
'''

CONSOLE_IMPORT_TEMPLATE = '''"""Viu Lab — импорт FBX через Python Console (Window → Python console → Load → Execute)."""
import csc

FBX_PATH = r"{fbx_path}"


def _ensure_scene(app):
    sm = app.get_scene_manager()
    current = sm.current_scene()
    if current is not None:
        return current
    try:
        app.get_action_manager().call_action("Application.New scene")
    except Exception:
        pass
    current = sm.current_scene()
    if current is not None:
        return current
    return sm.create_application_scene()


app = csc.app.get_application()
scene_tab = _ensure_scene(app)
if scene_tab is None:
    raise RuntimeError("No scene tab — create New scene first")
path = FBX_PATH.replace("\\\\", "/")
loader = app.get_tools_manager().get_tool("FbxSceneLoader").get_fbx_loader(scene_tab)
loader.import_scene(path)
print("Viu lab import OK:", path)
'''


def _settings_scripts_dir(config: Config) -> Optional[Path]:
    """ScriptsDir из settings.ini (AppData или рядом с exe)."""
    candidates: List[Path] = []
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        candidates.append(Path(local) / "Nekki Limited" / "Cascadeur" / "settings.ini")
    try:
        exe = resolve_cascadeur_exe(config)
        candidates.append(exe.parent / "settings.ini")
        candidates.append(exe.parent / "Settings.ini")
    except FileNotFoundError:
        pass

    for ini in candidates:
        if not ini.is_file():
            continue
        try:
            cp = configparser.ConfigParser()
            cp.read(ini, encoding="utf-8")
            for section in cp.sections():
                if cp.has_option(section, "ScriptsDir"):
                    raw = cp.get(section, "ScriptsDir").strip()
                    if raw:
                        p = Path(raw).expanduser()
                        if p.is_dir():
                            return p
        except (configparser.Error, OSError):
            continue
    return None


def discover_commands_dirs(config: Config) -> List[Path]:
    """Все папки, куда Cascadeur может подхватить Commands."""
    found: List[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            key = str(p.resolve()).lower()
        except OSError:
            key = str(p).lower()
        if key in seen:
            return
        seen.add(key)
        if p.is_dir():
            found.append(p)

    env = os.environ.get("VIU_CASCADEUR_SCRIPTS", "").strip()
    if env:
        add(Path(env).expanduser())

    custom = _settings_scripts_dir(config)
    if custom:
        add(custom)

    try:
        exe = resolve_cascadeur_exe(config)
        root = exe.parent
        for rel in (
            ("resources", "scripts", "python", "commands"),
            ("Resources", "scripts", "python", "commands"),
            ("resources", "scripts", "python", "user"),
            ("scripts", "python", "user"),
        ):
            add((root / Path(*rel)).resolve())
    except FileNotFoundError:
        pass

    docs = Path.home() / "Documents" / "Cascadeur" / "scripts" / "python" / "commands"
    add(docs)
    return found


def cascadeur_scripts_dir(config: Config) -> Path:
    """Основная папка commands для deploy."""
    dirs = discover_commands_dirs(config)
    for d in dirs:
        if d.name == "commands" or "commands" in d.as_posix().lower():
            return d
    try:
        exe = resolve_cascadeur_exe(config)
        target = exe.parent / "resources" / "scripts" / "python" / "commands"
        target.mkdir(parents=True, exist_ok=True)
        return target
    except FileNotFoundError:
        fallback = Path.home() / "Documents" / "Cascadeur" / "scripts" / "python" / "commands"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def scripts_status_text(config: Config) -> str:
    dirs = discover_commands_dirs(config)
    primary = cascadeur_scripts_dir(config)
    lines = [f"Commands (primary): {primary}"]
    if dirs:
        lines.append("Найденные папки scripts:")
        for d in dirs:
            mark = " ← deploy" if d.resolve() == primary.resolve() else ""
            n_py = len(list(d.glob("*.py"))) if d.is_dir() else 0
            lines.append(f"  • {d} ({n_py} .py){mark}")
    else:
        lines.append("Папки commands не найдены — проверь установку Cascadeur.")
    lines.append(
        "После deploy:\n"
        "  1. Commands → **Reload scripts** (не Reload commands!)\n"
        "  2. Ищи **Commands → Viu → LabImport** (подменю Viu, не верхний уровень)\n"
        "  3. Если нет — **перезапуск Cascadeur** или Python Console (см. artifacts/viu_lab_import_console.py)\n"
        "  4. Ошибки загрузки скрипта — **Window → Event log**"
    )
    deployed = primary / COMMAND_FILENAME
    if deployed.is_file():
        lines.append(f"• {COMMAND_FILENAME}: есть ({deployed.stat().st_size} B)")
    else:
        lines.append(f"• {COMMAND_FILENAME}: нет")
    return "\n".join(lines)


def pending_import_path(config: Config, topic: str = "cascadeur") -> Path:
    return config.data_dir / "lab" / topic / "pending_import.json"


def latest_inbox_fbx(config: Config) -> Optional[Path]:
    inbox = cascadeur_inbox(config)
    fbx_files = sorted(inbox.glob("*.fbx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return fbx_files[0] if fbx_files else None


def write_console_import_script(
    config: Config,
    fbx_path: Path,
    *,
    topic: str = "cascadeur",
) -> Tuple[bool, str, Path]:
    """Скрипт для Window → Python console → Load → Execute (обходит Commands menu)."""
    art = config.data_dir / "lab" / topic / "artifacts" / CONSOLE_FILENAME
    art.parent.mkdir(parents=True, exist_ok=True)
    body = CONSOLE_IMPORT_TEMPLATE.format(fbx_path=str(fbx_path.resolve()))
    try:
        art.write_text(body, encoding="utf-8")
    except OSError as exc:
        return False, str(exc), art
    return (
        True,
        f"Console script: {art}\n"
        "Cascadeur: Window → Python console → Load → Execute.",
        art,
    )


def deploy_import_command(config: Config) -> Tuple[bool, str, Path]:
    """Положить viu_lab_import.py во все commands-папки."""
    primary = cascadeur_scripts_dir(config)
    targets = discover_commands_dirs(config)
    if primary not in targets:
        targets = [primary] + targets
    written: List[str] = []
    errors: List[str] = []
    for scripts in targets:
        if scripts.name != "commands" and "commands" not in scripts.as_posix().lower():
            continue
        target = scripts / COMMAND_FILENAME
        try:
            scripts.mkdir(parents=True, exist_ok=True)
            target.write_text(IMPORT_COMMAND_SOURCE, encoding="utf-8")
            written.append(str(target))
        except OSError as exc:
            errors.append(f"{target}: {exc}")
    # Legacy path (старые прогоны lab) — на случай кастомного ScriptsDir
    for scripts in targets:
        if "user" not in scripts.as_posix().lower():
            continue
        target = scripts / COMMAND_FILENAME
        if str(target) in written:
            continue
        try:
            scripts.mkdir(parents=True, exist_ok=True)
            target.write_text(IMPORT_COMMAND_SOURCE, encoding="utf-8")
            written.append(str(target) + " (legacy user/)")
        except OSError:
            pass
    if not written:
        target = primary / COMMAND_FILENAME
        try:
            primary.mkdir(parents=True, exist_ok=True)
            target.write_text(IMPORT_COMMAND_SOURCE, encoding="utf-8")
            written.append(str(target))
        except OSError as exc:
            return False, f"Не удалось записать команду: {exc}", target
    msg = "Команда:\n" + "\n".join(f"  • {p}" for p in written)
    if errors:
        msg += "\nОшибки:\n" + "\n".join(errors)
    return True, msg, Path(written[0])


def write_pending_import(config: Config, fbx_path: Path, *, topic: str = "cascadeur") -> Tuple[bool, str]:
    payload = {"fbx": str(fbx_path.resolve())}
    lab_pending = pending_import_path(config, topic)
    lab_pending.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    written: List[str] = []
    try:
        lab_pending.write_text(text, encoding="utf-8")
        written.append(str(lab_pending))
    except OSError as exc:
        return False, str(exc)
    for scripts in discover_commands_dirs(config):
        if scripts.name != "commands" and "commands" not in scripts.as_posix().lower():
            continue
        scripts_pending = scripts / PENDING_FILENAME
        try:
            scripts.mkdir(parents=True, exist_ok=True)
            scripts_pending.write_text(text, encoding="utf-8")
            written.append(str(scripts_pending))
        except OSError:
            pass
    return True, "pending:\n" + "\n".join(f"  • {p}" for p in written)


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
        return False, (
            f"{hint}\n"
            "FBX не ассоциирован — используй Commands → Viu.Lab Import "
            "(после Reload scripts)."
        )

    time.sleep(3.0)
    note = f" (ранее: {prior_error})" if prior_error else ""
    return True, f"ShellExecute({exe.name}, {fbx_path.name}){note}"


def trigger_fbx_import(
    config: Config,
    fbx_path: Optional[Path] = None,
    *,
    topic: str = "cascadeur",
) -> Tuple[bool, str, bool]:
    """Deploy команды, pending, опционально открыть FBX. Третье значение — opened автоматически."""
    fbx = fbx_path or latest_inbox_fbx(config)
    if fbx is None or not fbx.is_file():
        return False, "Нет FBX в Cascadeur Inbox — сначала шаг Inbox.", False

    ok_deploy, deploy_msg, _script = deploy_import_command(config)
    if not ok_deploy:
        return False, deploy_msg, False

    ok_pending, pending_msg = write_pending_import(config, fbx, topic=topic)
    if not ok_pending:
        return False, pending_msg, False

    ok_console, console_msg, _console_path = write_console_import_script(config, fbx, topic=topic)
    diag = scripts_status_text(config)
    opened_ok, open_msg = _try_open_fbx(fbx, config)
    lines = [deploy_msg, pending_msg]
    if ok_console:
        lines.append(console_msg)
    lines.append(diag)
    manual = (
        "\n--- Ручной импорт (проверенный путь) ---\n"
        "1. Фокус Cascadeur (активное окно / 3-й монитор).\n"
        "2. **New scene** (если welcome).\n"
        "3. **File → Import → Fbx/Dae**.\n"
        "4. Preset **Scene**; Import mode **Add new**; INCLUDE: Animations, Objects, Blendshapes; **Open first take**.\n"
        f"5. Import → `{fbx}`\n"
        "6. **Rig Mode Helper** → **No** (для lab; rig позже).\n"
        "\n--- Python Console (если Commands не видит скрипт) ---\n"
        "Window → Python console → Load → "
        f"`.viu/lab/cascadeur/artifacts/{CONSOLE_FILENAME}` → Execute.\n"
        "\n--- Commands menu ---\n"
        "Reload scripts → **Commands → Viu → LabImport** (подменю Viu!)."
    )
    if opened_ok:
        lines.append(open_msg)
        lines.append(
            "Если открылся диалог Import — preset Model/Scene, Add new, Import."
        )
        lines.append(manual)
        return True, "\n".join(lines), True

    lines.append(f"Авто-открытие FBX: {open_msg}")
    lines.append(manual)
    return True, "\n".join(lines), False
