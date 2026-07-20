"""GUI разметки существ — кнопки размеров, без консольных команд."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, Optional

from ..config import Config
from .auto_size import apply_size_to_same_stem, auto_apply_size_guesses
from .models import (
    CONTACT_MODE_LABELS,
    CONTACT_MODES,
    GENITAL_PROFILE_LABELS,
    GENITAL_PROFILES,
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
        config: Optional[Config] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        self.store = store
        self.config = config
        self.on_finished = on_finished
        self._current: Optional[CreatureEntry] = None
        self._photo_refs: list = []
        self._lineup_busy = False

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
            "Уже размеченные (волк и т.п.) — галочка ниже.\n"
            "Скрины и очистка — кнопка «Студия существ» в Вью.",
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
        self.show_sized_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            left,
            text="Показать уже размеченных (исправить рост)",
            variable=self.show_sized_var,
            command=self._reload_list,
        ).pack(anchor="w", pady=2)
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

        anat_fr = ttk.LabelFrame(
            self.detail,
            text="Анатомия для NSFW-анимаций (все классы)",
            padding=6,
        )
        anat_fr.pack(fill="x", pady=(4, 6))
        self.genital_var = tk.StringVar(value="none")
        gen_row = ttk.Frame(anat_fr)
        gen_row.pack(fill="x")
        for val in GENITAL_PROFILES:
            ttk.Radiobutton(
                gen_row,
                text=GENITAL_PROFILE_LABELS.get(val, val),
                variable=self.genital_var,
                value=val,
            ).pack(side="left", padx=(0, 10))
        ttk.Label(
            anat_fr,
            text="Без гениталий — контакт через (мимик, цветок, осьминог…):",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(4, 0))
        contact_row = ttk.Frame(anat_fr)
        contact_row.pack(fill="x")
        self.contact_vars = {
            "oral": tk.BooleanVar(value=False),
            "tentacle": tk.BooleanVar(value=False),
            "hand": tk.BooleanVar(value=False),
        }
        for mode in CONTACT_MODES:
            ttk.Checkbutton(
                contact_row,
                text=CONTACT_MODE_LABELS.get(mode, mode),
                variable=self.contact_vars[mode],
            ).pack(side="left", padx=(0, 12))

        hrow = ttk.Frame(self.detail)
        hrow.pack(anchor="w", fill="x", pady=(0, 8))
        ttk.Label(hrow, text="Точный рост (м):", font=("Segoe UI", 10)).pack(
            side="left", padx=(0, 6)
        )
        self.height_var = tk.StringVar(value="")
        ttk.Entry(hrow, textvariable=self.height_var, width=8).pack(side="left")
        ttk.Label(
            hrow,
            text="пусто = из класса (Facehug 0.7, Крок 2.2, фея 0.23…)",
            font=("Segoe UI", 8),
        ).pack(side="left", padx=8)

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

        self.photo_fr = ttk.LabelFrame(
            self.detail,
            text="Скрины — лучше через Blender-студию (кнопка ниже)",
            padding=6,
        )
        self.photo_fr.pack(fill="x", pady=(10, 4))
        self.photo_status = ttk.Label(
            self.photo_fr, text="Скринов нет — после размера жми «Переснять»", font=("Segoe UI", 9)
        )
        self.photo_status.pack(anchor="w", pady=(0, 4))
        shots = ttk.Frame(self.photo_fr)
        shots.pack(fill="x")
        self.photo_front_lbl = ttk.Label(shots, text="front", relief="groove", anchor="center")
        self.photo_front_lbl.pack(side="left", padx=(0, 8))
        self.photo_three_quarter_lbl = ttk.Label(shots, text="¾", relief="groove", anchor="center")
        self.photo_three_quarter_lbl.pack(side="left", padx=(0, 8))
        self.photo_side_lbl = ttk.Label(shots, text="side", relief="groove", anchor="center")
        self.photo_side_lbl.pack(side="left")
        photo_btns = ttk.Frame(self.photo_fr)
        photo_btns.pack(fill="x", pady=(6, 0))
        ttk.Button(
            photo_btns,
            text="Открыть Blender-студию",
            command=self._open_studio_current,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(photo_btns, text="Переснять (headless)", command=self._reshoot_photos).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(photo_btns, text="Скрины ок ✓", command=self._mark_photos_ok).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(photo_btns, text="Плохо — поправлю blend", command=self._mark_photos_bad).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(photo_btns, text="Открыть папку", command=self._open_photo_folder).pack(
            side="left"
        )

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
        sized = sorted(self.store.sized(), key=lambda e: e.name.lower())
        show = list(pending)
        if self.show_sized_var.get():
            # размеченные в конец очереди для правок
            show.extend(sized)
        self.queue_status.config(
            text=f"В списке: {len(show)} · ждут: {len(pending)} · размечено: {len(sized)}"
        )
        for e in show:
            hint = self._hint_for(e)
            if e.size_class:
                hint = f"{e.size_class}/{e.target_height_m:.2f}m"
                if e.photo_ok:
                    hint += " ✓фото"
                elif e.has_photo_files():
                    hint += " ?фото"
            self.tree.insert(
                "",
                "end",
                iid=e.id,
                values=(e.name, hint, Path(e.path).suffix.lower()),
            )
        if not show:
            self.detail.pack_forget()
            self.done_panel.pack(fill="both", expand=True)
            self.done_text.delete("1.0", "end")
            self.done_text.insert(
                "end",
                self.store.summary_text()
                + "\n\nДальше: «Линейка существ» — только без одобренных скринов.\n"
                "Проверка: включи «Показать уже размеченных» → смотри front/side → «Скрины ок».\n"
                "Полный прогон всего каталога: creature_lineup need_photos=0",
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
        self._set_anatomy_display(e)
        if e.target_height_m > 0 and e.size_class:
            # показать текущий целевой рост для правки
            self.height_var.set(f"{e.target_height_m:.2f}".rstrip("0").rstrip("."))
        else:
            self.height_var.set("")
        photo_msg = "Скринов нет — жми «Переснять»"
        if e.photo_ok:
            photo_msg = "✓ Скрины одобрены"
        elif e.has_photo_files():
            photo_msg = "📷 Скрины сняты — проверь и жми «Скрины ок» или «Плохо»"
        if e.photo_notes:
            photo_msg += f" · {e.photo_notes[:80]}"
        self.photo_status.config(text=photo_msg)
        self._load_photo_previews(e)
        self.status_lbl.config(text="")

    def _set_anatomy_display(self, e: CreatureEntry) -> None:
        gp = (e.genital_profile or "none").strip()
        if gp not in GENITAL_PROFILES:
            gp = "none"
        self.genital_var.set(gp)
        modes = set(e.contact_modes or [])
        for mode, var in self.contact_vars.items():
            var.set(mode in modes)
        if e.nsfw_capable and gp == "none" and not modes:
            self.hint_lbl.config(
                text=(self.hint_lbl.cget("text") or "")
                + " · ⚠ старая NSFW-галочка — уточни анатомию"
            )

    def _anatomy_from_ui(self) -> tuple[str, list[str]]:
        gp = self.genital_var.get() or "none"
        if gp not in GENITAL_PROFILES:
            gp = "none"
        modes = [m for m, var in self.contact_vars.items() if var.get()]
        return gp, modes

    def _load_photo_previews(self, e: CreatureEntry) -> None:
        self._photo_refs.clear()
        for lbl, path_s in (
            (self.photo_front_lbl, e.photo_front),
            (self.photo_three_quarter_lbl, e.photo_three_quarter),
            (self.photo_side_lbl, e.photo_side),
        ):
            p = Path(path_s) if path_s else None
            if p and p.is_file() and p.suffix.lower() in (".png", ".gif"):
                try:
                    img = tk.PhotoImage(file=str(p))
                    while img.width() > 220 or img.height() > 220:
                        img = img.subsample(2, 2)
                    lbl.config(image=img, text="")
                    self._photo_refs.append(img)
                    continue
                except tk.TclError:
                    pass
            lbl.config(image="", text=(p.name if p else "—"))

    def _current_slug(self) -> str:
        if self._current is None:
            return ""
        return (self._current.slug or self._current.name or "").strip()

    def _open_studio_current(self) -> None:
        if self._current is None:
            return
        if self.config is None:
            messagebox.showinfo(
                "Вью",
                f"В чате: creature_studio_open slug={self._current_slug()}",
                parent=self.win,
            )
            return
        from .studio import open_creature_studio

        slug = self._current_slug()
        ok, msg = open_creature_studio(
            self.config, slug_filter=[slug], only_unapproved=False
        )
        if ok:
            messagebox.showinfo("Вью", msg.split("\n")[0] + "\n…", parent=self.win)
        else:
            messagebox.showerror("Вью", msg, parent=self.win)

    def _reshoot_photos(self) -> None:
        if self._current is None:
            return
        if self.config is None:
            messagebox.showinfo(
                "Вью",
                "Пересъёмка из окна разметки недоступна — в чате:\n"
                f"creature_lineup slug={self._current_slug()} open=0",
                parent=self.win,
            )
            return
        if self._lineup_busy:
            messagebox.showinfo("Вью", "Линейка уже запущена…", parent=self.win)
            return
        slug = self._current_slug()
        if not slug:
            return
        if not self._current.size_class:
            messagebox.showwarning(
                "Вью", "Сначала выбери размер (класс роста).", parent=self.win
            )
            return
        self._lineup_busy = True
        self.photo_status.config(text=f"Переснимаю {slug}… (Blender в фоне)")
        cfg = self.config
        cid = self._current.id

        def worker() -> None:
            from .lineup import run_creature_lineup

            ok, msg = run_creature_lineup(
                cfg,
                slug_filter=[slug],
                need_photos_only=False,
                open_result=False,
                split=False,
            )
            self.win.after(0, lambda: self._reshoot_done(cid, ok, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _reshoot_done(self, cid: str, ok: bool, msg: str) -> None:
        self._lineup_busy = False
        from .store import CreatureCatalogStore
        from .paths import creature_catalog_path

        if self.config is not None:
            self.store = CreatureCatalogStore(creature_catalog_path(self.config)).load()
        self.status_lbl.config(text=("✓ " if ok else "✗ ") + msg.split("\n")[0][:120])
        self._reload_list(select_id=cid)

    def _mark_photos_ok(self) -> None:
        if self._current is None:
            return
        updated = self.store.mark_photo_ok(self._current.id, ok=True)
        if updated is None:
            return
        self.store.save()
        self.status_lbl.config(text=f"✓ Скрины одобрены: {updated.name}")
        self._reload_list(select_id=self._current.id)

    def _mark_photos_bad(self) -> None:
        if self._current is None:
            return
        note = simpledialog.askstring(
            "Вью",
            "Что не так? (IK, текстуры, мечи…)\n"
            "Поправь .blend в Inbox и жми «Переснять».",
            parent=self.win,
            initialvalue=self._current.photo_notes or "",
        )
        if note is None:
            return
        updated = self.store.mark_photo_ok(
            self._current.id, ok=False, notes=note.strip() or "нужна правка blend"
        )
        if updated is None:
            return
        self.store.save()
        self.status_lbl.config(text="Отмечено: скрины нужно переделать")
        self._reload_list(select_id=self._current.id)

    def _open_photo_folder(self) -> None:
        if self._current is None:
            return
        slug = self._current_slug()
        if self.config is None or not slug:
            return
        from .paths import creature_processed_slug_dir

        folder = creature_processed_slug_dir(self.config, slug)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            else:
                import subprocess
                import sys

                if sys.platform == "darwin":
                    subprocess.Popen(["open", str(folder)])
                else:
                    subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror("Вью", str(exc), parent=self.win)

    def _parse_custom_height(self) -> float | None:
        raw = (self.height_var.get() or "").strip().replace(",", ".")
        if not raw:
            return None
        try:
            val = float(raw)
        except ValueError:
            messagebox.showerror("Вью", "Рост — число в метрах, например 0.7", parent=self.win)
            return -1.0
        if val <= 0 or val > 20:
            messagebox.showerror("Вью", "Рост должен быть от 0 до 20 м", parent=self.win)
            return -1.0
        return val

    def _apply_size(self, size: str) -> None:
        if self._current is None:
            return
        e = self._current
        loco = self._loco_choice()
        custom = self._parse_custom_height()
        if custom is not None and custom < 0:
            return
        updated = self.store.set_size(
            e.id, size, locomotion=loco, target_m=custom
        )
        if updated is None:
            messagebox.showerror("Вью", f"Не удалось поставить size={size}", parent=self.win)
            return
        gp, modes = self._anatomy_from_ui()
        updated.set_anatomy(genital_profile=gp, contact_modes=modes)
        self.store.upsert(updated)
        extra = apply_size_to_same_stem(
            self.store,
            e.id,
            size,
            locomotion=loco,
            genital_profile=gp,
            contact_modes=modes,
            target_m=updated.target_height_m,
        )
        self.store.save()
        anat = updated.anatomy_summary()
        msg = f"✓ {e.name} → {size} / {loco} / {updated.target_height_m:.2f}м"
        if anat != "—":
            msg += f" | {anat}"
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
    config: Optional[Config] = None,
    on_finished: Optional[Callable[[], None]] = None,
) -> CreatureCatalogReviewWindow:
    return CreatureCatalogReviewWindow(master, store, config=config, on_finished=on_finished)
