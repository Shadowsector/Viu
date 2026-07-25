"""GUI: библиотека эталонов I2V — импорт HS2, доработка, start/end на анимацию."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, List, Optional

from ...config import Config
from ...inbox_layout import inbox_references_dir
from .seed_library import (
    SeedEntry,
    accept_refined,
    activate_seed,
    bind_seed_to_slug,
    format_library_brief,
    import_seed,
    load_library,
    prepare_refine,
    seeds_for_slug,
)


def open_seed_library(
    master: tk.Misc,
    config: Config,
    *,
    on_finished: Optional[Callable[[bool, str], None]] = None,
    default_slug: str = "",
) -> None:
    win = tk.Toplevel(master)
    win.title("Эталоны I2V — библиотека")
    win.geometry("980x720")
    win.minsize(800, 560)

    body = ttk.Frame(win, padding=10)
    body.pack(fill="both", expand=True)

    ttk.Label(
        body,
        text=(
            "Скрин из HS2 → Inbox/references → «Из Inbox (HS2)». "
            "«Доработать» снимет описание позы и пометит под натуральное тело; "
            "потом «Принять доработанный». "
            "Привяжи start/end к slug анимации — съёмка подхватит сама."
        ),
        wraplength=940,
    ).pack(anchor="w", pady=(0, 8))

    paned = ttk.Panedwindow(body, orient="horizontal")
    paned.pack(fill="both", expand=True)
    left = ttk.Frame(paned)
    right = ttk.Frame(paned, padding=(8, 0, 0, 0))
    paned.add(left, weight=1)
    paned.add(right, weight=2)

    listbox = tk.Listbox(left, font=("Consolas", 10), height=24)
    listbox.pack(fill="both", expand=True)
    left_btns = ttk.Frame(left)
    left_btns.pack(fill="x", pady=(6, 0))

    title_var = tk.StringVar()
    slug_var = tk.StringVar(value=default_slug or "")
    status_var = tk.StringVar()
    path_var = tk.StringVar()
    notes_txt = tk.Text(right, height=12, wrap="word", font=("Consolas", 9))

    ttk.Label(right, text="Название").pack(anchor="w")
    ttk.Entry(right, textvariable=title_var).pack(fill="x", pady=(0, 4))
    ttk.Label(right, text="Анимация (catalog_slug)").pack(anchor="w")
    ttk.Entry(right, textvariable=slug_var).pack(fill="x", pady=(0, 4))
    ttk.Label(right, textvariable=status_var, wraplength=520).pack(anchor="w", pady=(0, 4))
    ttk.Label(right, textvariable=path_var, wraplength=520).pack(anchor="w", pady=(0, 4))
    ttk.Label(right, text="Заметки / vision").pack(anchor="w")
    notes_txt.pack(fill="both", expand=True)

    bind_row = ttk.Frame(right)
    bind_row.pack(fill="x", pady=(8, 0))
    act_row = ttk.Frame(right)
    act_row.pack(fill="x", pady=(6, 0))

    entries: List[SeedEntry] = []

    def refresh(*, select_id: str = "") -> None:
        nonlocal entries
        entries = load_library(config)
        listbox.delete(0, "end")
        for e in entries:
            listbox.insert("end", e.label())
        if select_id:
            for i, e in enumerate(entries):
                if e.id == select_id:
                    listbox.selection_set(i)
                    listbox.see(i)
                    show(e)
                    return
        if entries:
            listbox.selection_set(0)
            show(entries[0])
        else:
            show(None)

    def current() -> Optional[SeedEntry]:
        sel = listbox.curselection()
        if not sel:
            return None
        i = int(sel[0])
        if 0 <= i < len(entries):
            return entries[i]
        return None

    def show(e: Optional[SeedEntry]) -> None:
        if e is None:
            title_var.set("")
            status_var.set("")
            path_var.set("")
            notes_txt.delete("1.0", "end")
            return
        title_var.set(e.title)
        if e.slug:
            slug_var.set(e.slug)
        bound = seeds_for_slug(config, slug_var.get().strip() or e.slug)
        b_start = bound["start"].label() if bound.get("start") else "—"
        b_end = bound["end"].label() if bound.get("end") else "—"
        status_var.set(
            f"id={e.id} · {e.source} · {e.status}\n"
            f"Для slug «{slug_var.get() or e.slug or '—'}»: start={b_start} · end={b_end}"
        )
        p = e.resolve_path()
        path_var.set(str(p) if p else e.path)
        notes_txt.delete("1.0", "end")
        notes_txt.insert("1.0", e.notes or e.en_pose or "")

    def on_select(_evt=None) -> None:
        show(current())

    def do_import(*, from_hs2: bool, from_inbox: bool) -> None:
        initial = str(inbox_references_dir(config)) if from_inbox else None
        path = filedialog.askopenfilename(
            parent=win,
            title="Скрин эталона (HS2 / фото)" if from_hs2 else "Эталон позы",
            initialdir=initial,
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp"),
                ("All", "*.*"),
            ],
        )
        if not path:
            return
        slug = slug_var.get().strip()
        ok, msg, entry = import_seed(
            config,
            Path(path),
            title=Path(path).stem,
            slug=slug,
            from_hs2=from_hs2,
            activate=False,
        )
        if ok and entry is not None:
            refresh(select_id=entry.id)
            messagebox.showinfo("Эталон", msg, parent=win)
        else:
            messagebox.showerror("Эталон", msg, parent=win)

    def on_refine() -> None:
        e = current()
        if e is None:
            return
        ok, msg = prepare_refine(config, e.id)
        refresh(select_id=e.id)
        if ok:
            messagebox.showinfo("Доработать", msg, parent=win)
        else:
            messagebox.showerror("Доработать", msg, parent=win)

    def on_accept_refined() -> None:
        e = current()
        if e is None:
            return
        path = filedialog.askopenfilename(
            parent=win,
            title="Доработанный эталон (натуральное тело)",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All", "*.*")],
        )
        if not path:
            return
        ok, msg = accept_refined(config, e.id, Path(path), activate=False)
        refresh(select_id=e.id)
        if ok:
            messagebox.showinfo("Эталон", msg, parent=win)
        else:
            messagebox.showerror("Эталон", msg, parent=win)

    def on_bind(role: str) -> None:
        e = current()
        if e is None:
            return
        slug = slug_var.get().strip() or e.slug
        if not slug:
            slug = simpledialog.askstring(
                "Slug", "catalog_slug анимации (например sleep_idle):", parent=win
            ) or ""
        slug = slug.strip()
        if not slug:
            return
        slug_var.set(slug)
        ok, msg = bind_seed_to_slug(config, slug, e.id, role=role)
        refresh(select_id=e.id)
        if ok:
            messagebox.showinfo("Привязка", msg, parent=win)
        else:
            messagebox.showerror("Привязка", msg, parent=win)

    def on_activate(role: str) -> None:
        e = current()
        if e is None:
            return
        ok, msg = activate_seed(config, e.id, role=role)
        if ok:
            messagebox.showinfo("I2V", msg, parent=win)
        else:
            messagebox.showerror("I2V", msg, parent=win)

    def on_close() -> None:
        msg = format_library_brief(config)
        win.destroy()
        if on_finished:
            on_finished(True, msg)

    listbox.bind("<<ListboxSelect>>", on_select)

    ttk.Button(
        left_btns, text="Из Inbox (HS2)", command=lambda: do_import(from_hs2=True, from_inbox=True)
    ).pack(side="left")
    ttk.Button(
        left_btns, text="Файл…", command=lambda: do_import(from_hs2=False, from_inbox=False)
    ).pack(side="left", padx=4)

    ttk.Button(bind_row, text="→ start этой анимации", command=lambda: on_bind("start")).pack(
        side="left"
    )
    ttk.Button(bind_row, text="→ end этой анимации", command=lambda: on_bind("end")).pack(
        side="left", padx=6
    )

    ttk.Button(act_row, text="Доработать", command=on_refine).pack(side="left")
    ttk.Button(act_row, text="Принять доработанный…", command=on_accept_refined).pack(
        side="left", padx=6
    )
    ttk.Button(act_row, text="Сделать start сейчас", command=lambda: on_activate("start")).pack(
        side="left", padx=6
    )
    ttk.Button(act_row, text="Сделать end сейчас", command=lambda: on_activate("end")).pack(
        side="left"
    )

    bottom = ttk.Frame(body)
    bottom.pack(fill="x", pady=(8, 0))
    ttk.Button(bottom, text="Закрыть", command=on_close).pack(side="right")

    refresh()
