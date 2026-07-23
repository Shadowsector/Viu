"""Автономный playtest оверлея — без кнопок Дена."""

from __future__ import annotations

from ..subprocess_util import run_text
import subprocess
from ..integrations.unity.overlay import overlay_exe_path
from ..integrations.unity.paths import unity_project_root
from ..integrations.unity.process import (
    clear_unity_lockfile,
    kill_unity_processes,
    unity_process_running,
)
from ..integrations.unity.setup import (
    batch_overlay_build_command,
    batch_overlay_rebind_command,
    deploy_animation_pipeline,
    editor_scripts_healthy,
    find_unity_exe,
    open_editor_command,
)
from ..integrations.unity.overlay_tune import deploy_tune_template
from ..support import collect_support_bundle, upload_bundle_to_gist
from .base import AgentContext, Tool, ToolResult


def _overlay_process_running() -> bool:
    if sys.platform != "win32":
        return False
    from ..integrations.apps.process import _pids_for_image

    return bool(_pids_for_image("AnabarraOverlay.exe"))


def _prepare_boot_log(boot: Path) -> None:
    """Убрать старый boot-лог — иначе «✓» при неудачном запуске."""
    if not boot.is_file():
        return
    try:
        boot.unlink()
        return
    except OSError:
        pass
    stale = boot.parent / f"{boot.name}.stale.{int(time.time())}"
    try:
        boot.rename(stale)
    except OSError:
        pass


def _boot_log_fresh(boot: Path, since_ts: float) -> bool:
    if not boot.is_file():
        return False
    try:
        return boot.stat().st_mtime >= since_ts - 1.0
    except OSError:
        return False


def _boot_content_ok(boot_text: str) -> bool:
    low = boot_text.lower()
    return (
        "updatelayeredwindow" in low
        or "runtime-rev=" in low
        or "setlayeredwindowattributes=true" in low
        or "colorkey pass" in low
    )


def _wait_for_overlay_boot(
    boot: Path,
    launch_ts: float,
    wait_sec: float,
) -> tuple[bool, str]:
    deadline = time.time() + wait_sec
    boot_text = ""
    while time.time() < deadline:
        if _boot_log_fresh(boot, launch_ts):
            try:
                boot_text = boot.read_text(encoding="utf-8", errors="replace")
            except OSError:
                boot_text = ""
            if boot_text.strip():
                return True, boot_text
        time.sleep(2.0)
    if _boot_log_fresh(boot, launch_ts):
        try:
            boot_text = boot.read_text(encoding="utf-8", errors="replace")
        except OSError:
            boot_text = ""
        return bool(boot_text.strip()), boot_text
    return False, boot_text


class OverlayPlaytestTool(Tool):
    name = "overlay_playtest"
    description = (
        "Собрать оверлей, запустить LaunchOverlay.bat (bitblt), подождать, "
        "прочитать overlay_boot.log и вернуть вердикт. Дена не дёргать."
    )
    parameters = {
        "timeout": "таймаут сборки сек (по умолчанию 1800)",
        "wait_sec": "сколько ждать после запуска exe (по умолчанию 18)",
        "launch": "запускать ли exe (по умолчанию true)",
        "reopen_unity": "открыть Unity Editor после playtest (по умолчанию false)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        root = unity_project_root(ctx.config)
        if not (root / "Assets").is_dir():
            return ToolResult(False, f"Не Unity-проект: {root}")

        tex_ok, tex_msg = ensure_home_textures_exported(ctx.config)
        if not tex_ok:
            return ToolResult(False, f"Текстуры дома: {tex_msg}")

        ok, msg = deploy_animation_pipeline(root)
        if not ok:
            return ToolResult(False, msg)

        healthy, hint = editor_scripts_healthy(root)
        if not healthy:
            return ToolResult(False, hint)

        exe = find_unity_exe(ctx.config.unity_exe)
        if exe is None:
            return ToolResult(False, "Unity.exe не найден. Задай VIU_UNITY_EXE.")

        lines: List[str] = []
        ok_kill, kill_msg = kill_unity_processes()
        if kill_msg:
            lines.append(kill_msg)
        time.sleep(2.0)

        timeout = float(args.get("timeout") or 1800)

        # Перед сборкой — bake материалов (иначе снова фиолетовый сарай).
        rebind_cmd = batch_overlay_rebind_command(root, exe)
        try:
            rebind_proc = run_text(
                rebind_cmd,
                shell=True,
                timeout=min(timeout, 900),
                cwd=str(root),
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "Починка текстур зависла. Закрой Unity и попробуй снова.")
        if rebind_proc.returncode != 0:
            rebind_log = root / "overlay_rebind.log"
            hint = ""
            if rebind_log.is_file():
                hint = rebind_log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:]
                hint = ("\n" + hint[0]) if hint else ""
            return ToolResult(
                False,
                "✗ Не удалось привязать текстуры (bake)."
                + hint
                + "\n→ «Починить текстуры оверлея» или проверь Textures/ и .viu.json.",
            )

        cmd = batch_overlay_build_command(root, exe)
        try:
            proc = run_text(
                cmd, shell=True, timeout=timeout, cwd=str(root)
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "Сборка слишком долгая. Закрой Unity и попробуй снова.")

        log_path = root / "viu_overlay_build.log"
        important: list[str] = []
        if log_path.is_file():
            important = [
                ln
                for ln in log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                if ("[Viu]" in ln or "error CS" in ln) and "Licensing" not in ln
            ][-12:]

        if proc.returncode != 0:
            detail = "\n".join(important[-6:]) if important else "Смотри viu_overlay_build.log"
            return ToolResult(
                False,
                "✗ Сборка не удалась.\n" + detail + "\n→ «Что сломалось?» или закрой Unity и повтори.",
            )

        out_exe = overlay_exe_path(root)
        launcher = out_exe.parent / "LaunchOverlay.bat"
        deploy_tune_template(root, overwrite=False)
        lines.append(f"Сборка OK: {out_exe}")
        if important:
            lines.append("--- build ---")
            lines.extend(important[-8:])

        launch = str(args.get("launch", "true")).lower() not in ("0", "false", "no")
        launch_requested = launch and out_exe.is_file()
        launch_attempted = launch_requested and sys.platform == "win32"
        boot_fresh = False
        boot_content_ok = False
        proc_running = False
        verdict = ""
        if launch_requested:
            boot = out_exe.parent / "overlay_boot.log"
            launch_ts = time.time()
            _prepare_boot_log(boot)
            launch_error = ""
            if launch_attempted:
                try:
                    cwd = str(out_exe.parent)
                    if launcher.is_file():
                        # start через cmd без ожидания; предпочтительно .vbs без окна
                        vbs = launcher.with_suffix(".vbs")
                        if vbs.is_file():
                            subprocess.Popen(  # noqa: S603
                                ["wscript.exe", str(vbs)],
                                cwd=cwd,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            )
                            lines.append(f"Запуск (без терминала): {vbs}")
                        else:
                            subprocess.Popen(  # noqa: S603
                                ["cmd", "/c", "start", "", str(launcher)],
                                cwd=cwd,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            )
                            lines.append(f"Запуск: {launcher}")
                    else:
                        subprocess.Popen(  # noqa: S603
                            [
                                "cmd", "/c", "start", "", str(out_exe),
                                "-force-d3d11", "-force-d3d11-bitblt-model", "-popupwindow",
                            ],
                            cwd=cwd,
                        )
                        lines.append(f"Запуск exe + bitblt: {out_exe}")
                except OSError as exc:
                    launch_error = str(exc)
                    lines.append(f"Запуск не удался: {exc}")
            else:
                lines.append("(не Windows — запуск пропущен)")

            if launch_error:
                human = _playtest_human(
                    ok=False,
                    build_ok=True,
                    launch_attempted=True,
                    boot_fresh=False,
                    boot_content_ok=False,
                    proc_running=False,
                    out_exe=out_exe,
                    verdict=f"FAIL: запуск — {launch_error}",
                    eyes_miss=False,
                    eye_vision="",
                )
                return ToolResult(False, human)

            wait_sec = float(args.get("wait_sec") or 18)
            boot_fresh, boot_text = _wait_for_overlay_boot(boot, launch_ts, wait_sec)
            proc_running = _overlay_process_running()
            if launch_attempted and not boot_fresh and proc_running:
                boot_fresh, boot_text = _wait_for_overlay_boot(boot, launch_ts, 8.0)
                proc_running = _overlay_process_running()

            if boot_fresh and boot_text:
                boot_content_ok = _boot_content_ok(boot_text)
                lines.append("--- overlay_boot.log ---")
                # Awake/AfterWindow в начале; ColorKey раньше заливал хвост
                head = boot_text[:1200]
                tail = boot_text[-1200:]
                if len(boot_text) > 2400 and head != tail:
                    lines.append(head.rstrip())
                    lines.append("…")
                    lines.append(tail.lstrip())
                else:
                    lines.append(boot_text[-2500:])
                verdict = _verdict(boot_text)
                lines.append("--- вердикт ---")
                lines.append(verdict)
            elif launch_attempted:
                if boot.is_file():
                    verdict = "FAIL: overlay_boot.log не обновился (старый лог?)"
                    lines.append(
                        "overlay_boot.log есть, но не свежий — окно могло не стартовать."
                    )
                else:
                    verdict = "FAIL: overlay_boot.log нет"
                    lines.append(
                        "overlay_boot.log нет — окно могло не стартовать или скрипт не доехал."
                    )

        # Глаза: скрин оверлея → VL / gist Cursor — без «Ден, посмотри»
        try:
            from ..integrations.vision_eye import observe_window, upload_shot_note

            eye = observe_window(
                ctx.config,
                title_substr="AnabarraOverlay",
                prefix="overlay_eye",
            )
            if not eye.get("capture_ok"):
                eye = observe_window(
                    ctx.config,
                    title_substr="Unity",
                    prefix="overlay_eye_unity",
                )
            lines.append("--- eyes ---")
            lines.append(eye.get("capture_msg") or "")
            if eye.get("path"):
                lines.append("shot: " + eye["path"])
            if eye.get("vision"):
                lines.append(eye["vision"])
            if eye.get("path"):
                g_ok, g_msg = upload_shot_note(Path(eye["path"]), eye.get("vision") or "")
                lines.append("eye gist: " + g_msg)
                if not g_ok and eye.get("capture_ok"):
                    lines.append("(скрин локально — Cursor заберёт через support/handoff)")
            eye_low = (eye.get("vision") or "").lower()
            eyes_bad = any(
                t in eye_low
                for t in (
                    "broken",
                    "no_home",
                    "no_character",
                    "no_overlay",
                    "искажен",
                    "корёж",
                    "кореж",
                    "не виден",
                    "нет дома",
                    "сарай не",
                    "дом/сарай не",
                    "magenta",
                    "розов",
                )
            )
            # llava часто пишет «Вердикт: OK» при «дом не виден» — не верь OK
            if ("дом" in eye_low or "сарай" in eye_low) and (
                "не вид" in eye_low or "нет " in eye_low or "отсутств" in eye_low
            ):
                eyes_bad = True
            if eyes_bad:
                if verdict.startswith("OK:"):
                    verdict = "WARN: eyes — дом/персонаж криво (см. --- eyes ---). Дена не спрашивать."
                    lines.append("--- вердикт (после eyes) ---")
                    lines.append(verdict)
        except Exception as exc:  # noqa: BLE001
            lines.append(f"eyes: {exc}")

        # Вернуть Editor Дену — playtest не должен оставлять Unity мёртвым.
        # По умолчанию НЕ открываем Unity снова — Дену мешает лишний Editor + консоль.
        reopen = str(args.get("reopen_unity", "false")).lower() in ("1", "true", "yes")
        if reopen:
            try:
                if not unity_process_running() and exe is not None:
                    clear_unity_lockfile(root)
                    cmd_open = open_editor_command(root, exe)
                    kwargs: Dict[str, Any] = {"cwd": str(root)}
                    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                    subprocess.Popen(cmd_open, **kwargs)  # noqa: S603
                    lines.append("Unity Editor снова открыт.")
                elif unity_process_running():
                    lines.append("Unity Editor уже в процессах.")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"Не смогла reopen Unity: {exc}")

        # В чат не сыпем Licensing / gist — только улики [Viu]/Animator для вердикта.
        try:
            from ..integrations.unity.log_parser import default_editor_log

            elog = default_editor_log()
            if elog.is_file():
                try:
                    tail = elog.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
                    hits = [
                        ln for ln in tail
                        if any(
                            k in ln
                            for k in ("[Viu]", "Animator", "Avatar", "Overlay locomotion")
                        )
                        and "Licensing" not in ln
                    ]
                    if hits:
                        lines.extend(hits[-15:])
                except OSError:
                    pass
        except Exception:
            pass

        try:
            bundle = collect_support_bundle(ctx.config)
            upload_bundle_to_gist(bundle, description="Viu overlay_playtest")
        except Exception:
            pass

        build_ok = proc.returncode == 0
        eyes_miss = any("окно не найдено" in ln.lower() for ln in lines)
        eye_vision = ""
        for i, ln in enumerate(lines):
            if ln.startswith("--- eyes ---") and i + 1 < len(lines):
                # vision often a few lines later
                for j in range(i + 1, min(i + 8, len(lines))):
                    if lines[j].startswith("[llava") or "Вердикт" in lines[j] or "вердикт" in lines[j].lower():
                        eye_vision = "\n".join(lines[j : j + 5])
                        break
                break

        player_bad = any(
            x in "\n".join(lines)
            for x in (
                "state≠Walk",
                "не нашла стенку",
                "hasWalk=False",
                "Overlay locomotion FAIL",
            )
        )

        play_ok = build_ok and (
            not launch_attempted
            or (
                boot_fresh
                and boot_content_ok
                and not verdict.startswith("FAIL:")
                and not player_bad
            )
        )

        human = _playtest_human(
            ok=play_ok,
            build_ok=build_ok,
            launch_attempted=launch_attempted,
            boot_fresh=boot_fresh,
            boot_content_ok=boot_content_ok,
            proc_running=proc_running,
            out_exe=out_exe if build_ok else None,
            verdict=verdict,
            eyes_miss=eyes_miss,
            eye_vision=eye_vision,
        )
        return ToolResult(play_ok, human)


def _playtest_human(
    *,
    ok: bool,
    build_ok: bool,
    launch_attempted: bool,
    boot_fresh: bool,
    boot_content_ok: bool,
    proc_running: bool,
    out_exe: Path | None,
    verdict: str,
    eyes_miss: bool,
    eye_vision: str,
) -> str:
    """Короткий отчёт для чата — без Unity Licensing и списков файлов."""
    if not build_ok:
        return (
            "✗ Сборка не удалась.\n"
            "→ Нажми «Что сломалось?» — логи уйдут разработчику.\n"
            "Или закрой Unity и попробуй снова «▶ Запустить тестовую сцену»."
        )

    if launch_attempted and not boot_fresh:
        lines = ["✗ Сборка прошла, но оверлей не запустился."]
        if proc_running:
            lines.append(
                "Процесс AnabarraOverlay.exe есть, но свежий boot-лог не появился — "
                "окно может быть невидимо."
            )
        else:
            lines.append("Процесс AnabarraOverlay.exe не найден.")
        lines.append("→ Запусти вручную: Builds\\AnabarraOverlay\\LaunchOverlay.vbs")
        lines.append("→ Или «Что сломалось?» — логи уйдут разработчику.")
        if verdict.startswith("FAIL:"):
            lines.append(verdict.split("\n")[0][:160])
        return "\n".join(lines)

    if ok:
        headline = "✓ Оверлей собран и запущен."
    elif launch_attempted and boot_fresh:
        headline = "⚠ Оверлей запущен, но есть сомнения."
    else:
        headline = "✓ Сборка оверлея завершена."

    lines = [headline]
    if out_exe is not None:
        lines.append(f"Файл: {out_exe.name}")
        if launch_attempted:
            lines.append("Управление: A/D — ходить, W/S — глубина, Esc — выход.")
    if boot_content_ok:
        lines.append("Прозрачность: ок (весь экран).")
    if eyes_miss:
        lines.append("Глаза: окно не нашла — глянь на рабочий стол сам.")
    elif eye_vision:
        # Одна строка вердикта из llava, без мусора
        for ln in eye_vision.splitlines():
            if "вердикт" in ln.lower() or "OK" in ln or "FAIL" in ln:
                lines.append("Глаза: " + ln.strip()[:120])
                break
    if verdict.startswith("WARN:") or (verdict.startswith("FAIL:") and ok):
        lines.append(verdict.split("\n")[0][:160])
    if not ok and build_ok and launch_attempted:
        lines.append("")
        lines.append("→ Если картинка кривая: «Починить текстуры оверлея», потом снова запуск.")
    return "\n".join(lines)


def _verdict(boot_text: str) -> str:
    low = boot_text.lower()
    if "hwnd не найден" in low or "hwnd=0" in low:
        return "FAIL: окно Unity не найдено (HWND)."

    layered_ok = (
        "transparency=updatelayeredwindow" in low
        or "updatelayeredwindow init ok" in low
        or ("updatelayeredwindow" in low and "(per-pixel alpha) ok" in low)
    )
    colorkey_ok = (
        "setlayeredwindowattributes=true" in low or "colorkey pass" in low
    )
    if "setlayeredwindowattributes=false" in low and not layered_ok:
        return "FAIL: ColorKey не применился — снова magenta / flip-model?"

    if layered_ok or colorkey_ok:
        mode = "UpdateLayeredWindow" if layered_ok else "ColorKey"
        if "shanya=false" in low or "shanya=(false)" in low or "name=нет" in low:
            return (
                f"WARN: прозрачность ({mode}) ок, но Шаня не в сцене "
                "(пересобери: FindModelPath должен брать Shanya_Erisa, не Fall/Run)."
            )
        if "home=нет" in low:
            return f"WARN: прозрачность ({mode}) ок, дом не найден в сцене (Environment FBX?)."
        if "homemesh=0/" in low:
            return (
                f"WARN: дом в сцене, но меши выключены/съедены chroma "
                f"({mode}). Нужен URP Lit + #FF0080."
            )
        if "renderers=0/" in low:
            return f"WARN: прозрачность ({mode}) ок, но нет видимых мешей."
        return (
            f"OK: HWND + {mode} + сцена в boot-логе. Eyes/gist — источник правды, не Ден."
        )
    if "hwnd ok" in low:
        return "PARTIAL: HWND есть, прозрачность в логе не подтверждена."
    return "UNKNOWN: смотри boot-лог выше."
