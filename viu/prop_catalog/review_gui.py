"""GUI разметки предметов — не «item№32», а имя файла и галочки."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from .models import INTERACTION_CHOICES, PROP_CATEGORIES, PropEntry, suggest_can_lift
from .store import PropCatalogStore


class PropCatalogReviewWindow:
    """Окно разметки: список слева, карточка предмета справа."""

    def __init__(
        self,
        master: tk.Misc,
        store: PropCatalogStore,
        *,
        max_lift_kg: float = 35.0,
        on_saved: Optional[Callable[[PropEntry], None]] = None,
    ) -> None:
        self.store = store
        self.max_lift_kg = max_lift_kg
        self.on_saved = on_saved
        self._current: Optional[PropEntry] = None
        self._interaction_vars: dict[str, tk.BooleanVar] = {}

        self.win = tk.Toplevel(master)
        self.win.title("Вью — каталог предметов")
        self.win.geometry("920x620")
        self.win.minsize(760, 520)

        body = ttk.Frame(self.win, padding=8)
        body.pack(fill="both", expand=True)

        # Левая колонка — очередь
        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 8))
        ttk.Label(left, text="Очередь разметки", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.listbox = tk.Listbox(left, width=36, height=28, exportselection=False)
        self.listbox.pack(fill="y", expand=True, pady=4)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        ttk.Button(left, text="Обновить список", command=self._reload_list).pack(fill="x", pady=2)
        ttk.Button(left, text="Сканировать папку…", command=self._scan_folder).pack(fill="x", pady=2)

        # Правая колонка — карточка
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        self.file_label = ttk.Label(right, text="Выбери предмет слева", wraplength=520)
        self.file_label.pack(anchor="w", pady=(0, 4))

        self.preview = tk.Text(right, height=8, wrap="word", state="disabled", font=("Consolas", 9))
        self.preview.pack(fill="x", pady=4)

        form = ttk.Frame(right)
        form.pack(fill="x", pady=6)
        ttk.Label(form, text="Название:").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.name_var, width=40).grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(form, text="Категория:").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.category_var = tk.StringVar(value="unknown")
        ttk.Combobox(
            form, textvariable=self.category_var, values=list(PROP_CATEGORIES), width=18
        ).grid(row=1, column=1, sticky="w", pady=2)

        ttk.Label(form, text="Вес (кг):").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.weight_var = tk.StringVar()
        wrow = ttk.Frame(form)
        wrow.grid(row=2, column=1, sticky="w")
        ttk.Entry(wrow, textvariable=self.weight_var, width=10).pack(side="left")
        ttk.Label(wrow, text=f"  (Шаня ~до {max_lift_kg:.0f} кг — поднять)").pack(side="left")

        self.can_lift_var = tk.BooleanVar()
        self.can_push_var = tk.BooleanVar()
        ttk.Checkbutton(form, text="Можно поднять", variable=self.can_lift_var).grid(
            row=3, column=1, sticky="w"
        )
        ttk.Checkbutton(form, text="Можно толкать / сдвинуть", variable=self.can_push_var).grid(
            row=4, column=1, sticky="w"
        )
        form.columnconfigure(1, weight=1)

        ttk.Label(right, text="Что можно делать:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 2))
        checks = ttk.Frame(right)
        checks.pack(fill="x")
        for i, (key, label) in enumerate(INTERACTION_CHOICES):
            var = tk.BooleanVar()
            self._interaction_vars[key] = var
            ttk.Checkbutton(checks, text=label, variable=var).grid(
                row=i // 3, column=i % 3, sticky="w", padx=4, pady=1
            )

        ttk.Label(right, text="Заметки:").pack(anchor="w", pady=(8, 2))
        self.notes_text = tk.Text(right, height=3, wrap="word")
        self.notes_text.pack(fill="x")

        btns = ttk.Frame(right)
        btns.pack(fill="x", pady=10)
        ttk.Button(btns, text="Сохранить и дальше →", command=self._save_next).pack(side="left", padx=2)
        ttk.Button(btns, text="Пропустить", command=self._skip).pack(side="left", padx=2)
        ttk.Button(btns, text="Открыть файл…", command=self._open_file).pack(side="left", padx=2)

        self.weight_var.trace_add("write", lambda *_: self._auto_lift())
        self._reload_list()

    def _reload_list(self) -> None:
        self.listbox.delete(0, "end")
        self._pending = self.store.pending()
        for e in self._pending:
            self.listbox.insert("end", f"{Path(e.source_path).name}")
        if self._pending:
            self.listbox.selection_set(0)
            self._load_entry(self._pending[0])

    def _on_select(self, _event=None) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._pending):
            self._load_entry(self._pending[idx])

    def _load_entry(self, entry: PropEntry) -> None:
        self._current = entry
        path = Path(entry.source_path)
        self.file_label.config(text=str(path))
        self.name_var.set(entry.guess_display_name())
        self.category_var.set(entry.category if entry.category in PROP_CATEGORIES else "unknown")
        self.weight_var.set("" if entry.weight_kg is None else str(entry.weight_kg))
        self.can_lift_var.set(entry.can_lift)
        self.can_push_var.set(entry.can_push)
        for key, var in self._interaction_vars.items():
            var.set(key in entry.interactions)
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", entry.notes)

        preview_lines = [
            f"Файл: {path.name}",
            f"Размер: {path.stat().st_size // 1024} KB" if path.is_file() else "",
        ]
        if entry.mesh_names:
            preview_lines.append("Меши в .blend:")
            preview_lines.extend(f"  • {n}" for n in entry.mesh_names[:25])
        thumb = path.with_suffix(".png")
        if thumb.is_file():
            preview_lines.append(f"Превью: {thumb}")
        self._set_preview("\n".join(preview_lines))

    def _set_preview(self, text: str) -> None:
        self.preview.config(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.config(state="disabled")

    def _auto_lift(self) -> None:
        raw = self.weight_var.get().strip().replace(",", ".")
        if not raw:
            return
        try:
            w = float(raw)
        except ValueError:
            return
        if suggest_can_lift(w, self.max_lift_kg):
            self.can_lift_var.set(True)

    def _collect_form(self) -> Optional[PropEntry]:
        if self._current is None:
            return None
        e = PropEntry.from_dict(self._current.to_dict())
        e.display_name = self.name_var.get().strip() or e.guess_display_name()
        e.category = self.category_var.get().strip() or "unknown"
        raw_w = self.weight_var.get().strip().replace(",", ".")
        e.weight_kg = float(raw_w) if raw_w else None
        e.can_lift = self.can_lift_var.get()
        e.can_push = self.can_push_var.get()
        e.interactions = [k for k, v in self._interaction_vars.items() if v.get()]
        e.notes = self.notes_text.get("1.0", "end").strip()
        e.reviewed = True
        return e

    def _save_next(self) -> None:
        entry = self._collect_form()
        if entry is None:
            return
        self.store.upsert(entry)
        aff_path = self.store.path.parent / "affordances" / f"{entry.id}.json"
        aff_path.parent.mkdir(parents=True, exist_ok=True)
        aff_path.write_text(
            json.dumps(entry.to_affordance_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if self.on_saved:
            self.on_saved(entry)
        self._reload_list()
        if not self._pending:
            messagebox.showinfo("Каталог", "Все предметы в очереди размечены.", parent=self.win)

    def _skip(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = int(sel[0]) + 1
        self._reload_list()
        if idx < self.listbox.size():
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(idx)
            self._on_select()

    def _open_file(self) -> None:
        if self._current is None:
            return
        path = Path(self._current.source_path)
        if not path.is_file():
            messagebox.showwarning("Каталог", f"Файл не найден:\n{path}", parent=self.win)
            return
        import os
        import subprocess
        import sys

        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except OSError as exc:
            messagebox.showerror("Каталог", str(exc), parent=self.win)

    def _scan_folder(self) -> None:
        from .scanner import scan_folder

        folder = filedialog.askdirectory(title="Папка с моделями (FBX, blend…)", parent=self.win)
        if not folder:
            return
        try:
            n, seen = scan_folder(Path(folder), self.store)
        except OSError as exc:
            messagebox.showerror("Скан", str(exc), parent=self.win)
            return
        messagebox.showinfo(
            "Скан",
            f"Новых: {n}, уже в каталоге: {seen}",
            parent=self.win,
        )
        self._reload_list()


def open_prop_catalog_review(
    master: tk.Misc,
    store: PropCatalogStore,
    *,
    max_lift_kg: float = 35.0,
) -> PropCatalogReviewWindow:
    return PropCatalogReviewWindow(master, store, max_lift_kg=max_lift_kg)
