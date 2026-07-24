"""GUI: просмотр и правка Comfy MoCap промпта."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ...config import Config
from ...lab.comfy_pipeline import COMFY_TOPIC, apply_prompt_decision
from ...lab.session import load_session, new_session, save_session
from .prompt_edit import apply_draft_to_session, prompt_draft_text


def open_comfy_prompt_editor(
    master: tk.Misc,
    config: Config,
    *,
    on_finished: Optional[Callable[[bool, str], None]] = None,
) -> None:
    session = load_session(config, COMFY_TOPIC)
    if session is None:
        session = new_session(COMFY_TOPIC)
        save_session(config, session)

    win = tk.Toplevel(master)
    win.title("Вью — промпт Comfy MoCap")
    win.geometry("760x620")
    win.minsize(640, 480)

    body = ttk.Frame(win, padding=10)
    body.pack(fill="both", expand=True)

    ttk.Label(
        body,
        text=(
            "Полный черновик для Wan (действие, positive, negative, кадр).\n"
            "«Сохранить» — в сессию lab/comfy; «Сохранить и снять» — одобрить и продолжить lab."
        ),
        wraplength=720,
    ).pack(anchor="w", pady=(0, 8))

    txt = tk.Text(body, wrap="word", font=("Consolas", 10))
    txt.pack(fill="both", expand=True)
    txt.insert("1.0", prompt_draft_text(config))

    def do_save(*, approve: bool) -> None:
        body_text = txt.get("1.0", "end").strip()
        if not body_text:
            messagebox.showerror("Промпт", "Пустой текст.", parent=win)
            return
        sess = load_session(config, COMFY_TOPIC) or session
        ok, msg = apply_draft_to_session(config, sess, body_text)
        if not ok:
            messagebox.showerror("Промпт", msg, parent=win)
            return
        if approve:
            sess = load_session(config, COMFY_TOPIC) or sess
            if sess.status == "awaiting_prompt":
                msg2 = apply_prompt_decision(
                    config,
                    sess,
                    "approve",
                    str(sess.meta.get("action") or ""),
                )
                msg = msg + "\n\n" + msg2
            else:
                msg += "\n\nСессия не ждёт одобрения — override применится на следующей генерации."
        win.destroy()
        if on_finished:
            on_finished(True, msg)

    btns = ttk.Frame(body)
    btns.pack(fill="x", pady=(8, 0))
    ttk.Button(btns, text="Сохранить", command=lambda: do_save(approve=False)).pack(side="left")
    ttk.Button(btns, text="Сохранить и снять", command=lambda: do_save(approve=True)).pack(
        side="left", padx=8
    )
    ttk.Button(btns, text="Закрыть", command=win.destroy).pack(side="right")
