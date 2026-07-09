"""Запуск GUI без консоли — двойной клик, VBS, ярлык.

Пишет ошибки в viu_startup.log и показывает окно, если что-то сломалось.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "viu_startup.log"


def _ensure_path() -> None:
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def _show_error(text: str) -> None:
    print(text, file=sys.stderr)
    LOG.write_text(text, encoding="utf-8")
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
        from viu.env_file import load_env_file

        load_env_file(ROOT)
        from viu.gui import main as gui_main

        return gui_main()
    except Exception:
        _show_error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
