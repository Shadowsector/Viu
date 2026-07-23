"""Запуск GUI без консоли — двойной клик, VBS, ярлык.

Пишет ошибки в viu_startup.log и показывает окно, если что-то сломалось.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "viu_startup.log"
STATUS = ROOT / ".viu_launch_status"
STARTED = ROOT / ".viu_gui_started"


def _ensure_path() -> None:
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _set_status(msg: str) -> None:
    try:
        STATUS.write_text(msg, encoding="utf-8")
    except OSError:
        pass


def _mark_started() -> None:
    try:
        STARTED.write_text("ok\n", encoding="utf-8")
        _set_status("running")
    except OSError:
        pass


def _show_error(text: str) -> None:
    print(text, file=sys.stderr)
    try:
        LOG.write_text(text, encoding="utf-8")
    except OSError:
        pass
    _set_status("crash")
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Вью — ошибка запуска",
            text[:2000] + f"\n\nПодробности: {LOG}",
        )
        root.destroy()
    except Exception:
        pass


def main() -> int:
    _ensure_path()
    try:
        if STARTED.exists():
            STARTED.unlink()
    except OSError:
        pass
    try:
        from viu.env_file import bootstrap_env
        from viu.net_env import apply_proxy_scrub_to_process

        _set_status("loading")
        bootstrap_env(ROOT)
        apply_proxy_scrub_to_process()
        from viu.gui import main as gui_main

        return gui_main()
    except Exception:
        _show_error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
