"""GUI: выбрать лучший Comfy-клип из тройки ракурсов."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ...config import Config
from ...lab.comfy_pipeline import COMFY_TOPIC, apply_clip_pick_decision
from ...lab.session import load_session, save_session
from .clip_review import (
    STATUS_CANDIDATE,
    ComfyClipStore,
    clip_review_path,
    keep_clip,
    reject_batch,
)


def open_comfy_clip_review(
    master: tk.Misc,
    config: Config,
    *,
    on_finished: Optional[Callable[[bool, str], None]] = None,
) -> None:
    store = ComfyClipStore(clip_review_path(config)).load()
    session = load_session(config, COMFY_TOPIC)
    batch = ""
    if session is not None:
        batch = str(session.meta.get("clip_batch_id") or "")
    candidates = store.by_batch(batch) if batch else store.pending_candidates()
    candidates = [c for c in candidates if c.status == STATUS_CANDIDATE]
    if not candidates:
        messagebox.showinfo("Comfy клипы", "Нет кандидатов на оценку.", parent=master)
        if on_finished:
            on_finished(False, "Нет кандидатов.")
        return

    win = tk.Toplevel(master)
    win.title("Вью — выбрать клип для MoCap")
    win.geometry("720x520")
    win.minsize(640, 420)

    body = ttk.Frame(win, padding=10)
    body.pack(fill="both", expand=True)

    ttk.Label(
        body,
        text=(
            "Оставь лучший ракурс → kept/ + last-frame seed для следующей анимации.\n"
            "Остальные уйдут в rejected/."
        ),
        wraplength=680,
    ).pack(anchor="w", pady=(0, 8))

    chosen = tk.StringVar(value=candidates[0].id)
    for c in candidates:
        row = ttk.Frame(body)
        row.pack(fill="x", pady=2)
        ttk.Radiobutton(
            row,
            text=f"[{c.angle}] {c.angle_label}",
            variable=chosen,
            value=c.id,
        ).pack(side="left")
        ttk.Label(row, text=Path(c.path).name, foreground="#555").pack(side="left", padx=8)

    form = ttk.Frame(body)
    form.pack(fill="x", pady=10)
    ttk.Label(form, text="Оценка 1–5").grid(row=0, column=0, sticky="w")
    score_var = tk.StringVar(value="4")
    ttk.Combobox(form, textvariable=score_var, values=["1", "2", "3", "4", "5"], width=5).grid(
        row=0, column=1, sticky="w", padx=6
    )
    ttk.Label(form, text="Slug каталога").grid(row=1, column=0, sticky="w", pady=4)
    slug_var = tk.StringVar(value="")
    ttk.Entry(form, textvariable=slug_var, width=40).grid(row=1, column=1, sticky="w", padx=6)
    ttk.Label(form, text="enters_from (через запятую)").grid(row=2, column=0, sticky="w")
    enters_var = tk.StringVar(value="")
    ttk.Entry(form, textvariable=enters_var, width=40).grid(row=2, column=1, sticky="w", padx=6)
    ttk.Label(form, text="exits_to (через запятую)").grid(row=3, column=0, sticky="w", pady=4)
    exits_var = tk.StringVar(value="")
    ttk.Entry(form, textvariable=exits_var, width=40).grid(row=3, column=1, sticky="w", padx=6)
    ttk.Label(form, text="Заметки").grid(row=4, column=0, sticky="nw")
    notes = tk.Text(form, height=3, width=48)
    notes.grid(row=4, column=1, sticky="w", padx=6, pady=4)

    def _split_csv(raw: str) -> list[str]:
        return [p.strip() for p in raw.split(",") if p.strip()]

    def do_keep() -> None:
        cid = chosen.get()
        clip = next((c for c in candidates if c.id == cid), None)
        if clip is None:
            messagebox.showerror("Comfy", "Клип не найден", parent=win)
            return
        try:
            score = int(score_var.get())
        except ValueError:
            score = 4
        sess = load_session(config, COMFY_TOPIC)
        if sess is not None:
            sess.meta["catalog_slug"] = slug_var.get().strip()
            sess.meta["enters_from"] = _split_csv(enters_var.get())
            sess.meta["exits_to"] = _split_csv(exits_var.get())
            save_session(config, sess)
            msg = apply_clip_pick_decision(
                config,
                sess,
                "keep",
                {
                    "angle": clip.angle,
                    "score": score,
                    "notes": notes.get("1.0", "end").strip(),
                },
            )
        else:
            ok, msg, _ = keep_clip(
                config,
                cid,
                score=score,
                notes=notes.get("1.0", "end").strip(),
                catalog_slug=slug_var.get().strip(),
                enters_from=_split_csv(enters_var.get()),
                exits_to=_split_csv(exits_var.get()),
            )
            if not ok:
                messagebox.showerror("Comfy", msg, parent=win)
                return
        win.destroy()
        if on_finished:
            on_finished(True, msg)

    def do_reject() -> None:
        b = batch or (candidates[0].batch_id if candidates else "")
        ok, msg = reject_batch(config, b)
        sess = load_session(config, COMFY_TOPIC)
        if sess is not None and sess.status == "awaiting_clip_pick":
            apply_clip_pick_decision(config, sess, "reject_all", {})
        win.destroy()
        if on_finished:
            on_finished(ok, msg)

    btns = ttk.Frame(body)
    btns.pack(fill="x", pady=(8, 0))
    ttk.Button(btns, text="✓ Оставить выбранный", command=do_keep).pack(side="left")
    ttk.Button(btns, text="Отклонить все", command=do_reject).pack(side="left", padx=8)
    ttk.Button(btns, text="Закрыть", command=win.destroy).pack(side="right")
