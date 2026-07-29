"""Жёсткая диагностика Comfy: API ≠ живой GPU / UI.

Дена раздражает «ComfyUI OK running=0», когда в диспетчере нет тяжёлого
python и окно :8188 не прогружается. Этот модуль проверяет факты:

1. Кто слушает :8188 (pid/exe) + CPU / RAM / Responding
2. Скорость /queue, /, /object_info, /system_stats
3. Живой ли executor: POST /prompt с заведомо битым графом
4. Хвост comfy_launch.log (got prompt / traceback / Starting server)
5. Lab: awaiting_prompt vs реально в очереди

Вердикт — одна строка + что делать дальше.
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...config import Config
from .client import ComfyClient, ComfyError
from .paths import resolve_comfy_root
from .process import (
    _CREATE_NO_WINDOW,
    _launch_log_path,
    _looks_like_comfy_process,
    _pids_on_port,
    _process_identity,
    _parse_port,
    describe_port_listeners,
    extract_crash_summary,
)

_CREATE_NO_WINDOW = _CREATE_NO_WINDOW  # re-export for tests if needed

# Маркеры «сервер реально поднялся / считает / умер»
_LOG_GOOD = ("starting server", "to see the gui go to", "got prompt")
_LOG_BAD = (
    "traceback",
    "cuda out of memory",
    "outofmemory",
    "error while",
    "exception:",
    "killed",
    "access is denied",
    "value not in list",
    "prompt_outputs_failed_validation",
    "lora_name:",
    "failed to validate prompt",
)


@dataclass
class TimedHttp:
    path: str
    ok: bool
    ms: float
    detail: str = ""
    bytes_n: int = 0


@dataclass
class ProcessSnap:
    pid: int
    name: str = ""
    exe: str = ""
    cmdline: str = ""
    is_comfy: bool = False
    cpu_sec: Optional[float] = None
    cpu_delta: Optional[float] = None
    ram_mb: Optional[float] = None
    responding: Optional[bool] = None


@dataclass
class ComfyDiagReport:
    url: str
    verdict: str = "UNKNOWN"
    actions: List[str] = field(default_factory=list)
    lines: List[str] = field(default_factory=list)

    def text(self) -> str:
        chunks = [
            "=== comfy_diag ===",
            f"URL: {self.url}",
            f"ВЕРДИКТ: {self.verdict}",
        ]
        if self.actions:
            chunks.append("Дальше:")
            chunks.extend(f"  → {a}" for a in self.actions)
        chunks.append("")
        chunks.extend(self.lines)
        return "\n".join(chunks)


def _timed_get(base_url: str, path: str, *, timeout: float) -> TimedHttp:
    url = base_url.rstrip("/") + (path if path.startswith("/") else "/" + path)
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
        ms = (time.perf_counter() - t0) * 1000.0
        return TimedHttp(path=path, ok=True, ms=ms, bytes_n=len(raw), detail=f"HTTP {status}")
    except urllib.error.HTTPError as exc:
        ms = (time.perf_counter() - t0) * 1000.0
        return TimedHttp(path=path, ok=False, ms=ms, detail=f"HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001
        ms = (time.perf_counter() - t0) * 1000.0
        return TimedHttp(path=path, ok=False, ms=ms, detail=str(exc)[:200])


def _process_resource_snap(pid: int) -> Dict[str, Any]:
    """CPU seconds, RAM MB, Responding (Windows)."""
    out: Dict[str, Any] = {
        "cpu_sec": None,
        "ram_mb": None,
        "responding": None,
    }
    if sys.platform == "win32":
        try:
            ps = (
                f"$p = Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue; "
                f"if ($p) {{ "
                f"Write-Output ('CPU=' + $p.CPU); "
                f"Write-Output ('RAM=' + [math]::Round($p.WorkingSet64/1MB,1)); "
                f"Write-Output ('RESP=' + $p.Responding) "
                f"}}"
            )
            kwargs: dict = {"capture_output": True, "text": True, "timeout": 20}
            kwargs["creationflags"] = _CREATE_NO_WINDOW
            proc = subprocess.run(  # noqa: S603
                ["powershell", "-NoProfile", "-Command", ps],
                **kwargs,
            )
            for line in (proc.stdout or "").splitlines():
                if line.startswith("CPU="):
                    try:
                        out["cpu_sec"] = float(line[4:].strip().replace(",", "."))
                    except ValueError:
                        pass
                elif line.startswith("RAM="):
                    try:
                        out["ram_mb"] = float(line[4:].strip().replace(",", "."))
                    except ValueError:
                        pass
                elif line.startswith("RESP="):
                    out["responding"] = line[5:].strip().lower() in ("true", "1", "yes")
        except (OSError, subprocess.TimeoutExpired):
            pass
        return out
    try:
        # /proc: utime+stime in clock ticks
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        parts = stat.split()
        if len(parts) > 14:
            ticks = int(parts[13]) + int(parts[14])
            hz = os_sysconf_hz()
            out["cpu_sec"] = ticks / float(hz)
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace")
        for line in status.splitlines():
            if line.startswith("VmRSS:"):
                kb = int(line.split()[1])
                out["ram_mb"] = round(kb / 1024.0, 1)
                break
        out["responding"] = True
    except (OSError, ValueError, IndexError):
        pass
    return out


def os_sysconf_hz() -> int:
    try:
        import os

        return int(os.sysconf("SC_CLK_TCK"))
    except Exception:
        return 100


def sample_listeners(port: int, *, sample_sec: float = 1.2) -> List[ProcessSnap]:
    """Снимок слушателей :port + дельта CPU за sample_sec."""
    pids = _pids_on_port(port)
    first: Dict[int, Dict[str, Any]] = {}
    snaps: List[ProcessSnap] = []
    for pid in pids[:6]:
        ident = _process_identity(pid)
        res = _process_resource_snap(pid)
        first[pid] = res
        snaps.append(
            ProcessSnap(
                pid=pid,
                name=str(ident.get("name") or ""),
                exe=str(ident.get("exe") or ""),
                cmdline=str(ident.get("cmdline") or ""),
                is_comfy=_looks_like_comfy_process(ident),
                cpu_sec=res.get("cpu_sec"),
                ram_mb=res.get("ram_mb"),
                responding=res.get("responding"),
            )
        )
    if sample_sec > 0 and snaps:
        time.sleep(sample_sec)
        for snap in snaps:
            res2 = _process_resource_snap(snap.pid)
            c1 = first.get(snap.pid, {}).get("cpu_sec")
            c2 = res2.get("cpu_sec")
            if isinstance(c1, (int, float)) and isinstance(c2, (int, float)):
                snap.cpu_delta = max(0.0, float(c2) - float(c1))
            if res2.get("ram_mb") is not None:
                snap.ram_mb = res2.get("ram_mb")
            if res2.get("responding") is not None:
                snap.responding = res2.get("responding")
    return snaps


def probe_prompt_executor(client: ComfyClient, *, timeout: float = 8.0) -> Tuple[bool, str, float]:
    """Битый граф → быстрый error = executor жив; таймаут = завис."""
    bad = {
        "1": {
            "class_type": "ViuDiagNonexistentNode_DoNotCreate",
            "inputs": {},
        }
    }
    old_timeout = client.timeout
    client.timeout = timeout
    t0 = time.perf_counter()
    try:
        client.queue_prompt(bad)
        ms = (time.perf_counter() - t0) * 1000.0
        return False, f"битый граф принят (!?) за {ms:.0f}ms — странно", ms
    except ComfyError as exc:
        ms = (time.perf_counter() - t0) * 1000.0
        msg = str(exc)
        # Ожидаем HTTP 400 / node errors — значит /prompt обработан
        alive = (
            "HTTP 4" in msg
            or "prompt error" in msg.lower()
            or "node" in msg.lower()
            or "class_type" in msg.lower()
            or "viuDiag".lower() in msg.lower()
            or "nonexistent" in msg.lower()
        )
        if alive or ms < timeout * 1000 * 0.9:
            return True, f"executor ответил на /prompt за {ms:.0f}ms ({msg[:160]})", ms
        return False, f"/prompt завис/странно за {ms:.0f}ms: {msg[:200]}", ms
    except Exception as exc:  # noqa: BLE001
        ms = (time.perf_counter() - t0) * 1000.0
        return False, f"/prompt исключение за {ms:.0f}ms: {exc}", ms
    finally:
        client.timeout = old_timeout


def _log_tail_analysis(config: Config, *, max_lines: int = 40) -> Tuple[str, List[str]]:
    root = resolve_comfy_root(config)
    if root is None:
        return "(нет root ComfyUI)", []
    log = _launch_log_path(config, root)
    if not log.is_file():
        return f"(нет лога {log})", []
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(лог не читается: {exc})", []
    if not text.strip():
        return (
            f"Лог пуст: {log} — поставь VIU_COMFY_SHOW_CONSOLE=1 и comfy_ensure restart=1",
            ["empty_log"],
        )
    lines = text.splitlines()
    tail = lines[-max_lines:]
    flags: List[str] = []
    blob = "\n".join(tail).lower()
    if any(m in blob for m in _LOG_GOOD):
        flags.append("log_started")
    if "got prompt" in blob:
        flags.append("got_prompt_recent")
    if "value not in list" in blob and "lora_name" in blob:
        flags.append("lora_name_mismatch")
    if "prompt_outputs_failed_validation" in blob:
        flags.append("prompt_validation_failed")
    if any(m in blob for m in _LOG_BAD):
        flags.append("log_errors")
    # «Loading» без Starting server — часто UI/custom nodes зависли при старте
    if "loading" in blob and "starting server" not in blob:
        flags.append("stuck_loading")
    crash = extract_crash_summary(log, max_chars=900)
    block = [f"Лог: {log} (хвост {len(tail)} строк)"]
    block.extend(f"  | {ln}" for ln in tail[-18:])
    if crash and "traceback" in crash.lower():
        block.append("— crash summary —")
        block.extend(f"  ! {ln}" for ln in crash.splitlines()[:12])
        flags.append("crash_summary")
    return "\n".join(block), flags


def _lab_line(config: Config) -> str:
    try:
        from ...lab.comfy_pipeline import COMFY_TOPIC
        from ...lab.session import load_session

        sess = load_session(config, COMFY_TOPIC)
        if sess is None:
            return "Lab comfy: сессии нет"
        action = str((sess.meta or {}).get("action") or "")[:80]
        approved = bool((sess.meta or {}).get("approved"))
        return (
            f"Lab comfy: status={sess.status} step={sess.step} "
            f"approved={approved} action={action or '—'}"
        )
    except Exception as exc:  # noqa: BLE001
        return f"Lab comfy: ({exc})"


def _system_stats_line(client: ComfyClient) -> str:
    try:
        data = client._get("/system_stats")
    except ComfyError as exc:
        return f"system_stats: нет ({exc})"
    if not isinstance(data, dict):
        return "system_stats: не dict"
    devices = data.get("devices") or []
    bits = []
    for d in devices[:4]:
        if not isinstance(d, dict):
            continue
        name = d.get("name") or d.get("type") or "?"
        vram = d.get("vram_total") or d.get("vram_free")
        bits.append(f"{name}" + (f" vram={vram}" if vram is not None else ""))
    sysinfo = data.get("system") or {}
    comfy_v = ""
    if isinstance(sysinfo, dict):
        comfy_v = str(sysinfo.get("comfyui_version") or sysinfo.get("ram_total") or "")
    return "system_stats: " + (", ".join(bits) if bits else "devices=?") + (
        f" | {comfy_v}" if comfy_v else ""
    )


def run_comfy_diag(
    config: Config,
    *,
    sample_sec: float = 1.2,
    http_timeout: float = 12.0,
    probe_prompt: bool = True,
) -> ComfyDiagReport:
    url = str(getattr(config, "comfy_url", None) or "http://127.0.0.1:8188")
    port = _parse_port(url)
    report = ComfyDiagReport(url=url)
    L = report.lines
    flags: List[str] = []

    client = ComfyClient(base_url=url, timeout=http_timeout)
    t0 = time.perf_counter()
    ok_ping, ping_msg = client.ping()
    ping_ms = (time.perf_counter() - t0) * 1000.0
    L.append(f"1) API /queue: {'OK' if ok_ping else 'FAIL'} за {ping_ms:.0f}ms — {ping_msg}")
    queue_running = 0
    queue_pending = 0
    if ok_ping:
        try:
            q = client.get_queue()
            queue_running = len(q.get("queue_running") or [])
            queue_pending = len(q.get("queue_pending") or [])
        except Exception:
            pass
        if queue_running > 0:
            flags.append("queue_running")
        if queue_pending > 0:
            flags.append("queue_pending")
    if not ok_ping:
        flags.append("api_dead")
    elif ping_ms > 5000:
        flags.append("api_slow")

    L.append("")
    L.append("2) Процесс на порту (то, что видно в диспетчере):")
    snaps = sample_listeners(port, sample_sec=sample_sec if ok_ping else 0.0)
    if not snaps:
        L.append(describe_port_listeners(port))
        if ok_ping:
            flags.append("no_pid_but_api")
        else:
            flags.append("no_listener")
    else:
        any_comfy = False
        for s in snaps:
            any_comfy = any_comfy or s.is_comfy
            tag = "Comfy" if s.is_comfy else "НЕ похож на Comfy"
            resp = (
                "Responding=yes"
                if s.responding is True
                else ("Responding=NO ← окно/UI мёртв" if s.responding is False else "Responding=?")
            )
            cpu_d = (
                f"ΔCPU={s.cpu_delta:.2f}s/{sample_sec:.1f}s"
                if s.cpu_delta is not None
                else "ΔCPU=?"
            )
            ram = f"RAM={s.ram_mb:.0f}MB" if s.ram_mb is not None else "RAM=?"
            L.append(f"  pid={s.pid} {s.name or '?'} [{tag}] {ram} {cpu_d} {resp}")
            if s.exe:
                L.append(f"    exe: {s.exe}")
            if s.cmdline and "main.py" in s.cmdline.lower():
                short = s.cmdline if len(s.cmdline) <= 200 else s.cmdline[:197] + "…"
                L.append(f"    cmd: {short}")
            if s.responding is False:
                flags.append("not_responding")
            if s.is_comfy and s.cpu_delta is not None and s.cpu_delta < 0.05 and ok_ping:
                flags.append("comfy_idle_cpu")
            if s.is_comfy and s.cpu_delta is not None and s.cpu_delta >= 0.5:
                flags.append("comfy_busy_cpu")
            if s.ram_mb is not None and s.ram_mb < 200 and s.is_comfy:
                flags.append("comfy_tiny_ram")
        if not any_comfy:
            flags.append("wrong_listener")

    L.append("")
    L.append("3) HTTP (UI / граф / железо):")
    ui = _timed_get(url, "/", timeout=min(8.0, http_timeout))
    L.append(f"  GET / → {'OK' if ui.ok else 'FAIL'} {ui.ms:.0f}ms {ui.bytes_n}b ({ui.detail})")
    if not ui.ok or ui.ms > 6000 or (ui.ok and ui.bytes_n < 80):
        flags.append("ui_broken")

    if ok_ping:
        t1 = time.perf_counter()
        try:
            info = client._get("/object_info")
            oi_ms = (time.perf_counter() - t1) * 1000.0
            n = len(info) if isinstance(info, dict) else 0
            L.append(f"  GET /object_info → OK {oi_ms:.0f}ms, нод={n}")
            if oi_ms > 10000:
                flags.append("object_info_slow")
            if n < 20:
                flags.append("few_nodes")
        except ComfyError as exc:
            oi_ms = (time.perf_counter() - t1) * 1000.0
            L.append(f"  GET /object_info → FAIL {oi_ms:.0f}ms ({exc})")
            flags.append("object_info_fail")
        L.append(f"  {_system_stats_line(client)}")
    else:
        L.append("  /object_info /system_stats — пропуск (API мёртв)")

    L.append("")
    L.append("4) Executor /prompt (битый граф — должен сразу отвергнуть):")
    # Не слать тестовый /prompt, пока Comfy уже считает — засоряет лог и pending.
    skip_probe = (not probe_prompt) or queue_running > 0 or queue_pending > 0
    if ok_ping and not skip_probe:
        alive, detail, _ms = probe_prompt_executor(client, timeout=min(8.0, http_timeout))
        L.append(f"  {'OK' if alive else 'FAIL'} — {detail}")
        if alive:
            flags.append("executor_alive")
        else:
            flags.append("executor_dead")
    elif ok_ping and skip_probe and (queue_running > 0 or queue_pending > 0):
        L.append(
            f"  пропуск — очередь busy (running={queue_running}, pending={queue_pending}); "
            "executor считаем живым"
        )
        flags.append("executor_alive")
    else:
        L.append("  пропуск")

    L.append("")
    L.append("5) Lab + лог:")
    L.append(f"  {_lab_line(config)}")
    try:
        from ...lab.comfy_pipeline import COMFY_TOPIC
        from ...lab.session import load_session

        sess = load_session(config, COMFY_TOPIC)
        if sess is not None and sess.status == "awaiting_prompt":
            flags.append("waiting_panel")
        if sess is not None and sess.status == "running" and sess.meta.get("approved"):
            flags.append("lab_should_queue")
    except Exception:
        pass

    log_block, log_flags = _log_tail_analysis(config)
    flags.extend(log_flags)
    L.append(log_block)

    # --- вердикт ---
    verdict, actions = _verdict(flags, ok_ping=ok_ping)
    report.verdict = verdict
    report.actions = actions
    L.append("")
    L.append(f"flags: {', '.join(flags) if flags else '(none)'}")
    return report


def _verdict(flags: List[str], *, ok_ping: bool) -> Tuple[str, List[str]]:
    f = set(flags)
    actions: List[str] = []

    if "api_dead" in f or "no_listener" in f:
        return (
            "МЁРТВ — :8188 не отвечает",
            [
                "comfy_ensure restart=1",
                "Смотри .viu/logs/comfy_launch.log",
                "VIU_COMFY_SHOW_CONSOLE=1 если лог пуст",
            ],
        )

    if "not_responding" in f or ("ui_broken" in f and "object_info_fail" in f):
        return (
            "ЗАВИС — процесс есть, UI/API не тянет",
            [
                "Убей pid в диспетчере / comfy_ensure restart=1",
                "Проверь custom_nodes (ReActor) — comfy_reactor_fix",
                "Лог: нет Starting server → custom nodes блокируют старт",
            ],
        )

    if "wrong_listener" in f or "no_pid_but_api" in f:
        return (
            "ПОДОЗРИТЕЛЬНО — на :8188 не тот процесс / PID не виден",
            [
                "comfy_ensure restart=1 (убить порт и поднять заново)",
                "В диспетчере ищи python из U:\\Viu\\ComfyUI\\…, не Вью",
            ],
        )

    if "executor_dead" in f or "object_info_fail" in f or "object_info_slow" in f:
        return (
            "ПОЛУЖИВОЙ — /queue отвечает, граф/executor нет",
            [
                "comfy_ensure restart=1",
                "Пока грузятся ноды — подожди; если >2 мин — смотри лог Loading…",
                "comfy_reactor_fix если ReActor/custom_nodes",
            ],
        )

    if "lora_name_mismatch" in f or (
        "prompt_validation_failed" in f and "got_prompt_recent" in f
    ):
        return (
            "LoRA НЕ ИЗ СПИСКА COMFY — got prompt, но 400 value_not_in_list",
            [
                "Имена вроде Body/….safetensors не совпали с combo Comfy (у тебя ~56 шт.)",
                "comfy_lora_scan → выбери LoRA заново или lora: none",
                "Если файл на диске есть, а в списке нет — comfy_ensure restart=1",
                "Потом снова «Снять»",
            ],
        )

    if "crash_summary" in f or "log_errors" in f:
        actions = ["Читай crash в comfy_launch.log", "comfy_ensure restart=1"]
        if "stuck_loading" in f:
            actions.append("Custom nodes залипли на Loading — отключи последний node pack")
        return ("ЛОГ С ОШИБКАМИ — генерация могла упасть", actions)

    if "lab_should_queue" in f and "got_prompt_recent" in f and "comfy_idle_cpu" in f:
        return (
            "LAB СТАВИЛ JOBS, НО COMFY ИХ ОТКЛОНИЛ — очередь пуста, CPU спокойный",
            [
                "Смотри ERROR в comfy_launch.log (часто LoRA / нода)",
                "диагностика comfy ещё раз после фикса",
            ],
        )

    if "waiting_panel" in f and "executor_alive" in f:
        return (
            "ЖИВ, НО ЖДЁТ «Снять» — очередь пуста поэтому CPU спокойный",
            [
                "Telegram панель → «Снять» (или снова MoCap)",
                "После Снять в диспетчере CPU/GPU python Comfy должен взлететь",
                "В логе появится got prompt",
            ],
        )

    if "lab_should_queue" in f and "comfy_idle_cpu" in f and "got_prompt_recent" not in f:
        return (
            "LAB ДУМАЕТ ЧТО СНИМАЕТ, А COMFY ПРОСТАИВАЕТ",
            [
                "Смотри статус lab / journal — шаг генерации мог не дойти до queue_prompt",
                "Снова «Снять» / lab_step topic=comfy run_all=1",
                "comfy_diag ещё раз через 10с",
            ],
        )

    if "executor_alive" in f and "comfy_idle_cpu" in f:
        return (
            "ЖИВ И ПРОСТАИВАЕТ — генерации нет, потому что в очередь ничего не ставили",
            [
                "Это не поломка: idle python без Wan почти не грузит ПК",
                "Съёмка: панель «Снять» / MoCap / comfy_mocap",
                "Когда пойдёт — увидишь got prompt + рост CPU/GPU",
            ],
        )

    if "comfy_busy_cpu" in f or "got_prompt_recent" in f or "queue_running" in f:
        return (
            "СЧИТАЕТ — CPU/лог/очередь показывают работу",
            ["Жди клипы; Студия / лог progress %", "Не жми interrupt зря"],
        )

    if ok_ping:
        return (
            "API ЖИВ — нужна съёмка или рестарт если UI пустой",
            [
                "Если окно белое: hard refresh / другой браузер / restart=1",
                "Съёмка через панель «Снять», не через пустой canvas",
            ],
        )

    return ("НЕЯСНО", ["Пришли этот отчёт целиком", "comfy_ensure restart=1"])


def format_comfy_diag(config: Config, **kwargs: Any) -> str:
    return run_comfy_diag(config, **kwargs).text()
