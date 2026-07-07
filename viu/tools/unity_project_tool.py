"""Инструменты записи в Unity-проект и автонастройки Шани."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict

from ..integrations.unity.animation_scan import ANIMATIONS_REL
from ..integrations.unity.paths import resolve_in_unity_project, unity_project_root
from ..integrations.unity.setup import (
    batch_overlay_build_command,
    batch_setup_command,
    batch_sync_animations_command,
    deploy_animation_pipeline,
    deploy_shanya_setup,
    editor_scripts_healthy,
    find_unity_exe,
    open_editor_command,
    strip_risky_packages,
)
from ..integrations.unity.overlay import overlay_exe_path
from ..integrations.unity.overlay_tune import deploy_tune_template, write_tune_lane
from ..integrations.unity.process import (
    prepare_unity_for_batch,
    unity_lockfile,
    unity_process_running,
)
from ..integrations.unity.verify import verify_unity_project
from .base import AgentContext, Tool, ToolResult


def _root(ctx: AgentContext, args: Dict[str, Any]) -> Path:
    override = args.get("project_path")
    return unity_project_root(ctx.config, override)


def _ensure_batch_ready(root: Path, *, auto_kill: bool = True) -> tuple[ToolResult | None, str]:
    """(ошибка или None, заметка о подготовке)."""
    ok, msg = prepare_unity_for_batch(root, auto_kill=auto_kill)
    if not ok:
        return ToolResult(False, msg), ""
    return None, msg


class UnityReadTool(Tool):
    name = "unity_read"
    description = (
        "Прочитать файл в Unity-проекте (VIU_UNITY_PROJECT). "
        "Путь относительно корня проекта, напр. Packages/manifest.json"
    )
    parameters = {
        "path": "относительный путь в Unity-проекте",
        "project_path": "корень проекта (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        rel = args.get("path", "")
        if not rel:
            return ToolResult(False, "Не указан path")
        root = _root(ctx, args)
        try:
            target = resolve_in_unity_project(root, rel)
            if not target.is_file():
                return ToolResult(False, f"Файл не найден: {target}")
            return ToolResult(True, target.read_text(encoding="utf-8", errors="replace"))
        except (ValueError, OSError) as exc:
            return ToolResult(False, str(exc))


class UnityWriteTool(Tool):
    name = "unity_write"
    description = (
        "Записать файл в Unity-проект (VIU_UNITY_PROJECT). "
        "Для Editor-скриптов, manifest.json и т.п."
    )
    parameters = {
        "path": "относительный путь",
        "content": "содержимое",
        "project_path": "корень проекта (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        rel = args.get("path", "")
        content = args.get("content", "")
        if not rel:
            return ToolResult(False, "Не указан path")
        root = _root(ctx, args)
        try:
            target = resolve_in_unity_project(root, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolResult(True, f"Записано {len(content)} символов → {target}")
        except (ValueError, OSError) as exc:
            return ToolResult(False, str(exc))


class UnityListTool(Tool):
    name = "unity_list"
    description = "Список файлов в каталоге Unity-проекта"
    parameters = {
        "path": "относительный путь (по умолчанию Assets)",
        "project_path": "корень проекта (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        rel = args.get("path") or "Assets"
        root = _root(ctx, args)
        try:
            target = resolve_in_unity_project(root, rel)
            if not target.is_dir():
                return ToolResult(False, f"Каталог не найден: {target}")
            lines = []
            for p in sorted(target.iterdir()):
                lines.append(p.name + ("/" if p.is_dir() else ""))
            return ToolResult(True, "\n".join(lines) if lines else "(пусто)")
        except (ValueError, OSError) as exc:
            return ToolResult(False, str(exc))


class UnityDeploySetupTool(Tool):
    name = "unity_deploy_setup"
    description=(
        "Скопировать скрипты Viu в Unity: ShanyaSetup, ShanyaAnimationSync, "
        "ShanyaLocomotion, viu_clips.json. Меню: Viu → Setup Shanya / Sync Animations"
    )
    parameters = {"project_path": "корень проекта (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект (нет Assets): {root}")
        ok, msg = deploy_shanya_setup(root)
        hint = (
            "\nДальше: открой Unity → дождись компиляции →\n"
            "  **Viu → Sync Animations** (скан Animations/) или **Setup Shanya (Idle)**\n"
            "Положи FBX в Assets/Characters/Shanya/Animations/ — при открытом Unity импорт подхватится сам.\n"
            "Или: unity_sync_animations / unity_run_setup (batchmode, Unity закрыт)."
        )
        return ToolResult(ok, msg + hint)


class UnityFixManifestTool(Tool):
    name = "unity_fix_manifest"
    description=(
        "Убрать из Packages/manifest.json пакеты, часто ломающие Play "
        "(Input System, AI Navigation). Unity должен быть закрыт."
    )
    parameters = {
        "project_path": "корень проекта (опционально)",
        "packages": "список через запятую (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        pkgs_raw = args.get("packages")
        pkgs = [p.strip() for p in pkgs_raw.split(",") if p.strip()] if pkgs_raw else None
        ok, msg = strip_risky_packages(root, pkgs)
        return ToolResult(ok, msg)


class UnityRunSetupTool(Tool):
    name = "unity_run_setup"
    description=(
        "Запустить Unity в batchmode: deploy ShanyaSetup + Setup Shanya (Idle). "
        "Unity Editor должен быть **закрыт**. Нужен VIU_UNITY_EXE или Hub 6000.3.x."
    )
    parameters = {
        "project_path": "корень проекта (опционально)",
        "timeout": "таймаут секунд (по умолчанию 600)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")
        ok, msg = deploy_shanya_setup(root)
        if not ok:
            return ToolResult(False, msg)
        prep, _prep_msg = _ensure_batch_ready(root, auto_kill=True)
        if prep is not None:
            return prep
        exe = find_unity_exe(ctx.config.unity_exe)
        if exe is None:
            return ToolResult(
                False,
                "Unity.exe не найден. Задай VIU_UNITY_EXE=путь\\к\\Unity.exe "
                "или установи 6.3 LTS через Hub.",
            )
        cmd = batch_setup_command(root, exe)
        timeout = float(args.get("timeout") or 600)
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(root),
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"Таймаут {timeout}s. Смотри {root / 'viu_setup.log'}")
        log_path = root / "viu_setup.log"
        viu_lines: list[str] = []
        tail = ""
        if log_path.is_file():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-40:])
            # Ключевые строки Viu/ошибки — чтобы сразу видеть причину.
            viu_lines = [
                ln for ln in lines
                if "[Viu]" in ln or "error CS" in ln or "Exception" in ln
            ][-15:]
        ok_run = proc.returncode == 0
        head = "Настройка прошла." if ok_run else "Настройка не удалась."
        important = ("\nГлавное:\n" + "\n".join(viu_lines)) if viu_lines else ""
        hint = (
            "\nСцена сохранена в Assets/Scenes/GameTest.unity — открой её и нажми Play."
            if ok_run
            else "\nПришли мне viu_setup.log (кнопка «Отправить логи разработчику»)."
        )
        body = f"{head} exit={proc.returncode}{important}{hint}\n\n--- хвост лога ---\n{tail or proc.stderr or '(нет вывода)'}"
        return ToolResult(ok_run, body)


class UnityVerifyTool(Tool):
    name = "unity_verify"
    description=(
        "Проверить результат setup: viu_setup.log, Controller, Editor.log, Play. "
        "После unity_run_setup или Play в Unity."
    )
    parameters = {
        "project_path": "корень проекта (опционально)",
        "log_path": "Editor.log (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from pathlib import Path

        from ..integrations.unity import default_editor_log

        root = _root(ctx, args)
        log_raw = args.get("log_path")
        log_path = Path(log_raw).expanduser() if log_raw else default_editor_log()
        result = verify_unity_project(root, log_path)
        ok = (
            result.setup_log_ok
            and result.controller_found
            and not result.cs_errors
            and not (result.editor_log and (result.editor_log.safe_mode or result.editor_log.playmode_blockers))
        )
        return ToolResult(ok, result.render())


class UnityInitProjectTool(Tool):
    name = "unity_init_project"
    description=(
        "Подготовить чистый Unity-проект для Шани: fix manifest + deploy Editor-скрипты + "
        "записать факты в память. Unity закрыт."
    )
    parameters = {"project_path": "корень проекта (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")
        parts = []
        ok1, msg1 = strip_risky_packages(root)
        parts.append(f"manifest: {msg1}")
        ok2, msg2 = deploy_animation_pipeline(root)
        parts.append(f"pipeline: {msg2}")
        ctx.memory.add(
            f"Unity Шани: проект={root}, LTS 6.3, Humanoid Create From This Model, "
            "Avatar Shanya_ErisaAvatar, без Input System в manifest."
        )
        parts.append("Память: факты проекта записаны.")
        parts.append(
            "\nДальше:\n"
            "1. Открой Unity, импортируй FBX в Assets/Characters/Shanya/\n"
            "2. Анимации (Idle, Walk…) — в Assets/Characters/Shanya/Animations/\n"
            "3. Модель → Rig → Humanoid → Configure → Apply\n"
            "4. Viu → Sync Animations или unity_sync_animations\n"
            "5. Viu → Setup Shanya (Idle) или unity_run_setup\n"
            "6. unity_verify"
        )
        return ToolResult(ok1 and ok2, "\n".join(parts))


class UnityScanAnimationsTool(Tool):
    name = "unity_scan_animations"
    description = (
        "Скан папки Assets/Characters/Shanya/Animations/: классификация FBX "
        "(Idle/Walk/Run…), Humanoid, непонятные имена → ask_user / viu_clips.json"
    )
    parameters = {"project_path": "корень проекта (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.unity.animation_scan import scan_animations_folder

        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")
        scan = scan_animations_folder(root)
        ok = bool(scan.clips) and not scan.questions
        return ToolResult(ok, scan.render())


class UnitySyncAnimationsTool(Tool):
    name = "unity_sync_animations"
    description = (
        "Deploy скриптов + Unity batchmode: ShanyaAnimationSync — Humanoid, "
        "Animator Controller из Animations/*.fbx. Unity Editor должен быть **закрыт**."
    )
    parameters = {
        "project_path": "корень проекта (опционально)",
        "timeout": "таймаут секунд (по умолчанию 600)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")
        ok, msg = deploy_animation_pipeline(root)
        if not ok:
            return ToolResult(False, msg)
        healthy, hint = editor_scripts_healthy(root)
        if not healthy:
            return ToolResult(False, hint)
        prep, _prep_msg = _ensure_batch_ready(root, auto_kill=True)
        if prep is not None:
            return prep
        exe = find_unity_exe(ctx.config.unity_exe)
        if exe is None:
            return ToolResult(
                False,
                "Unity.exe не найден. Задай VIU_UNITY_EXE или открой Unity → "
                "меню Viu → Sync Animations (scan folder).",
            )
        cmd = batch_sync_animations_command(root, exe)
        timeout = float(args.get("timeout") or 600)
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(root),
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"Таймаут {timeout}s. Смотри {root / 'viu_anim_sync.log'}")
        log_path = root / "viu_anim_sync.log"
        tail = ""
        if log_path.is_file():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-30:])
        ok_run = proc.returncode == 0
        body = f"{msg}\n\nexit={proc.returncode}\n{tail or proc.stderr or proc.stdout or '(нет вывода)'}"
        if not ok_run and "activeInputHandler" in body:
            body += (
                "\n\n→ В проекте всё ещё старый ShanyaSetup.cs. "
                "Нажми «Обновить Вью», дождись «Зависимости установлены», "
                "затем «Обновить аниматор»."
            )
        return ToolResult(ok_run, body)


class UnityOpenTool(Tool):
    name = "unity_open"
    description = (
        "Открыть Unity Editor (обычное окно) с проектом Анабарра, чтобы можно было "
        "настроить сцену и нажать Play. Безопасно — движок просто запускается."
    )
    parameters = {"project_path": "корень Unity-проекта (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")
        exe = find_unity_exe(ctx.config.unity_exe)
        if exe is None:
            return ToolResult(
                False,
                "Unity.exe не найден. Задай VIU_UNITY_EXE=путь\\к\\Unity.exe "
                "или открой проект вручную через Unity Hub.",
            )
        if unity_process_running():
            return ToolResult(
                True,
                "Unity уже запущен — переключись на его окно.",
            )
        prepare_unity_for_batch(root, auto_kill=False)  # убрать зависший lockfile
        cmd = open_editor_command(root, exe)
        try:
            kwargs: Dict[str, Any] = {"cwd": str(root)}
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(cmd, **kwargs)  # noqa: S603 — запуск без ожидания
        except OSError as exc:
            return ToolResult(False, f"Не удалось запустить Unity: {exc}")
        scene = root / "Assets" / "Scenes" / "GameTest.unity"
        scene_hint = (
            "Открой сцену Assets/Scenes/GameTest.unity (двойной клик в панели Project) — "
            "в ней уже стоит Шаня."
            if scene.is_file()
            else "Помести Шаню в сцену через меню Viu → Setup Shanya (Idle)."
        )
        return ToolResult(
            True,
            f"Открываю Unity ({exe.name}) с проектом {root.name}. "
            f"Запуск занимает 30–90 секунд. Когда откроется: {scene_hint} "
            "Затем нажми ▶ Play и проверь Idle↔Walk на A/D.",
        )


class UnityPrepareSceneTool(Tool):
    name = "unity_prepare_scene"
    description = (
        "Собрать всё сам и открыть Unity готовым к Play: deploy скриптов + Animator + "
        "сцена с Шаней (batch, Unity должен быть ЗАКРЫТ), затем запуск редактора. "
        "От пользователя нужен только Play. Не вызывай при открытом Unity."
    )
    parameters = {"project_path": "корень проекта (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")

        prep, prep_msg = _ensure_batch_ready(root, auto_kill=True)
        if prep is not None:
            return prep

        deploy_animation_pipeline(root)
        exe = find_unity_exe(ctx.config.unity_exe)
        if exe is None:
            return ToolResult(
                False,
                "Не нашёл Unity.exe. Впиши путь в настройки: "
                "VIU_UNITY_EXE=C:\\Program Files\\Unity\\Hub\\Editor\\6000.3.19f1\\Editor\\Unity.exe",
            )

        cmd = batch_setup_command(root, exe)
        timeout = float(args.get("timeout") or 600)
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=str(root)
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"Сборка сцены заняла больше {timeout}s. Смотри viu_setup.log.")

        log_path = root / "viu_setup.log"
        important: list[str] = []
        if log_path.is_file():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            important = [
                ln for ln in lines if "[Viu]" in ln or "error CS" in ln or "Exception" in ln
            ][-12:]

        if proc.returncode != 0:
            detail = "\n".join(important) if important else "(подробности в viu_setup.log)"
            return ToolResult(
                False,
                "Не удалось собрать сцену. Причина:\n" + detail +
                "\n\nНажми «Отправить логи разработчику» и пришли мне файл — я разберусь.",
            )

        # Успех — открываем редактор со сценой.
        try:
            kwargs: Dict[str, Any] = {"cwd": str(root)}
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(open_editor_command(root, exe), **kwargs)  # noqa: S603
        except OSError as exc:
            return ToolResult(
                True,
                "Сцену собрал (Assets/Scenes/GameTest.unity), но открыть Unity не смог: "
                f"{exc}. Открой проект вручную и нажми ▶ Play.",
            )

        return ToolResult(
            True,
            (f"{prep_msg}\n\n" if prep_msg else "") +
            "Готово! Я сам собрал сцену с Шаней и открываю Unity.\n"
            "Когда редактор загрузится (30–90 секунд), вверху ПО ЦЕНТРУ нажми "
            "зелёную кнопку ▶ (Play). Шаня стоит на месте (Idle), а по клавишам "
            "A/D должна пойти (Walk). Больше от тебя ничего не нужно — только Play.",
        )


class UnityOverlayTool(Tool):
    name = "unity_overlay"
    description = (
        "Собрать и запустить десктоп-оверлей: прозрачная полоса у панели задач, "
        "Шаня ходит по A/D. Unity Editor должен быть **закрыт**. Долгая сборка (~5–15 мин)."
    )
    parameters = {
        "project_path": "корень проекта (опционально)",
        "timeout": "таймаут секунд (по умолчанию 1800)",
        "launch": "запустить exe после сборки (по умолчанию true)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")

        ok, msg = deploy_animation_pipeline(root)
        if not ok:
            return ToolResult(False, msg)
        healthy, hint = editor_scripts_healthy(root)
        if not healthy:
            return ToolResult(False, hint)

        prep, prep_msg = _ensure_batch_ready(root, auto_kill=True)
        if prep is not None:
            return prep

        exe = find_unity_exe(ctx.config.unity_exe)
        if exe is None:
            return ToolResult(
                False,
                "Unity.exe не найден. Задай VIU_UNITY_EXE или установи Unity 6.3 LTS через Hub.",
            )

        cmd = batch_overlay_build_command(root, exe)
        timeout = float(args.get("timeout") or 1800)
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=str(root)
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                False,
                f"Сборка оверлея заняла больше {timeout}s. Смотри {root / 'viu_overlay_build.log'}.",
            )

        log_path = root / "viu_overlay_build.log"
        important: list[str] = []
        if log_path.is_file():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            important = [
                ln for ln in lines if "[Viu]" in ln or "error CS" in ln or "Exception" in ln
            ][-15:]

        if proc.returncode != 0:
            detail = "\n".join(important) if important else "(подробности в viu_overlay_build.log)"
            return ToolResult(
                False,
                "Сборка оверлея не удалась.\n" + detail +
                "\n\nПришли viu_overlay_build.log через «Отправить логи разработчику».",
            )

        out_exe = overlay_exe_path(root)
        deploy_tune_template(root, overwrite=False)
        launch = str(args.get("launch", "true")).lower() not in ("0", "false", "no")
        launched = ""
        if launch and out_exe.is_file():
            try:
                kwargs: Dict[str, Any] = {"cwd": str(out_exe.parent)}
                if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                    kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                subprocess.Popen([str(out_exe)], **kwargs)  # noqa: S603
                launched = (
                    "\n\nЗапускаю оверлей (на весь экран). A/D — ходьба, Esc — выход. "
                    "Глубина: **W** подойти, **S** отойти, **F5** — сохранить настройки."
                )
            except OSError as exc:
                launched = f"\n\nСобрано, но запустить не смог: {exc}. Запусти вручную: {out_exe}"

        body = (
            (f"{prep_msg}\n" if prep_msg else "")
            + f"{msg}\n\n"
            + f"Сборка OK: {out_exe}"
            + launched
        )
        if important:
            body += "\n\n--- лог ---\n" + "\n".join(important)
        return ToolResult(True, body)


class UnityOverlayTuneTool(Tool):
    name = "unity_overlay_tune"
    description = (
        "Переключить глубину оверлея без пересборки: записать overlay_tune.json "
        "и перезапустить AnabarraOverlay.exe. lane=taskbar (в глубину) или attention (на экран)."
    )
    parameters = {
        "lane": "taskbar | attention",
        "project_path": "корень проекта (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        lane = (args.get("lane") or "taskbar").strip().lower()
        try:
            path = write_tune_lane(root, lane)
        except ValueError as exc:
            return ToolResult(False, str(exc))
        label = "у панели (в глубину)" if lane == "taskbar" else "на экран (ближе)"
        return ToolResult(
            True,
            f"Записал {path}\n"
            f"Режим: {label}.\n"
            "Закрой AnabarraOverlay.exe и запусти снова. "
            "В оверлее: W/S — глубина на лету, F5 — сохранить удачные цифры.",
        )


class UnityImportStagingTool(Tool):
    name = "unity_import_staging"
    description = (
        "Скопировать *.fbx из папки-входа (VIU_ANIM_STAGING, по умолчанию "
        "U:\\Anabarra\\Animations) в Assets/Characters/Shanya/Animations/"
    )
    parameters = {
        "staging_path": "папка с FBX (опционально)",
        "project_path": "корень Unity-проекта (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = _root(ctx, args)
        raw = args.get("staging_path") or ctx.config.unity_anim_staging
        staging = Path(raw).expanduser().resolve()
        if not staging.is_dir():
            return ToolResult(
                False,
                f"Папка не найдена: {staging}\n"
                "Положи FBX туда или задай VIU_ANIM_STAGING.",
            )
        dest = resolve_in_unity_project(root, ANIMATIONS_REL)
        dest.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for fbx in sorted(staging.glob("*.fbx")):
            target = dest / fbx.name
            shutil.copy2(fbx, target)
            copied.append(fbx.name)
        if not copied:
            return ToolResult(False, f"В {staging} нет *.fbx")
        lines = [f"Скопировано в {dest}:"]
        lines.extend(f"  + {name}" for name in copied)
        lines.append("\nДальше: Sync Animations (Unity открыт → само, иначе кнопка).")
        return ToolResult(True, "\n".join(lines))
