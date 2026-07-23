"""Окно разметки одной анимации — scope, описание, привязка к каталогу."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable, Optional

from .categories import ANIMATION_CATEGORIES, category_label
from .models import ANIMATION_SCOPES, DEFAULT_SCOPE, normalize_scope, scope_save_warning, AnimationImportReview
from .store import AnimationCatalogStore


class AnimationReviewWindow:
    """Одна анимация за раз — как prop catalog, но про движение."""

    def __init__(
        self,
        master: tk.Misc,
        store: AnimationCatalogStore,
        *,
        on_saved: Optional[Callable[[], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ) -> None:
        self.store = store
        self.on_saved = on_saved
        self.on_finished = on_finished
        self._current: Optional[AnimationImportReview] = None

        self.win = tk.Toplevel(master)
        self.win.title("Вью — анимация (одна за раз)")
        self.win.geometry("820x640")
        self.win.minsize(720, 520)

        body = ttk.Frame(self.win, padding=10)
        body.pack(fill="both", expand=True)

        self.queue_label = ttk.Label(body, text="", font=("Segoe UI", 10, "bold"))
        self.queue_label.pack(anchor="w")

        ttk.Label(
            body,
            text=(
                "Scope «Девушки-biped (Шаня + NPC)» — для Mixamo у всех девушек, "
                "включая Шаню. «Только Шаня» — уникальное. "
                "«NPC без Шани» — осознанно не на главную."
            ),
            wraplength=760,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 8))

        self.form = ttk.Frame(body)
        self.form.pack(fill="both", expand=True)

        self._field_rows: dict[str, tk.Text | ttk.Combobox | ttk.Entry | ttk.Label] = {}

        self._build_row("original", "Исходный файл", readonly=True)
        self._build_row("clip", "В Unity", readonly=True)
        self._build_row("slug", "Slug каталога", entry=True)
        self._build_row("title", "Название", entry=True)
        self._build_category_row()
        self._build_scope_row()
        self._build_row("animator_state", "Animator state", entry=True)
        self._build_row("when_used", "Когда применяется", text=True, height=3)
        self._build_row("looks_like", "Как выглядит", text=True, height=4)
        self._build_row("purpose", "Зачем в игре", text=True, height=2)
        self._build_row("notes", "Заметки (необяз.)", text=True, height=2)

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="✓ Сохранить → следующая", command=self._save_next).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(btns, text="Пропустить (defaults OK)", command=self._skip_defaults).pack(
            side="left", padx=6
        )
        ttk.Button(btns, text="Готово — закрыть", command=self._finish).pack(side="right")

        self._load_next()

    def _build_row(
        self,
        key: str,
        label: str,
        *,
        readonly: bool = False,
        entry: bool = False,
        text: bool = False,
        height: int = 1,
    ) -> None:
        row = ttk.Frame(self.form)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=22).pack(side="left", anchor="n")
        if readonly:
            w = ttk.Label(row, text="", wraplength=520, font=("Segoe UI", 9))
            w.pack(side="left", fill="x", expand=True)
        elif entry:
            w = ttk.Entry(row, width=70)
            w.pack(side="left", fill="x", expand=True)
        else:
            w = tk.Text(row, height=height, wrap="word", font=("Segoe UI", 10))
            w.pack(side="left", fill="x", expand=True)
        self._field_rows[key] = w

    def _build_category_row(self) -> None:
        row = ttk.Frame(self.form)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="Категория", width=22).pack(side="left")
        values = [f"{cid} — {category_label(cid)}" for cid in ANIMATION_CATEGORIES]
        cb = ttk.Combobox(row, values=values, width=48, state="readonly")
        cb.pack(side="left", fill="x", expand=True)
        self._field_rows["category"] = cb

    def _build_scope_row(self) -> None:
        row = ttk.Frame(self.form)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="Scope (кому)", width=22).pack(side="left", anchor="n")
        inner = ttk.Frame(row)
        inner.pack(side="left", fill="x", expand=True)
        values = [f"{k} — {v[0]}" for k, v in ANIMATION_SCOPES.items()]
        cb = ttk.Combobox(inner, values=values, width=48, state="readonly")
        cb.pack(fill="x")
        self._scope_hint = ttk.Label(inner, text="", wraplength=520, font=("Segoe UI", 8))
        self._scope_hint.pack(anchor="w", pady=(2, 0))
        cb.bind("<<ComboboxSelected>>", self._on_scope_change)
        self._field_rows["scope"] = cb

    def _on_scope_change(self, _evt=None) -> None:
        key = self._combo_key(self._field_rows["scope"])
        hint = ANIMATION_SCOPES.get(key, ("", ""))[1]
        self._scope_hint.config(text=hint)

    def _combo_key(self, cb: ttk.Combobox) -> str:
        val = cb.get()
        return val.split(" — ")[0].strip() if " — " in val else val.strip()

    def _set_readonly(self, key: str, text: str) -> None:
        w = self._field_rows[key]
        if isinstance(w, ttk.Label):
            w.config(text=text)

    def _set_entry(self, key: str, text: str) -> None:
        w = self._field_rows[key]
        if isinstance(w, ttk.Entry):
            w.delete(0, tk.END)
            w.insert(0, text)

    def _set_text(self, key: str, text: str) -> None:
        w = self._field_rows[key]
        if isinstance(w, tk.Text):
            w.delete("1.0", tk.END)
            w.insert("1.0", text)

    def _get_entry(self, key: str) -> str:
        w = self._field_rows[key]
        if isinstance(w, ttk.Entry):
            return w.get().strip()
        return ""

    def _get_text(self, key: str) -> str:
        w = self._field_rows[key]
        if isinstance(w, tk.Text):
            return w.get("1.0", tk.END).strip()
        return ""

    def _load_next(self) -> None:
        pending = self.store.pending_reviews()
        if not pending:
            self.queue_label.config(text="Очередь пуста — можно закрыть.")
            self._current = None
            return
        self._current = pending[0]
        n = len(pending)
        self.queue_label.config(
            text=f"В очереди: {n}  ·  Сейчас: {self._current.original_name}"
        )
        r = self._current
        self._set_readonly("original", r.original_name)
        self._set_readonly("clip", r.clip_file)
        self._set_entry("slug", r.suggested_slug)
        self._set_entry("title", r.suggested_title)
        cat_cb = self._field_rows["category"]
        if isinstance(cat_cb, ttk.Combobox):
            for i, cid in enumerate(ANIMATION_CATEGORIES):
                if cid == r.category:
                    cat_cb.current(i)
                    break
        scope_cb = self._field_rows["scope"]
        if isinstance(scope_cb, ttk.Combobox):
            keys = list(ANIMATION_SCOPES.keys())
            norm = normalize_scope(r.scope)
            try:
                scope_cb.current(keys.index(norm))
            except ValueError:
                scope_cb.current(0)
            self._on_scope_change()
        self._set_entry("animator_state", r.animator_state)
        self._set_text("when_used", r.when_used)
        self._set_text("looks_like", r.looks_like)
        self._set_text("purpose", r.purpose)
        self._set_text("notes", r.notes)

    def _collect_review(self) -> Optional[AnimationImportReview]:
        if self._current is None:
            return None
        r = self._current
        r.suggested_slug = self._get_entry("slug") or r.suggested_slug
        r.suggested_title = self._get_entry("title") or r.suggested_title
        cat_cb = self._field_rows["category"]
        if isinstance(cat_cb, ttk.Combobox):
            r.category = self._combo_key(cat_cb)
        scope_cb = self._field_rows["scope"]
        if isinstance(scope_cb, ttk.Combobox):
            r.scope = normalize_scope(self._combo_key(scope_cb))
        r.animator_state = self._get_entry("animator_state") or r.animator_state
        r.when_used = self._get_text("when_used")
        r.looks_like = self._get_text("looks_like")
        r.purpose = self._get_text("purpose")
        r.notes = self._get_text("notes")
        return r

    def _write_viu_clips_override(self, review: AnimationImportReview, wish_clip_name: str) -> None:
        """Дописать viu_clips.json если имя файла неочевидное."""
        try:
            clip_path = Path(review.clip_file)
            manifest = clip_path.parent / "viu_clips.json"
            state = review.animator_state or review.suggested_slug.replace("_", " ").title()
            entry = {"file": wish_clip_name, "state": state.replace(" ", "")}
            data: dict = {"comment": "Viu overrides", "overrides": [entry]}
            if manifest.is_file():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    overrides = list(data.get("overrides") or [])
                    overrides = [o for o in overrides if o.get("file") != wish_clip_name]
                    overrides.append(entry)
                    data["overrides"] = overrides
                except json.JSONDecodeError:
                    pass
            manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _save_review(self) -> bool:
        review = self._collect_review()
        if review is None:
            return False
        review.scope = normalize_scope(review.scope)
        warn = scope_save_warning(review.scope)
        if warn:
            if not messagebox.askyesno("Scope", f"{warn}\n\nСохранить всё равно?"):
                return False
        wish = self.store.confirm_pending(review)
        self._write_viu_clips_override(review, wish.clip_file)
        self.store.save()
        if self.on_saved:
            self.on_saved()
        return True

    def _save_next(self) -> None:
        if not self._save_review():
            return
        self._load_next()
        if self._current is None:
            messagebox.showinfo("Вью", "Все анимации разметены.\nДальше: «Загрузить в Animator Unity».")

    def _skip_defaults(self) -> None:
        if self._current is None:
            return
        if self._save_review():
            self._load_next()

    def _finish(self) -> None:
        if self._current is not None:
            if messagebox.askyesno("Закрыть", "Сохранить текущую перед закрытием?"):
                if not self._save_review():
                    return
        self.win.destroy()
        if self.on_finished:
            self.on_finished()


def open_animation_review(
    master: tk.Misc,
    store: AnimationCatalogStore,
    *,
    on_saved: Optional[Callable[[], None]] = None,
    on_finished: Optional[Callable[[], None]] = None,
) -> AnimationReviewWindow:
    return AnimationReviewWindow(
        master,
        store,
        on_saved=on_saved,
        on_finished=on_finished,
    )
