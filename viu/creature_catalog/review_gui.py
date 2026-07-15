"""GUI разметки существ — кнопки размеров, без консольных команд."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

from .auto_size import apply_size_to_same_stem, auto_apply_size_guesses
from .models import (
    LOCOMOTION,
    QUAD_SIZE_CLASSES,
    SIZE_CLASSES,
    STATUS_SKIP,
    CreatureEntry,
    suggest_size_from_name,
)
from .store import CreatureCatalogStore

_LOCO_RU = {
    "biped": "на двух ногах",
    "quadruped": "на четырёх",
    "amorph": "слизень / аморф",
    "tentacle": "щупальца",
    "mimic": "мимик",
    "flyer": "летает",
    "unknown": "неясно",
}


class CreatureCatalogReviewWindow:
    """Очередь слева, справа — крупные кнопки классов роста."""

    def __init__(
        self,
        master: tk.Misc,
        store: CreatureCatalogStore,
        *,
        on_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        self.store = store
        self.on_finished = on_finished
        self._current: Optional[CreatureEntry] = None

        self.win = tk.Toplevel(master)
        self.win.title("Вью — разметить существ")
        self.win.geometry("1080x700")
        self.win.minsize(900, 580)

        body = ttk.Frame(self.win, padding=8)
        body.pack(fill="both", expand=True)

        paned = ttk.PanedWindow(body, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, width=340)
        right = ttk.Frame(paned)
        paned.add(left, weight=1)
        paned.add(right, weight=3)

        ttk.Label(left, text="Очередь", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(
            left,
            text="Жми размер справа — сохранится само.\n"
            "Одинаковые имена (fbx+blend) размечаются вместе.",
            font=("Segoe UI", 8),
            wraplength=320,
        ).pack(anchor="w", pady=(0, 4))

        self.queue_status = ttk.Label(left, text="", font=("Segoe UI", 9))
        self.queue_status.pack(anchor="w", pady=(0, 4))

        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill="both", expand=True, pady=4)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("name", "hint", "file"),
            show="headings",
            selectmode="browse",
            height=22,
        )
        self.tree.heading("name", text="Имя")
        self.tree.heading("hint", text="Подсказка")
        self.tree.heading("file", text="Файл")
        self.tree.column("name", width=120, minwidth=80, stretch=True)
        self.tree.column("hint", width=90, minwidth=60, stretch=False)
        self.tree.column("file", width=90, minwidth=50, stretch=False)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        ttk.Button(left, text="Авто по именам файлов", command=self._run_auto).pack(
            fill="x", pady=(6, 2)
        )
        ttk.Button(left, text="✓ Готово — закрыть", command=self._finish_and_close).pack(
            fill="x", pady=2
        )

        # --- правая панель ---
        self.done_panel = ttk.LabelFrame(right, text="Очередь пуста", padding=12)
        self.done_text = tk.Text(
            self.done_panel, height=8, wrap="word", font=("Segoe UI", 10)
        )
        self.done_text.pack(fill="both", expand=True)
        ttk.Button(
            self.done_panel,
            text="✓ Закрыть и вернуться во Вью",
            command=self._finish_and_close,
        ).pack(pady=(8, 0))

        self.detail = ttk.Frame(right)
        self.detail.pack(fill="both", expand=True)

        self.title_lbl = ttk.Label(
            self.detail, text="Выбери существо слева", font=("Segoe UI", 14, "bold")
        )
        self.title_lbl.pack(anchor="w", pady=(0, 4))

        self.path_lbl = ttk.Label(
            self.detail, text="", font=("Segoe UI", 8), wraplength=680
        )
        self.path_lbl.pack(anchor="w")

        self.hint_lbl = ttk.Label(
            self.detail, text="", font=("Segoe UI", 9), foreground="#444", wraplength=680
        )
        self.hint_lbl.pack(anchor="w", pady=(4, 8))

        loco_row = ttk.Frame(self.detail)
        loco_row.pack(anchor="w", fill="x", pady=4)
        ttk.Label(loco_row, text="Как ходит:", font=("Segoe UI", 10)).pack(
            side="left", padx=(0, 8)
        )
        self.loco_var = tk.StringVar(value="biped")
        loco_values = [f"{k} — {_LOCO_RU.get(k, k)}" for k in LOCOMOTION if k != "unknown"]
        self.loco_combo = ttk.Combobox(
            loco_row,
            textvariable=self.loco_var,
            values=loco_values,
            width=36,
            state="readonly",
        )
        self.loco_combo.pack(side="left")
        self.loco_combo.bind("<<ComboboxSelected>>", lambda _e: None)

        self.nsfw_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.detail,
            text="NSFW (есть гениталии / взрослый контент)",
            variable=self.nsfw_var,
        ).pack(anchor="w", pady=(4, 8))

        ttk.Label(
            self.detail,
            text="Размер (нажми один раз):",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(4, 2))

        biped_fr = ttk.LabelFrame(self.detail, text="Двуногие / антропоморфы", padding=6)
        biped_fr.pack(fill="x", pady=4)
        biped_btns = ttk.Frame(biped_fr)
        biped_btns.pack(fill="x")
        for i, (sid, spec) in enumerate(SIZE_CLASSES.items()):
            txt = f"{spec['label_ru']}\n~{int(spec['target_m'] * 100)} см"
            btn = ttk.Button(
                biped_btns,
                text=txt,
                width=16,
                command=lambda s=sid: self._apply_size(s),
            )
            btn.grid(row=0, column=i, padx=3, pady=2, sticky="ew")
            biped_btns.columnconfigure(i, weight=1)

        quad_fr = ttk.LabelFrame(self.detail, text="Четвероногие (высота в холке)", padding=6)
        quad_fr.pack(fill="x", pady=4)
        quad_btns = ttk.Frame(quad_fr)
        quad_btns.pack(fill="x")
        for i, (sid, spec) in enumerate(QUAD_SIZE_CLASSES.items()):
            txt = f"{spec['label_ru']}\n~{int(spec['target_m'] * 100)} см"
            btn = ttk.Button(
                quad_btns,
                text=txt,
                width=18,
                command=lambda s=sid: self._apply_size(s),
            )
            btn.grid(row=0, column=i, padx=3, pady=2, sticky="ew")
            quad_btns.columnconfigure(i, weight=1)

        skip_row = ttk.Frame(self.detail)
        skip_row.pack(fill="x", pady=(12, 4))
        ttk.Button(skip_row, text="Пропустить (не сейчас)", command=self._skip).pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(
            skip_row,
            text="Morphs (уши/хвост/гениталии) не трогаем — только класс роста.",
            font=("Segoe UI", 8),
            wraplength=420,
        ).pack(side="left")

        self.status_lbl = ttk.Label(self.detail, text="", font=("Segoe UI", 9))
        self.status_lbl.pack(anchor="w", pady=(8, 0))

        self.win.protocol("WM_DELETE_WINDOW", self._finish_and_close)
        self._reload_list()

    def _loco_choice(self) -> str:
        raw = (self.loco_var.get() or "biped").strip()
        return raw.split(" — ", 1)[0].strip() or "biped"

    def _set_loco_display(self, loco: str) -> None:
        key = loco if loco in LOCOMOTION else "biped"
        self.loco_var.set(f"{key} — {_LOCO_RU.get(key, key)}")

    def _hint_for(self, e: CreatureEntry) -> str:
        guesses = suggest_size_from_name(e.name) or list(e.tags or [])
        if guesses:
            return "/".join(guesses[:2])
        return "—"

    def _reload_list(self, select_id: str = "") -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        pending = sorted(self.store.pending(), key=lambda e: e.name.lower())
        sized = sum(1 for e in self.store.all() if e.size_class)
        self.queue_status.config(
            text=f"Ждут: {len(pending)} · уже размечено: {sized}"
        )
        for e in pending:
            self.tree.insert(
                "",
                "end",
                iid=e.id,
                values=(e.name, self._hint_for(e), Path(e.path).suffix.lower()),
            )
        if not pending:
            self.detail.pack_forget()
            self.done_panel.pack(fill="both", expand=True)
            self.done_text.delete("1.0", "end")
            self.done_text.insert(
                "end",
                self.store.summary_text()
                + "\n\nДальше во Вью можно нажать «Линейка существ» "
                "(или написать линейка существ) — сравнить рост с Шаней в Blender.",
            )
            self._current = None
            return

        self.done_panel.pack_forget()
        self.detail.pack(fill="both", expand=True)
        target = select_id if select_id and self.tree.exists(select_id) else None
        if target is None:
            kids = self.tree.get_children()
            target = kids[0] if kids else None
        if target:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
            self._show_entry(target)

    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        self._show_entry(sel[0])

    def _show_entry(self, cid: str) -> None:
        e = self.store.get(cid)
        if e is None:
            return
        self._current = e
        self.title_lbl.config(text=e.name)
        self.path_lbl.config(text=e.path)
        guesses = suggest_size_from_name(e.name) or list(e.tags or [])
        hint_parts = []
        if guesses:
            hint_parts.append("По имени похоже на: " + ", ".join(guesses))
        if e.notes:
            hint_parts.append(e.notes.split("\n")[0][:120])
        if e.textures_external:
            hint_parts.append("Текстуры рядом (отдельная папка).")
        self.hint_lbl.config(text=" · ".join(hint_parts) or "Класс роста — на глаз.")
        loco = e.locomotion if e.locomotion != "unknown" else (
            "quadruped" if (guesses and guesses[0].startswith("quad_")) else "biped"
        )
        self._set_loco_display(loco)
        self.nsfw_var.set(bool(e.nsfw_capable))
        self.status_lbl.config(text="")

    def _apply_size(self, size: str) -> None:
        if self._current is None:
            return
        e = self._current
        loco = self._loco_choice()
        updated = self.store.set_size(e.id, size, locomotion=loco)
        if updated is None:
            messagebox.showerror("Вью", f"Не удалось поставить size={size}", parent=self.win)
            return
        if self.nsfw_var.get():
            updated.nsfw_capable = True
            self.store.upsert(updated)
        extra = apply_size_to_same_stem(
            self.store,
            e.id,
            size,
            locomotion=loco,
            nsfw=self.nsfw_var.get(),
        )
        self.store.save()
        msg = f"✓ {e.name} → {size} / {loco}"
        if extra:
            msg += f" (+{extra} файл(ов) с тем же именем)"
        self.status_lbl.config(text=msg)
        self._reload_list()

    def _skip(self) -> None:
        if self._current is None:
            return
        e = self._current
        e.status = STATUS_SKIP
        e.reviewed = True
        e.notes = ((e.notes or "") + "\nskip: вручную").strip()
        self.store.upsert(e)
        self.store.save()
        self._reload_list()

    def _run_auto(self) -> None:
        n, lines = auto_apply_size_guesses(self.store)
        if n == 0:
            messagebox.showinfo(
                "Вью",
                "Уверенных догадок по имени нет — размечай кнопками.",
                parent=self.win,
            )
        else:
            messagebox.showinfo(
                "Вью",
                f"Авто: размечено {n}.\n" + "\n".join(lines[:20]),
                parent=self.win,
            )
        self._reload_list()

    def _finish_and_close(self) -> None:
        try:
            self.store.save()
        except OSError:
            pass
        cb = self.on_finished
        self.win.destroy()
        if cb:
            cb()


def open_creature_catalog_review(
    master: tk.Misc,
    store: CreatureCatalogStore,
    *,
    on_finished: Optional[Callable[[], None]] = None,
) -> CreatureCatalogReviewWindow:
    return CreatureCatalogReviewWindow(master, store, on_finished=on_finished)
