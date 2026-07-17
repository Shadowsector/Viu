"""GUI: оценка работы лаборатории по нескольким критериям."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Optional

from ..config import Config
from ..lab.ratings import LAB_CRITERIA
from ..lab.session import load_session, save_session


def open_lab_rating_review(
    master: tk.Misc,
    config: Config,
    topic: str = "cascadeur",
    *,
    on_finished: Optional[Callable[[bool, str], None]] = None,
) -> None:
    session = load_session(config, topic)
    if session is None:
        if on_finished:
            on_finished(False, "Нет lab-сессии")
        return

    win = tk.Toplevel(master)
    win.title("Вью — оценка лаборатории")
    win.geometry("520x520")
    win.transient(master)

    ttk.Label(
        win,
        text=f"Lab: {topic} — оцени работу Вью (1 = слабо, 5 = отлично)",
        wraplength=480,
    ).pack(anchor="w", padx=12, pady=(12, 8))

    if session.last_report:
        txt = tk.Text(win, height=8, wrap="word", font=("Segoe UI", 9))
        txt.pack(fill="x", padx=12, pady=4)
        txt.insert("1.0", session.last_report[:2500])
        txt.config(state="disabled")

    scales: Dict[str, tk.IntVar] = {}
    for cid, title, hint in LAB_CRITERIA:
        row = ttk.Frame(win)
        row.pack(fill="x", padx=12, pady=4)
        ttk.Label(row, text=title, width=16).pack(side="left")
        var = tk.IntVar(value=3)
        scales[cid] = var
        ttk.Scale(row, from_=1, to=5, orient="horizontal", variable=var, length=220).pack(
            side="left", padx=8
        )
        ttk.Label(row, text=hint, wraplength=200, font=("Segoe UI", 8)).pack(side="left")

    ttk.Label(win, text="Комментарий (опционально):").pack(anchor="w", padx=12, pady=(8, 0))
    notes = tk.Text(win, height=3, wrap="word")
    notes.pack(fill="x", padx=12, pady=4)

    def submit() -> None:
        values = {cid: int(var.get()) for cid, var in scales.items()}
        session.ratings = values
        session.rating_notes = notes.get("1.0", "end").strip()
        session.status = "completed"
        save_session(config, session)
        from ..lab.session import append_journal
        from ..lab.ratings import average_score

        avg = average_score(values)
        append_journal(
            config,
            topic,
            f"### Оценка (GUI)\n\n{values}\n\n{session.rating_notes}\n\nСреднее: {avg:.1f}/5",
        )
        win.destroy()
        if on_finished:
            on_finished(True, f"Оценки сохранены. Среднее {avg:.1f}/5")

    def skip() -> None:
        win.destroy()
        if on_finished:
            on_finished(False, "Оценка отменена")

    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=12, pady=12)
    ttk.Button(btns, text="Сохранить оценки", command=submit).pack(side="left")
    ttk.Button(btns, text="Позже", command=skip).pack(side="left", padx=8)
