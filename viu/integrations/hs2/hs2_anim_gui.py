"""GUI: HS2 анимации → Inbox."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ..config import Config
from ..integrations.hs2 import (
    hs2_fbx_dump_dir,
    import_fbx_dump,
    resolve_hs2_root,
    retarget_first_dump,
    scan_abdata,
)
from ..integrations.hs2.paths import default_retarget_rig_path


def open_hs2_anim_window(
    root: tk.Misc,
    config: Config,
    *,
    on_finished: Optional[Callable[[bool, str], None]] = None,
) -> None:
    win = tk.Toplevel(root)
    win.title("HS2 → анимации Шани")
    win.geometry("640x420")
    win.transient(root)

    hs2 = resolve_hs2_root(config)
    dump = hs2_fbx_dump_dir(config)
    rig = default_retarget_rig_path(config)

    head = ttk.Label(
        win,
        text=(
            "1) MeshExporter / Studio: FBX в fbx_dump\n"
            "2) «В Inbox» или «Ретаргет» (нужен Mixamo X Bot)\n"
            "3) Unity — «Принять анимацию (Inbox)»"
        ),
        justify=tk.LEFT,
    )
    head.pack(fill=tk.X, padx=10, pady=8)

    info = ttk.Label(win, text="", justify=tk.LEFT)
    info.pack(fill=tk.X, padx=10)

    def refresh_info() -> None:
        n = len(list(dump.rglob("*.fbx")))
        info.configure(
            text=(
                f"HS2: {hs2 or 'не найден (VIU_HS2_ROOT)'}\n"
                f"Дамп: {dump} ({n} FBX)\n"
                f"Риг: {rig or 'нет Mixamo_XBot.fbx'}"
            )
        )

    refresh_info()

    log = tk.Text(win, height=12, wrap=tk.WORD)
    log.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

    def append(msg: str) -> None:
        log.insert(tk.END, msg + "\n")
        log.see(tk.END)

    def finish(ok: bool, msg: str) -> None:
        append(msg)
        if on_finished:
            on_finished(ok, msg)

    btns = ttk.Frame(win)
    btns.pack(fill=tk.X, padx=10, pady=6)

    def do_scan() -> None:
        r = scan_abdata(config, use_cache=False)
        append(r.format_brief(limit=30))

    def do_import() -> None:
        rep = import_fbx_dump(config, limit=30)
        append(rep.format())
        finish(rep.ok, rep.format())

    def do_retarget() -> None:
        ok, msg = retarget_first_dump(config)
        append(msg)
        finish(ok, msg)

    ttk.Button(btns, text="Скан abdata", command=do_scan).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="FBX дамп → Inbox", command=do_import).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="Ретаргет (Blender)", command=do_retarget).pack(side=tk.LEFT, padx=4)
    ttk.Button(btns, text="Закрыть", command=win.destroy).pack(side=tk.RIGHT, padx=4)
