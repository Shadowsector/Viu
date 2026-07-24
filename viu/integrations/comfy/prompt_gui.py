"""GUI: Wan-промпт, который реально уходит в Comfy."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ...config import Config
from ...lab.comfy_pipeline import COMFY_TOPIC, apply_prompt_decision
from ...lab.session import load_session, new_session, save_session
from .prompt_edit import apply_draft_to_session, format_wan_editor_text

FinishedCb = Callable[..., None]


def open_comfy_prompt_editor(
    master: tk.Misc,
    config: Config,
    *,
    on_finished: Optional[FinishedCb] = None,
) -> None:
    session = load_session(config, COMFY_TOPIC)
    if session is None:
        session = new_session(COMFY_TOPIC)
        save_session(config, session)

    win = tk.Toplevel(master)
    win.title("Промпт Wan → Comfy")
    win.geometry("820x640")
    win.minsize(680, 520)

    body = ttk.Frame(win, padding=10)
    body.pack(fill="both", expand=True)

    ttk.Label(
        body,
        text=(
            "Редактируй строки Wan ниже.\n"
            "«Отправить в Comfy» — сохранить промпт.\n"
            "«Отправить и снять» — сохранить и сразу поставить jobs в очередь Comfy "
            "(граф в браузере может остаться пустым — это API, не canvas)."
        ),
        wraplength=780,
    ).pack(anchor="w", pady=(0, 8))

    txt = tk.Text(body, wrap="word", font=("Consolas", 10))
    txt.pack(fill="both", expand=True)
    txt.insert("1.0", format_wan_editor_text(config))

    def do_send(*, approve: bool) -> None:
        body_text = txt.get("1.0", "end").strip()
        if not body_text:
            messagebox.showerror("Промпт", "Пустой текст.", parent=win)
            return
        sess = load_session(config, COMFY_TOPIC) or session
        ok, msg = apply_draft_to_session(config, sess, body_text)
        if not ok:
            messagebox.showerror("Промпт", msg, parent=win)
            return
        start_shoot = False
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
                start_shoot = True
            else:
                # Не в awaiting — всё равно пометить shoot и запустить lab
                sess.meta["approved"] = True
                sess.meta["approved_action"] = str(
                    sess.meta.get("action") or sess.meta.get("approved_action") or ""
                )
                sess.meta["shoot_intent"] = True
                sess.meta["auto_approved_shoot"] = True
                sess.meta.pop("lora_pick_done", None)
                if sess.status in ("idle", "completed", "paused"):
                    sess.status = "running"
                    if sess.step < 3:
                        sess.step = 3
                save_session(config, sess)
                msg += (
                    "\n\nЗапускаю съёмку с этим промптом "
                    "(очередь Comfy через API — граф в браузере может быть пустым)."
                )
                start_shoot = True
        win.destroy()
        if on_finished:
            on_finished(True, msg, start_shoot)

    btns = ttk.Frame(body)
    btns.pack(fill="x", pady=(8, 0))
    ttk.Button(btns, text="Отправить в Comfy", command=lambda: do_send(approve=False)).pack(
        side="left"
    )
    ttk.Button(btns, text="Отправить и снять", command=lambda: do_send(approve=True)).pack(
        side="left", padx=8
    )
    ttk.Button(btns, text="Закрыть", command=win.destroy).pack(side="right")
