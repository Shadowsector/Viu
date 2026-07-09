"""GUI разметки предметов — не «item№32», а имя файла и галочки."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Optional

from .interactions import (
    INTERACTION_CHOICES_PROPS,
    INTERACTION_CHOICES_SHELL,
    PROP_FLAG_CHOICES,
    SHELL_FLAG_CHOICES,
    normalize_interactions,
)
from .models import (
    PROP_CATEGORIES,
    PROP_ROLES,
    PropEntry,
    suggest_can_lift,
    suggest_category_for_role,
    suggest_category_from_mesh,
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
        self._flag_vars: dict[str, tk.BooleanVar] = {}
        self._blender_exe = blender_exe
        self._config = config
        self._suspend_role_trace = False

        self.win = tk.Toplevel(master)
        self.win.title("Вью — каталог предметов")
        self.win.geometry("1040x680")
        self.win.minsize(860, 560)

        body = ttk.Frame(self.win, padding=8)
        body.pack(fill="both", expand=True)

        paned = ttk.PanedWindow(body, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, width=320)
        right = ttk.Frame(paned)
        paned.add(left, weight=1)
        paned.add(right, weight=3)

        ttk.Label(left, text="Очередь разметки", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(
            left,
            text="Тяни разделитель — шире список.\nProps = мебель. Shell = стены/деревья.",
            font=("Segoe UI", 8),
            wraplength=300,
        ).pack(anchor="w", pady=(0, 4))

        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill="both", expand=True, pady=4)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("collection", "mesh", "file"),
            show="headings",
            selectmode="browse",
            height=24,
        )
        self.tree.heading("collection", text="Коллекция")
        self.tree.heading("mesh", text="Объект")
        self.tree.heading("file", text="Файл")
        self.tree.column("collection", width=80, minwidth=50, stretch=False)
        self.tree.column("mesh", width=160, minwidth=100, stretch=True)
        self.tree.column("file", width=100, minwidth=60, stretch=False)
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        ttk.Button(left, text="Обновить список", command=self._reload_list).pack(fill="x", pady=2)
        ttk.Button(left, text="Разложить по объектам Blender", command=self._expand_blends).pack(
            fill="x", pady=2
        )
        ttk.Button(left, text="Building/Landscape → shell (все)", command=self._bulk_shell).pack(
            fill="x", pady=2
        )
        ttk.Button(left, text="Сканировать папку…", command=self._scan_folder).pack(fill="x", pady=2)

        self.file_label = ttk.Label(right, text="Выбери предмет слева", wraplength=640)
        self.file_label.pack(anchor="w", pady=(0, 4))

        self.preview = tk.Text(right, height=6, wrap="word", state="disabled", font=("Consolas", 9))
        self.preview.pack(fill="x", pady=4)

        form = ttk.Frame(right)
        form.pack(fill="x", pady=6)
        ttk.Label(form, text="Название:").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.name_var, width=48).grid(
            row=0, column=1, sticky="ew", pady=2, columnspan=2
        )

        ttk.Label(form, text="Меш в файле:").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        self.mesh_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.mesh_var, width=48, state="readonly").grid(
            row=1, column=1, sticky="ew", pady=2, columnspan=2
        )

        ttk.Label(form, text="Коллекция:").grid(row=2, column=0, sticky="w", padx=2, pady=2)
        self.collection_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.collection_var, width=48, state="readonly").grid(
            row=2, column=1, sticky="ew", pady=2, columnspan=2
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
        self.role_hint = ttk.Label(
            form,
            text="shell = геометрия без веса; interactive = Props",
            font=("Segoe UI", 8),
        )
        self.role_hint.grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 4))

        self.category_label = ttk.Label(form, text="Категория:")
        self.category_label.grid(row=5, column=0, sticky="w", padx=2, pady=2)
        self.category_var = tk.StringVar(value="unknown")
        self.category_combo = ttk.Combobox(
            form, textvariable=self.category_var, values=list(PROP_CATEGORIES), width=18
        )
        self.category_combo.grid(row=5, column=1, sticky="w", pady=2)
        self.category_hint = ttk.Label(
            form,
            text="food = съесть; tableware = тарелка/кувшин (взять, не есть)",
            font=("Segoe UI", 8),
        )
        self.category_hint.grid(row=6, column=1, columnspan=2, sticky="w", pady=(0, 4))

        self.weight_label = ttk.Label(form, text="Вес (кг):")
        self.weight_label.grid(row=7, column=0, sticky="w", padx=2, pady=2)
        self.weight_var = tk.StringVar()
        self.wrow = ttk.Frame(form)
        self.wrow.grid(row=7, column=1, sticky="w")
        self.weight_entry = ttk.Entry(self.wrow, textvariable=self.weight_var, width=10)
        self.weight_entry.pack(side="left")
        self.weight_hint = ttk.Label(self.wrow, text=f"  (Шаня ~до {max_lift_kg:.0f} кг — поднять)")
        self.weight_hint.pack(side="left")

        self.can_lift_var = tk.BooleanVar()
        self.can_push_var = tk.BooleanVar()
        self.can_lift_cb = ttk.Checkbutton(form, text="Можно поднять", variable=self.can_lift_var)
        self.can_lift_cb.grid(row=8, column=1, sticky="w")
        self.can_push_cb = ttk.Checkbutton(
            form, text="Толкать / тянуть (legacy)", variable=self.can_push_var
        )
        self.can_push_cb.grid(row=9, column=1, sticky="w")
        form.columnconfigure(1, weight=1)

        self.sections_frame = ttk.Frame(right)
        self.sections_frame.pack(fill="x", pady=6)

        self.shell_section = ttk.LabelFrame(
            self.sections_frame, text="Shell — геометрия (без веса и grab)", padding=6
        )
        self._shell_checks = ttk.Frame(self.shell_section)
        self._shell_checks.pack(fill="x")
        for i, (key, label) in enumerate(INTERACTION_CHOICES_SHELL):
            var = self._interaction_var(key)
            ttk.Checkbutton(self._shell_checks, text=label, variable=var).grid(
                row=i // 2, column=i % 2, sticky="w", padx=4, pady=1
            )
        self._shell_flags = ttk.Frame(self.shell_section)
        self._shell_flags.pack(fill="x", pady=(4, 0))
        for key, label in SHELL_FLAG_CHOICES:
            var = tk.BooleanVar()
            self._flag_vars[key] = var
            ttk.Checkbutton(self._shell_flags, text=label, variable=var).pack(side="left", padx=4)

        self.props_section = ttk.LabelFrame(
            self.sections_frame, text="Props — что можно делать", padding=6
        )
        self._props_checks = ttk.Frame(self.props_section)
        self._props_checks.pack(fill="x")
        for i, (key, label) in enumerate(INTERACTION_CHOICES_PROPS):
            var = self._interaction_var(key)
            ttk.Checkbutton(self._props_checks, text=label, variable=var).grid(
                row=i // 3, column=i % 3, sticky="w", padx=4, pady=1
            )
        self._prop_flags = ttk.Frame(self.props_section)
        self._prop_flags.pack(fill="x", pady=(4, 0))
        for key, label in PROP_FLAG_CHOICES:
            var = tk.BooleanVar()
            self._flag_vars[key] = var
            ttk.Checkbutton(self._prop_flags, text=label, variable=var).pack(side="left", padx=4)

        self.simple_section = ttk.LabelFrame(
            self.sections_frame,
            text="Decor / atmosphere / undefined — достаточно роли и заметок",
            padding=6,
        )
        ttk.Label(
            self.simple_section,
            text="Нет веса и grab. Нажми «Сохранить и дальше» — или смени роль на interactive/shell.",
            wraplength=560,
        ).pack(anchor="w")

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
        self.role_var.trace_add("write", lambda *_: self._update_form_mode())

        from .dedupe import repair_overmerged_duplicates
        from .scanner import apply_auto_reviews_to_store

        fixed = repair_overmerged_duplicates(self.store)
        auto_n = apply_auto_reviews_to_store(self.store)
        msgs: list[str] = []
        if fixed:
            msgs.append(f"Вернули в очередь: {fixed} (ложное «объединение»).")
        if auto_n:
            msgs.append(f"Авто-разметка: {auto_n} (Plane, Building…).")
        if msgs:
            messagebox.showinfo("Каталог", "\n".join(msgs), parent=self.win)
        self._reload_list()

    def _interaction_var(self, key: str) -> tk.BooleanVar:
        if key not in self._interaction_vars:
            self._interaction_vars[key] = tk.BooleanVar()
        return self._interaction_vars[key]

    def _update_form_mode(self) -> None:
        if self._suspend_role_trace:
            return
        role = self.role_var.get().strip() or "interactive"
        is_props = role == "interactive"
        is_shell = role == "shell"
        is_simple = role in ("decor", "atmosphere", "undefined")

        for w, show in (
            (self.category_label, is_props),
            (self.category_combo, is_props),
            (self.category_hint, is_props),
            (self.weight_label, is_props),
            (self.wrow, is_props),
            (self.can_lift_cb, is_props),
            (self.can_push_cb, is_props),
        ):
            if show:
                w.grid()
            else:
                w.grid_remove()

        self.shell_section.pack_forget()
        self.props_section.pack_forget()
        self.simple_section.pack_forget()

        if is_shell:
            self.shell_section.pack(fill="x", pady=(0, 4))
        elif is_props:
            self.props_section.pack(fill="x", pady=(0, 4))
        elif is_simple:
            self.simple_section.pack(fill="x", pady=(0, 4))

        hints = {
            "shell": "Стены, деревья, крыша — блок «Shell» ниже. Без веса.",
            "interactive": "Мебель, посуда — вес и Props ниже.",
            "decor": "Декор — роль и заметки, сохрани.",
            "atmosphere": "Туман/пыль — остаётся в сцене.",
            "undefined": "Служебный меш (Plane…) — не для игры.",
        }
        self.role_hint.config(text=hints.get(role, "shell / interactive / decor / undefined"))

    def _reload_list(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._pending = self.store.pending()
        for i, e in enumerate(self._pending):
            col = e.collection or "—"
            mesh = e.mesh_name or Path(e.source_path).name
            self.tree.insert("", "end", iid=str(i), values=(col, mesh, e.short_source()))
        if self._pending:
            self.tree.selection_set("0")
            self.tree.focus("0")
            self._load_entry(self._pending[0])

    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
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
        role = entry.role or suggest_role(entry.mesh_name) or "interactive"
        self.name_var.set(entry.guess_display_name())
        cat = entry.category if entry.category in PROP_CATEGORIES else "unknown"
        if cat == "unknown" and role == "interactive":
            cat = suggest_category_from_mesh(entry.mesh_name) or "furniture"
        elif cat == "unknown" and role:
            cat = suggest_category_for_role(role)
        self.weight_var.set("" if entry.weight_kg is None else str(entry.weight_kg))
        self.can_lift_var.set(entry.can_lift)
        self.can_push_var.set(entry.can_push or "move" in entry.interactions)
        interactions = normalize_interactions(entry.interactions)
        for key, var in self._interaction_vars.items():
            var.set(key in interactions)
        for key, var in self._flag_vars.items():
            var.set(getattr(entry, key, False))
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", entry.notes)

        preview_lines = [
            f"Файл: {path.name}",
            f"Размер: {path.stat().st_size // 1024} KB" if path.is_file() else "",
        ]
        if entry.mesh_name:
            preview_lines.append(f"Размечаем меш: {entry.mesh_name}")
        if entry.role == "undefined":
            preview_lines.append("Служебный Plane/Cube — в Blender часто скрыт или без коллекции.")
        if entry.role == "shell" and entry.can_climb:
            preview_lines.append("Climbable — у персонажа нужен can_climb.")
        self._set_preview("\n".join(preview_lines))

        self._suspend_role_trace = True
        self.category_var.set(cat)
        self.role_var.set(role)
        self._suspend_role_trace = False
        self._update_form_mode()

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
        role = e.role

        if role in ("shell", "atmosphere", "decor"):
            e.weight_kg = None
            e.can_lift = False
            e.can_push = False
            e.category = suggest_category_for_role(role) if role else e.category
        else:
            raw_w = self.weight_var.get().strip().replace(",", ".")
            e.weight_kg = float(raw_w) if raw_w else None
            e.can_lift = self.can_lift_var.get()
            e.can_push = self.can_push_var.get()

        e.interactions = normalize_interactions(
            [k for k, v in self._interaction_vars.items() if v.get()]
        )
        if e.can_push and "move" not in e.interactions:
            e.interactions.append("move")

        for key, var in self._flag_vars.items():
            setattr(e, key, var.get())

        e.notes = self.notes_text.get("1.0", "end").strip()
        e.reviewed = True
        return e

    def _persist_entry(self, entry: PropEntry) -> None:
        from .dedupe import propagate_entry_to_duplicates

        self.store.upsert(entry, save=False)
        propagate_entry_to_duplicates(self.store, entry)
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
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0]) + 1
        self._reload_list()
        if idx < len(self._pending):
            self.tree.selection_set(str(idx))
            self.tree.focus(str(idx))
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
        from .models import AUTO_LANDSCAPE_COLLECTIONS, AUTO_SHELL_COLLECTIONS

        targets = AUTO_SHELL_COLLECTIONS | AUTO_LANDSCAPE_COLLECTIONS
        n = 0
        for entry in list(self.store.pending()):
            col = (entry.collection or "").lower().strip()
            if col not in targets:
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
