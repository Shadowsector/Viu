"""GUI разметки предметов — не «item№32», а имя файла и галочки."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Optional

from .models import (
    INTERACTION_CHOICES,
    PROP_CATEGORIES,
    PROP_ROLES,
    PropEntry,
    suggest_can_lift,
    suggest_category_for_role,
    suggest_role,
)
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
        blender_exe: str = "",
        config: Optional[Any] = None,
    ) -> None:
        self.store = store
        self.max_lift_kg = max_lift_kg
        self.on_saved = on_saved
        self._current: Optional[PropEntry] = None
        self._interaction_vars: dict[str, tk.BooleanVar] = {}
        self._blender_exe = blender_exe
        self._config = config

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
        ttk.Button(left, text="Разложить по объектам Blender", command=self._expand_blends).pack(
            fill="x", pady=2
        )
        ttk.Button(left, text="Building/Landscape → shell (все)", command=self._bulk_shell).pack(
            fill="x", pady=2
        )
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

        ttk.Label(form, text="Меш в файле:").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.mesh_var = tk.StringVar()
        mesh_entry = ttk.Entry(form, textvariable=self.mesh_var, width=40, state="readonly")
        mesh_entry.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(form, text="Коллекция:").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.collection_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.collection_var, width=40, state="readonly").grid(
            row=2, column=1, sticky="ew", pady=2
        )

        ttk.Label(form, text="Роль:").grid(row=3, column=0, sticky="w", padx=2, pady=2)
        self.role_var = tk.StringVar(value="")
        role_combo = ttk.Combobox(
            form,
            textvariable=self.role_var,
            values=[r for r in PROP_ROLES if r],
            width=18,
        )
        role_combo.grid(row=3, column=1, sticky="w", pady=2)
        ttk.Label(
            form,
            text="Building=стены, Props=мебель, Landscape=фон",
            font=("Segoe UI", 8),
        ).grid(row=4, column=1, sticky="w", pady=(0, 4))

        ttk.Label(form, text="Категория:").grid(row=5, column=0, sticky="w", padx=2, pady=2)
        self.category_var = tk.StringVar(value="unknown")
        ttk.Combobox(
            form, textvariable=self.category_var, values=list(PROP_CATEGORIES), width=18
        ).grid(row=5, column=1, sticky="w", pady=2)

        ttk.Label(form, text="Вес (кг):").grid(row=6, column=0, sticky="w", padx=2, pady=2)
        self.weight_var = tk.StringVar()
        wrow = ttk.Frame(form)
        wrow.grid(row=6, column=1, sticky="w")
        ttk.Entry(wrow, textvariable=self.weight_var, width=10).pack(side="left")
        ttk.Label(wrow, text=f"  (Шаня ~до {max_lift_kg:.0f} кг — поднять)").pack(side="left")

        self.can_lift_var = tk.BooleanVar()
        self.can_push_var = tk.BooleanVar()
        ttk.Checkbutton(form, text="Можно поднять", variable=self.can_lift_var).grid(
            row=7, column=1, sticky="w"
        )
        ttk.Checkbutton(form, text="Можно толкать / сдвинуть", variable=self.can_push_var).grid(
            row=8, column=1, sticky="w"
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
        ttk.Button(btns, text="Shell — без разметки →", command=self._save_shell).pack(side="left", padx=2)
        ttk.Button(btns, text="Пропустить", command=self._skip).pack(side="left", padx=2)
        ttk.Button(btns, text="Открыть файл…", command=self._open_file).pack(side="left", padx=2)

        self.weight_var.trace_add("write", lambda *_: self._auto_lift())
        from .scanner import apply_auto_reviews_to_store

        auto_n = apply_auto_reviews_to_store(self.store)
        if auto_n:
            messagebox.showinfo(
                "Каталог",
                f"Авто-разметка: {auto_n} объектов (Building, Landscape, пыль/туман…).\n"
                "Тебе остались в основном Props.",
                parent=self.win,
            )
        self._reload_list()

    def _reload_list(self) -> None:
        self.listbox.delete(0, "end")
        self._pending = self.store.pending()
        for e in self._pending:
            self.listbox.insert("end", e.list_label())
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
        self.file_label.config(text=entry.list_label() + f"\n{path}")
        self.mesh_var.set(entry.mesh_name or "— (весь файл — нажми «Разложить по объектам»)")
        self.collection_var.set(entry.collection or "—")
        role = entry.role or suggest_role(entry.mesh_name)
        self.role_var.set(role)
        self.name_var.set(entry.guess_display_name())
        cat = entry.category if entry.category in PROP_CATEGORIES else "unknown"
        if cat == "unknown" and role:
            cat = suggest_category_for_role(role)
        self.category_var.set(cat)
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
        if entry.mesh_name:
            preview_lines.append(f"Размечаем меш: {entry.mesh_name}")
        if entry.mesh_names:
            preview_lines.append("Объекты в .blend (как в Outliner):")
            for n in entry.mesh_names[:50]:
                mark = " ←" if n == entry.mesh_name else ""
                preview_lines.append(f"  • {n}{mark}")
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
        e.role = self.role_var.get().strip()
        e.category = self.category_var.get().strip() or "unknown"
        raw_w = self.weight_var.get().strip().replace(",", ".")
        e.weight_kg = float(raw_w) if raw_w else None
        e.can_lift = self.can_lift_var.get()
        e.can_push = self.can_push_var.get()
        e.interactions = [k for k, v in self._interaction_vars.items() if v.get()]
        e.notes = self.notes_text.get("1.0", "end").strip()
        e.reviewed = True
        return e

    def _persist_entry(self, entry: PropEntry) -> None:
        self.store.upsert(entry)
        aff_path = self.store.path.parent / "affordances" / f"{entry.id}.json"
        aff_path.parent.mkdir(parents=True, exist_ok=True)
        aff_path.write_text(
            json.dumps(entry.to_affordance_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if self.on_saved:
            self.on_saved(entry)

    def _save_next(self) -> None:
        entry = self._collect_form()
        if entry is None:
            return
        self._persist_entry(entry)
        self._reload_list()
        if not self._pending:
            messagebox.showinfo("Каталог", "Все предметы в очереди размечены.", parent=self.win)

    def _save_shell(self) -> None:
        """Быстро пометить стены/пол — без веса и галочек."""
        if self._current is None:
            return
        e = PropEntry.from_dict(self._current.to_dict())
        e.role = "shell"
        e.category = "building"
        e.interactions = []
        e.can_lift = False
        e.can_push = False
        e.weight_kg = None
        e.reviewed = True
        if not e.display_name.strip():
            e.display_name = e.mesh_name.replace("_", " ") if e.mesh_name else e.guess_display_name()
        self._persist_entry(e)
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

    def _bulk_shell(self) -> None:
        from .models import AUTO_SHELL_COLLECTIONS

        n = 0
        for entry in list(self.store.pending()):
            col = (entry.collection or "").lower().strip()
            if col not in AUTO_SHELL_COLLECTIONS:
                continue
            e = PropEntry.from_dict(entry.to_dict())
            e.role = "shell"
            e.category = "building"
            e.reviewed = True
            e.interactions = []
            e.can_lift = False
            e.can_push = False
            e.weight_kg = None
            self._persist_entry(e)
            n += 1
        messagebox.showinfo(
            "Каталог",
            f"Помечено shell: {n} (Building/Landscape).",
            parent=self.win,
        )
        self._reload_list()

    def _expand_blends(self) -> None:
        from .scanner import rescan_file_level_blends

        try:
            n, seen = rescan_file_level_blends(
                self.store, blender_exe=self._blender_exe, config=self._config
            )
        except RuntimeError as exc:
            messagebox.showerror("Blender", str(exc), parent=self.win)
            return
        messagebox.showinfo(
            "Скан",
            f"Разложено по объектам Blender.\nНовых карточек: {n}, уже были: {seen}",
            parent=self.win,
        )
        self._reload_list()

    def _scan_folder(self) -> None:
        from .scanner import scan_folder

        folder = filedialog.askdirectory(title="Папка с моделями (FBX, blend…)", parent=self.win)
        if not folder:
            return
        try:
            n, seen = scan_folder(
                Path(folder),
                self.store,
                blender_exe=self._blender_exe,
                config=self._config,
            )
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
    blender_exe: str = "",
    config: Any = None,
) -> PropCatalogReviewWindow:
    return PropCatalogReviewWindow(
        master,
        store,
        max_lift_kg=max_lift_kg,
        blender_exe=blender_exe,
        config=config,
    )
