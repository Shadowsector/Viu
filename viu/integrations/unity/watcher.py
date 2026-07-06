"""Фоновый наблюдатель папки Animations/ в Unity-проекте."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ...config import Config
from .animation_scan import folder_fingerprint, scan_animations_folder
from .setup import batch_sync_animations_command, deploy_animation_pipeline, find_unity_exe


@dataclass
class WatcherState:
    last_fingerprint: str = ""
    last_scan_summary: str = ""
    pending_questions: list = field(default_factory=list)
    notifications: list = field(default_factory=list)


class AnimationFolderWatcher:
    """Раз в interval_sec проверяет Animations/; при изменениях — скан и уведомление."""

    def __init__(
        self,
        config: Config,
        interval_sec: float = 300.0,
        on_notify: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.config = config
        self.interval_sec = max(30.0, interval_sec)
        self.on_notify = on_notify
        self.state = WatcherState()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state_path = config.data_dir / "unity_anim_watcher.json"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._load_state()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="viu-anim-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_sec):
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001
                self._notify(f"[Viu watcher] ошибка: {exc}")

    def tick(self) -> Optional[str]:
        """Один проход скана. Возвращает текст уведомления или None."""
        raw = self.config.unity_project
        if not raw:
            return None
        project = Path(raw).expanduser().resolve()
        fp = folder_fingerprint(project)
        if not fp:
            return None
        if fp == self.state.last_fingerprint:
            return None

        self.state.last_fingerprint = fp
        scan = scan_animations_folder(project)
        self.state.last_scan_summary = scan.render()
        self.state.pending_questions = scan.questions

        lines = ["Обнаружены изменения в Animations/."]
        for c in scan.clips:
            if c.suggested_state and not c.needs_question:
                lines.append(f"  + {c.file_name} → {c.suggested_state}")
        if scan.questions:
            lines.append("Нужны уточнения — спроси Viu или допиши viu_clips.json")

        auto = self.config.unity_auto_sync
        if auto and not scan.questions and scan.has_new_actionable:
            msg = self._try_batch_sync(project)
            lines.append(msg)

        if not auto or scan.questions:
            lines.append(
                "Unity открыт → импорт подхватится сам (Viu Sync). "
                "Иначе: меню Viu → Sync Animations или unity_sync_animations."
            )

        text = "\n".join(lines)
        self.state.notifications.append(text)
        self._save_state()
        self._notify(text)
        return text

    def _try_batch_sync(self, project: Path) -> str:
        deploy_animation_pipeline(project)
        exe = find_unity_exe(self.config.unity_exe)
        if exe is None:
            return "VIU_UNITY_EXE не задан — batch sync пропущен."
        import subprocess

        cmd = batch_sync_animations_command(project, exe)
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=600, cwd=str(project)
            )
        except subprocess.TimeoutExpired:
            return "Batch sync: таймаут 600s (закрой Unity и повтори)."
        if proc.returncode == 0:
            return "Batch sync: Animator обновлён."
        return f"Batch sync: exit {proc.returncode} (см. viu_anim_sync.log)"

    def _notify(self, text: str) -> None:
        if self.on_notify:
            self.on_notify(text)

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_fingerprint": self.state.last_fingerprint,
            "pending_questions": self.state.pending_questions,
            "last_scan": self.state.last_scan_summary,
        }
        self._state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            self.state.last_fingerprint = data.get("last_fingerprint", "")
            self.state.pending_questions = data.get("pending_questions", [])
        except (json.JSONDecodeError, OSError):
            pass
