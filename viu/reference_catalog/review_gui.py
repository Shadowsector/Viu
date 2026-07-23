"""Окно референсов — скан inbox, LLaVA-описание, заметки."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ..config import Config
from .models import ReferenceEntry
from .scanner import scan_references_inbox
from .store import ReferenceCatalogStore


class ReferenceReviewWindow:
    def __init__(
        self,
        master: tk.Misc,
        config: Config,
        store: ReferenceCatalogStore,
        *,
        on_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.config = config
        self.store = store
        self.on_closed = on_closed
        self._current: Optional[ReferenceEntry] = None

        self.win = tk.Toplevel(master)
        self.win.title("Вью — референсы")
        self.win.geometry("900x620")
        self.win.minsize(760, 520)
        self.win.protocol("WM_DELETE_WINDOW", self._close)

        body = ttk.Frame(self.win, padding=10)
        body.pack(fill="both", expand=True)

        self.status = ttk.Label(body, text="", font=("Segoe UI", 10, "bold"))
        self.status.pack(anchor="w", pady=(0, 6))

        ttk.Label(
            body,
            text="Клади картинки и видео в Inbox/references/. "
            "«LLaVA» — авто-описание для Comfy. Без подпапок в каталоге.",
            wraplength=840,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 8))

        split = ttk.Panedwindow(body, orient="horizontal")
        split.pack(fill="both", expand=True)

        left = ttk.Frame(split)
        split.add(left, weight=1)
        self.listbox = tk.Listbox(left, height=16, font=("Segoe UI", 10))
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scroll.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        right = ttk.Frame(split, padding=6)
        split.add(right, weight=2)

        self.title_var = tk.StringVar()
        ttk.Label(right, text="Название").grid(row=0, column=0, sticky="w")
        ttk.Entry(right, textvariable=self.title_var, width=60).grid(
            row=0, column=1, sticky="ew", pady=2
        )

        ttk.Label(right, text="RU (что на кадре)").grid(row=1, column=0, sticky="nw")
        self.ru = tk.Text(right, height=4, width=60, font=("Segoe UI", 10))
        self.ru.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(right, text="EN pose").grid(row=2, column=0, sticky="nw")
        self.en_pose = tk.Text(right, height=2, width=60, font=("Segoe UI", 9))
        self.en_pose.grid(row=2, column=1, sticky="ew", pady=2)

        ttk.Label(right, text="EN look").grid(row=3, column=0, sticky="nw")
        self.en_look = tk.Text(right, height=2, width=60, font=("Segoe UI", 9))
        self.en_look.grid(row=3, column=1, sticky="ew", pady=2)

        ttk.Label(right, text="Заметки").grid(row=4, column=0, sticky="nw")
        self.notes = tk.Text(right, height=3, width=60, font=("Segoe UI", 9))
        self.notes.grid(row=4, column=1, sticky="ew", pady=2)

        right.columnconfigure(1, weight=1)

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="↻ Скан inbox", command=self._rescan).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="LLaVA — описать", command=self._vision).pack(side="left", padx=6)
        ttk.Button(btns, text="✓ Сохранить", command=self._save).pack(side="left", padx=6)
        ttk.Button(btns, text="Закрыть", command=self._close).pack(side="right")

        self._entries: list[ReferenceEntry] = []
        self._rescan()

    def _rescan(self) -> None:
        added, total = scan_references_inbox(self.config)
        self.store = self.store.load() if hasattr(self.store, "load") else self.store
        from .paths import reference_catalog_path

        self.store = ReferenceCatalogStore(reference_catalog_path(self.config)).load()
        self._entries = sorted(self.store.all_entries(), key=lambda e: e.path.lower())
        self.listbox.delete(0, tk.END)
        for e in self._entries:
            mark = "✓" if e.reviewed else "○"
            self.listbox.insert(tk.END, f"{mark} {e.title or Path(e.path).name}")
        pending = len(self.store.pending())
        self.status.config(
            text=f"В каталоге: {total} · новых из inbox: {added} · без описания: {pending}"
        )
        if self._entries:
            self.listbox.selection_set(0)
            self._on_select()

    def _on_select(self, _event=None) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        self._current = self._entries[sel[0]]
        e = self._current
        self.title_var.set(e.title)
        self._set_text(self.ru, e.ru)
        self._set_text(self.en_pose, e.en_pose)
        self._set_text(self.en_look, e.en_look)
        self._set_text(self.notes, e.notes)

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value or "")

    @staticmethod
    def _get_text(widget: tk.Text) -> str:
        return widget.get("1.0", tk.END).strip()

    def _save(self) -> None:
        if not self._current:
            return
        e = self._current
        e.title = self.title_var.get().strip() or e.title
        e.ru = self._get_text(self.ru)
        e.en_pose = self._get_text(self.en_pose)
        e.en_look = self._get_text(self.en_look)
        e.notes = self._get_text(self.notes)
        e.reviewed = bool(e.ru or e.en_pose)
        self.store.upsert(e)
        self.store.save()
        try:
            from ..viu_memory import record_reference_inspiration

            if e.reviewed:
                record_reference_inspiration(self.config, e)
        except OSError:
            pass
        self._rescan()

    def _vision(self) -> None:
        if not self._current:
            return
        from ..integrations.comfy.reference_vision import (
            describe_reference,
            format_reference_report,
        )

        e = self._current
        try:
            desc = describe_reference(
                self.config,
                e.path,
                frame="middle" if e.kind == "video" else "first",
                hint=e.title,
                save_json=True,
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Вью", str(exc))
            return
        e.ru = desc.ru or e.ru
        e.en_pose = desc.en_pose or e.en_pose
        e.en_look = desc.en_look or e.en_look
        e.tags = desc.tags or e.tags
        e.verdict = desc.verdict
        e.vision_ok = desc.vision_ok
        e.reviewed = desc.vision_ok and desc.verdict != "EMPTY"
        self.store.upsert(e)
        self.store.save()
        self._on_select()
        if e.reviewed and (e.ru or e.en_pose):
            try:
                from ..viu_memory import record_reference_inspiration

                record_reference_inspiration(self.config, e)
            except OSError:
                pass
        messagebox.showinfo("LLaVA", format_reference_report(desc)[:1500])

    def _close(self) -> None:
        if self.on_closed:
            self.on_closed()
        self.win.destroy()


def open_reference_review(master: tk.Misc, config: Config) -> ReferenceReviewWindow:
    from .paths import reference_catalog_path

    store = ReferenceCatalogStore(reference_catalog_path(config)).load()
    return ReferenceReviewWindow(master, config, store)
