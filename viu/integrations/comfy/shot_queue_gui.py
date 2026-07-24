"""Окно очереди MoCap: что снимется дальше, правка промптов до ухода на работу."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, List, Optional

from ...config import Config
from .shot_queue import (
    ShotQueueItem,
    format_queue_brief,
    load_items,
    move_item,
    rebuild_queue,
    save_items,
    update_item,
)


def open_shot_queue_editor(
    master: tk.Misc,
    config: Config,
    *,
    on_finished: Optional[Callable[[bool, str], None]] = None,
    on_edit_prompt: Optional[Callable[[], None]] = None,
) -> None:
    win = tk.Toplevel(master)
    win.title("Очередь MoCap — план съёмки")
    win.geometry("960x700")
    win.minsize(780, 560)

    body = ttk.Frame(win, padding=10)
    body.pack(fill="both", expand=True)

    ttk.Label(
        body,
        text=(
            "Список кадров, которые Вью снимет по порядку (дома и «Нет дома»). "
            "Подкрути action / positive / negative, пропусти лишнее, затем иди на работу — "
            "away пойдёт по этой очереди, а не выдумает touch_self поверх sit."
        ),
        wraplength=920,
    ).pack(anchor="w", pady=(0, 8))

    paned = ttk.Panedwindow(body, orient="horizontal")
    paned.pack(fill="both", expand=True)

    left = ttk.Frame(paned, padding=(0, 0, 8, 0))
    right = ttk.Frame(paned)
    paned.add(left, weight=1)
    paned.add(right, weight=2)

    listbox = tk.Listbox(left, font=("Consolas", 10), height=22)
    listbox.pack(fill="both", expand=True)
    list_btns = ttk.Frame(left)
    list_btns.pack(fill="x", pady=(6, 0))

    slug_var = tk.StringVar()
    action_var = tk.StringVar()
    title_var = tk.StringVar()
    notes_var = tk.StringVar()
    status_var = tk.StringVar()

    ttk.Label(right, text="Slug").pack(anchor="w")
    ttk.Entry(right, textvariable=slug_var).pack(fill="x", pady=(0, 4))
    ttk.Label(right, text="Название").pack(anchor="w")
    ttk.Entry(right, textvariable=title_var).pack(fill="x", pady=(0, 4))
    ttk.Label(right, text="Действие / Action").pack(anchor="w")
    ttk.Entry(right, textvariable=action_var).pack(fill="x", pady=(0, 4))
    ttk.Label(right, text="Заметка для Вью (наругать / уточнить)").pack(anchor="w")
    ttk.Entry(right, textvariable=notes_var).pack(fill="x", pady=(0, 4))
    ttk.Label(right, text="Статус").pack(anchor="w")
    ttk.Label(right, textvariable=status_var).pack(anchor="w", pady=(0, 6))

    ttk.Label(right, text="Positive (Wan)").pack(anchor="w")
    pos_txt = tk.Text(right, height=8, wrap="word", font=("Consolas", 9))
    pos_txt.pack(fill="both", expand=True, pady=(0, 4))
    ttk.Label(right, text="Negative").pack(anchor="w")
    neg_txt = tk.Text(right, height=4, wrap="word", font=("Consolas", 9))
    neg_txt.pack(fill="both", expand=True, pady=(0, 4))

    items: List[ShotQueueItem] = []
    selected_id: Optional[str] = None

    def refresh_list(*, select_id: Optional[str] = None) -> None:
        nonlocal items
        items = load_items(config)
        listbox.delete(0, "end")
        for it in items:
            mark = {"pending": "·", "done": "✓", "skipped": "✗"}.get(it.status, "?")
            title = it.title_ru or it.catalog_slug or "?"
            listbox.insert("end", f"{mark} {it.catalog_slug} — {title[:40]}")
        if select_id:
            for i, it in enumerate(items):
                if it.id == select_id:
                    listbox.selection_clear(0, "end")
                    listbox.selection_set(i)
                    listbox.see(i)
                    break

    def current_item() -> Optional[ShotQueueItem]:
        sel = listbox.curselection()
        if not sel:
            return None
        i = int(sel[0])
        if 0 <= i < len(items):
            return items[i]
        return None

    def show_item(it: Optional[ShotQueueItem]) -> None:
        nonlocal selected_id
        selected_id = it.id if it else None
        if it is None:
            slug_var.set("")
            title_var.set("")
            action_var.set("")
            notes_var.set("")
            status_var.set("")
            pos_txt.delete("1.0", "end")
            neg_txt.delete("1.0", "end")
            return
        slug_var.set(it.catalog_slug)
        title_var.set(it.title_ru)
        action_var.set(it.action)
        notes_var.set(it.notes)
        status_var.set(it.status)
        pos_txt.delete("1.0", "end")
        pos_txt.insert("1.0", it.wan_positive)
        neg_txt.delete("1.0", "end")
        neg_txt.insert("1.0", it.wan_negative)

    def on_select(_evt=None) -> None:
        show_item(current_item())

    def save_current() -> bool:
        it = current_item()
        if it is None:
            return False
        update_item(
            config,
            it.id,
            catalog_slug=slug_var.get().strip(),
            title_ru=title_var.get().strip(),
            action=action_var.get().strip(),
            notes=notes_var.get().strip(),
            wan_positive=pos_txt.get("1.0", "end").strip(),
            wan_negative=neg_txt.get("1.0", "end").strip(),
        )
        refresh_list(select_id=it.id)
        return True

    def on_rebuild() -> None:
        save_current()
        rebuilt = rebuild_queue(config, limit=8, keep_edits=True)
        refresh_list(select_id=rebuilt[0].id if rebuilt else None)
        if rebuilt:
            show_item(rebuilt[0])
        messagebox.showinfo(
            "Очередь",
            f"Собрала {len(rebuilt)} кадров.\n{format_queue_brief(config)}",
            parent=win,
        )

    def on_skip() -> None:
        it = current_item()
        if it is None:
            return
        save_current()
        update_item(config, it.id, status="skipped")
        refresh_list()
        show_item(current_item())

    def on_pending() -> None:
        it = current_item()
        if it is None:
            return
        save_current()
        update_item(config, it.id, status="pending")
        refresh_list(select_id=it.id)

    def on_up() -> None:
        it = current_item()
        if it is None:
            return
        save_current()
        move_item(config, it.id, delta=-1)
        refresh_list(select_id=it.id)

    def on_down() -> None:
        it = current_item()
        if it is None:
            return
        save_current()
        move_item(config, it.id, delta=1)
        refresh_list(select_id=it.id)

    def on_clear_done() -> None:
        keep = [i for i in load_items(config) if i.status == "pending"]
        save_items(config, keep)
        refresh_list()
        show_item(current_item())

    def on_save_close() -> None:
        save_current()
        msg = format_queue_brief(config)
        win.destroy()
        if on_finished:
            on_finished(True, msg)

    listbox.bind("<<ListboxSelect>>", on_select)

    ttk.Button(list_btns, text="Собрать / обновить", command=on_rebuild).pack(
        side="left"
    )
    ttk.Button(list_btns, text="↑", width=3, command=on_up).pack(side="left", padx=4)
    ttk.Button(list_btns, text="↓", width=3, command=on_down).pack(side="left")

    edit_btns = ttk.Frame(right)
    edit_btns.pack(fill="x", pady=(6, 0))
    ttk.Button(edit_btns, text="Сохранить строку", command=save_current).pack(side="left")
    ttk.Button(edit_btns, text="Пропустить", command=on_skip).pack(side="left", padx=6)
    ttk.Button(edit_btns, text="Вернуть в очередь", command=on_pending).pack(side="left")
    if on_edit_prompt:
        ttk.Button(
            edit_btns, text="Промпт Wan (текущий lab)", command=on_edit_prompt
        ).pack(side="left", padx=6)

    bottom = ttk.Frame(body)
    bottom.pack(fill="x", pady=(8, 0))
    ttk.Button(bottom, text="Убрать done/skipped", command=on_clear_done).pack(
        side="left"
    )
    ttk.Button(bottom, text="Сохранить и закрыть", command=on_save_close).pack(
        side="right"
    )
    ttk.Button(bottom, text="Закрыть", command=win.destroy).pack(side="right", padx=8)

    items = load_items(config)
    if not items:
        items = rebuild_queue(config, limit=8)
    refresh_list(select_id=items[0].id if items else None)
    if items:
        listbox.selection_set(0)
        show_item(items[0])
